"""허브 API 시험. 검사 규칙은 DB 없이, 경로는 kilostone_dummy 에 접속될 때만 돈다."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api import hub_checks as hc  # noqa: E402

DUMMY_DSN = "postgresql+psycopg://postgres@localhost:5432/kilostone_dummy"


# ---------- 검사 규칙 5개, DB 없이 ----------

def test_cumulative_decrease():
    assert hc.check_cumulative_decrease(900, 1000)["rule"] == "cumulative_decrease"
    assert hc.check_cumulative_decrease(1000, 1000) is None
    assert hc.check_cumulative_decrease(1100, 1000) is None
    assert hc.check_cumulative_decrease(None, 1000) is None
    assert hc.check_cumulative_decrease(900, None) is None


def test_efficiency_mismatch():
    # distance/fuel = 5.0
    assert hc.check_efficiency_mismatch(6.0, 100, 20)["rule"] == "efficiency_mismatch"  # 20% 차이
    assert hc.check_efficiency_mismatch(5.5, 100, 20) is None  # 10% 차이
    assert hc.check_efficiency_mismatch(5.75, 100, 20) is None  # 정확히 15%
    assert hc.check_efficiency_mismatch(5.0, 100, 0) is None  # 연료 0 이면 검사 불가
    assert hc.check_efficiency_mismatch(None, 100, 20) is None


def test_idle_pto_over_time():
    assert hc.check_idle_pto_over_time(8, 5, 4)["rule"] == "idle_pto_over_time"
    assert hc.check_idle_pto_over_time(8, 5, 3) is None
    assert hc.check_idle_pto_over_time(8, 9, None)["rule"] == "idle_pto_over_time"
    assert hc.check_idle_pto_over_time(None, 5, 4) is None


def test_digit_jump():
    recent = [100, 110, 90, 105, 95]  # 중앙값 100
    assert hc.check_digit_jump("distance", 1000, recent)["rule"] == "digit_jump"
    assert hc.check_digit_jump("distance", 10, recent)["rule"] == "digit_jump"
    assert hc.check_digit_jump("distance", 150, recent) is None
    assert hc.check_digit_jump("distance", 999, recent) is None
    assert hc.check_digit_jump("distance", 1000, []) is None
    assert hc.check_digit_jump("distance", 1000, [None, 0]) is None
    assert hc.check_digit_jump("distance", None, recent) is None


def test_duplicate_date():
    assert hc.check_duplicate_date(True)["rule"] == "duplicate_date"
    assert hc.check_duplicate_date(False) is None


def test_run_checks_collects_fields():
    rec = {"distance": 1000, "consumed_fuel": 20, "cumulative_distance": 5, "time_h": 1, "time_idle_h": 2}
    rules = {(w["field"], w["rule"]) for w in hc.run_checks(rec, prev_cumulative=10, recent=[{"distance": 100, "consumed_fuel": 20}], duplicate=True)}
    assert rules == {
        ("cumulative_distance", "cumulative_decrease"),
        ("time_h", "idle_pto_over_time"),
        ("distance", "digit_jump"),
        ("date", "duplicate_date"),
    }
    assert hc.run_checks({"distance": 100, "consumed_fuel": 20}) == []


def test_main_registers_hub_routes():
    from api.main import app
    paths = {r.path for r in app.routes}
    for p in ("/hub/months", "/hub/summary", "/hub/vehicles", "/hub/driving", "/hub/driving/check"):
        assert p in paths


# ---------- DB 시험, kilostone_dummy 에 접속될 때만 ----------

@pytest.fixture(scope="module")
def pg():
    from sqlalchemy import create_engine, text
    engine = create_engine(DUMMY_DSN, connect_args={"connect_timeout": 3})
    try:
        with engine.connect() as c:
            has_schema = c.execute(text("SELECT 1 FROM information_schema.schemata WHERE schema_name = 'hub'")).first()
            has_col = c.execute(text(
                "SELECT 1 FROM information_schema.columns WHERE table_schema = 'hub' "
                "AND table_name = 'delivery' AND column_name = 'amount_source'"
            )).first()
    except Exception as e:  # 접속 불가(비밀번호 파일 없음 등)
        engine.dispose()
        pytest.skip(f"kilostone_dummy 접속 불가: {type(e).__name__}")
    if not has_schema:
        engine.dispose()
        pytest.skip("hub 스키마 없음")
    if not has_col:
        engine.dispose()
        pytest.skip("hub.delivery.amount_source 칸이 아직 없음")
    yield engine
    engine.dispose()


@pytest.fixture(scope="module")
def seeded(pg):
    """먼 미래 달(2098~2099)에 시험 행을 넣고 끝에 지운다."""
    from sqlalchemy import text
    ids = {"delivery": [], "client": []}
    with pg.begin() as c:
        for v, end in (("T_V1", None), ("T_V2", "2099-01-31")):
            c.execute(text("DELETE FROM hub.driving WHERE vehicle_id = :v"), {"v": v})
            c.execute(text("DELETE FROM hub.vehicle WHERE vehicle_id = :v"), {"v": v})
            c.execute(text("INSERT INTO hub.vehicle (vehicle_id, brand, color, service_start, service_end) "
                           "VALUES (:v, 'TestBrand', '흰색', '2098-01-01', :e)"), {"v": v, "e": end})
        a = c.execute(text("INSERT INTO hub.client (name) VALUES ('T_거래처A') RETURNING client_id")).scalar()
        b = c.execute(text("INSERT INTO hub.client (name) VALUES ('T_거래처B') RETURNING client_id")).scalar()
        ids["client"] = [a, b]
        rows = [
            ("2099-03-05", a, 1000, 100, "computed_invoice"),
            ("2099-03-06", b, 3000, 300, "computed_invoice"),
            ("2099-03-07", None, 500, 50, "computed_invoice"),
            ("2099-02-10", a, 2000, 200, "computed_invoice"),
            ("2098-03-10", a, 4000, 400, "computed_invoice"),
        ]
        for d, cid, kg, amt, src in rows:
            ids["delivery"].append(c.execute(text(
                "INSERT INTO hub.delivery (date, client_id, weight_kg, supply_amount, amount_source, vehicle_id, grain, source_kind) "
                "VALUES (:d, :c, :kg, :a, :s, 'T_V1', 'row', 'table') RETURNING delivery_id"
            ), {"d": d, "c": cid, "kg": kg, "a": amt, "s": src}).scalar())
        c.execute(text("INSERT INTO hub.driving (vehicle_id, date, distance, cumulative_distance, consumed_fuel, entered_via) "
                       "VALUES ('T_V1', '2099-03-01', 100, 1000, 20, 'excel')"))
    yield ids
    with pg.begin() as c:
        c.execute(text("DELETE FROM hub.delivery WHERE delivery_id = ANY(:i)"), {"i": ids["delivery"]})
        c.execute(text("DELETE FROM hub.driving WHERE vehicle_id IN ('T_V1', 'T_V2')"))
        c.execute(text("DELETE FROM hub.vehicle WHERE vehicle_id IN ('T_V1', 'T_V2')"))
        c.execute(text("DELETE FROM hub.client WHERE client_id = ANY(:i)"), {"i": ids["client"]})


@pytest.fixture()
def client(pg, seeded):
    from fastapi.testclient import TestClient
    from api.main import app
    from api.routers.hub import hub_engine
    app.dependency_overrides[hub_engine] = lambda: pg
    yield TestClient(app)
    app.dependency_overrides.pop(hub_engine, None)


def test_months(client):
    j = client.get("/hub/months").json()
    assert {"2099-03", "2099-02", "2098-03"} <= set(j["months"])
    assert j["months"] == sorted(j["months"], reverse=True)
    assert j["latest"] == j["months"][0]


def test_summary_comparisons_and_clients(client):
    j = client.get("/hub/summary", params={"month": "2099-03"}).json()
    assert j["month"] == "2099-03"
    assert j["revenue"] == {"this_month": 450, "prev_month": 200, "same_month_last_year": 400}
    assert j["weight_ton"] == {"this_month": 4.5, "prev_month": 2.0, "same_month_last_year": 4.0}
    assert j["revenue_has_computed"] is True
    names = [c["client_name"] for c in j["by_client"]]
    assert names == ["T_거래처B", "T_거래처A", "미지정"]
    assert j["by_client"][2]["client_id"] is None
    assert j["by_client"][0]["revenue"] == 300 and j["by_client"][0]["weight_ton"] == 3.0
    assert j["driving"]["days"] == 1 and j["driving"]["distance_km"] == 100
    assert j["driving"]["fuel_l"] == 20 and j["driving"]["avg_efficiency"] == 5.0


def test_summary_null_comparisons(client):
    j = client.get("/hub/summary", params={"month": "2099-02"}).json()
    assert j["revenue"] == {"this_month": 200, "prev_month": None, "same_month_last_year": None}
    assert j["weight_ton"]["prev_month"] is None
    j = client.get("/hub/summary", params={"month": "2097-01"}).json()
    assert j["revenue"]["this_month"] is None and j["by_client"] == []
    assert j["driving"]["avg_efficiency"] is None


def test_summary_bad_month(client):
    assert client.get("/hub/summary", params={"month": "2099-13"}).status_code == 422


def test_vehicles_current(client):
    rows = {r["vehicle_id"]: r for r in client.get("/hub/vehicles").json()}
    assert rows["T_V1"]["current"] is True and rows["T_V1"]["service_end"] is None
    assert rows["T_V2"]["current"] is False and rows["T_V2"]["service_end"] == "2099-01-31"
    assert rows["T_V1"]["brand"] == "TestBrand"


def _body(**kw):
    base = {"vehicle_id": "T_V1", "date": "2099-03-10", "distance": 100, "cumulative_distance": 1100,
            "consumed_fuel": 20, "fuel_efficiency": 5.0, "time_h": 8, "time_idle_h": 1, "time_pto_h": 1}
    base.update(kw)
    return base


def test_driving_post_flow(client, pg):
    from sqlalchemy import text
    # 경고 없음 -> 저장
    r = client.post("/hub/driving", json=_body())
    assert r.status_code == 200 and r.json()["warnings"] == [] and r.json()["driving_id"]
    with pg.connect() as c:
        row = c.execute(text("SELECT entered_via, flags, created_at_kst FROM hub.driving WHERE driving_id = :i"),
                        {"i": r.json()["driving_id"]}).one()
    assert row.entered_via == "app" and row.flags is None and row.created_at_kst is not None

    # 누적거리 감소 -> confirm false 면 409, 저장 안 됨
    bad = _body(date="2099-03-11", cumulative_distance=500)
    assert client.post("/hub/driving/check", json=bad).json()["warnings"][0]["rule"] == "cumulative_decrease"
    r = client.post("/hub/driving", json=bad)
    assert r.status_code == 409 and r.json()["warnings"][0]["rule"] == "cumulative_decrease"
    assert client.get("/hub/driving", params={"vehicle_id": "T_V1"}).json()[0]["date"] == "2099-03-10"

    # confirm true -> flags 에 담아 저장
    r = client.post("/hub/driving", json={**bad, "confirm": True})
    assert r.status_code == 200 and r.json()["warnings"][0]["rule"] == "cumulative_decrease"
    with pg.connect() as c:
        flags = c.execute(text("SELECT flags FROM hub.driving WHERE driving_id = :i"), {"i": r.json()["driving_id"]}).scalar()
    assert flags["cumulative_distance"][0]["rule"] == "cumulative_decrease"

    # 같은 날짜 -> confirm 이어도 409
    r = client.post("/hub/driving", json={**_body(), "confirm": True})
    assert r.status_code == 409 and any(w["rule"] == "duplicate_date" for w in r.json()["warnings"])

    # 목록은 최근 날짜 먼저, flags 와 entered_via 포함
    rows = client.get("/hub/driving", params={"vehicle_id": "T_V1", "limit": 2}).json()
    assert [x["date"] for x in rows] == ["2099-03-11", "2099-03-10"]
    assert rows[0]["entered_via"] == "app" and "flags" in rows[0]


def test_driving_post_unknown_vehicle(client):
    assert client.post("/hub/driving", json=_body(vehicle_id="NOPE")).status_code == 404
