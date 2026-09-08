"use client";

import { DrivingLog, LogsPage } from "@/types/log";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import Link from "next/link";
import { Pencil, Trash2, ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";

interface Props {
  data: LogsPage | null;
  loading: boolean;
  page: number;
  onPageChange: (p: number) => void;
  onDelete: (id: number) => Promise<void>;
}

export default function LogTable({ data, loading, page, onPageChange, onDelete }: Props) {
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const handleDelete = async (log: DrivingLog) => {
    if (!confirm(`${log.date} ${log.vehicle_id} 기록을 삭제하시겠습니까?`)) return;
    setDeletingId(log.id);
    try {
      await onDelete(log.id);
    } finally {
      setDeletingId(null);
    }
  };

  if (loading) return <Skeleton className="h-64 w-full" />;
  if (!data || data.items.length === 0) return <p className="text-muted-foreground text-sm text-center py-12">기록이 없습니다.</p>;

  const totalPages = Math.ceil(data.total / data.per_page);

  return (
    <div className="space-y-3">
      {/* 데스크탑 테이블 */}
      <div className="hidden md:block rounded-md border bg-card">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>날짜</TableHead>
              <TableHead>차량</TableHead>
              <TableHead className="text-right">주행(km)</TableHead>
              <TableHead className="text-right">연비(km/L)</TableHead>
              <TableHead className="text-right">소모(L)</TableHead>
              <TableHead>출처</TableHead>
              <TableHead className="w-20" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.items.map((log) => (
              <TableRow key={log.id}>
                <TableCell className="py-2.5 font-medium">{log.date}</TableCell>
                <TableCell className="py-2.5 text-xs">{log.vehicle_id}</TableCell>
                <TableCell className="py-2.5 text-right">{log.distance?.toLocaleString("ko")}</TableCell>
                <TableCell className="py-2.5 text-right">{log.fuel_efficiency?.toFixed(2) ?? "-"}</TableCell>
                <TableCell className="py-2.5 text-right">{log.consumed_fuel?.toFixed(1) ?? "-"}</TableCell>
                <TableCell className="py-2.5">
                  <Badge variant={log.source === "manual" ? "outline" : "secondary"} className="text-[10px] px-1.5 py-0">
                    {log.source === "manual" ? "수동" : "자동"}
                  </Badge>
                </TableCell>
                <TableCell className="py-2.5">
                  <div className="flex gap-1">
                    <Button variant="ghost" size="icon" className="h-7 w-7" asChild>
                      <Link href={`/logs/${log.id}/edit`}><Pencil className="w-3.5 h-3.5" /></Link>
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-7 w-7"
                      disabled={deletingId === log.id}
                      onClick={() => handleDelete(log)}
                    >
                      <Trash2 className="w-3.5 h-3.5 text-destructive" />
                    </Button>
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      {/* 모바일 카드 목록 */}
      <div className="md:hidden space-y-2">
        {data.items.map((log) => (
          <div key={log.id} className="border border-border rounded-lg p-3 bg-card space-y-1">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-sm">{log.date}</span>
              <Badge variant={log.source === "manual" ? "outline" : "secondary"} className="text-[10px] px-1.5 py-0">
                {log.source === "manual" ? "수동" : "자동"}
              </Badge>
            </div>
            <p className="text-[11px] text-muted-foreground">{log.vehicle_id}</p>
            <div className="flex gap-4 text-xs pt-1">
              <div className="flex flex-col">
                <span className="text-muted-foreground text-[10px]">주행</span>
                <span className="font-medium">{log.distance?.toLocaleString("ko")} km</span>
              </div>
              <div className="flex flex-col">
                <span className="text-muted-foreground text-[10px]">연비</span>
                <span className="font-medium">{log.fuel_efficiency?.toFixed(2) ?? "-"} km/L</span>
              </div>
              <div className="flex flex-col">
                <span className="text-muted-foreground text-[10px]">연료소모</span>
                <span className="font-medium">{log.consumed_fuel?.toFixed(1) ?? "-"} L</span>
              </div>
            </div>
            <div className="flex gap-2 justify-end pt-1">
              <Button variant="outline" size="sm" className="h-7 text-[11px] px-2.5" asChild>
                <Link href={`/logs/${log.id}/edit`}><Pencil className="w-3 h-3 mr-1" />수정</Link>
              </Button>
              <Button variant="outline" size="sm" className="h-7 text-[11px] px-2.5" onClick={() => handleDelete(log)} disabled={deletingId === log.id}>
                <Trash2 className="w-3 h-3 mr-1 text-destructive" />삭제
              </Button>
            </div>
          </div>
        ))}
      </div>

      {/* 페이지네이션 */}
      <div className="flex items-center justify-between text-xs text-muted-foreground pt-2">
        <span>전체 {data.total.toLocaleString("ko")}건</span>
        <div className="flex items-center gap-3">
          <Button variant="outline" size="icon" className="h-7 w-7" disabled={page === 1} onClick={() => onPageChange(page - 1)}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <span className="font-medium">{page} / {totalPages}</span>
          <Button variant="outline" size="icon" className="h-7 w-7" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)}>
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
