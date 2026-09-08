"use client";

import { useEffect, useState } from "react";
import { pipelineApi } from "@/lib/api";
import { PipelineRun } from "@/types/pipeline_run";
import { format } from "date-fns";
import { ko } from "date-fns/locale";
import { AlertTriangle, CheckCircle, XCircle } from "lucide-react";

const ALERT_THRESHOLD = 5.0;

export default function PipelineBanner() {
  const [run, setRun] = useState<PipelineRun | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    pipelineApi.latest()
      .then(setRun)
      .catch(() => setError(true));
  }, []);

  if (error || !run) return null;

  const isAlert = run.rejection_rate >= ALERT_THRESHOLD;
  const isFailed = run.status === "failed";

  const colorClass = isFailed
    ? "bg-red-950/40 border-red-800 text-red-300"
    : isAlert
    ? "bg-yellow-950/40 border-yellow-700 text-yellow-300"
    : "bg-blue-950/40 border-blue-800 text-blue-300";

  const Icon = isFailed ? XCircle : isAlert ? AlertTriangle : CheckCircle;

  const dateLabel = run.finished_at
    ? format(new Date(run.finished_at), "M월 d일 HH:mm", { locale: ko })
    : "-";

  return (
    <div className={`flex items-center gap-2 px-3 py-2.5 rounded-lg border text-[11px] ${colorClass}`}>
      <Icon className="w-3.5 h-3.5 flex-shrink-0" />
      {isFailed ? (
        <span className="font-medium">최근 파이프라인 실패 ({dateLabel}) — {run.error_message?.slice(0, 60)}...</span>
      ) : (
        <span>
          최근 데이터 업데이트: <strong>{dateLabel}</strong> · 처리 {run.rows_processed.toLocaleString("ko")}건
          {run.rows_rejected > 0 && (
            <> · 이상치 <strong>{run.rejection_rate.toFixed(1)}%</strong> ({run.rows_rejected}건)</>
          )}
          {!isAlert && run.rows_rejected === 0 && " · 모든 데이터 무결함"}
        </span>
      )}
    </div>
  );
}
