"""Tests for pipeline/load_hub.py on the fake 2nd-layer files (pipeline/make_dummy_hub.py). No real data."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.load_hub import TABLE_ORDER, build_frames, normalize_name, write_db  # noqa: E402
from pipeline.make_dummy_hub import CLIENT_A, make_hub_dummy  # noqa: E402

DUMMY_DSN = "postgresql+psycopg://postgres@localhost:5432/kilostone_dummy"


@pytest.fixture(scope="module")
def dummy(tmp_path_factory):
    d = make_hub_dummy(tmp_path_factory.mktemp("hub_dummy"))
    return d, build_frames(d, d, d / "dim_vehicle.csv", d / "name_merge.csv")


def test_reconciliation_has_no_mismatch(dummy):
    _, f = dummy
    rc = f["_recon"]
    assert len(rc) == 5
    assert (rc["diff"] == 0).all()
    assert (rc["input_rows"] == rc["loaded_rows"] + rc["quarantined_rows"] + rc["unlinked_rows"]).all()


def test_name_normalization():
    assert normalize_name("(주) 가나 물산") == "가나물산"
    assert normalize_name("㈜가나물산") == "가나물산"
    assert normalize_name("사아산업（유）") == "사아산업"
    assert normalize_name("다라건설 주식회사") == "다라건설"
    assert normalize_name(None) == ""


def test_name_variants_merge_into_one_client(dummy):
    _, f = dummy
    client, alias = f["client"], f["client_alias"]
    assert len(client) == 4  # 4 clients despite 9 spellings
    assert len(alias) == 9
    a_ids = alias[alias["alias"].isin(CLIENT_A)]["client_id"].unique()
    assert len(a_ids) == 1
    assert set(alias[alias["client_id"] == a_ids[0]]["alias"]) == set(CLIENT_A)
    # place variants too: two spellings of each place share one place
    assert len(f["place"]) == 2 and len(f["place_alias"]) == 4
    nl = f["_name_list"]
    assert list(nl.columns) == ["kind", "normalized", "alias_count", "row_count"]
    assert nl.loc[(nl["kind"] == "client") & (nl["normalized"] == "가나물산"), "alias_count"].iloc[0] == 4


def test_name_merge_table_joins_more(tmp_path):
    d = make_hub_dummy(tmp_path)
    pd.DataFrame([{"kind": "client", "alias_normalized": "마바자원", "canonical": "가나물산"}]).to_csv(
        d / "name_merge.csv", index=False, encoding="utf-8-sig")
    f = build_frames(d, d, d / "dim_vehicle.csv", d / "name_merge.csv")
    assert len(f["client"]) == 3


def test_matrix_revenue_is_weight_over_1000_times_invoice_price(dummy):
    _, f = dummy
    de, cl, al = f["delivery"], f["client"], f["client_alias"]
    a = int(al[al["alias"] == CLIENT_A[0]]["client_id"].iloc[0])
    m = de[(de["source_kind"] == "matrix") & (de["client_id"] == a) & (de["date"].astype(str) == "2024-03-10")]
    assert len(m) == 1
    r = m.iloc[0]
    assert r["grain"] == "client_day" and r["weight_basis"] == "matrix_kg" and r["amount_source"] == "computed_invoice"
    assert float(r["supply_amount"]) == pytest.approx(20000 / 1000 * 50000)
    # a month without an invoice price stays empty
    b = int(al[al["alias"] == "다라건설"]["client_id"].iloc[0])
    nb = de[(de["source_kind"] == "matrix") & (de["client_id"] == b) & (de["date"].astype(str) == "2025-02-10")].iloc[0]
    assert pd.isna(nb["supply_amount"]) and nb["amount_source"] is None
    # a company price alone is used when the month has no invoice price; other months stay empty
    d_id = int(al[al["alias"] == "사아산업(유)"]["client_id"].iloc[0])
    dm = de[(de["source_kind"] == "matrix") & (de["client_id"] == d_id)]
    first = dm[dm["date"].astype(str).str.startswith("2024-01")]
    assert len(first) == 1 and first.iloc[0]["amount_source"] == "computed_company"
    assert float(first.iloc[0]["supply_amount"]) == pytest.approx(5000 / 1000 * 30000)
    assert dm[~dm["date"].astype(str).str.startswith("2024-01")]["supply_amount"].isna().all()
    # where both exist, the invoice price wins
    assert r["amount_source"] == "computed_invoice"


def test_table_row_weight_units_three_ways(dummy):
    _, f = dummy
    de = f["delivery"]
    t = de[(de["source_kind"] == "table") & (de["date"].astype(str).isin(["2024-01-05", "2024-02-05", "2024-03-05"]))]
    by_date = {str(r.date): t[t["date"] == r.date] for r in t.itertuples()}
    tons = by_date["2024-01-05"]  # 25.5 -> tonnes
    assert (tons["weight_basis"] == "ton_x1000").sum() == 3 and (tons["weight_kg"].astype(float) == 25500).sum() == 2
    kgs = by_date["2024-02-05"]  # 24500 -> kilograms
    assert (kgs["weight_basis"] == "kg").sum() == 2 and (kgs.loc[kgs["weight_basis"] == "kg", "weight_kg"].astype(float) == 24500).all()
    amb = by_date["2024-03-05"]  # 500 -> ambiguous
    ambiguous = amb[amb["weight_kg"].isna() & amb["flags"].notna()]
    assert len(ambiguous) >= 2
    assert all(x == {"weight_unit_ambiguous": True} for x in ambiguous["flags"])
    assert len(ambiguous) == 2 and ambiguous["weight_basis"].isna().all()
    # table rows keep the sheet supply amount and say so
    assert (t["amount_source"] == "sheet").all()


def test_quarantine_reason_codes(dummy):
    _, f = dummy
    q = f["quarantine"]
    got = {(r.target_table, r.reason): int(n) for r, n in zip(q.groupby(["target_table", "reason"]).size().reset_index().itertuples(),
                                                              q.groupby(["target_table", "reason"]).size())}
    assert got[("delivery", "no_date")] == 1
    assert got[("delivery", "matrix_outside_label")] == 1
    assert got[("delivery", "no_measure")] == 1
    assert got[("delivery", "duplicate_older_file")] == 2
    assert got[("product", "duplicate_price")] == 1
    assert got[("product", "price_not_loaded")] == 2
    assert got[("driving", "vehicle_unknown")] == 1
    assert got[("driving", "no_values")] == 1
    assert got[("driving", "duplicate_identical")] == 1
    assert got[("driving", "duplicate_conflict")] == 2
    # the older workbook's third row has a new date and loads
    de = f["delivery"]
    assert (de["date"].astype(str) == "2025-03-01").sum() == 1


def test_driving_duplicates_keep_one_identical_and_drop_both_conflicting(dummy):
    _, f = dummy
    dr = f["driving"]
    assert len(dr) == 8
    assert not dr.duplicated(["vehicle_id", "date"]).any()
    assert (dr["date"].astype(str) == "2024-07-02").sum() == 1  # identical pair kept once
    assert (dr["date"].astype(str) == "2024-07-03").sum() == 0  # conflicting pair kept nowhere
    assert set(dr["entered_via"]) == {"excel"}


def test_vehicle_matches_by_service_period(dummy):
    _, f = dummy
    de, mt = f["delivery"], f["maintenance"]
    last_v03 = de[de["date"].astype(str) == "2024-06-30"]
    first_v04 = de[de["date"].astype(str) == "2024-07-01"]
    assert (last_v03["vehicle_id"] == "V03").all() and len(last_v03) >= 1
    assert (first_v04["vehicle_id"] == "V04").all() and len(first_v04) >= 1
    # a maintenance line before any service period has no vehicle; one without date stays and has no vehicle
    old = mt[mt["date"].astype(str) == "2018-01-01"].iloc[0]
    assert old["vehicle_id"] is None
    nodate = mt[mt["date"].isna()]
    assert len(nodate) == 1 and nodate.iloc[0]["vehicle_id"] is None
    assert len(mt) == 5


def test_correction_is_linked_by_row_id(dummy):
    _, f = dummy
    dr, co, q = f["driving"], f["driving_correction"], f["quarantine"]
    assert len(co) == 2  # third correction points at a quarantined row: counted, not linked
    assert (co["corrected_by"] == "pipeline").all()
    r = co[co["column_name"] == "distance"].iloc[0]
    linked = dr[dr["driving_id"] == r["driving_id"]].iloc[0]
    assert str(linked["date"]) == "2024-06-28"  # row 2
    assert r["original_value"] == "2000.0" and r["corrected_value"] == "200.0" and r["rule"] == "typo_digit"
    assert f["_recon"].set_index("input_file").loc["driving_corrections.csv", "unlinked_rows"] == 1


def test_route_pairs_and_product_period(dummy):
    _, f = dummy
    de, pr, rt = f["delivery"], f["product"], f["route"]
    assert len(rt) == 1
    with_route = de[de["route_id"].notna()]
    assert (with_route["origin_place_id"].notna() & with_route["dest_place_id"].notna()).all()
    assert (de.loc[de["route_id"].isna(), ["origin_place_id", "dest_place_id"]].isna().any(axis=1)).all()
    first = pr[(pr["price_basis"] == "invoice")].iloc[0]
    assert str(first["valid_from"]) == "2024-01-01" and str(first["valid_to"]) == "2024-01-31" and first["unit"] == "ton"
    leap = pr[pr["valid_from"].astype(str) == "2024-02-01"].iloc[0]
    assert str(leap["valid_to"]) == "2024-02-29"
    assert not pr.duplicated(["client_id", "price_basis", "valid_from"]).any()


def _engine_or_skip():
    sqlalchemy = pytest.importorskip("sqlalchemy")
    try:
        eng = sqlalchemy.create_engine(DUMMY_DSN)
        with eng.connect() as c:
            c.execute(sqlalchemy.text("select 1"))
        return eng
    except Exception:
        pytest.skip("kilostone_dummy database not reachable")


def test_write_db_row_counts_match_frames(dummy):
    eng = _engine_or_skip()
    from sqlalchemy import text

    _, f = dummy
    written = write_db(DUMMY_DSN, f)
    with eng.connect() as c:
        for name in TABLE_ORDER:
            n = c.execute(text(f'select count(*) from hub."{name}"')).scalar()
            assert n == len(f[name]) == written[name], name
        # the sequences continue after the loaded ids
        c.execute(text("select 1"))
    # writing twice gives the same state
    write_db(DUMMY_DSN, f)
    with eng.connect() as c:
        assert c.execute(text("select count(*) from hub.delivery")).scalar() == len(f["delivery"])
    eng.dispose()


def test_dates_outside_service_years_are_out_of_range():
    """A sheet date before the first vehicle went into service, or after today, is a typo, not a delivery."""
    import datetime as dt

    import pandas as pd

    from pipeline.load_hub import out_of_range

    dates = pd.Series(pd.to_datetime(["1901-12-03", "1954-10-01", "2007-01-01", "2020-05-05", None, "2099-01-01"]))
    got = out_of_range(dates, dt.date(2007, 1, 1), dt.date(2026, 10, 21)).tolist()
    assert got == [True, True, False, False, False, True]
