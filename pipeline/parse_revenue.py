"""Parse revenue and maintenance workbooks into one standard file per folder.

- Byte-identical files are read once (hash groups); the file correspondence table is written next to the output.
- Sheets that parse as driving-log sheets are skipped (they live in driving.csv).
- Reconciliation per sheet: source rows = loaded + blank + total + header + skipped_driving + quarantined.
Console output: counts and allow-listed words only. Values, coordinates, sheet names and other header text stay out.
"""
from __future__ import annotations

import sys
import warnings
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common import list_excel, load_config, path_from, raw_subdir, write_csv  # noqa: E402
from pipeline.parse_driving import parse_sheet as parse_driving_sheet  # noqa: E402
from pipeline.revenue_common import (  # noqa: E402
    KEY_COLS, STD_COLS, group_by_hash, match_ratio, parse_table_sheet, reconciled, safe_label, sheet_numbers,
    summary_rows,
)

warnings.filterwarnings("ignore")

RECON_COLS = ["source_folder", "source_file_no", "source_sheet_no", "file_hash", "status", "source_rows", "loaded",
              "excluded_blank", "excluded_total", "excluded_header", "skipped_driving", "summary_rows", "quarantined", "photos",
              "records", "merged_fill_cells", "reason", "balanced"]


def out_columns(kind: str) -> list[str]:
    return KEY_COLS + ["table_kind"] + STD_COLS[kind] + ["date_basis", "merged_fill", "extra"]


def picture_positions(path: Path) -> dict[int, list[tuple[int, int]]]:
    """Sheet ordinal -> list of (row, col) picture anchors. Positions only."""
    from openpyxl import load_workbook

    out: dict[int, list[tuple[int, int]]] = {}
    try:
        wb = load_workbook(path, read_only=False, data_only=True)
    except Exception:
        return out
    for sno, ws in enumerate(wb.worksheets, start=1):
        pos = []
        for im in getattr(ws, "_images", []):
            try:
                pos.append((im.anchor._from.row + 1, im.anchor._from.col + 1))
            except AttributeError:
                pos.append((0, 0))
        if pos:
            out[sno] = pos
    wb.close()
    return out


def merged_by_sheet(path: Path, n_sheets: int) -> dict[int, list[tuple[int, int, int, int]]]:
    """Sheet ordinal -> merged ranges (min_row, min_col, max_row, max_col), 1-based. Empty when the sheet count differs."""
    from openpyxl import load_workbook

    out: dict[int, list] = {}
    try:
        wb = load_workbook(path, read_only=False, data_only=True)
    except Exception:
        return out
    if len(wb.worksheets) == n_sheets:
        for sno, ws in enumerate(wb.worksheets, start=1):
            rngs = [(m.min_row, m.min_col, m.max_row, m.max_col) for m in ws.merged_cells.ranges]
            if rngs:
                out[sno] = rngs
    wb.close()
    return out


