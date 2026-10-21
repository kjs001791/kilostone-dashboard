import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline import make_dummy_revenue as md  # noqa: E402
from pipeline import parse_revenue as pr  # noqa: E402
from pipeline.revenue_common import map_std, safe_label  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "revenue_dummy"


@pytest.fixture(scope="module")
def fixtures():
    md.make(FIX)
    return FIX


@pytest.fixture(scope="module")
def rev(fixtures):
    return pr.parse_kind(fixtures / "revenue", "revenue")


@pytest.fixture(scope="module")
def mnt(fixtures):
    return pr.parse_kind(fixtures / "maintenance", "maintenance", with_pictures=True)


def test_reconciliation_has_no_mismatch(rev, mnt):
    assert rev["recon"]["balanced"].all()
    assert mnt["recon"]["balanced"].all()
    r = rev["recon"]
    assert (r["source_rows"] == r[["loaded", "excluded_blank", "excluded_total", "excluded_header", "skipped_driving", "summary_rows",
                                   "excluded_footer", "quarantined"]].sum(axis=1)).all()


def test_expected_row_classes(rev):
    r = rev["recon"]
    s1 = r[(r.source_file_no == 1) & (r.source_sheet_no == 1)].iloc[0]
    for k, col in (("loaded", "loaded"), ("blank", "excluded_blank"), ("total", "excluded_total"), ("header", "excluded_header")):
        assert s1[col] == md.TRUTH["A_sheet1"][k]
    s2 = r[(r.source_file_no == 1) & (r.source_sheet_no == 2)].iloc[0]
    for k, col in (("loaded", "loaded"), ("blank", "excluded_blank"), ("total", "excluded_total"), ("header", "excluded_header")):
        assert s2[col] == md.TRUTH["A_sheet2"][k]


def test_identical_file_read_once(rev):
    fm = rev["filemap"]
    assert rev["stats"]["files"] == 4 and rev["stats"]["unique_files"] == 3
    assert fm.loc[fm.file_no == 2, "duplicate_of"].iloc[0] == 1
    assert 2 not in set(rev["recon"]["source_file_no"])
    assert 2 not in set(rev["frame"]["source_file_no"])


def test_driving_sheet_skipped_and_unknown_quarantined(rev):
    r = rev["recon"]
    d = r[(r.source_file_no == 3) & (r.source_sheet_no == 1)].iloc[0]
    assert d["status"] == "skipped_driving" and d["skipped_driving"] == d["source_rows"] and d["loaded"] == 0
    q = r[(r.source_file_no == 3) & (r.source_sheet_no == 2)].iloc[0]
    assert q["status"] == "no_header" and q["quarantined"] == q["source_rows"]
    assert 3 not in set(rev["frame"]["source_file_no"])


def test_extra_keeps_unmapped_columns(rev):
    f = rev["frame"]
    s1 = f[(f.source_file_no == 1) & (f.source_sheet_no == 1)]
    assert len(s1) == 6
    ex = [json.loads(x) for x in s1["extra"]]
    assert all(md.OTHER_HEADER in e for e in ex)
    assert ex[0][md.OTHER_HEADER] == "ZZMEMO0"
    assert s1["amount"].notna().all() and s1["date"].notna().all() and s1["client"].notna().all()
    s2 = f[(f.source_file_no == 1) & (f.source_sheet_no == 2)]
    ex2 = [json.loads(x) for x in s2["extra"]]
    keys = set().union(*[set(e) for e in ex2])
    assert f"{md.CLIENTS[0]}_수량" in keys and f"{md.CLIENTS[1]}_금액" in keys
    assert s2["amount"].isna().all()  # client-specific columns are not forced into the standard amount


def test_maintenance_photo_position_and_count(mnt):
    assert len(mnt["photos"]) == 1
    assert mnt["recon"]["photos"].sum() == 1
    assert mnt["frame"]["cost"].notna().sum() == 3
    assert mnt["recon"]["balanced"].all()


