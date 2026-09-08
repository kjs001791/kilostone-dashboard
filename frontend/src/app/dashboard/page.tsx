"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import AppShell from "@/components/layout/AppShell";
import KpiCard from "@/components/dashboard/KpiCard";
import EfficiencyChart from "@/components/dashboard/EfficiencyChart";
import DistanceChart from "@/components/dashboard/DistanceChart";
import FuelChart from "@/components/dashboard/FuelChart";
import CorrelationChart from "@/components/dashboard/CorrelationChart";
import PipelineBanner from "@/components/dashboard/PipelineBanner";
import { statsApi } from "@/lib/api";
import { StatsResponse } from "@/types/stats";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";

const PERIOD_OPTIONS = [
  { value: "all", label: "전체" },
  { value: "365", label: "최근 1년" },
  { value: "180", label: "최근 6개월" },
  { value: "90", label: "최근 3개월" },
  { value: "30", label: "최근 30일" },
];

const VEHICLE_OPTIONS = [
  { value: "all", label: "전체 차량" },
  { value: "MAN TGX", label: "MAN TGX" },
  { value: "Daewoo Prima", label: "대우 프리마" },
  { value: "Scania", label: "스카니아" },
];

export default function DashboardPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [fetching, setFetching] = useState(true);
  const [vehicleFilter, setVehicleFilter] = useState("all");
  const [periodDays, setPeriodDays] = useState("all");

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace("/login");
  }, [isAuthenticated, isLoading, router]);

  useEffect(() => {
    if (!isAuthenticated) return;
    setFetching(true);
    statsApi
      .get(vehicleFilter !== "all" ? { vehicle_id: vehicleFilter } : undefined)
      .then(setStats)
      .finally(() => setFetching(false));
  }, [isAuthenticated, vehicleFilter]);

  const filteredMonthly = (() => {
    if (!stats || periodDays === "all") return stats?.monthly ?? [];
    const cutoff = new Date();
    cutoff.setDate(cutoff.getDate() - Number(periodDays));
    return stats.monthly.filter(
      (m) => new Date(m.year, m.month - 1) >= cutoff
    );
  })();

  if (isLoading) return null;

  return (
    <AppShell>
      <div className="p-4 md:p-6 space-y-5">
        <PipelineBanner />
        
        <div className="flex flex-col sm:flex-row gap-3 items-start sm:items-center justify-between">
          <h1 className="text-xl font-bold tracking-tight">대시보드</h1>

          <div className="flex gap-2">
            <Select value={vehicleFilter} onValueChange={setVehicleFilter}>
              <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
              <SelectContent>
                {VEHICLE_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Select value={periodDays} onValueChange={setPeriodDays}>
              <SelectTrigger className="w-36"><SelectValue /></SelectTrigger>
              <SelectContent>
                {PERIOD_OPTIONS.map((o) => (
                  <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </div>

        {/* KPI 카드 4개 */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          {fetching ? (
            Array.from({ length: 4 }).map((_, i) => (
              <Skeleton key={i} className="h-24 rounded-lg" />
            ))
          ) : (
            <>
              <KpiCard
                title="평균 연비"
                value={stats?.summary.avg_fuel_efficiency?.toFixed(2) ?? "-"}
                unit="km/L"
              />
              <KpiCard
                title="총 주행거리"
                value={stats?.summary.total_distance.toLocaleString("ko") ?? "-"}
                unit="km"
              />
              <KpiCard
                title="총 연료소모"
                value={stats?.summary.total_consumed_fuel?.toLocaleString("ko") ?? "-"}
                unit="L"
              />
              <KpiCard
                title="총 기록 수"
                value={stats?.summary.total_records.toLocaleString("ko") ?? "-"}
                unit="건"
              />
            </>
          )}
        </div>

        {/* 차트 2×2 그리드 */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <EfficiencyChart data={filteredMonthly} loading={fetching} />
          <DistanceChart data={filteredMonthly} loading={fetching} />
          <FuelChart data={filteredMonthly} loading={fetching} />
          <CorrelationChart vehicleId={vehicleFilter !== "all" ? vehicleFilter : undefined} loading={fetching} />
        </div>
      </div>
    </AppShell>
  );
}
