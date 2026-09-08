from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import text
from sqlalchemy.engine import Engine
from typing import Optional
from datetime import date
from api.dependencies import get_db_engine, get_current_user
from api.schemas.log import DrivingLogCreate, DrivingLogUpdate, DrivingLogResponse, LogsPage

router = APIRouter(prefix="/logs", tags=["logs"])

ALL_COLUMNS = """
    id, date, vehicle_id, distance, cumulative_distance,
    speed, time, time_idle, time_pto,
    fuel_efficiency, fuel_rate_per_hour,
    consumed_fuel, consumed_fuel_idle, consumed_fuel_pto,
    refuel, reurea, source, created_at
"""

@router.get("", response_model=LogsPage)
def get_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    vehicle_id: Optional[str] = None,
    date_from: Optional[date] = None,
    date_to: Optional[date] = None,
    engine: Engine = Depends(get_db_engine),
    _: str = Depends(get_current_user),
):
    offset = (page - 1) * per_page
    filters = []
    params: dict = {"limit": per_page, "offset": offset}

    if vehicle_id:
        filters.append("vehicle_id = :vehicle_id")
        params["vehicle_id"] = vehicle_id
    if date_from:
        filters.append("date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        filters.append("date <= :date_to")
        params["date_to"] = date_to

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with engine.connect() as conn:
        total = conn.execute(text(f"SELECT COUNT(*) FROM driving_logs {where}"), params).scalar()
        rows = conn.execute(
            text(f"SELECT {ALL_COLUMNS} FROM driving_logs {where} ORDER BY date DESC, id DESC LIMIT :limit OFFSET :offset"),
            params
        ).mappings().all()

    return {"total": total, "page": page, "per_page": per_page, "items": [dict(r) for r in rows]}


@router.get("/{log_id}", response_model=DrivingLogResponse)
def get_log(
    log_id: int,
    engine: Engine = Depends(get_db_engine),
    _: str = Depends(get_current_user),
):
    with engine.connect() as conn:
        row = conn.execute(
            text(f"SELECT {ALL_COLUMNS} FROM driving_logs WHERE id = :id"),
            {"id": log_id}
        ).mappings().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"id={log_id} 기록을 찾을 수 없습니다.")
    return dict(row)


@router.post("", response_model=DrivingLogResponse, status_code=status.HTTP_201_CREATED)
def create_log(
    body: DrivingLogCreate,
    engine: Engine = Depends(get_db_engine),
    _: str = Depends(get_current_user),
):
    data = body.model_dump()
    data["source"] = "manual"

    columns = ", ".join(data.keys())
    placeholders = ", ".join(f":{k}" for k in data.keys())

    with engine.connect() as conn:
        result = conn.execute(text(f"INSERT INTO driving_logs ({columns}) VALUES ({placeholders})"), data)
        conn.commit()
        new_id = result.lastrowid

    with engine.connect() as conn:
        row = conn.execute(text(f"SELECT {ALL_COLUMNS} FROM driving_logs WHERE id = :id"), {"id": new_id}).mappings().one()
    return dict(row)


@router.put("/{log_id}", response_model=DrivingLogResponse)
def update_log(
    log_id: int,
    body: DrivingLogUpdate,
    engine: Engine = Depends(get_db_engine),
    _: str = Depends(get_current_user),
):
    # Only update non-None fields
    data = {k: v for k, v in body.model_dump().items() if v is not None}
    if not data:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="수정할 필드가 없습니다.")

    data["source"] = "manual"
    data["id"] = log_id

    set_clause = ", ".join(f"{k} = :{k}" for k in data.keys() if k != "id")

    with engine.connect() as conn:
        result = conn.execute(text(f"UPDATE driving_logs SET {set_clause} WHERE id = :id"), data)
        conn.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"id={log_id} 기록을 찾을 수 없습니다.")

    with engine.connect() as conn:
        row = conn.execute(text(f"SELECT {ALL_COLUMNS} FROM driving_logs WHERE id = :id"), {"id": log_id}).mappings().one()
    return dict(row)


@router.delete("/{log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_log(
    log_id: int,
    engine: Engine = Depends(get_db_engine),
    _: str = Depends(get_current_user),
):
    with engine.connect() as conn:
        result = conn.execute(text("DELETE FROM driving_logs WHERE id = :id"), {"id": log_id})
        conn.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"id={log_id} 기록을 찾을 수 없습니다.")
    return None
