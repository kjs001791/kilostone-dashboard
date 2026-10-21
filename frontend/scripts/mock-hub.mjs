import http from "node:http";

const PORT = 8001;
const cors = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
};
const send = (res, code, body) => {
  res.writeHead(code, { ...cors, "Content-Type": "application/json; charset=utf-8" });
  res.end(JSON.stringify(body));
};

const summary = {
  month: "2025-02",
  revenue: { this_month: 18450000, prev_month: 16200000, same_month_last_year: null },
  revenue_has_computed: true,
  weight_ton: { this_month: 412.34, prev_month: 380.1, same_month_last_year: null },
  by_client: [
    { client_id: 1, client_name: "대한시멘트", weight_ton: 210.5, revenue: 9800000, days: 15 },
    { client_id: 2, client_name: "동양레미콘", weight_ton: 140.2, revenue: 6100000, days: 12 },
    { client_id: 0, client_name: "미지정", weight_ton: 61.6, revenue: 2550000, days: 5 },
  ],
  driving: { days: 20, distance_km: 5230, fuel_l: 1480.5, avg_efficiency: 3.53 },
};
const recent = [
  { driving_id: 3, vehicle_id: "V04", date: "2025-02-10", distance: 262, fuel_efficiency: 3.4, flags: [] },
  { driving_id: 2, vehicle_id: "V04", date: "2025-02-09", distance: 240, fuel_efficiency: 3.6, flags: [{ rule: "digit_jump" }] },
  { driving_id: 1, vehicle_id: "V04", date: "2025-02-08", distance: 255, fuel_efficiency: 3.5, flags: [] },
];

// 목 규칙: 누적거리 < 100000 이면 cumulative_decrease, 날짜가 2025-02-10 이면 duplicate_date
function warnings(b) {
  const w = [];
  if (b.cumulative_distance != null && b.cumulative_distance < 100000)
    w.push({ field: "cumulative_distance", rule: "cumulative_decrease", message: "직전 기록보다 누적거리가 줄었습니다" });
  if (b.date === "2025-02-10")
    w.push({ field: null, rule: "duplicate_date", message: "같은 날짜 기록이 이미 있습니다" });
  return w;
}

http
  .createServer((req, res) => {
    if (req.method === "OPTIONS") return send(res, 204, {});
    const url = new URL(req.url, "http://x");
    const p = url.pathname;
    if (req.method === "GET" && p === "/hub/months") return send(res, 200, { months: ["2025-02", "2025-01"], latest: "2025-02" });
    if (req.method === "GET" && p === "/hub/summary") return send(res, 200, summary);
    if (req.method === "GET" && p === "/hub/vehicles")
      return send(res, 200, [{ vehicle_id: "V04", brand: "Scania", model: null, color: "흰색", service_start: "2023-09-01", service_end: null, current: true }]);
    if (req.method === "GET" && p === "/hub/driving") return send(res, 200, recent);
    if (req.method === "POST" && (p === "/hub/driving/check" || p === "/hub/driving")) {
      let raw = "";
      req.on("data", (c) => (raw += c));
      req.on("end", () => {
        const b = JSON.parse(raw || "{}");
        const w = warnings(b);
        if (p.endsWith("/check")) return send(res, 200, { warnings: w });
        if (w.some((x) => x.rule === "duplicate_date")) return send(res, 409, { warnings: w });
        if (w.length && !b.confirm) return send(res, 409, { warnings: w });
        return send(res, 200, { driving_id: 99, warnings: b.confirm ? w : [] });
      });
      return;
    }
    send(res, 404, { detail: "not found" });
  })
  .listen(PORT, () => console.log(`mock hub on ${PORT}`));
