// empty = same origin; next.config.mjs forwards /hub to the API. NEXT_PUBLIC_API_URL is the old app's setting
// and points at localhost, which a phone cannot reach, so the hub screens use their own variable.
const BASE_URL = process.env.NEXT_PUBLIC_HUB_API_URL ?? "";

export interface Compare {
  this_month: number | null;
  prev_month: number | null;
  same_month_last_year: number | null;
}

export interface ClientRow {
  client_id: number;
  client_name: string;
  weight_ton: number;
  revenue: number;
  days: number;
}

export interface HubSummary {
  month: string;
  revenue: Compare;
  revenue_has_computed: boolean;
  weight_ton: Compare;
  by_client: ClientRow[];
  driving: {
    days: number;
    distance_km: number;
    fuel_l: number;
    avg_efficiency: number | null;
  };
}

export interface HubMonths {
  months: string[];
  latest: string | null;
}

export interface HubVehicle {
  vehicle_id: string;
  brand: string | null;
  model: string | null;
  color: string | null;
  service_start: string | null;
  service_end: string | null;
  current: boolean;
}

export interface HubWarning {
  field: string | null;
  rule: string;
  message: string;
}

export const DRIVING_FIELDS = [
  "distance",
  "cumulative_distance",
  "consumed_fuel",
  "fuel_efficiency",
  "speed",
  "time_h",
  "time_idle_h",
  "time_pto_h",
  "refuel",
  "reurea",
] as const;
export type DrivingField = (typeof DRIVING_FIELDS)[number];

export type DrivingPayload = {
  vehicle_id: string;
  date: string;
} & Partial<Record<DrivingField, number | null>>;

export interface DrivingRecord {
  driving_id?: number;
  vehicle_id: string;
  date: string;
  distance: number | null;
  fuel_efficiency: number | null;
  flags: unknown;
  [key: string]: unknown;
}

export interface SaveResult {
  ok: boolean;
  status: number;
  warnings: HubWarning[];
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE_URL}/hub${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`요청 실패 (${res.status})`);
  return res.json();
}

async function postJson(path: string, body: unknown) {
  const res = await fetch(`${BASE_URL}/hub${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  return { res, data };
}

export const hubApi = {
  months: () => getJson<HubMonths>("/months"),
  summary: (month?: string) =>
    getJson<HubSummary>(`/summary${month ? `?month=${encodeURIComponent(month)}` : ""}`),
  vehicles: () => getJson<HubVehicle[]>("/vehicles"),
  recent: (vehicleId: string, limit = 5) =>
    getJson<DrivingRecord[]>(
      `/driving?vehicle_id=${encodeURIComponent(vehicleId)}&limit=${limit}`
    ),
  check: async (payload: DrivingPayload): Promise<HubWarning[]> => {
    const { res, data } = await postJson("/driving/check", payload);
    if (!res.ok) throw new Error(`검사 실패 (${res.status})`);
    return data.warnings ?? [];
  },
  save: async (payload: DrivingPayload, confirm: boolean): Promise<SaveResult> => {
    const { res, data } = await postJson("/driving", { ...payload, confirm });
    return { ok: res.ok, status: res.status, warnings: data.warnings ?? [] };
  },
};
