"""Which copy is newer: revenue-only workbooks versus the shared (driving+revenue) workbooks.

Reads data/parsed/revenue.csv (written by parse_revenue.py) and hashes both raw folders.
Rows are matched on table kind + date (+ client, origin, destination, item, vehicle when present).
Prints and stores counts only: no dates, no values, no names.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common import list_excel, load_config, path_from, raw_subdir, write_csv  # noqa: E402
from pipeline.revenue_common import file_hash  # noqa: E402

KEY_TEXT = ["client", "origin", "destination", "item", "vehicle"]
VAL_COLS = ["quantity", "weight_ton", "trips", "unit_price", "amount", "supply_amount", "vat", "total_amount", "note"]
NUM_COLS = VAL_COLS[:-1]


def correspondence(cfg) -> pd.DataFrame:
    rows = []
    for kind in ("driving", "revenue", "maintenance"):
        folder = raw_subdir(cfg, kind)
        if folder is None:
            continue
        for no, f in enumerate(list_excel(folder), start=1):
            rows.append({"folder": kind, "file_no": no, "file_name": f.name, "file_hash": file_hash(f)})
    return pd.DataFrame(rows)


def compare(rev: pd.DataFrame, only_hashes: set, shared_hashes: set) -> dict:
    rev = rev[rev["date"].notna()].copy()
    a = rev[rev["file_hash"].isin(only_hashes)].copy()
    b = rev[rev["file_hash"].isin(shared_hashes)].copy()
    out = {"rows_with_date_only_side": int(len(a)), "rows_with_date_shared_side": int(len(b))}
    kinds_a, kinds_b = set(a["table_kind"]), set(b["table_kind"])
    out["table_kinds_only_side"], out["table_kinds_shared_side"] = len(kinds_a), len(kinds_b)
    out["table_kinds_in_both"] = len(kinds_a & kinds_b)
    for df in (a, b):
        for c in KEY_TEXT:
            df[c] = df[c].fillna("").astype(str)
    key = ["table_kind", "date"] + KEY_TEXT
    ga, gb = a.groupby(key, sort=False), b.groupby(key, sort=False)
    ka, kb = set(ga.groups), set(gb.groups)
    both = ka & kb
    out.update({"keys_only_side": len(ka), "keys_shared_side": len(kb), "keys_in_both": len(both),
                "dates_in_both": len({(k[0], k[1]) for k in both})})
    cells = {"same": 0, "different": 0, "one_side_empty": 0, "both_empty": 0}
    multi = {"sum_same": 0, "sum_different": 0}
    n_single = n_multi = 0
    ia, ib = ga.indices, gb.indices
    for k in both:
        ra, rb = a.iloc[ia[k]], b.iloc[ib[k]]
        if len(ra) == 1 and len(rb) == 1:
            n_single += 1
            for c in VAL_COLS:
                x, y = ra[c].iloc[0], rb[c].iloc[0]
                xe, ye = pd.isna(x) or x == "", pd.isna(y) or y == ""
                if xe and ye:
                    cells["both_empty"] += 1
                elif xe or ye:
                    cells["one_side_empty"] += 1
                elif x == y:
                    cells["same"] += 1
                else:
                    cells["different"] += 1
        else:
            n_multi += 1
            same = all(round(float(ra[c].sum()), 6) == round(float(rb[c].sum()), 6) for c in NUM_COLS)
            multi["sum_same" if same else "sum_different"] += 1
    out.update({"keys_compared_cellwise": n_single, "keys_with_several_rows": n_multi, "cells": cells, "multi_row_keys": multi})
    gaps = {}
    for k in sorted(kinds_a & kinds_b):
        da = pd.to_datetime(a.loc[a["table_kind"] == k, "date"]).max()
        db = pd.to_datetime(b.loc[b["table_kind"] == k, "date"]).max()
        gaps[k] = int((da - db).days)
    out["last_date_gap_days_by_table_kind(only_side minus shared_side)"] = gaps
    if len(a) and len(b):
        out["last_date_gap_days_overall"] = int((pd.to_datetime(a["date"]).max() - pd.to_datetime(b["date"]).max()).days)
    out["only_side_dates_not_in_shared"] = int(len(set(a["date"]) - set(b["date"])))
    out["only_side_dates_after_shared_last"] = int((pd.to_datetime(pd.Series(sorted(set(a["date"]))))
                                                    > pd.to_datetime(b["date"]).max()).sum()) if len(b) else 0
    return out


def compare_matrix(rev: pd.DataFrame, only_hashes: set, shared_hashes: set) -> dict:
    """Matrix (horizontal) rows: key = date + original header, value = sum of the cell values. Counts only."""
    m = rev[(rev["table_kind"] == "matrix") & rev["date"].notna()].copy()
    ex = m["extra"].map(json.loads)
    m["h"] = ex.map(lambda e: e.get("header", ""))
    m["v"] = pd.to_numeric(ex.map(lambda e: e.get("value")), errors="coerce")
    m = m[m["v"].notna()]
    g = {}
    for label, hs in (("a", only_hashes), ("b", shared_hashes)):
        g[label] = m[m["file_hash"].isin(hs)].groupby(["date", "h"])["v"].sum().round(6)
    both = g["a"].index.intersection(g["b"].index)
    same = int((g["a"].loc[both] == g["b"].loc[both]).sum())
    last = {k: pd.to_datetime(v.index.get_level_values("date")).max() for k, v in g.items() if len(v)}
    return {"matrix_keys_only_side": int(len(g["a"])), "matrix_keys_shared_side": int(len(g["b"])),
            "matrix_keys_in_both": int(len(both)), "matrix_values_same": same,
            "matrix_values_different": int(len(both)) - same,
            "matrix_dates_in_both": int(len(set(g["a"].index.get_level_values("date")) & set(g["b"].index.get_level_values("date")))),
            "matrix_last_date_gap_days": int((last["a"] - last["b"]).days) if len(last) == 2 else None}


def main() -> int:
    cfg = load_config()
    parsed = path_from(cfg, "parsed_dir")
    corr = correspondence(cfg)
    hv = {k: set(g["file_hash"]) for k, g in corr.groupby("folder")}
    only = hv.get("revenue", set()) - hv.get("driving", set())
    shared = hv.get("revenue", set()) & hv.get("driving", set())
    corr["in_driving"] = corr["file_hash"].isin(hv.get("driving", set()))
    corr["in_revenue"] = corr["file_hash"].isin(hv.get("revenue", set()))
    write_csv(corr, parsed / "file_correspondence.csv")
    rev = pd.read_csv(parsed / "revenue.csv", encoding="utf-8-sig", dtype={"file_hash": str})
    res = {"driving_files": int((corr.folder == "driving").sum()), "revenue_files": int((corr.folder == "revenue").sum()),
           "driving_files_with_identical_revenue_file": int(((corr.folder == "driving") & corr.in_revenue).sum()),
           "driving_files_without_revenue_copy": int(((corr.folder == "driving") & ~corr.in_revenue).sum()),
           "revenue_only_files": len(only), "shared_files": len(shared)}
    res.update(compare(rev, only, shared))
    res.update(compare_matrix(rev, only, shared))
    rc = pd.read_csv(parsed / "revenue_reconciliation.csv", encoding="utf-8-sig", dtype={"file_hash": str})
    for label, hs in (("only_side", only), ("shared_side", shared)):
        sub = rc[rc["file_hash"].isin(hs)]
        res[f"sheets_{label}_by_status"] = {k: int(v) for k, v in sub["status"].value_counts().items()}
        res[f"rows_{label}"] = {c: int(sub[c].sum()) for c in ("source_rows", "loaded", "quarantined", "skipped_driving")}
    p = path_from(cfg, "profile_dir") / "revenue_latest_compare.json"
    p.write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


def safe_main() -> int:
    try:
        return main()
    except Exception as e:
        print("failed, exception class:", type(e).__name__)
        return 1


if __name__ == "__main__":
    sys.exit(safe_main())
