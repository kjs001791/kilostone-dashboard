"use client";

import { MonthlyStats } from "@/types/stats";
import { ComposedChart, Area, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer } from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { format } from "date-fns";
import { ko } from "date-fns/locale";

interface Props { data: MonthlyStats[]; loading: boolean; }

export default function FuelChart({ data, loading }: Props) {
  const chartData = data.map((d) => ({
    label: format(new Date(d.year, d.month - 1), "yy.MM", { locale: ko }),
    value: d.total_consumed_fuel,
  }));

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium">월별 연료소모량</CardTitle>
      </CardHeader>
      <CardContent>
        {loading ? (
          <Skeleton className="h-52 w-full" />
        ) : (
          <ResponsiveContainer width="100%" height={210}>
            <ComposedChart data={chartData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#3C4043" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 11 }} unit=" L" />
              <Tooltip formatter={(v: number) => [`${v?.toLocaleString("ko")} L`, "소모량"]} />
              <Area type="monotone" dataKey="value" fill="rgba(242,139,130,0.2)" stroke="#F28B82" />
            </ComposedChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
