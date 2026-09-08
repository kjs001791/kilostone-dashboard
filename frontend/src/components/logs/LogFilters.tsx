"use client";

import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { VEHICLE_OPTIONS } from "@/types/log";
import { Button } from "@/components/ui/button";
import { X } from "lucide-react";

interface Props {
  value: {
    vehicle_id?: string;
    date_from?: string;
    date_to?: string;
  };
  onChange: (filters: Props["value"]) => void;
}

export default function LogFilters({ value, onChange }: Props) {
  const clearFilters = () => onChange({});

  return (
    <div className="bg-card border rounded-lg p-4 space-y-4">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <div className="space-y-1.5">
          <Label size="sm">차량</Label>
          <Select
            value={value.vehicle_id ?? "all"}
            onValueChange={(v) => onChange({ ...value, vehicle_id: v === "all" ? undefined : v })}
          >
            <SelectTrigger><SelectValue placeholder="전체" /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">전체</SelectItem>
              {VEHICLE_OPTIONS.map((o) => (
                <SelectItem key={o.value} value={o.value}>{o.label}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label size="sm">시작일</Label>
          <Input
            type="date"
            value={value.date_from ?? ""}
            onChange={(e) => onChange({ ...value, date_from: e.target.value || undefined })}
          />
        </div>
        <div className="space-y-1.5">
          <Label size="sm">종료일</Label>
          <Input
            type="date"
            value={value.date_to ?? ""}
            onChange={(e) => onChange({ ...value, date_to: e.target.value || undefined })}
          />
        </div>
      </div>
      {(value.vehicle_id || value.date_from || value.date_to) && (
        <div className="flex justify-end">
          <Button variant="ghost" size="sm" onClick={clearFilters} className="h-8 px-2 text-xs">
            <X className="w-3 h-3 mr-1" /> 필터 초기화
          </Button>
        </div>
      )}
    </div>
  );
}
