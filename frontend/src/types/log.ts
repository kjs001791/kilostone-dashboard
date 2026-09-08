export interface DrivingLog {
  id: number;
  date: string;                        // "YYYY-MM-DD"
  vehicle_id: string;
  distance: number;
  cumulative_distance: number | null;
  speed: number | null;
  time: string | null;                 // "HH:MM"
  time_idle: string | null;
  time_pto: string | null;
  fuel_efficiency: number | null;
  fuel_rate_per_hour: number | null;
  consumed_fuel: number | null;
  consumed_fuel_idle: number | null;
  consumed_fuel_pto: number | null;
  refuel: number | null;
  reurea: number | null;
  source: "pipeline" | "manual";
  created_at: string;
}

export interface LogsPage {
  total: number;
  page: number;
  per_page: number;
  items: DrivingLog[];
}

export interface LogCreatePayload {
  date: string;
  vehicle_id: string;
  distance: number;
  cumulative_distance?: number;
  speed?: number;
  time?: string;
  time_idle?: string;
  time_pto?: string;
  fuel_efficiency?: number;
  fuel_rate_per_hour?: number;
  consumed_fuel?: number;
  consumed_fuel_idle?: number;
  consumed_fuel_pto?: number;
  refuel?: number;
  reurea?: number;
}

export type LogUpdatePayload = Partial<LogCreatePayload>;

export const VEHICLE_OPTIONS = [
  { value: "MAN TGX", label: "MAN TGX" },
  { value: "Daewoo Prima", label: "대우 프리마" },
  { value: "Scania", label: "스카니아" },
] as const;

export type VehicleId = typeof VEHICLE_OPTIONS[number]["value"];

export const isScania = (vehicleId: string) => vehicleId === "Scania";
