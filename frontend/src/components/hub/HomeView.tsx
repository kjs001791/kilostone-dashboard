"use client";

import { useEffect, useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { BottomTabs } from "./BottomTabs";
import { TopNav } from "./TopNav";
import { hubApi, type HubSummary } from "@/lib/hubApi";

const won = (n: number) => `${Math.round(n).toLocaleString("ko-KR")}원`;

function Delta({ label, now, base }: { label: string; now: number | null; base: number | null }) {
  let text = "비교 없음";
  let cls = "text-muted-foreground";
  if (now != null && base != null && base !== 0) {
    const p = ((now - base) / Math.abs(base)) * 100;
    text = `${p > 0 ? "+" : ""}${p.toFixed(1)}%`;
    cls = p > 0 ? "text-red-400" : p < 0 ? "text-blue-400" : "";
  }
  return (
    <div className="flex items-center justify-between py-1 text-base">
      <span>{label}</span>
      <span className={`font-semibold ${cls}`}>{text}</span>
    </div>
  );
}

export function HomeView() {
  const [months, setMonths] = useState<string[]>([]);
  const [month, setMonth] = useState<string>("");
  const [data, setData] = useState<HubSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    hubApi
      .months()
      .then((m) => {
        setMonths(m.months);
        if (m.latest) setMonth(m.latest);
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!month) return;
    setData(null);
    hubApi
      .summary(month)
      .then(setData)
      .catch((e) => setError(e.message));
  }, [month]);

  const eff = data?.driving.avg_efficiency;

  return (
    <div className="min-h-screen bg-background pb-24 text-base lg:pb-8">
      <TopNav />
      <main className="mx-auto max-w-md space-y-4 p-4 lg:max-w-6xl lg:p-6">
        <select
          aria-label="달 고르기"
          value={month}
          onChange={(e) => setMonth(e.target.value)}
          className="h-12 w-full rounded-md border border-input bg-background px-3 text-lg font-semibold lg:w-64"
        >
          {months.map((m) => (
            <option key={m} value={m}>
              {m.replace("-", "년 ")}월
            </option>
          ))}
        </select>

        {error && <p className="text-base text-red-500">{error}</p>}
        {!data && !error && <p className="text-base text-muted-foreground">불러오는 중...</p>}

        {data && (
          <>
            <div className="space-y-4 lg:grid lg:grid-cols-3 lg:gap-4 lg:space-y-0">
            <Card data-testid="card-revenue">
              <CardContent className="p-4">
                <p className="text-base text-muted-foreground">이번 달 매출</p>
                <p className="text-3xl font-bold">{won(data.revenue.this_month ?? 0)}</p>
                {data.revenue_has_computed && (
                  <p className="text-sm text-muted-foreground">일부는 톤×단가로 계산한 값</p>
                )}
                <div className="mt-2 border-t pt-2">
                  <Delta label="지난달 대비" now={data.revenue.this_month} base={data.revenue.prev_month} />
                  <Delta label="작년 같은 달 대비" now={data.revenue.this_month} base={data.revenue.same_month_last_year} />
                </div>
              </CardContent>
            </Card>

            <Card data-testid="card-weight">
              <CardContent className="p-4">
                <p className="text-base text-muted-foreground">이번 달 운송량</p>
                <p className="text-3xl font-bold">{(data.weight_ton.this_month ?? 0).toFixed(1)}톤</p>
              </CardContent>
            </Card>

            <Card data-testid="card-driving">
              <CardContent className="p-4">
                <p className="text-base text-muted-foreground">운행 요약</p>
                <div className="mt-1 space-y-1 text-lg">
                  <p>운행일 <b>{data.driving.days}일</b></p>
                  <p>주행거리 <b>{Math.round(data.driving.distance_km).toLocaleString("ko-KR")} km</b></p>
                  <p>평균 연비 <b>{eff != null ? eff.toFixed(2) : "-"} km/L</b></p>
                </div>
              </CardContent>
            </Card>
            </div>

            <section>
              <h2 className="mb-2 text-xl font-bold">거래처별</h2>
              <ul className="space-y-2 lg:hidden">
                {data.by_client.map((c) => (
                  <li key={`${c.client_id}-${c.client_name}`} className="rounded-lg border p-3">
                    <p className="text-lg font-semibold">{c.client_name}</p>
                    <div className="mt-1 flex justify-between text-base">
                      <span>{c.weight_ton.toFixed(1)}톤 · {c.days}일</span>
                      <span className="font-semibold">{won(c.revenue)}</span>
                    </div>
                  </li>
                ))}
              </ul>
              <table className="hidden w-full text-left text-base lg:table" data-testid="client-table">
                <thead>
                  <tr className="border-b text-muted-foreground">
                    <th className="py-2 font-semibold">거래처</th>
                    <th className="py-2 text-right font-semibold">운송량(톤)</th>
                    <th className="py-2 text-right font-semibold">매출</th>
                    <th className="py-2 text-right font-semibold">운행일</th>
                    <th className="py-2 text-right font-semibold">매출 비중(%)</th>
                  </tr>
                </thead>
                <tbody>
                  {data.by_client.map((c) => {
                    const total = data.by_client.reduce((s, x) => s + x.revenue, 0);
                    return (
                      <tr key={`${c.client_id}-${c.client_name}`} className="border-b">
                        <td className="py-2 font-semibold">{c.client_name}</td>
                        <td className="py-2 text-right">{c.weight_ton.toFixed(1)}</td>
                        <td className="py-2 text-right">{won(c.revenue)}</td>
                        <td className="py-2 text-right">{c.days}일</td>
                        <td className="py-2 text-right">{total === 0 ? "" : ((c.revenue / total) * 100).toFixed(1)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </section>
          </>
        )}
      </main>
      <BottomTabs />
    </div>
  );
}
