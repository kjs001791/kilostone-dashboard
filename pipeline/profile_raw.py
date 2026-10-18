"""Structure profile of the three raw folders. Output holds structure only.

driving      : header-row texts (column names), column types, decimals statistics, layout counts
revenue,
maintenance  : sheet ordinal, used range, merged ranges, picture anchors, column type grid. No sheet names, no cell text.
File names are replaced by ordinals. Console output is counts only.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import sys
import warnings
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common import (  # noqa: E402
    NUMERIC_COLS, decimals_hist, infer_decimals, is_empty, list_excel, load_config, path_from, raw_subdir, safe_label, write_text,
)
from pipeline.parse_driving import build_header, find_header, map_columns, parse_sheet, vehicle_from_structure  # noqa: E402

warnings.filterwarnings("ignore")


def cell_type(v) -> str:
    if v is None or (isinstance(v, str) and not v.strip()):
        return "B"
    if isinstance(v, bool):
        return "O"
    if isinstance(v, (int, float)):
        return "N"
    if isinstance(v, (dt.datetime, dt.date, dt.time)):
        return "D"
    return "S"


def profile_driving(folder: Path) -> dict:
    files = list_excel(folder)
    per_vehicle = defaultdict(lambda: {"files": set(), "sheets": 0, "header_levels": Counter(), "matched": Counter(),
                                       "unmatched": Counter(), "dec": defaultdict(list), "rows": 0, "date_min": None, "date_max": None})
    problems = Counter()
    for fno, f in enumerate(files, start=1):
        try:
            book = pd.read_excel(f, sheet_name=None, header=None, dtype=object)
        except Exception as e:
            problems["unreadable:" + type(e).__name__] += 1
            continue
        for sno, (_, df) in enumerate(book.items(), start=1):
            hr, dc = find_header(df)
            if hr is None:
                problems["no_date_header"] += 1
                continue
            hdr = build_header(df, hr, dc)
            if hdr is None:
                problems["no_data_row"] += 1
                continue
            colmap, unmatched, _ = map_columns(hdr)
            rows, counts, info = parse_sheet(df, fno, sno)
            v = info["vehicle"] or "Unknown"
            pv = per_vehicle[v]
            pv["files"].add(fno)
            pv["sheets"] += 1
            pv["header_levels"][hdr["levels"]] += 1
            for k in info["matched"]:
                pv["matched"][k] += 1
            for u in unmatched:
                pv["unmatched"][safe_label(u)] += 1
            pv["rows"] += counts["loaded"]
            for r in rows:
                for c in NUMERIC_COLS:
                    x = r.get(c)
                    if x is not None and not (isinstance(x, float) and np.isnan(x)):
                        pv["dec"][c].append(x)
                d = r.get("date")
                if d is not None:
                    pv["date_min"] = d if pv["date_min"] is None or d < pv["date_min"] else pv["date_min"]
                    pv["date_max"] = d if pv["date_max"] is None or d > pv["date_max"] else pv["date_max"]
    out = {"files": len(files), "problems": dict(problems), "vehicles": {}}
    for v, pv in per_vehicle.items():
        dec = {}
        for c, vals in pv["dec"].items():
            dec[c] = {"n": len(vals), "hist": decimals_hist(vals), "inferred_decimals": infer_decimals(vals)}
        tol = None
        if "cumulative_distance" in dec and "distance" in dec:
            tol = 10.0 ** -dec["cumulative_distance"]["inferred_decimals"] + 10.0 ** -dec["distance"]["inferred_decimals"]
        out["vehicles"][v] = {
            "files": len(pv["files"]), "sheets": pv["sheets"], "rows_loaded": pv["rows"],
            "header_levels": dict(pv["header_levels"]), "matched_columns": dict(pv["matched"]),
            "unmatched_header_texts": dict(pv["unmatched"].most_common(40)), "decimals": dec,
            "tolerance_C_plus_D": tol,
            "years_present": sorted({} if pv["date_min"] is None else range(pv["date_min"].year, pv["date_max"].year + 1)),
        }
    return out


def profile_workbooks(folder: Path, max_grid_rows: int = 30, max_cols: int = 40) -> dict:
    from openpyxl import load_workbook

    files = list_excel(folder)
    out = {"files": len(files), "problems": {}, "file_list": []}
    problems = Counter()
    for fno, f in enumerate(files, start=1):
        rec = {"file": fno, "sheets": []}
        try:
            wb = load_workbook(f, data_only=True)
        except Exception as e:
            problems["unreadable:" + type(e).__name__] += 1
            out["file_list"].append(rec)
            continue
        for sno, ws in enumerate(wb.worksheets, start=1):
            s = {"sheet": sno, "max_row": ws.max_row, "max_col": ws.max_column,
                 "merged_ranges": sorted(str(r) for r in ws.merged_cells.ranges)[:40], "n_merged": len(ws.merged_cells.ranges)}
            try:
                s["pictures"] = [{"row": im.anchor._from.row + 1, "col": im.anchor._from.col + 1} for im in ws._images][:20]
            except Exception:
                s["pictures"] = "unreadable"
            ncol = min(ws.max_column or 0, max_cols)
            col_types = [Counter() for _ in range(ncol)]
            col_dec = [Counter() for _ in range(ncol)]
            grid = []
            for r, row in enumerate(ws.iter_rows(min_row=1, max_row=min(ws.max_row or 0, 3000), max_col=ncol, values_only=True), start=1):
                types = "".join(cell_type(v) for v in row)
                if r <= max_grid_rows:
                    grid.append(types)
                for c, v in enumerate(row):
                    col_types[c][cell_type(v)] += 1
                    if isinstance(v, (int, float)) and not isinstance(v, bool):
                        col_dec[c][min(3, len(str(round(float(v), 4)).split(".")[1].rstrip("0")) if "." in str(round(float(v), 4)) else 0)] += 1
            rle, prev, k = [], None, 0
            for g in grid:
                if g == prev:
                    k += 1
                else:
                    if prev is not None:
                        rle.append([prev, k])
                    prev, k = g, 1
            if prev is not None:
                rle.append([prev, k])
            s["type_grid_first_rows_rle"] = rle
            s["column_types"] = [dict(c) for c in col_types]
            s["numeric_decimals_by_column"] = [{str(k): v for k, v in c.items()} for c in col_dec]
            rec["sheets"].append(s)
        out["file_list"].append(rec)
        wb.close()
    out["problems"] = dict(problems)
    out["n_sheets"] = sum(len(r["sheets"]) for r in out["file_list"])
    return out


def main(argv) -> int:
    cfg = load_config()
    prof = {}
    use_dummy = "--dummy" in argv
    if use_dummy:
        d = path_from(cfg, "fixtures_dir") / "xlsx_dummy"
        prof["driving"] = profile_driving(d)
        outp = Path(argv[argv.index("--dummy") + 1]) if len(argv) > argv.index("--dummy") + 1 else path_from(cfg, "profile_dir") / "dummy_profile.json"
    else:
        outp = path_from(cfg, "profile_dir") / "raw_profile.json"
        for kind in ("driving", "revenue", "maintenance"):
            folder = raw_subdir(cfg, kind)
            if folder is None:
                prof[kind] = {"folder": "not found"}
                print(f"{kind}: folder not found")
                continue
            prof[kind] = profile_driving(folder) if kind == "driving" else profile_workbooks(folder)
    write_text(outp, json.dumps(prof, ensure_ascii=False, indent=1, default=str))
    for kind, p in prof.items():
        if "files" in p:
            print(f"{kind}: files {p['files']}  problems {p.get('problems')}", end="")
            if kind == "driving":
                print("  vehicles", {v: (x["files"], x["sheets"], x["rows_loaded"]) for v, x in p["vehicles"].items()})
            else:
                print(f"  sheets {p.get('n_sheets')}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:
        print("failed, exception class:", type(e).__name__)
        sys.exit(1)
