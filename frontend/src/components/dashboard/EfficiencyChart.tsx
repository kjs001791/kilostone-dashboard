"use client";

import { MonthlyStats } from "@/types/stats";
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ReferenceLine, ResponsiveContainer } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { format } from "date-fns";
import { ko } from "date-fns/locale";

interface Props { data: MonthlyStats[]; loading: boolean; }

export default function EfficiencyChart({ data, loading }: Props) {
  const chartData = data
    .filter((d) => d.avg_fuel_efficiency !== null)
    .map((d) => ({
      label: format(new Date(d.year, d.month - 1), "yy.MM", { locale: ko }),
      value: d.avg_fuel_efficiency,
    }));

  const avg = chartData.length
    ? chartData.reduce((s, d) => s + (d.value ?? 0), 0) / chartData.length
    : 0;

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">연비 추이</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-52 w-full" />
        ) : (
          <ResponsiveContainer width="100%" height={210}>
            <LineChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#3C4043" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis domain={["auto", "auto"]} tick={{ fontSize: 11 }} unit=" km/L" />
              <Tooltip formatter={(v: number) => [`${v.toFixed(2)} km/L`, "연비"]} />
              <ReferenceLine y={avg} stroke="#F28B82" strokeDasharray="4 4" label={{ value: `평균 ${avg.toFixed(2)}`, fill: "#F28B82", fontSize: 11 }} />
              <Line type="monotone" dataKey="value" stroke="#81C995" strokeWidth={2} dot={false} />
            </LineChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
