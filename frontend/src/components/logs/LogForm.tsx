"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { VEHICLE_OPTIONS, isScania, LogCreatePayload } from "@/types/log";

const schema = z.object({
  date: z.string().min(1, "날짜를 입력하세요"),
  vehicle_id: z.string().min(1, "차량을 선택하세요"),
  distance: z.number({ invalid_type_error: "숫자를 입력하세요" }).min(0).max(1500),
  cumulative_distance: z.number().optional().nullable(),
  speed: z.number().min(0).max(120).optional().nullable(),
  time: z.string().regex(/^\d{1,3}:\d{2}$/, "HH:MM 형식").optional().or(z.literal("")).nullable(),
  time_idle: z.string().regex(/^\d{1,3}:\d{2}$/).optional().or(z.literal("")).nullable(),
  time_pto: z.string().regex(/^\d{1,3}:\d{2}$/).optional().or(z.literal("")).nullable(),
  fuel_efficiency: z.number().min(1.0).max(6.0).optional().nullable(),
  fuel_rate_per_hour: z.number().optional().nullable(),
  consumed_fuel: z.number().min(0).max(500).optional().nullable(),
  consumed_fuel_idle: z.number().optional().nullable(),
  consumed_fuel_pto: z.number().optional().nullable(),
  refuel: z.number().optional().nullable(),
  reurea: z.number().optional().nullable(),
});

type FormValues = z.infer<typeof schema>;

interface Props {
  defaultValues?: Partial<FormValues>;
  onSubmit: (payload: LogCreatePayload) => Promise<void>;
  submitLabel?: string;
}

export default function LogForm({ defaultValues, onSubmit, submitLabel = "저장" }: Props) {
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { 
      date: new Date().toISOString().slice(0, 10),
      ...defaultValues 
    },
  });

  const vehicleId = form.watch("vehicle_id") ?? "";
  const showScaniaFields = isScania(vehicleId);

  const handleSubmit = async (values: FormValues) => {
    const payload: LogCreatePayload = Object.fromEntries(
      Object.entries(values).map(([k, v]) => [k, v === "" ? null : v])
    ) as any;
    await onSubmit(payload);
  };

  return (
    <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-6">
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <Field label="날짜" error={form.formState.errors.date?.message}>
          <Input type="date" {...form.register("date")} />
        </Field>

        <Field label="차량" error={form.formState.errors.vehicle_id?.message}>
          <Select
            value={form.watch("vehicle_id")}
            onValueChange={(v) => form.setValue("vehicle_id", v)}
          >
            <SelectTrigger><SelectValue placeholder="차량 선택" /></SelectTrigger>
            <SelectContent>
              {VEHICLE_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </Field>

        <Field label="주행거리 (km)" error={form.formState.errors.distance?.message}>
          <Input type="number" step="0.1" {...form.register("distance", { valueAsNumber: true })} />
        </Field>

        <Field label="연비 (km/L)" error={form.formState.errors.fuel_efficiency?.message}>
          <Input type="number" step="0.01" {...form.register("fuel_efficiency", { valueAsNumber: true })} />
        </Field>

        <Field label="연료소모량 (L)" error={form.formState.errors.consumed_fuel?.message}>
          <Input type="number" step="0.01" {...form.register("consumed_fuel", { valueAsNumber: true })} />
        </Field>

        <Field label="주유량 (L)">
          <Input type="number" step="0.1" {...form.register("refuel", { valueAsNumber: true })} />
        </Field>

        <Field label="요소수 (L)">
          <Input type="number" step="0.1" {...form.register("reurea", { valueAsNumber: true })} />
        </Field>

        <Field label="누적거리 (km)">
          <Input type="number" step="0.1" {...form.register("cumulative_distance", { valueAsNumber: true })} />
        </Field>

        <Field label="평균속도 (km/h)" error={form.formState.errors.speed?.message}>
          <Input type="number" step="0.1" {...form.register("speed", { valueAsNumber: true })} />
        </Field>

        <Field label="운행시간 (HH:MM)" error={form.formState.errors.time?.message}>
          <Input placeholder="06:30" {...form.register("time")} />
        </Field>
      </div>

      {showScaniaFields && (
        <div className="bg-muted/30 border border-border rounded-lg p-4 space-y-4">
          <p className="text-[11px] text-muted-foreground font-bold uppercase tracking-wider">스카니아 전용 상세 항목</p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field label="공회전 연료 (L)">
              <Input type="number" step="0.01" {...form.register("consumed_fuel_idle", { valueAsNumber: true })} />
            </Field>
            <Field label="PTO 연료 (L)">
              <Input type="number" step="0.01" {...form.register("consumed_fuel_pto", { valueAsNumber: true })} />
            </Field>
            <Field label="시간당 연료 (L/h)">
              <Input type="number" step="0.01" {...form.register("fuel_rate_per_hour", { valueAsNumber: true })} />
            </Field>
            <div className="grid grid-cols-2 gap-2">
              <Field label="공회전 시간" error={form.formState.errors.time_idle?.message}>
                <Input placeholder="00:45" {...form.register("time_idle")} />
              </Field>
              <Field label="PTO 시간" error={form.formState.errors.time_pto?.message}>
                <Input placeholder="00:00" {...form.register("time_pto")} />
              </Field>
            </div>
          </div>
        </div>
      )}

      <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
        {form.formState.isSubmitting ? "저장 중..." : submitLabel}
      </Button>
    </form>
  );
}

function Field({ label, error, children }: { label: string; error?: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1.5">
      <Label className="text-xs font-semibold">{label}</Label>
      {children}
      {error && <p className="text-[10px] text-destructive font-medium">{error}</p>}
    </div>
  );
}
