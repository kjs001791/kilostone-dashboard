"use client";

import { useRouter } from "next/navigation";
import { useAuth } from "@/contexts/AuthContext";
import { useEffect } from "react";
import AppShell from "@/components/layout/AppShell";
import LogForm from "@/components/logs/LogForm";
import { logsApi } from "@/lib/api";
import { LogCreatePayload } from "@/types/log";
import { useToast } from "@/hooks/use-toast";

export default function NewLogPage() {
  const { isAuthenticated, isLoading } = useAuth();
  const router = useRouter();
  const { toast } = useToast();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) router.replace("/login");
  }, [isAuthenticated, isLoading, router]);

  const handleSubmit = async (payload: LogCreatePayload) => {
    try {
      await logsApi.create(payload);
      toast({ description: "기록이 저장되었습니다." });
      router.push("/logs");
    } catch (e: any) {
      toast({ variant: "destructive", description: e.message || "저장 실패" });
    }
  };

  if (isLoading) return null;

  return (
    <AppShell>
      <div className="p-4 md:p-6 max-w-2xl mx-auto">
        <h1 className="text-xl font-semibold mb-6">운행기록 추가</h1>
        <LogForm onSubmit={handleSubmit} />
      </div>
    </AppShell>
  );
}
