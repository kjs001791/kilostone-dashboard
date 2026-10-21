"""허브(PostgreSQL 스키마 hub) 조회·입력 경로. 약속은 api/HUB_API.md. 로그인 없음(로컬 전용)."""
import datetime as dt
import json
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from api.hub_checks import run_checks
from api.hub_db import get_hub_engine

router = APIRouter(prefix="/hub", tags=["hub"])

MONTH_PATTERN = r"^\d{4}-(0[1-9]|1[0-2])$"


def hub_engine():
    return get_hub_engine()


def _num(v):
    if v is None:
        return None
    return float(v) if isinstance(v, Decimal) else v


def _shift_month(first: dt.date, delta: int) -> dt.date:
    idx = first.year * 12 + (first.month - 1) + delta
    return dt.date(idx // 12, idx % 12 + 1, 1)


@router.get("/months")
def months(engine=Depends(hub_engine)):
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT DISTINCT to_char(date, 'YYYY-MM') AS m FROM hub.delivery ORDER BY m DESC"
        )).all()
    ms = [r.m for r in rows]
    return {"months": ms, "latest": ms[0] if ms else None}


@router.get("/summary")
def summary(month: Optional[str] = Query(None, pattern=MONTH_PATTERN), engine=Depends(hub_engine)):
    with engine.connect() as conn:
        if month is None:
            latest = conn.execute(text("SELECT to_char(max(date), 'YYYY-MM') FROM hub.delivery")).scalar()
            if latest is None:
                raise HTTPException(status_code=404, detail="데이터가 있는 달이 없습니다")
            month = latest
        first = dt.date(int(month[:4]), int(month[5:7]), 1)
        nxt = _shift_month(first, 1)
        prev = _shift_month(first, -1)
        ly = _shift_month(first, -12)

        def month_totals(start: dt.date):
            r = conn.execute(text(
                "SELECT sum(supply_amount) AS rev, sum(weight_kg) AS kg "
                "FROM hub.delivery WHERE date >= :a AND date < :b"
            ), {"a": start, "b": _shift_month(start, 1)}).one()
            rev = _num(r.rev)
            ton = _num(r.kg) / 1000 if r.kg is not None else None
            return rev, ton

        cur_rev, cur_ton = month_totals(first)
        prev_rev, prev_ton = month_totals(prev)
        ly_rev, ly_ton = month_totals(ly)

        has_computed = bool(conn.execute(text(
            "SELECT EXISTS (SELECT 1 FROM hub.delivery WHERE date >= :a AND date < :b "
            "AND amount_source = 'computed_invoice')"
        ), {"a": first, "b": nxt}).scalar())

        clients = conn.execute(text(
            "SELECT d.client_id, coalesce(c.name, '미지정') AS client_name, "
            "sum(d.weight_kg) AS kg, sum(d.supply_amount) AS rev, count(DISTINCT d.date) AS days "
            "FROM hub.delivery d LEFT JOIN hub.client c ON c.client_id = d.client_id "
            "WHERE d.date >= :a AND d.date < :b "
            "GROUP BY d.client_id, c.name "
            "ORDER BY sum(d.supply_amount) DESC NULLS LAST, sum(d.weight_kg) DESC NULLS LAST, d.client_id NULLS LAST"
        ), {"a": first, "b": nxt}).all()

        drv = conn.execute(text(
            "SELECT count(DISTINCT date) AS days, sum(distance) AS dist, sum(consumed_fuel) AS fuel "
            "FROM hub.driving WHERE date >= :a AND date < :b"
        ), {"a": first, "b": nxt}).one()

    dist, fuel = _num(drv.dist), _num(drv.fuel)
    return {
        "month": month,
        "revenue": {"this_month": cur_rev, "prev_month": prev_rev, "same_month_last_year": ly_rev},
        "revenue_has_computed": has_computed,
        "weight_ton": {"this_month": cur_ton, "prev_month": prev_ton, "same_month_last_year": ly_ton},
        "by_client": [
            {
                "client_id": c.client_id,
                "client_name": c.client_name,
                "weight_ton": _num(c.kg) / 1000 if c.kg is not None else None,
                "revenue": _num(c.rev),
                "days": c.days,
            }
            for c in clients
        ],
        "driving": {
            "days": drv.days,
            "distance_km": dist,
            "fuel_l": fuel,
            "avg_efficiency": (dist / fuel) if dist is not None and fuel else None,
        },
    }