def test_safe_label_only_allow_list():
    assert safe_label("금액") == "금액"
    assert safe_label("금액(원)") == "금액"
    assert safe_label(md.CLIENTS[0]) == f"<other:{len(md.CLIENTS[0])}chars>"
    assert safe_label("ZZCLIENT_ALPHA 금액").startswith("<other:")
    assert map_std("revenue", "공급가액") == "supply_amount"


def test_console_has_no_outside_text(fixtures, capsys, monkeypatch):
    for kind, sub in (("revenue", "revenue"), ("maintenance", "maintenance")):
        res = pr.parse_kind(fixtures / sub, kind, with_pictures=(kind == "maintenance"))
        for line in pr.report_lines(kind, res):
            print(line)
    out = capsys.readouterr().out
    assert out
    for s in md.SECRET_STRINGS:
        assert s not in out
    assert "<other:" in out


def test_day_only_dates_use_year_month_context_and_are_flagged():
    import pandas as pd
    from pipeline.revenue_common import parse_table_sheet

    rows = [["2021년 3월 ZZTITLE", None, None], ["일자", "거래처", "금액"], ["5일", "ZZCLIENT_ALPHA", 100],
            ["월계", None, 100], ["6일", "ZZCLIENT_BETA", 50]]
    out, counts, info = parse_table_sheet("revenue", pd.DataFrame(rows, dtype=object), 1, 1, "h", "revenue", "ZZSHEET", "x.xlsx")
    assert [r["date"] for r in out] == ["2021-03-05", "2021-03-06"]
    assert {r["date_basis"] for r in out} == {"day_only+preamble"}
    assert counts["total"] == 1 and counts["loaded"] == 2
    assert "#raw" in out[0]["extra"]


def _sheet(rev, sno):
    r = rev["recon"]
    return r[(r.source_file_no == 4) & (r.source_sheet_no == sno)].iloc[0]


def test_merged_date_is_filled_and_marked(rev):
    f = rev["frame"]
    s1 = f[(f.source_file_no == 4) & (f.source_sheet_no == 1)].sort_values("source_row_no")
    assert list(s1["date"].iloc[:3]) == [s1["date"].iloc[0]] * 3 and s1["date"].notna().all()
    assert list(s1["merged_fill"].iloc[:3]) == ["", "date", "date"]
    assert _sheet(rev, 1)["merged_fill_cells"] == 2


def test_horizontal_sheet_is_unpivoted(rev):
    r = _sheet(rev, 2)
    assert r["status"] == "matrix" and r["balanced"]
    f = rev["frame"]
    m = f[(f.source_file_no == 4) & (f.source_sheet_no == 2)]
    assert (m["table_kind"] == "matrix").all() and m["date"].notna().all()
    ex = [json.loads(x) for x in m["extra"]]
    assert {e["header"] for e in ex} >= set(md.CLIENTS)
    assert len(m) == r["records"]
    assert not any(e["value"] == 0 and e["outside_label"] for e in ex)  # zeros outside labels are dropped
    cont = [e for e, row in zip(ex, m.itertuples()) if row.source_row_no == 5]
    assert cont and m[m.source_row_no == 5]["date"].iloc[0] == m[m.source_row_no == 4]["date"].iloc[0]  # carried down


def test_summary_sheet_confirmed_only_when_numbers_match(rev):
    s = _sheet(rev, 3)
    assert s["status"] == "summary_duplicate" and s["reason"] == "합계표(중복 정보)"
    assert s["summary_rows"] == 4 and s["quarantined"] == 0 and s["balanced"]
    f = rev["frame"]
    assert (f[(f.source_file_no == 4) & (f.source_sheet_no == 3)]["table_kind"] == "summary").all()
    u = _sheet(rev, 4)
    assert u["status"] == "no_header" and u["reason"] == "머리글 없음" and u["quarantined"] == u["source_rows"]