def parse_kind(folder: Path, kind: str, folder_name: str | None = None, with_pictures: bool = False):
    """Return dict with frame, recon, filemap, photos, stats."""
    folder_name = folder_name or kind
    files = list_excel(folder)
    hashes, canon = group_by_hash(files)
    rows_all, recon, photos = [], [], []
    stats = {"status": Counter(), "mapped": Counter(), "extra_keys": Counter(), "bad_cells": Counter(),
             "table_kind": Counter(), "day_only": Counter(), "files": len(files), "unique_files": len(set(canon)), "sheets_read": 0,
             "sheets_with_date": 0, "unreadable": Counter(), "merged_fill": 0, "merged_fill_sheets": 0,
             "matrix_sheets": 0, "matrix_records": 0, "matrix_labels": 0, "zero_dropped": 0, "summary_sheets": 0,
             "summary_rows": 0, "summary_checks": []}
    filemap = []
    for fno, f in enumerate(files, start=1):
        dup_of = canon[fno - 1] if canon[fno - 1] != fno else ""
        filemap.append({"folder": folder_name, "file_no": fno, "file_name": f.name, "file_hash": hashes[fno - 1],
                        "read_as_file_no": canon[fno - 1], "duplicate_of": dup_of})
        if dup_of:
            continue
        try:
            book = pd.read_excel(f, sheet_name=None, header=None, dtype=object)
        except Exception as e:  # message may carry values: class name only
            stats["unreadable"][type(e).__name__] += 1
            continue
        pics = picture_positions(f) if with_pictures else {}
        merges = merged_by_sheet(f, len(book))
        pending = []
        for sno, (sname, df) in enumerate(book.items(), start=1):
            stats["sheets_read"] += 1
            counts = Counter()
            try:
                drows, dcounts, dinfo = parse_driving_sheet(df, fno, sno) if kind == "revenue" else ([], None, {"status": "x"})
                if kind == "revenue" and dinfo["status"] == "ok":
                    counts["source"] = len(df)
                    counts["skipped_driving"] = len(df)
                    info = {"status": "skipped_driving", "mapped": [], "extra_keys": Counter(), "bad_cells": Counter(),
                            "has_date": False, "table_kind": ""}
                    rows = []
                else:
                    rows, counts, info = parse_table_sheet(kind, df, fno, sno, hashes[fno - 1], folder_name, str(sname), f.name,
                                                       merges.get(sno))
            except Exception as e:
                stats["status"]["sheet_error:" + type(e).__name__] += 1
                counts = Counter({"source": len(df), "quarantined": len(df)})
                rows, info = [], {"status": "sheet_error:" + type(e).__name__, "mapped": [], "extra_keys": Counter(),
                                  "bad_cells": Counter(), "has_date": False, "table_kind": ""}
            pending.append({"sno": sno, "df": df, "rows": rows, "counts": counts, "info": info})
        # summary check: a sheet without header whose numbers equal column sums of the normal sheets of the same file
        sums = [v for q in pending if q["info"]["status"] == "ok" for v in q["info"].get("sumcols", {}).values()]
        for q in pending:
            info = q["info"]
            reason = ""
            if info["status"] == "no_header":
                reason = "머리글 없음"
                raw = q["df"].values.tolist()
                matched, total = match_ratio(sheet_numbers(raw), sums)
                stats["summary_checks"].append((matched, total))
                if total >= 3 and matched / total >= 0.5:
                    q["rows"], q["counts"] = summary_rows(raw, fno, q["sno"], hashes[fno - 1], folder_name)
                    info.update({"status": "summary_duplicate", "table_kind": "summary"})
                    reason = "합계표(중복 정보)"
            counts, rows, sno = q["counts"], q["rows"], q["sno"]
            stats["status"][info["status"]] += 1
            stats["mapped"].update(info["mapped"])
            stats["extra_keys"].update(info["extra_keys"])
            stats["bad_cells"].update(info["bad_cells"])
            stats["day_only"].update(info.get("day_only", {}))
            stats["merged_fill"] += info.get("merged_fill", 0)
            stats["merged_fill_sheets"] += int(info.get("merged_fill", 0) > 0)
            if info["status"] == "matrix":
                stats["matrix_sheets"] += 1
                stats["matrix_records"] += info["records"]
                stats["matrix_labels"] += info["labels"]
                stats["zero_dropped"] += info["zero_dropped"]
            if info["status"] == "summary_duplicate":
                stats["summary_sheets"] += 1
                stats["summary_rows"] += counts["summary"]
            if info["table_kind"]:
                stats["table_kind"][info["table_kind"]] += 1
            stats["sheets_with_date"] += int(info["has_date"])
            for pos in pics.get(sno, []):
                photos.append({"source_folder": folder_name, "source_file_no": fno, "source_sheet_no": sno,
                               "row": pos[0], "col": pos[1]})
            rows_all.extend(rows)
            recon.append({"source_folder": folder_name, "source_file_no": fno, "source_sheet_no": sno,
                          "file_hash": hashes[fno - 1], "status": info["status"], "source_rows": counts["source"],
                          "loaded": counts["loaded"], "excluded_blank": counts["blank"],
                          "excluded_total": counts["total"], "excluded_header": counts["header"],
                          "skipped_driving": counts["skipped_driving"], "summary_rows": counts["summary"],
                          "quarantined": counts["quarantined"], "photos": len(pics.get(sno, [])),
                          "records": info.get("records", 0), "merged_fill_cells": info.get("merged_fill", 0),
                          "reason": reason, "balanced": reconciled(counts)})
    cols = out_columns(kind)
    frame = pd.DataFrame(rows_all)
    for c in cols:
        if c not in frame.columns:
            frame[c] = None
    frame = frame[cols]
    return {"frame": frame, "recon": pd.DataFrame(recon, columns=RECON_COLS), "filemap": pd.DataFrame(filemap),
            "photos": pd.DataFrame(photos, columns=["source_folder", "source_file_no", "source_sheet_no", "row", "col"]),
            "stats": stats}


