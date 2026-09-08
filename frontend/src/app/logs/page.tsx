"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import AppShell from "@/components/layout/AppShell";
import LogTable from "@/components/logs/LogTable";
import LogFilters from "@/components/logs/LogFilters";
import { logsApi } from "@/lib/api";
import { LogsPage } from "@/types/log";
import { Button } from "@/components/ui/button";
import Link from "next/link";
import { PlusCircle } from "lucide-react";

export default function LogsPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const [data, setData] = useState<LogsPage | null>(null);
  const [page, setPage] = useState(1);
  const [filters, setFilters] = useState<{
    vehicle_id?: string;
    date_from?: string;
    date_to?: string;
  }>({});
  const [fetching, setFetching] = useState(true);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace("/login");
  }, [isAuthenticated, isLoading, router]);

  useEffect(() => {
    if (!isAuthenticated) return;
    setFetching(true);
    logsApi.list({ page, per_page: 20, ...filters })
      .then(setData)
      .catch(() => {})
      .finally(() => setFetching(false));
  }, [isAuthenticated, page, filters]);

  if (isLoading) return null;

  return (
    <AppShell>
      <div className="p-4 md:p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-semibold">기록 조회</h1>
          <Button asChild size="sm">
            <Link href="/logs/new"><PlusCircle className="w-4 h-4 mr-1" />추가</Link>
          </Button>
        </div>

        <LogFilters value={filters} onChange={(f) => { setFilters(f); setPage(1); }} />

        <LogTable
          data={data}
          loading={fetching}
          page={page}
          onPageChange={setPage}
          onDelete={async (id) => {
            try {
              await logsApi.delete(id);
              const newData = await logsApi.list({ page, per_page: 20, ...filters });
              setData(newData);
            } catch (e) {
              alert("삭제 실패");
            }
          }}
        />
      </div>
    </AppShell>
  );
}
