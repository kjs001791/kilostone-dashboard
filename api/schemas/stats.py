from pydantic import BaseModel
from typing import Optional

class StatsSummary(BaseModel):
    total_distance: float
    avg_fuel_efficiency: Optional[float]
    total_consumed_fuel: Optional[float]
    total_records: int

class MonthlyStats(BaseModel):
    year: int
    month: int
    total_distance: float
    avg_fuel_efficiency: Optional[float]
    total_consumed_fuel: Optional[float]
    record_count: int

class StatsResponse(BaseModel):
    summary: StatsSummary
    monthly: list[MonthlyStats]
