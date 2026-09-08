from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.engine import Engine
from typing import Optional
from api.dependencies import get_db_engine, get_current_user
from api.schemas.stats import StatsResponse, StatsSummary, MonthlyStats

router = APIRouter(prefix="/stats", tags=["stats"])

@router.get("", response_model=StatsResponse)
def get_stats(
    vehicle_id: Optional[str] = None,
    year: Optional[int] = None,
    engine: Engine = Depends(get_db_engine),
    _: str = Depends(get_current_user),
):
    filters = []
    params = {}
    if vehicle_id:
        filters.append("vehicle_id = :vehicle_id")
        params["vehicle_id"] = vehicle_id
    if year:
        filters.append("YEAR(date) = :year")
        params["year"] = year

    where = ("WHERE " + " AND ".join(filters)) if filters else ""

    with engine.connect() as conn:
        summary_row = conn.execute(text(f"""
            SELECT
                COALESCE(SUM(distance), 0)        AS total_distance,
                AVG(fuel_efficiency)               AS avg_fuel_efficiency,
                SUM(consumed_fuel)                 AS total_consumed_fuel,
                COUNT(*)                           AS total_records
            FROM driving_logs {where}
        """), params).mappings().one()

        monthly_rows = conn.execute(text(f"""
            SELECT
                YEAR(date)              AS year,
                MONTH(date)             AS month,
                SUM(distance)           AS total_distance,
                AVG(fuel_efficiency)    AS avg_fuel_efficiency,
                SUM(consumed_fuel)      AS total_consumed_fuel,
                COUNT(*)                AS record_count
            FROM driving_logs {where}
            GROUP BY YEAR(date), MONTH(date)
            ORDER BY year ASC, month ASC
        """), params).mappings().all()

    return {
        "summary": dict(summary_row),
        "monthly": [dict(r) for r in monthly_rows],
    }
