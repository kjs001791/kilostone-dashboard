"use client";

import { useEffect, useState } from "react";
import { logsApi } from "@/lib/api";
import { ScatterChart, Scatter, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, ZAxis } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

interface Props { vehicleId?: string; loading: boolean; }

export default function CorrelationChart({ vehicleId, loading }: Props) {
  const [data, setData] = useState<any[]>([]);
  const [fetching, setFetching] = useState(false);

  useEffect(() => {
    setFetching(true);
    logsApi.list({ per_page: 100, vehicle_id: vehicleId })
      .then((res) => {
        const points = res.items
          .filter((item) => item.speed && item.fuel_efficiency)
          .map((item) => ({
            x: item.speed,
            y: item.fuel_efficiency,
          }));
        setData(points);
      })
      .finally(() => setFetching(false));
  }, [vehicleId]);

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">속도 vs 연비 상관관계</CardTitle>
      </CardHeader>
      <CardContent>
        {loading || fetching ? (
          <Skeleton className="h-52 w-full" />
        ) : (
          <ResponsiveContainer width="100%" height={210}>
            <ScatterChart>
              <CartesianGrid strokeDasharray="3 3" stroke="#3C4043" />
              <XAxis type="number" dataKey="x" name="속도" unit=" km/h" tick={{ fontSize: 11 }} domain={["dataMin - 5", "dataMax + 5"]} />
              <YAxis type="number" dataKey="y" name="연비" unit=" km/L" tick={{ fontSize: 11 }} domain={["dataMin - 0.5", "dataMax + 0.5"]} />
              <ZAxis type="number" range={[64]} />
              <Tooltip cursor={{ strokeDasharray: "3 3" }} />
              <Scatter name="운행기록" data={data} fill="#FBBC04" />
            </ScatterChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
