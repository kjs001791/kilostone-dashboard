"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import AppShell from "@/components/layout/AppShell";
import { statsApi } from "@/lib/api";
import { StatsResponse } from "@/types/stats";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Legend } from "recharts";
import { Skeleton } from "@/components/ui/skeleton";

export default function VehiclesPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<any[]>([]);
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace("/login");
  }, [isAuthenticated, isLoading, router]);

  useEffect(() => {
    if (!isAuthenticated) return;
    
    // 3개 차량 데이터를 각각 가져와서 병합
    const vehicles = ["MAN TGX", "Daewoo Prima", "Scania"];
    Promise.all(vehicles.map(v => statsApi.get({ vehicle_id: v })))
      .then((results) => {
        const chartData = results.map((res, i) => ({
          name: vehicles[i],
          efficiency: res.summary.avg_fuel_efficiency,
          distance: res.summary.total_distance / 1000, // 단위를 1000km로 조정
        }));
        setData(chartData);
      })
      .finally(() => setFetching(false));
  }, [isAuthenticated]);

  if (isLoading) return null;

  return (
    <AppShell>
      <div className="p-4 md:p-6 space-y-6">
        <h1 className="text-xl font-semibold">차량별 성능 비교</h1>
        
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">차량별 평균 연비 (km/L)</CardTitle>
            </CardHeader>
            <CardContent>
              {fetching ? <Skeleton className="h-64 w-full" /> : (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={data} layout="vertical" margin={{ left: 30 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} />
                    <XAxis type="number" domain={[0, 5]} tick={{fontSize: 12}} />
                    <YAxis dataKey="name" type="category" tick={{fontSize: 11}} />
                    <Tooltip formatter={(v: any) => [`${v.toFixed(2)} km/L`, "평균 연비"]} />
                    <Bar dataKey="efficiency" fill="#81C995" radius={[0, 4, 4, 0]} barSize={40} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-sm font-medium">차량별 누적 주행거리 (천 km)</CardTitle>
            </CardHeader>
            <CardContent>
              {fetching ? <Skeleton className="h-64 w-full" /> : (
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={data} layout="vertical" margin={{ left: 30 }}>
                    <CartesianGrid strokeDasharray="3 3" horizontal={true} vertical={false} />
                    <XAxis type="number" tick={{fontSize: 12}} />
                    <YAxis dataKey="name" type="category" tick={{fontSize: 11}} />
                    <Tooltip formatter={(v: any) => [`${v.toLocaleString()} 천 km`, "누적 거리"]} />
                    <Bar dataKey="distance" fill="#8AB4F8" radius={[0, 4, 4, 0]} barSize={40} />
                  </BarChart>
                </ResponsiveContainer>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </AppShell>
  );
}
