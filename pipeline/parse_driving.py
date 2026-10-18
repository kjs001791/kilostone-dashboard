"""Parse driving-log workbooks (MAN, Daewoo Prima, Scania layouts) into one standard table.

Reconciliation per sheet: source rows = loaded + excluded_blank + excluded_total + excluded_text + quarantined.
Console output: counts and column names only. Values, coordinates and sheet names stay out of it.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
import tomllib
import warnings
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common import (  # noqa: E402
    NUMERIC_COLS, ROOT, STD_COLUMNS, clean_header, is_empty, list_excel, load_config, looks_total, map_header,
    parse_date, parse_number, parse_time_hours, path_from, raw_subdir, safe_label, write_csv,
)

warnings.filterwarnings("ignore")

# Known model words -> normalised model key. Plain "대우" alone is not a model word: a newer Daewoo model must not be taken for Prima.
# Korean words are matched on the title with whitespace removed, latin words on the lower-cased title with word boundaries.
MODEL_WORDS = [
    (re.compile(r"스카니아|scania"), "Scania"),
    (re.compile(r"대우프리마|daewoo?prima|프리마"), "Daewoo"),
    (re.compile(r"(?<![a-z])man(?![a-z])|tgx"), "MAN"),
]
DRIVING_WORD = "운행"  # a title holding this word marks the sheet as a driving log
VEHICLES_PATH = ROOT / "pipeline" / "vehicles.toml"
SCAN_ROWS = 40


def find_header(df: pd.DataFrame):
    """Return (row index, date column index) of the first row holding a date label."""
    for r in range(min(SCAN_ROWS, len(df))):
        row = df.iloc[r].tolist()
        for c, v in enumerate(row):
            if isinstance(v, str) and clean_header(v) in ("날짜", "일자"):
                return r, c
    for r in range(min(SCAN_ROWS, len(df))):
        row = df.iloc[r].tolist()
        for c, v in enumerate(row):
            if isinstance(v, str) and map_header(v) == "date":
                return r, c
    return None, None


def n_filled(row) -> int:
    return sum(1 for v in row if not is_empty(v))


def build_header(df: pd.DataFrame, hr: int, dc: int):
    """Header block = up to two filled rows above the date row, the date row, rows between it and the first data row."""
    data_start = None
    for r in range(hr + 1, min(hr + 9, len(df))):
        if parse_date(df.iat[r, dc])[1] == "ok":
            data_start = r
            break
    if data_start is None:
        return None
    above = []
    r = hr - 1
    while r >= 0 and r >= hr - 4 and len(above) < 2:
        row = df.iloc[r].tolist()
        if n_filled(row) == 0:
            r -= 1
            continue
        if n_filled(row) >= 2 and sum(isinstance(v, str) for v in row if not is_empty(v)) >= 2:
            above.insert(0, r)
            r -= 1
        else:
            break
    block = above + list(range(hr, data_start))
    ncol = df.shape[1]
    levels = []
    for i, r in enumerate(block):
        vals = [("" if is_empty(v) else str(v).strip()) for v in df.iloc[r].tolist()]
        if i < len(block) - 1:  # merged upper levels: fill to the right
            last = ""
            for c in range(ncol):
                if vals[c]:
                    last = vals[c]
                elif last:
                    vals[c] = last
        levels.append(vals)
    combined, last_level = [], []
    for c in range(ncol):
        parts = []
        for lv in levels:
            if lv[c] and (not parts or parts[-1] != lv[c]):
                parts.append(lv[c])
        combined.append("_".join(parts))
        last_level.append(levels[-1][c])
    return {"data_start": data_start, "combined": combined, "last": last_level, "levels": len(block)}


def map_columns(hdr: dict):
    """Return (colmap, unmatched, dup, extra_cols). extra_cols = [(column index, original header)] for headers that map to no standard column
    or to one already taken; their values are kept in the `extra` field."""
    colmap, unmatched, dup, extra_cols = {}, [], 0, []
    for c, (comb, last) in enumerate(zip(hdr["combined"], hdr["last"])):
        if not comb:
            continue
        std = map_header(last) if last else None
        if std is None:
            std = map_header(comb)
        if std is None:
            unmatched.append(comb)
            extra_cols.append((c, comb))
        elif std in colmap:
            dup += 1
            extra_cols.append((c, comb))
        else:
            colmap[std] = c
    return colmap, unmatched, dup, extra_cols


def vehicle_from_structure(colmap: dict):
    if any(k in colmap for k in ("fuel_rate_per_hour", "consumed_fuel_idle", "consumed_fuel_pto", "time_idle", "time_pto")):
        return "Scania"
    if "cumulative_distance" in colmap:
        return "Daewoo"
    if "speed" in colmap or "time" in colmap:
        return "MAN"
    return None


def model_key_of(text: str) -> str:
    """Normalised model key found in a text, or '' when no known model word is there."""
    low = str(text).lower()
    flat = re.sub(r"\s+", "", low)
    for rx, key in MODEL_WORDS:
        if rx.search(flat) or rx.search(low):
            return key
    return ""


def find_title(df: pd.DataFrame, hr: int):
    """First text cell above the header row that holds a known model word or the word 운행. Returns the cell text or ''."""
    for r in range(min(hr, 15)):
        for v in df.iloc[r].tolist():
            if isinstance(v, str) and v.strip() and (DRIVING_WORD in v or model_key_of(v)):
                return v.strip()[:200]
    return ""


def header_text_model(df: pd.DataFrame, upto: int) -> str:
    text = " ".join(str(v) for v in df.iloc[:max(upto, 1)].values.ravel() if not is_empty(v))
    return model_key_of(text)


def title_hash(title: str) -> str:
    return "unk-" + hashlib.sha1(re.sub(r"\s+", "", title.lower()).encode("utf-8")).hexdigest()[:6]


def _jsonable(v):
    if hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, float) and v == int(v):
        return int(v)
    return v if isinstance(v, (int, float, str, bool)) else str(v)


def parse_sheet(df: pd.DataFrame, file_no: int, sheet_no: int):
    """Return (rows, counts, info). counts keys: source, loaded, blank, total, text, quarantined.

    The vehicle is read from the sheet title first (known model word, else a hash of the title text). The shape of the columns is only
    a fallback when there is no title, and rows that used it are counted (vehicle_source = structure).
    A sheet is a driving log when it has a date column with dates below it, at least one measurement column, and evidence:
    the title holds the word for driving or a known model word, or a daily-distance column exists. Unknown columns are kept in `extra`.
    """
    info = {"status": "ok", "vehicle": None, "vehicle_source": None, "vehicle_text_mismatch": False, "admit": "",
            "model_key": "", "unmatched": [], "dup_headers": 0, "bad_cells": Counter(), "matched": []}
    counts = Counter()
    hr, dc = find_header(df)
    if hr is None:
        info["status"] = "no_date_header"
        counts["source"] = len(df)
        counts["quarantined"] = len(df)
        return [], counts, info
    hdr = build_header(df, hr, dc)
    if hdr is None:
        info["status"] = "no_data_row"
        counts["source"] = len(df) - hr - 1
        counts["quarantined"] = counts["source"]
        return [], counts, info
    colmap, unmatched, dup, extra_cols = map_columns(hdr)
    info["unmatched"], info["dup_headers"], info["matched"] = unmatched, dup, sorted(colmap)
    colmap["date"] = dc
    title = find_title(df, hr)
    title_key = model_key_of(title) if title else ""
    text_key = "" if title_key else header_text_model(df, hdr["data_start"])
    guess = vehicle_from_structure(colmap)
    if title:
        key = title_key or title_hash(title)
        src = "title" if title_key else "title_unknown_model"
        model_key = title_key
    elif text_key:
        key, src, model_key = text_key, "header_text", text_key
    elif guess:
        key, src, model_key = guess, "structure", ""
    else:
        key, src, model_key = "Unknown", "none", ""
    info["vehicle"], info["vehicle_source"], info["model_key"] = key, src, model_key
    info["vehicle_text_mismatch"] = bool(model_key and guess and model_key != guess)
    has_measure = any(k in colmap for k in NUMERIC_COLS + ["time", "time_idle", "time_pto"])
    evidence = bool(title) or bool(text_key) or "distance" in colmap
    old_admit = guess is not None and "distance" in colmap  # the first rounds' rule: one of three known layouts with a daily distance
    if not (has_measure and evidence):
        info["status"] = "unknown_layout"  # no measurement column or nothing that says this is a driving log: quarantine the whole sheet
        counts["source"] = len(df) - hdr["data_start"]
        counts["quarantined"] = counts["source"]
        return [], counts, info
    info["admit"] = "known_layout" if old_admit else ("relaxed_distance_col" if "distance" in colmap else "relaxed_title")

    rows = []
    start = hdr["data_start"]
    counts["source"] = len(df) - start
    for r in range(start, len(df)):
        row = df.iloc[r].tolist()
        if n_filled(row) == 0:
            counts["blank"] += 1
            continue
        if looks_total(row[: min(len(row), dc + 2)]):
            counts["total"] += 1
            continue
        d, dk = parse_date(row[dc])
        rec = {"source_file": file_no, "source_sheet_no": sheet_no, "source_row_no": r + 1, "vehicle": key, "vehicle_title": title,
               "vehicle_model_key": model_key, "vehicle_id": "", "vehicle_source": src}
        any_num = False
        for std in NUMERIC_COLS:
            if std in colmap:
                v, k = parse_number(row[colmap[std]])
                rec[std] = v
                if k == "ok":
                    any_num = True
                elif k == "text":
                    info["bad_cells"][std] += 1
        for std, out in (("time", "time_h"), ("time_idle", "time_idle_h"), ("time_pto", "time_pto_h")):
            if std in colmap:
                v, k = parse_time_hours(row[colmap[std]])
                rec[out] = v
                if k == "ok":
                    any_num = True
                elif k == "text":
                    info["bad_cells"][std] += 1
        ex = {}
        for c, name in extra_cols:
            v = row[c] if c < len(row) else None
            if not is_empty(v):
                ex[name if name not in ex else f"{name}#{c}"] = _jsonable(v)
        rec["extra"] = json.dumps(ex, ensure_ascii=False) if ex else ""
        if dk == "ok":
            rec["date"] = d
            rec["has_values"] = any_num
            rows.append(rec)
            counts["loaded"] += 1
        elif any_num:
            counts["quarantined"] += 1
            info.setdefault("quarantine_reasons", Counter())["date_unparsed"] += 1
        else:
            counts["text"] += 1
    return rows, counts, info


def parse_folder(folder: Path):
    files = list_excel(folder)
    all_rows, recon, quarantine_files = [], [], Counter()
    unmatched_all, bad_all, vehicle_src, mismatch = Counter(), Counter(), Counter(), 0
    n_sheets = n_parsed = 0
    for fno, f in enumerate(files, start=1):
        try:
            book = pd.read_excel(f, sheet_name=None, header=None, dtype=object)
        except Exception as e:  # message may contain values: keep class name only
            quarantine_files[type(e).__name__] += 1
            recon.append({"file_no": fno, "file_name": f.name, "sheet_no": 0, "status": "file_unreadable:" + type(e).__name__,
                          "vehicle": "", "vehicle_source": "", "admit": "", "source_rows": 0, "loaded": 0, "excluded_blank": 0, "excluded_total": 0,
                          "excluded_text": 0, "quarantined": 0, "balanced": True})
            continue
        for sno, (_, df) in enumerate(book.items(), start=1):
            n_sheets += 1
            try:
                rows, counts, info = parse_sheet(df, fno, sno)
            except Exception as e:
                quarantine_files["sheet_error:" + type(e).__name__] += 1
                recon.append({"file_no": fno, "file_name": f.name, "sheet_no": sno, "status": "sheet_error:" + type(e).__name__,
                              "vehicle": "", "vehicle_source": "", "admit": "", "source_rows": len(df), "loaded": 0, "excluded_blank": 0,
                              "excluded_total": 0, "excluded_text": 0, "quarantined": len(df), "balanced": True})
                continue
            if info["status"] == "ok":
                n_parsed += 1
            else:
                quarantine_files[info["status"]] += 1
            all_rows.extend(rows)
            if info["status"] == "ok":
                for u in info["unmatched"]:
                    unmatched_all[safe_label(u)] += 1
            bad_all.update(info["bad_cells"])
            vehicle_src[(info["vehicle"], info["vehicle_source"])] += 1
            mismatch += int(info["vehicle_text_mismatch"])
            bal = counts["source"] == counts["loaded"] + counts["blank"] + counts["total"] + counts["text"] + counts["quarantined"]
            recon.append({"file_no": fno, "file_name": f.name, "sheet_no": sno, "status": info["status"],
                          "vehicle": info["vehicle"] or "", "vehicle_source": info["vehicle_source"] or "", "admit": info["admit"],
                          "source_rows": counts["source"], "loaded": counts["loaded"],
                          "excluded_blank": counts["blank"], "excluded_total": counts["total"],
                          "excluded_text": counts["text"], "quarantined": counts["quarantined"], "balanced": bal})
    return files, all_rows, recon, quarantine_files, unmatched_all, bad_all, vehicle_src, mismatch, n_sheets, n_parsed


# ---------------------------------------------------------------- vehicle table (pipeline/vehicles.toml)
def load_vehicle_table(path: Path = VEHICLES_PATH) -> list:
    """Filled entries of vehicles.toml. An entry counts when vehicle_id (a meaningless number such as V01) is filled."""
    if not Path(path).exists():
        return []
    with open(path, "rb") as f:
        raw = tomllib.load(f).get("vehicle", [])
    out = []
    for e in raw:
        vid = str(e.get("vehicle_id", "")).strip()
        if not vid:
            continue
        brand = str(e.get("brand", "")).strip()
        words = [re.sub(r"\s+", "", str(w).lower()) for w in e.get("title_words", []) if str(w).strip()]
        out.append({"id": vid, "brand": brand, "brand_key": (model_key_of(brand) if brand else "") or re.sub(r"\s+", "", brand.lower()),
                    "model": str(e.get("model", "")).strip(), "year": str(e.get("model_year", "")).strip(), "words": words,
                    "start": pd.Timestamp(e["service_start"]) if str(e.get("service_start", "")).strip() else None,
                    "end": pd.Timestamp(e["service_end"]) if str(e.get("service_end", "")).strip() else None})
    return out


def assign_vehicle_ids(df: pd.DataFrame, table: list):
    """Set vehicle_id (and `vehicle`, the grouping key) on rows that match exactly one table entry by brand (or title word) and by service dates.

    Brand = the brand key found in the title, a title word of the entry, or the entry's brand text inside the title. Two cars of one brand are
    told apart by their service dates. Returns (frame, counts) with counts = assigned / ambiguous / unmatched rows.
    """
    counts = Counter()
    if not table or df.empty:
        counts["unmatched"] = len(df)
        return df, counts
    ids = []
    for t, mk, d in zip(df["vehicle_title"].fillna(""), df["vehicle_model_key"].fillna(""), pd.to_datetime(df["date"])):
        flat = re.sub(r"\s+", "", str(t).lower())
        hits = []
        for e in table:
            by_name = (any(w in flat for w in e["words"]) or (mk and mk.lower() == e["brand_key"].lower())
                       or (e["brand_key"] and e["brand_key"].lower() in flat))
            in_range = (e["start"] is None or d >= e["start"]) and (e["end"] is None or d <= e["end"])
            if by_name and in_range:
                hits.append(e["id"])
        hits = sorted(set(hits))
        if len(hits) == 1:
            ids.append(hits[0])
            counts["assigned"] += 1
        else:
            ids.append("")
            counts["ambiguous" if hits else "unmatched"] += 1
    df = df.copy()
    df["vehicle_id"] = ids
    has = df["vehicle_id"] != ""
    df.loc[has, "vehicle"] = df.loc[has, "vehicle_id"]
    return df, counts


MIN_PERIOD_ROWS = 20  # a stretch shorter than this is a stray row, not a period of its own
PERIOD_GAP_DAYS = 30


def split_periods(df: pd.DataFrame):
    """Provisional split of one brand key into periods (Scania-1, Scania-2) while vehicles.toml is empty.

    A break is made where one key's rows stop for more than PERIOD_GAP_DAYS and other keys have rows inside the gap (another car ran meanwhile).
    A break is kept only when both sides hold at least MIN_PERIOD_ROWS rows. Rows that already have a vehicle_id are left alone.
    Returns (frame, info) with info = {key: periods} for keys that were split.
    """
    df = df.copy()
    df["vehicle_period"] = 1
    info = {}
    free = df["vehicle_id"].fillna("") == ""
    dates = pd.to_datetime(df["date"])
    for key in sorted(df.loc[free, "vehicle"].unique()):
        sel = df.index[free & (df["vehicle"] == key)]
        order = sel[np.argsort(dates.loc[sel].to_numpy(), kind="stable")]
        dd = dates.loc[order].to_numpy()
        other = np.sort(dates.loc[df["vehicle"] != key].to_numpy())
        cuts = []  # positions i where a new period starts at order[i]
        for i in range(1, len(order)):
            if (dd[i] - dd[i - 1]) / np.timedelta64(1, "D") > PERIOD_GAP_DAYS:
                if np.searchsorted(other, dd[i], "left") - np.searchsorted(other, dd[i - 1], "right") >= 1:
                    cuts.append(i)
        while cuts:
            bounds = [0] + cuts + [len(order)]
            sizes = [bounds[j + 1] - bounds[j] for j in range(len(bounds) - 1)]
            j = int(np.argmin(sizes))
            if sizes[j] >= MIN_PERIOD_ROWS:
                break
            # drop the break that joins the small stretch to its larger neighbour
            if j == 0:
                cuts.pop(0)
            elif j == len(sizes) - 1:
                cuts.pop(-1)
            else:
                cuts.pop(j if sizes[j + 1] >= sizes[j - 1] else j - 1)
        if cuts:
            period = np.ones(len(order), int)
            for c in cuts:
                period[c:] += 1
            df.loc[order, "vehicle_period"] = period
            df.loc[order, "vehicle"] = [f"{key}-{n}" for n in period]
            info[key] = len(cuts) + 1
    return df, info


PARSE_EXTRA_COLUMNS = ["vehicle_title", "vehicle_model_key", "vehicle_id", "vehicle_period", "vehicle_source", "extra"]


def to_frame(rows: list, vehicle_table: list | None = None, split: bool = False) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    cols = STD_COLUMNS + PARSE_EXTRA_COLUMNS + ["has_values"]
    if df.empty:
        return pd.DataFrame(columns=cols)
    for c in cols:
        if c not in df.columns:
            df[c] = None
    if vehicle_table:
        df, _ = assign_vehicle_ids(df, vehicle_table)
    if split:
        df, _ = split_periods(df)
    else:
        df["vehicle_period"] = 1
    df = df.sort_values(["vehicle", "date", "source_file", "source_sheet_no", "source_row_no"], kind="stable").reset_index(drop=True)
    df["row_id"] = range(1, len(df) + 1)
    return df[cols]


def main() -> int:
    cfg = load_config()
    folder = raw_subdir(cfg, "driving")
    if folder is None:
        print("driving folder: not found (check pipeline/config.toml)")
        return 1
    (files, rows, recon, qf, unmatched, bad, vsrc, mism, n_sheets, n_parsed) = parse_folder(folder)
    table = load_vehicle_table()
    df = to_frame(rows, table, split=True)
    out = path_from(cfg, "parsed_dir")
    write_csv(df, out / "driving.csv")
    rc = pd.DataFrame(recon)
    write_csv(rc, out / "driving_reconciliation.csv")
    print(f"files: {len(files)}  sheets: {n_sheets}  parsed sheets: {n_parsed}")
    print("sheet/file problems by kind:", dict(qf) if qf else "none")
    if len(rc):
        tot = {k: int(rc[k].sum()) for k in ("source_rows", "loaded", "excluded_blank", "excluded_total", "excluded_text", "quarantined")}
        print("rows:", tot)
        print("unbalanced sheets:", int((~rc["balanced"]).sum()))
        ok = rc[rc["status"] == "ok"]
        print("loaded rows by admit reason:", {k: int(g["loaded"].sum()) for k, g in ok.groupby("admit")}, " sheets:", ok["admit"].value_counts().to_dict())
    print("rows by vehicle:", df["vehicle"].value_counts().to_dict() if len(df) else {})
    print("rows by vehicle source:", df["vehicle_source"].value_counts().to_dict() if len(df) else {})
    print("keys split into periods:", {k: int(g["vehicle_period"].max()) for k, g in df.groupby(df["vehicle"].str.replace(r"-\d+$", "", regex=True)) if g["vehicle_period"].max() > 1})
    print("vehicle table entries in use:", len(table), " rows with vehicle_id:", int((df["vehicle_id"].fillna("") != "").sum()) if len(df) else 0)
    print("sheets by (vehicle, source):", {f"{k[0]}/{k[1]}": v for k, v in vsrc.items()})
    print("title model key vs structure guess disagreements (sheets):", mism)
    print("rows with extra columns kept:", int((df["extra"].fillna("") != "").sum()) if len(df) else 0)
    print("non-numeric cell counts by column:", dict(bad) if bad else "none")
    top = [(k, v) for k, v in unmatched.most_common(30)]
    print("unmatched header labels (label, sheets):", top if top else "none")
    if len(df):
        for c in NUMERIC_COLS + ["time_h"]:
            if c in df.columns:
                print(f"  {c}: non-null {int(df[c].notna().sum())}")
        yrs = pd.to_datetime(df["date"]).dt.year
        print("rows by year:", yrs.value_counts().sort_index().to_dict())
    return 0


def safe_main() -> int:
    try:
        return main()
    except Exception as e:  # exception text can carry cell values
        print("failed, exception class:", type(e).__name__)
        return 1


if __name__ == "__main__":
    sys.exit(safe_main())