@router.get("/vehicles")
def vehicles(engine=Depends(hub_engine)):
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT vehicle_id, brand, model, color, service_start, service_end, "
            "(service_end IS NULL) AS current FROM hub.vehicle ORDER BY vehicle_id"
        )).mappings().all()
    return jsonable_encoder([dict(r) for r in rows])


@router.get("/driving")
def driving(vehicle_id: str, limit: int = Query(30, ge=1, le=1000), engine=Depends(hub_engine)):
    with engine.connect() as conn:
        rows = conn.execute(text(
            "SELECT * FROM hub.driving WHERE vehicle_id = :v ORDER BY date DESC, driving_id DESC LIMIT :n"
        ), {"v": vehicle_id, "n": limit}).mappings().all()
    return jsonable_encoder([{k: _num(v) for k, v in r.items()} for r in rows])


class DrivingIn(BaseModel):
    vehicle_id: str
    date: dt.date
    distance: Optional[float] = None
    cumulative_distance: Optional[float] = None
    consumed_fuel: Optional[float] = None
    fuel_efficiency: Optional[float] = None
    speed: Optional[float] = None
    time_h: Optional[float] = None
    time_idle_h: Optional[float] = None
    time_pto_h: Optional[float] = None
    refuel: Optional[float] = None
    reurea: Optional[float] = None
    confirm: bool = False


_VALUE_COLS = [
    "distance", "cumulative_distance", "consumed_fuel", "fuel_efficiency", "speed",
    "time_h", "time_idle_h", "time_pto_h", "refuel", "reurea",
]


def _warnings_for(conn, body: DrivingIn) -> list:
    p = {"v": body.vehicle_id, "d": body.date}
    prev = conn.execute(text(
        "SELECT cumulative_distance FROM hub.driving WHERE vehicle_id = :v AND date < :d "
        "AND cumulative_distance IS NOT NULL ORDER BY date DESC LIMIT 1"
    ), p).scalar()
    recent = conn.execute(text(
        "SELECT distance, consumed_fuel FROM hub.driving WHERE vehicle_id = :v "
        "AND date < :d AND date >= :d - 30"
    ), p).all()
    dup = bool(conn.execute(text(
        "SELECT EXISTS (SELECT 1 FROM hub.driving WHERE vehicle_id = :v AND date = :d)"
    ), p).scalar())
    return run_checks(
        body.model_dump(),
        prev_cumulative=_num(prev),
        recent=[{"distance": _num(r.distance), "consumed_fuel": _num(r.consumed_fuel)} for r in recent],
        duplicate=dup,
    )


@router.post("/driving/check")
def driving_check(body: DrivingIn, engine=Depends(hub_engine)):
    with engine.connect() as conn:
        return {"warnings": _warnings_for(conn, body)}


@router.post("/driving")
def driving_save(body: DrivingIn, engine=Depends(hub_engine)):
    with engine.begin() as conn:
        if conn.execute(text("SELECT 1 FROM hub.vehicle WHERE vehicle_id = :v"), {"v": body.vehicle_id}).first() is None:
            raise HTTPException(status_code=404, detail="없는 차량입니다")
        warnings = _warnings_for(conn, body)
        has_dup = any(w["rule"] == "duplicate_date" for w in warnings)
        if has_dup or (warnings and not body.confirm):
            return JSONResponse(status_code=409, content={"warnings": warnings})
        flags = None
        if warnings:
            flags = {}
            for w in warnings:
                flags.setdefault(w["field"], []).append({"rule": w["rule"], "message": w["message"]})
        cols = ["vehicle_id", "date"] + _VALUE_COLS
        params = {c: getattr(body, c) for c in cols}
        params["flags"] = json.dumps(flags, ensure_ascii=False) if flags else None
        try:
            with conn.begin_nested():
                new_id = conn.execute(text(
                    f"INSERT INTO hub.driving ({', '.join(cols)}, entered_via, flags, created_at_kst) "
                    f"VALUES ({', '.join(':' + c for c in cols)}, 'app', CAST(:flags AS jsonb), now()) "
                    "RETURNING driving_id"
                ), params).scalar()
        except IntegrityError:
            dup = [{"field": "date", "rule": "duplicate_date", "message": "같은 차량의 같은 날짜 기록이 이미 있습니다"}]
            return JSONResponse(status_code=409, content={"warnings": dup})
    return {"driving_id": new_id, "warnings": warnings}
