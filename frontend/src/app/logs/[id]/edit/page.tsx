"use client";

import { useEffect, useState } from "react";
import { useRouter, useParams } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import AppShell from "@/components/layout/AppShell";
import LogForm from "@/components/logs/LogForm";
import { apiFetch, logsApi } from "@/lib/api";
import { DrivingLog, LogCreatePayload } from "@/types/log";
import { useToast } from "@/hooks/use-toast";
import { Skeleton } from "@/components/ui/skeleton";

export default function EditLogPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const params = useParams();
  const { toast } = useToast();
  const [log, setLog] = useState<DrivingLog | null>(null);

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace("/login");
  }, [isAuthenticated, isLoading, router]);

  useEffect(() => {
    if (!isAuthenticated || !params.id) return;
    apiFetch<DrivingLog>(`/logs/${params.id}`)
      .then(setLog)
      .catch(() => toast({ variant: "destructive", description: "기록을 불러오지 못했습니다." }));
  }, [isAuthenticated, params.id, toast]);

  const handleSubmit = async (payload: LogCreatePayload) => {
    try {
      await logsApi.update(Number(params.id), payload);
      toast({ description: "수정되었습니다." });
      router.push("/logs");
    } catch (e: any) {
      toast({ variant: "destructive", description: e.message || "수정 실패" });
    }
  };

  if (isLoading) return null;

  return (
    <AppShell>
      <div className="p-4 md:p-6 max-w-2xl mx-auto">
        <h1 className="text-xl font-semibold mb-6">운행기록 수정</h1>
        {log ? (
          <LogForm
            defaultValues={{ 
              ...log, 
              date: log.date,
              time: log.time || "",
              time_idle: log.time_idle || "",
              time_pto: log.time_pto || ""
            }}
            onSubmit={handleSubmit}
            submitLabel="수정 저장"
          />
        ) : (
          <Skeleton className="h-96 w-full" />
        )}
      </div>
    </AppShell>
  );
}