def test_wide_sheet_tail_lines_price_rows_and_rowsum(rev):
    r = _sheet(rev, 5)
    assert r["status"] == "matrix" and r["balanced"]
    assert r["excluded_footer"] == 9 and r["excluded_total"] == 1
    f = rev["frame"]
    m = f[(f.source_file_no == 4) & (f.source_sheet_no == 5)]
    # (a) no date-level record from the total row or tail lines
    assert (m["source_row_no"] < 82).all()
    # (c) the row-sum column makes no record, and its cells agree with the client cells
    ex = [json.loads(x) for x in m["extra"]]
    assert all(e["col"] != 8 for e in ex)
    st = rev["stats"]
    assert st["rowsum_checked"] == 77 and st["rowsum_mismatch"] == 0 and st["footer_unknown"] == 0
    # (d) client and kilograms are standard columns
    cl = m[m["client"].notna()]
    assert set(cl["client"]) == set(md.MX_CLIENTS)
    assert cl["weight_kg"].notna().all()
    for rec, e in zip(m.itertuples(), ex):
        if e["outside_label"]:
            assert rec.client is None or rec.client != rec.client
            assert rec.weight_kg != rec.weight_kg  # NaN
        else:
            assert rec.client == e["header"] and rec.weight_kg == e["value"]
    assert m["date"].notna().all()
    # (b) price rows: clients x 3 blocks
    p = rev["price"]
    p = p[(p.source_file_no == 4) & (p.source_sheet_no == 5)]
    assert len(p) == 6 * 3
    assert set(p["price_basis"]) == {"company", "invoice", "diff"}
    for i, name in enumerate(md.MX_CLIENTS):
        assert p[(p.client == name) & (p.price_basis == "company")]["unit_price"].iloc[0] == md.MX_PRICE_COMPANY[i]
        assert p[(p.client == name) & (p.price_basis == "invoice")]["unit_price"].iloc[0] == md.MX_PRICE_INVOICE[i]
    assert set(p["year_month"]) == {"2020-01"}
    assert p[p.price_basis == "diff"]["total_amount"].notna().all()
    assert json.loads(p[p.price_basis == "diff"]["source_row_nos"].iloc[0]) == [94]


def test_console_prints_no_tail_text(fixtures, capsys):
    res = pr.parse_kind(fixtures / "revenue", "revenue")
    for line in pr.report_lines("revenue", res):
        print(line)
    out = capsys.readouterr().out
    assert "row-sum check" in out and "ZZMX" not in out


def test_line_item_header_stays_on_table_path():
    """A header that maps line-item words (quantity, unit price, supply amount, VAT) is a table, even when its
    other labels and dated rows would also pass the horizontal test. Only a corner cell and a row-sum column
    send a sheet to the horizontal parser first."""
    import pandas as pd

    from pipeline.revenue_common import parse_table_sheet

    head = ["거래처", "가나상사", "다라물산", "수량", "단가", "공급가액", "부가세"]
    body = [[pd.Timestamp(2020, 1, d), 1000 + d, 2000 + d, 3, 10, 30, 3] for d in range(1, 11)]
    df = pd.DataFrame([head] + body, dtype=object)
    rows, counts, info = parse_table_sheet("revenue", df, 1, 1, "h", "revenue")
    assert info["status"] == "ok"
    assert info["table_kind"] != "matrix"
    assert {"quantity", "unit_price", "supply_amount", "vat"} <= set(info["mapped"])


