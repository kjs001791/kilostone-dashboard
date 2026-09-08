export interface PipelineRun {
  run_id: number;
  started_at: string;
  finished_at: string | null;
  status: "running" | "completed" | "failed";
  input_files: string[] | null;
  rows_processed: number;
  rows_rejected: number;
  rejection_rate: number;
  error_message: string | null;
}