def report_lines(kind: str, res: dict) -> list[str]:
    st, rc, fr = res["stats"], res["recon"], res["frame"]
    tot = {k: int(rc[k].sum()) for k in ("source_rows", "loaded", "excluded_blank", "excluded_total", "excluded_header",
                                          "skipped_driving", "summary_rows", "quarantined")}
    chk = st["summary_checks"]
    deciles = Counter(min(int(10 * m / t), 9) if t else -1 for m, t in chk)
    lines = [f"[{kind}] files: {st['files']}  read once: {st['unique_files']}  sheets read: {st['sheets_read']}"
             f"  unreadable files: {dict(st['unreadable']) if st['unreadable'] else 'none'}",
             f"[{kind}] sheet status: {dict(st['status'])}",
             f"[{kind}] rows: {tot}",
             f"[{kind}] unbalanced sheets: {int((~rc['balanced']).sum()) if len(rc) else 0}",
             f"[{kind}] sheets with a date column: {st['sheets_with_date']}",
             f"[{kind}] mapped standard columns (sheets): {dict(st['mapped'])}",
             f"[{kind}] non-parsable cells moved to extra (by standard column): {dict(st['bad_cells']) if st['bad_cells'] else 'none'}",
             f"[{kind}] day-only dates completed with year-month from (source, cells): {dict(st['day_only']) if st['day_only'] else 'none'}",
             f"[{kind}] extra header labels (label, cells): {st['extra_keys'].most_common(25)}",
             f"[{kind}] merged-cell fill: cells {st['merged_fill']} in {st['merged_fill_sheets']} sheets",
             f"[{kind}] matrix sheets: {st['matrix_sheets']}  labels: {st['matrix_labels']}  records: {st['matrix_records']}"
             f"  zero cells dropped: {st['zero_dropped']}",
             f"[{kind}] summary candidates (sheets without header): {len(chk)}  confirmed: {st['summary_sheets']}"
             f"  matched numbers: {sum(m for m, t in chk)} of {sum(t for m, t in chk)}"
             f"  ratio-decile histogram (-1 = no numbers): {dict(sorted(deciles.items()))}",
             f"[{kind}] photos recorded: {len(res['photos'])}"]
    return lines


def main() -> int:
    cfg = load_config()
    out = path_from(cfg, "parsed_dir")
    code = 0
    for kind in ("revenue", "maintenance"):
        folder = raw_subdir(cfg, kind)
        if folder is None:
            print(f"{kind} folder: not found (check pipeline/config.toml)")
            code = 1
            continue
        res = parse_kind(folder, kind, with_pictures=(kind == "maintenance"))
        write_csv(res["frame"], out / f"{kind}.csv")
        write_csv(res["recon"], out / f"{kind}_reconciliation.csv")
        write_csv(res["filemap"], out / f"{kind}_file_map.csv")
        if kind == "maintenance":
            write_csv(res["photos"], out / "maintenance_photos.csv")
        for line in report_lines(kind, res):
            print(line)
        print(f"[{kind}] output rows: {len(res['frame'])}  output columns: {list(res['frame'].columns)}")
    return code


def safe_main() -> int:
    try:
        return main()
    except Exception as e:  # exception text can carry cell values
        print("failed, exception class:", type(e).__name__)
        return 1


if __name__ == "__main__":
    sys.exit(safe_main())
