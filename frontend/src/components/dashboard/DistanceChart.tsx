"use client";

import { MonthlyStats } from "@/types/stats";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { format } from "date-fns";
import { ko } from "date-fns/locale";

interface Props { data: MonthlyStats[]; loading: boolean; }

export default function DistanceChart({ data, loading }: Props) {
  const chartData = data.map((d) => ({
    label: format(new Date(d.year, d.month - 1), "yy.MM", { locale: ko }),
    value: d.total_distance,
  }));

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">월별 주행거리</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-52 w-full" />
        ) : (
          <ResponsiveContainer width="100%" height={210}>
            <BarChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#3C4043" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} unit=" km" />
              <Tooltip formatter={(v: number) => [`${v.toLocaleString("ko")} km`, "주행거리"]} />
              <Bar dataKey="value" fill="#8AB4F8" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
