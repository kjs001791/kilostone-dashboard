"use client";

import { useCallback, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { toast } from "@/hooks/use-toast";
import { BottomTabs } from "./BottomTabs";
import { TopNav } from "./TopNav";
import {
  DRIVING_FIELDS,
  hubApi,
  type DrivingField,
  type DrivingPayload,
  type DrivingRecord,
  type HubVehicle,
  type HubWarning,
} from "@/lib/hubApi";

const LABELS: Record<DrivingField, string> = {
  distance: "주행거리 (km)",
  cumulative_distance: "누적거리 (km)",
  consumed_fuel: "연료 소모량 (L)",
  fuel_efficiency: "연비 (km/L)",
  speed: "평균속도 (km/h)",
  time_h: "운행시간 (시간)",
  time_idle_h: "공회전시간 (시간)",
  time_pto_h: "PTO시간 (시간)",
  refuel: "주유량 (L)",
  reurea: "요소수 주입량 (L)",
};

function today() {
  const d = new Date();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
}

export function DriveForm() {
  const router = useRouter();
  const [date, setDate] = useState(today());
  const [vehicles, setVehicles] = useState<HubVehicle[]>([]);
  const [vehicleId, setVehicleId] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [fieldWarn, setFieldWarn] = useState<HubWarning[]>([]);
  const [saveWarn, setSaveWarn] = useState<HubWarning[]>([]);
  const [recent, setRecent] = useState<DrivingRecord[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    hubApi
      .vehicles()
      .then((v) => {
        setVehicles(v);
        const cur = v.find((x) => x.current) ?? v[0];
        if (cur) setVehicleId(cur.vehicle_id);
      })
      .catch((e) => setError(e.message));
  }, []);

  useEffect(() => {
    if (!vehicleId) return;
    hubApi.recent(vehicleId, 10).then(setRecent).catch(() => setRecent([]));
  }, [vehicleId]);

  const build = useCallback((): DrivingPayload => {
    const p: DrivingPayload = { vehicle_id: vehicleId, date };
    for (const f of DRIVING_FIELDS) {
      const raw = (values[f] ?? "").trim();
      const n = raw === "" ? null : Number(raw);
      p[f] = n !== null && Number.isFinite(n) ? n : null;
    }
    return p;
  }, [vehicleId, date, values]);

  const runCheck = async () => {
    if (!vehicleId) return;
    try {
      setFieldWarn(await hubApi.check(build()));
    } catch {
      /* 검사 실패는 저장 때 다시 나온다 */
    }
  };

  const save = async (confirm: boolean) => {
    setBusy(true);
    setError(null);
    try {
      const r = await hubApi.save(build(), confirm);
      if (r.ok) {
        toast({ title: "저장했습니다" });
        router.push("/");
      } else if (r.status === 409 && r.warnings.length > 0) {
        setSaveWarn(r.warnings);
      } else {
        setError(`저장하지 못했습니다 (${r.status})`);
      }
    } catch {
      setError("서버에 연결하지 못했습니다");
    } finally {
      setBusy(false);
    }
  };

  const duplicate = saveWarn.some((w) => w.rule === "duplicate_date");
  const inputCls = "h-12 w-full rounded-md border border-input bg-background px-3 text-lg";
  const known = DRIVING_FIELDS as readonly string[];

  return (
    <div className="min-h-screen bg-background pb-24 text-base lg:pb-8">
      <TopNav />
      <main className="mx-auto max-w-md p-4 lg:max-w-6xl lg:p-6">
        <h1 className="mb-4 text-2xl font-bold">운행 입력</h1>
        <div className="lg:grid lg:grid-cols-2 lg:items-start lg:gap-8">
        <div className="space-y-4">

        <label className="block">
          <span className="text-base font-semibold">날짜</span>
          <input type="date" className={inputCls} value={date} onChange={(e) => setDate(e.target.value)} onBlur={runCheck} />
        </label>

        <label className="block">
          <span className="text-base font-semibold">차량</span>
          <select className={inputCls} value={vehicleId} onChange={(e) => setVehicleId(e.target.value)}>
            {vehicles.map((v) => (
              <option key={v.vehicle_id} value={v.vehicle_id}>
                {v.vehicle_id} {v.brand ?? ""} {v.color ?? ""}
                {v.current ? " (현재)" : ""}
              </option>
            ))}
          </select>
        </label>

        <div className="space-y-4 lg:grid lg:grid-cols-2 lg:gap-x-4 lg:space-y-0 lg:gap-y-4">
        {DRIVING_FIELDS.map((f) => {
          const ws = fieldWarn.filter((w) => w.field === f);
          return (
            <div key={f}>
              <label className="block">
                <span className="text-base font-semibold">{LABELS[f]}</span>
                <input
                  name={f}
                  inputMode="decimal"
                  className={inputCls}
                  value={values[f] ?? ""}
                  onChange={(e) => setValues((s) => ({ ...s, [f]: e.target.value }))}
                  onBlur={runCheck}
                />
              </label>
              {ws.map((w) => (
                <p key={w.rule} className="mt-1 text-base font-semibold text-red-500">
                  {w.message}
                </p>
              ))}
            </div>
          );
        })}
        </div>

        {fieldWarn
          .filter((w) => !w.field || !known.includes(w.field))
          .map((w) => (
            <p key={w.rule} className="text-base font-semibold text-red-500">
              {w.message}
            </p>
          ))}

        {error && <p className="text-base font-semibold text-red-500">{error}</p>}

        {saveWarn.length > 0 && (
          <div role="alert" className="space-y-2 rounded-lg border border-red-500 p-3">
            <p className="text-lg font-bold text-red-500">확인이 필요합니다</p>
            <ul className="list-disc pl-5 text-base text-red-500">
              {saveWarn.map((w) => (
                <li key={w.rule}>{w.message}</li>
              ))}
            </ul>
            {!duplicate && (
              <Button className="h-12 w-full text-lg" variant="destructive" disabled={busy} onClick={() => save(true)}>
                그래도 저장
              </Button>
            )}
          </div>
        )}

        <Button className="h-14 w-full text-lg" disabled={busy || !vehicleId} onClick={() => save(false)}>
          저장
        </Button>
        </div>

        <section>
          <h2 className="mb-2 mt-4 text-xl font-bold lg:mt-0">최근 기록</h2>
          <ul className="space-y-2">
            {recent.map((r, i) => {
              const hasFlag = Array.isArray(r.flags)
                ? r.flags.length > 0
                : !!r.flags && Object.keys(r.flags as object).length > 0;
              return (
                <li key={`${r.date}-${i}`} className={`items-center justify-between rounded-lg border p-3 text-base ${i >= 5 ? "hidden lg:flex" : "flex"}`}>
                  <span className="font-semibold">{r.date}</span>
                  <span>
                    {r.distance ?? "-"} km · {r.fuel_efficiency ?? "-"} km/L
                  </span>
                  {hasFlag && <span className="font-bold text-red-500">경고</span>}
                </li>
              );
            })}
            {recent.length === 0 && <li className="text-muted-foreground">기록이 없습니다</li>}
          </ul>
        </section>
        </div>
      </main>
      <BottomTabs />
    </div>
  );
}
