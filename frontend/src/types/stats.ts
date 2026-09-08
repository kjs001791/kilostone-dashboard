export interface StatsSummary {
  total_distance: number;
  avg_fuel_efficiency: number | null;
  total_consumed_fuel: number | null;
  total_records: number;
}

export interface MonthlyStats {
  year: number;
  month: number;
  total_distance: number;
  avg_fuel_efficiency: number | null;
  total_consumed_fuel: number | null;
  record_count: number;
}

export interface StatsResponse {
  summary: StatsSummary;
  monthly: MonthlyStats[];
}
