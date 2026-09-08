from pydantic import BaseModel, field_validator
from datetime import date, datetime
from typing import Optional

class DrivingLogBase(BaseModel):
    date: date
    vehicle_id: str
    distance: Optional[float] = None
    cumulative_distance: Optional[float] = None
    speed: Optional[float] = None
    time: Optional[str] = None          # "HH:MM" 형식
    time_idle: Optional[str] = None
    time_pto: Optional[str] = None
    fuel_efficiency: Optional[float] = None
    fuel_rate_per_hour: Optional[float] = None
    consumed_fuel: Optional[float] = None
    consumed_fuel_idle: Optional[float] = None
    consumed_fuel_pto: Optional[float] = None
    refuel: Optional[float] = None
    reurea: Optional[float] = None

class DrivingLogCreate(DrivingLogBase):
    # 아래 validator들은 app/services/data_validator.py 로직을 Pydantic으로 포팅한 것
    @field_validator('fuel_efficiency')
    @classmethod
    def check_fuel_efficiency(cls, v):
        if v is not None and not (1.0 <= v <= 6.0):
            raise ValueError(f"연비 {v} km/L가 허용 범위(1.0~6.0)를 벗어났습니다.")
        return v

    @field_validator('distance')
    @classmethod
    def check_distance(cls, v):
        if v is not None and not (0 <= v <= 1500):
            raise ValueError(f"주행거리 {v} km가 비정상적입니다.")
        return v

    @field_validator('speed')
    @classmethod
    def check_speed(cls, v):
        if v is not None and not (0 <= v <= 120):
            raise ValueError(f"평균속도 {v} km/h가 비정상적입니다.")
        return v

class DrivingLogUpdate(DrivingLogBase):
    date: Optional[date] = None
    vehicle_id: Optional[str] = None

class DrivingLogResponse(DrivingLogBase):
    id: int
    source: str
    created_at: datetime

    model_config = {"from_attributes": True}

class LogsPage(BaseModel):
    total: int
    page: int
    per_page: int
    items: list[DrivingLogResponse]