def _old_wide_sheet(total_label, price_names):
    """2015-2019 horizontal layout: trips under one date share it, a price block lists one client per line."""
    import datetime as dt

    import pandas as pd
    n = None
    rows = [["김 성 훈", n, n, n, n], [n] * 5, ["㈜대신산업   (3월분)", n, n, n, n],
            ["날짜 거래처", "쌍용(P/C)", "쌍용(S/C)", "한남시멘트", n]]
    days = [(2, 25000, n, 24000), (3, n, 30000, n), (4, 26000, n, n), (5, 25500, n, n)]
    for d, a, b, c in days:
        rows.append([dt.datetime(2016, 3, d), a, b, c, n])
    rows.append([n, 26500, n, n, n])  # second trip on the 5th
    rows.append([total_label, 103.0, 30.0, 24.0, n])
    rows.append([n] * 5)
    rows.append([n, "단  가", "수  량", "공급가액", "세  액"])
    for name, price, qty in zip(price_names, (5000, 6000, 7000), (103.0, 30.0, 24.0)):
        rows.append([name, price, qty, price * qty, price * qty * 0.1])
    rows.append([n, n, 157.0, 1063000.0, 106300.0])
    rows.append(["합계금액", 1169300.0, n, n, n])
    rows.append(["차액", 1000, n, n, n])
    rows.append(["3월 25일 입금", 1169300.0, n, n, n])
    return pd.DataFrame(rows, dtype=object)


@pytest.mark.parametrize("total_label, names", [
    ("합  계", ["쌍용(P/C)", "쌍용(S/C)", "한남시멘트"]),
    (None, ["쌍용벌크운반비", "쌍용슬래그운반비", "한남시멘트운반비"]),  # no total label, names differ from the header
])
def test_old_wide_sheet_price_block_per_client(total_label, names):
    from pipeline.revenue_common import parse_table_sheet, reconciled
    df = _old_wide_sheet(total_label, names)
    rows, counts, info = parse_table_sheet("revenue", df, 1, 1, "h", "revenue")
    assert info["status"] == "matrix"  # short sheet: the price header sits inside the header scan window
    assert reconciled(counts)
    w = [r["weight_kg"] for r in rows if r["weight_kg"] is not None]
    assert sorted(w) == sorted([25000, 24000, 30000, 26000, 25500, 26500])  # no total, price or amount as weight
    assert all(r["date"] for r in rows)
    assert [r["date"] for r in rows if r["weight_kg"] == 26500] == ["2016-03-05"]
    assert info["unlabeled_total"] == (0 if total_label else 1)
    got = {p["client"]: (p["price_basis"], p["unit_price"], p["supply_amount"]) for p in info["price_rows"]}
    assert got == {"쌍용(P/C)": ("company", 5000, 515000), "쌍용(S/C)": ("company", 6000, 180000),
                   "한남시멘트": ("company", 7000, 168000)}
    assert {p["year_month"] for p in info["price_rows"]} == {"2016-03"}
    assert info["price_unmatched"] == 0


def test_deposit_lines_under_the_price_block_are_not_trips():
    """2020s layout: bank deposit lines sit under 차이 금액 with the amount in a client column."""
    import datetime as dt

    import pandas as pd
    from pipeline.revenue_common import parse_table_sheet, reconciled
    n = None
    rows = [["9월분 (주)대신산업 거래내역", n, n, n], ["거래처  날 짜", "창원쌍용 (P/C)", "광양쌍용 (P/C)", "동아C&C대신"]]
    for d in range(1, 6):
        rows.append([dt.datetime(2023, 2, d), 25000, n, 24000])
    rows.append(["합    계", 125.0, 0.0, 120.0])
    rows.append(["단가(회사인정)", 5000, 5000, 6000])
    rows.append(["공 급 가 액", 625000, 0, 720000])
    rows.append(["차이 금액", 0, 0, 0])
    rows.append([n, dt.datetime(2023, 3, 10), "대체", 1500000])  # deposit: date, kind, amount in the 동아 column
    rows.append([n, n, n, 3000000])  # SUM of deposits
    rows.append([n, n, "미수금", 0])
    df = pd.DataFrame(rows, dtype=object)
    out, counts, info = parse_table_sheet("revenue", df, 1, 1, "h", "revenue")
    assert info["status"] == "matrix"
    assert reconciled(counts)
    assert sorted(r["weight_kg"] for r in out if r["weight_kg"] is not None) == [24000] * 5 + [25000] * 5
    assert all(r["source_row_no"] <= 7 for r in out)
