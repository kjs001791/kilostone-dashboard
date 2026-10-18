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
                                   "quarantined"]].sum(axis=1)).all()


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
