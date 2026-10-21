"""Shared helpers for the revenue and maintenance parsers.

Console and report rule: counts and allow-listed business words only. A header or sheet text that is not on the
allow list may be a client name, so it is printed as <other:Nchars> and never as text.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

from pipeline.common import (
    clean_header, is_empty, looks_total, parse_date, parse_number,
)

# ---------------------------------------------------------------- allow list
# standard column -> business words (whitespace removed before matching). Order inside RULES = priority on ties.
REVENUE_RULES = [
    ("unit_price", ["단가", "운임단가"]),
    ("supply_amount", ["공급가액", "공급가"]),
    ("vat", ["부가세", "부가가치세", "세액"]),
    ("total_amount", ["합계금액", "합계", "총액"]),
    ("amount", ["금액", "운임", "매출액", "매출", "청구액", "운송료", "청구금액"]),
    ("weight_ton", ["톤수", "톤", "중량"]),
    ("quantity", ["수량", "물량"]),
    ("trips", ["운행횟수", "횟수", "회수", "건수"]),
    ("origin", ["상차지", "출발지", "상차"]),
    ("destination", ["하차지", "도착지", "하차", "납품처"]),
    ("client", ["거래처명", "거래처", "업체명", "업체", "상호"]),
    ("item", ["품목", "품명", "상품", "제품"]),
    ("vehicle", ["차량번호", "차량", "차번", "차종", "호차"]),
    ("date", ["날짜", "일자", "일시", "년월일"]),
    ("note", ["비고", "적요", "메모"]),
]
MAINTENANCE_RULES = [
    ("unit_price", ["단가"]),
    ("quantity", ["수량", "개수"]),
    ("odometer_km", ["주행거리", "누적거리", "키로수", "km"]),
    ("cost", ["수리비", "정비비", "부품비", "공임", "비용", "금액"]),
    ("shop", ["정비업체", "정비소", "공업사", "업체", "거래처"]),
    ("item", ["정비내용", "정비항목", "수리내용", "교체내용", "항목", "부품", "내용", "정비"]),
    ("vehicle", ["차량번호", "차량", "차번", "차종"]),
    ("date", ["날짜", "일자", "일시", "정비일"]),
    ("note", ["비고", "적요", "메모"]),
]
RULES = {"revenue": REVENUE_RULES, "maintenance": MAINTENANCE_RULES}
NUMERIC_STD = {"unit_price", "supply_amount", "vat", "total_amount", "amount", "weight_ton", "weight_kg", "quantity",
               "trips", "odometer_km", "cost"}
STD_COLS = {
    "revenue": ["date", "vehicle", "client", "origin", "destination", "item", "quantity", "weight_ton", "weight_kg", "trips",
                "unit_price", "amount", "supply_amount", "vat", "total_amount", "note"],
    "maintenance": ["date", "vehicle", "item", "shop", "quantity", "unit_price", "cost", "odometer_km", "note"],
}
KEY_COLS = ["source_folder", "source_file_no", "source_sheet_no", "source_row_no", "file_hash"]
MIN_HITS = {"revenue": 2, "maintenance": 1}
SCAN_ROWS = 40
FILL_STD = {"date", "client", "origin", "destination", "item", "vehicle"}
MAX_HEADER_EXTRA = 2
# standard words a horizontal sheet's header row can map: the corner cell and the row-sum column
MATRIX_HEADER_STD = {"client", "date", "shop", "total_amount"}

_BASE = {kind: {w for _, words in rules for w in words} for kind, rules in RULES.items()}
# footer words of horizontal sheets: printable, but kept out of REVENUE_RULES so that map_std is unchanged
FOOTER_WORDS = {"회사받은금액", "청구한금액", "차이금액", "회사인정", "발행단가"}
ALLOW_WORDS = sorted(set().union(*_BASE.values()) | FOOTER_WORDS, key=lambda w: (-len(w), w))
PRICE_COLS = ["source_folder", "source_file_no", "source_sheet_no", "file_hash", "year_month", "client", "price_basis",
              "unit_price", "supply_amount", "vat", "total_amount", "source_row_nos"]


def _flat(kind: str):
    out = []
    for order, (std, words) in enumerate(RULES[kind]):
        for w in words:
            out.append((clean_header(w), std, order))
    return out


_FLAT = {k: _flat(k) for k in RULES}
_UNIT = re.compile(r"[(\[](원|천원|만원|개|톤|kg|km|회|대|%|l|L|ton|EA)[)\]]", re.I)
_STRIP = re.compile(r"[\d\s()\[\]{}.,:;/\\*#_\-+]+")


def map_std(kind: str, text) -> str | None:
    """Standard column for a header text, or None. Exact match first, then longest contained word."""
    t = clean_header(text)
    if not t or len(t) > 30:
        return None
    flat = _FLAT[kind]
    for w, std, _ in flat:
        if t == w:
            return std
    best = None
    for w, std, order in flat:
        if len(w) >= 2 and w in t:
            key = (-len(w), order)
            if best is None or key < best[0]:
                best = (key, std)
    return best[1] if best else None


def safe_label(text) -> str:
    """Printable form of a header. Only an exact allow-list word (after dropping digits, units and brackets) passes."""
    t = str(text)
    core = _STRIP.sub("", _UNIT.sub("", t))
    if core in ALLOW_WORDS:
        return core
    return f"<other:{len(t)}chars>"


# ---------------------------------------------------------------- files
def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def group_by_hash(files: list[Path]):
    """Return (hashes in file order, canonical file number per file number). File numbers start at 1."""
    hashes = [file_hash(f) for f in files]
    first: dict[str, int] = {}
    canon = []
    for no, h in enumerate(hashes, start=1):
        first.setdefault(h, no)
        canon.append(first[h])
    return hashes, canon


def n_filled(row) -> int:
    return sum(1 for v in row if not is_empty(v))


def _is_textish(v) -> bool:
    return isinstance(v, str) and not is_empty(v) and parse_number(v)[1] != "ok" and parse_date(v)[1] != "ok"


def json_value(v):
    if is_empty(v):
        return None
    if isinstance(v, (pd.Timestamp,)) or hasattr(v, "isoformat"):
        return v.isoformat()
    if isinstance(v, (int, np.integer)):
        return int(v)
    if isinstance(v, (float, np.floating)):
        f = float(v)
        return int(f) if f.is_integer() else f
    return str(v).strip()


# ---------------------------------------------------------------- date context and totals
_YM = re.compile(r"(20\d{2})\s*(?:년|[.\-/])\s*(\d{1,2})")
_DAY_ONLY = re.compile(r"^\s*(\d{1,2})\s*일\s*$")
_TOTAL_EXACT = {"계", "월계", "합계", "총계", "소계", "누계", "총합계", "총합", "합산", "누적계"}
_TOTAL_PART = ("합계", "총계", "소계", "누계", "월계", "총합")


def infer_ym(preamble_text: str, sheet_name: str, file_name: str):
    """Year and month for sheets whose date column holds only the day of month. Order: text above the header,
    sheet name, file name. Returns ((year, month), source) or (None, "")."""
    for src, text in (("preamble", preamble_text), ("sheet_name", sheet_name), ("file_name", file_name)):
        m = _YM.search(text or "")
        if m and 1 <= int(m.group(2)) <= 12:
            return (int(m.group(1)), int(m.group(2))), src
    return None, ""


def is_total_row(row, ncol: int) -> bool:
    for v in row[: min(ncol, 6)]:
        if isinstance(v, str) and not is_empty(v):
            t = clean_header(v)
            if len(t) <= 8 and (t in _TOTAL_EXACT or any(w in t for w in _TOTAL_PART)):
                return True
    return False


# ---------------------------------------------------------------- header
def find_header_row(kind: str, rows: list[list]) -> int | None:
    best, best_hits = None, 0
    for r in range(min(SCAN_ROWS, len(rows))):
        vals = rows[r]
        hits = 0
        for v in vals:
            if isinstance(v, str) and not is_empty(v) and map_std(kind, v):
                hits += 1
        text_only = all(isinstance(v, str) or is_empty(v) for v in vals)
        if text_only and hits > best_hits:
            best, best_hits = r, hits
    return best if best is not None and best_hits >= MIN_HITS[kind] else None


def build_header(kind: str, rows: list[list], hr: int, ncol: int):
    """Header block = one text row above (group labels) when it has >=2 filled cells, the header row, and following
    text-only rows that still hold header words. Returns dict or None when no data row follows."""
    block = [hr]
    above = hr - 1
    while above >= 0 and n_filled(rows[above]) == 0 and above >= hr - 2:
        above -= 1
    if above >= 0 and n_filled(rows[above]) >= 2 and all(isinstance(v, str) or is_empty(v) for v in rows[above]) \
            and not any(map_std(kind, v) for v in rows[above] if isinstance(v, str) and not is_empty(v)):
        block.insert(0, above)
    r = hr + 1
    extra = 0
    while r < len(rows) and extra < MAX_HEADER_EXTRA:
        row = rows[r]
        text_only = all(isinstance(v, str) or is_empty(v) for v in row)
        hit = sum(1 for v in row if isinstance(v, str) and not is_empty(v) and map_std(kind, v))
        if text_only and n_filled(row) >= 2 and hit >= 1:
            block.append(r)
            extra += 1
            r += 1
        else:
            break
    data_start = block[-1] + 1
    # skip blank rows between header and data
    levels = []
    for i, rr in enumerate(block):
        vals = [("" if is_empty(v) else str(v).strip()) for v in rows[rr]]
        if i < len(block) - 1:
            last = ""
            for c in range(ncol):
                if vals[c]:
                    last = vals[c]
                elif last:
                    vals[c] = last
        levels.append(vals)
    return {"block": block, "data_start": data_start, "levels": levels}


def header_columns(kind: str, hdr: dict, ncol: int):
    """Return (colmap std->col, keys per column, std-mapped columns). Columns whose upper header level is not an
    allow-list word are client-specific and stay in extra under their combined header."""
    levels = hdr["levels"]
    colmap: dict[str, int] = {}
    keys: list[str] = []
    for c in range(ncol):
        parts = []
        for lv in levels:
            if lv[c] and (not parts or parts[-1] != lv[c]):
                parts.append(lv[c])
        combined = "_".join(parts)
        keys.append(combined)
        if not parts:
            continue
        upper_ok = all(map_std(kind, p) for p in parts[:-1])
        std = map_std(kind, parts[-1]) if upper_ok else None
        if std is None and upper_ok:
            std = map_std(kind, combined)
        if std and std not in colmap:
            colmap[std] = c
    return colmap, keys


# ---------------------------------------------------------------- sheet
def parse_table_sheet(kind: str, df: pd.DataFrame, file_no: int, sheet_no: int, fhash: str, folder: str,
                      sheet_name: str = "", file_name: str = "", merged=None):
    """Return (rows, counts, info). counts: source, loaded, blank, total, header, summary, quarantined.
    merged = list of (min_row, min_col, max_row, max_col), 1-based, from openpyxl."""
    counts = Counter()
    info = {"status": "ok", "mapped": [], "extra_keys": Counter(), "bad_cells": Counter(), "has_date": False,
            "table_kind": "", "day_only": Counter(), "merged_fill": 0, "sumcols": Counter(), "records": 0}
    rows = df.values.tolist()
    counts["source"] = len(rows)
    ncol = df.shape[1]
    active = [c for c in range(ncol) if any(not is_empty(r[c]) for r in rows)]
    if not active:
        info["status"] = "empty_sheet"
        counts["blank"] = len(rows)
        return [], counts, info
    hr = find_header_row(kind, rows)
    hdr = build_header(kind, rows, hr, ncol) if hr is not None else None
    colmap, keys = header_columns(kind, hdr, ncol) if hdr else ({}, [])
    # a horizontal sheet also maps a few standard words in its header row (corner cell, row-sum column), so the
    # matrix test runs first when those are the only mapped words; a header with line-item words stays a table
    # a short horizontal sheet can have its price block header (단가, 수량, 공급가액, 세액) inside the scan window,
    # which then outscores the real header; a matrix corner above the chosen header row gets the matrix test too
    corner = find_matrix_corner(kind, rows)
    if set(colmap) <= MATRIX_HEADER_STD or (corner is not None and hr is not None and corner[0] < hr):
        mx = parse_matrix_sheet(kind, rows, ncol, active, merged or [], file_no, sheet_no, fhash, folder, sheet_name,
                                file_name)
        if mx is not None:
            return mx
    if not colmap:
        info["status"] = "no_header"
        counts["quarantined"] = len(rows)
        return [], counts, info
    info["mapped"] = sorted(colmap)
    info["has_date"] = "date" in colmap
    info["table_kind"] = "+".join(s for s in STD_COLS[kind] if s in colmap)
    mapped_cols = set(colmap.values())
    start = hdr["data_start"]
    pre = " ".join(str(v) for rr in rows[:start] for v in rr if not is_empty(v))
    ym, ym_src = infer_ym(pre, sheet_name, file_name)
    fill: dict = {}
    for (r1, c1, r2, c2) in (merged or []):
        cz = c1 - 1
        if r2 > r1 and cz in mapped_cols and r1 - 1 < len(rows) and not is_empty(rows[r1 - 1][cz]):
            std_of = [k for k, v in colmap.items() if v == cz][0]
            if std_of in FILL_STD:
                for rr in range(max(r1, start), min(r2, len(rows))):
                    if is_empty(rows[rr][cz]):
                        fill[(rr, cz)] = rows[r1 - 1][cz]
    counts["header"] = start  # everything above the first data row: title, group labels, header rows
    out = []
    for r in range(start, len(rows)):
        row = rows[r]
        if n_filled(row) == 0:
            counts["blank"] += 1
            continue
        if is_total_row(row, ncol):
            counts["total"] += 1
            continue
        textcells = [v for v in row if not is_empty(v)]
        if len(textcells) >= 2 and all(isinstance(v, str) for v in textcells) and \
                sum(1 for v in textcells if map_std(kind, v)) >= max(2, len(textcells) // 2):
            counts["header"] += 1  # repeated header row inside the data
            continue
        rec = {"source_folder": folder, "source_file_no": file_no, "source_sheet_no": sheet_no,
               "source_row_no": r + 1, "file_hash": fhash, "table_kind": info["table_kind"]}
        extra: dict = {}
        filled = []
        for std, c in colmap.items():
            v = row[c]
            if is_empty(v) and (r, c) in fill:
                v = fill[(r, c)]
                filled.append(std)
                info["merged_fill"] += 1
            if is_empty(v):
                rec[std] = None
                continue
            if std == "date":
                d, k = parse_date(v)
                dm = _DAY_ONLY.match(v) if isinstance(v, str) else None
                if k == "ok":
                    rec[std] = d.date().isoformat()
                    rec["date_basis"] = "cell"
                elif dm and ym:
                    try:
                        rec[std] = pd.Timestamp(ym[0], ym[1], int(dm.group(1))).date().isoformat()
                        rec["date_basis"] = "day_only+" + ym_src
                        info["day_only"][ym_src] += 1
                        extra[(keys[c] or f"col_{c + 1}") + "#raw"] = json_value(v)
                    except ValueError:
                        rec[std] = None
                        extra[keys[c] or f"col_{c + 1}"] = json_value(v)
                        info["bad_cells"][std] += 1
                else:
                    rec[std] = None
                    extra[keys[c] or f"col_{c + 1}"] = json_value(v)
                    info["bad_cells"][std] += 1
            elif std in NUMERIC_STD:
                x, k = parse_number(v)
                if k == "ok":
                    rec[std] = x
                else:
                    rec[std] = None
                    extra[keys[c] or f"col_{c + 1}"] = json_value(v)
                    info["bad_cells"][std] += 1
            else:
                rec[std] = str(v).strip()
        for c in active:
            if c in mapped_cols or is_empty(row[c]):
                continue
            key = keys[c] or f"col_{c + 1}"
            k2, n = key, 2
            while k2 in extra:
                k2, n = f"{key}#{n}", n + 1
            extra[k2] = json_value(row[c])
            info["extra_keys"][safe_label(key)] += 1
        rec["merged_fill"] = ",".join(filled)
        for c in active:
            v = row[c]
            if isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool):
                info["sumcols"][c] += float(v)
        rec["extra"] = json.dumps(extra, ensure_ascii=False) if extra else ""
        out.append(rec)
        counts["loaded"] += 1
    info["records"] = len(out)
    return out, counts, info


# ---------------------------------------------------------------- matrix (labels spread across the top)
def _num(v) -> bool:
    return isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, bool) and not is_empty(v)


# price block of the older horizontal sheets: one header row of these words, then one line per client
PRICE_BLOCK_WORDS = {"단가": "unit_price", "수량": "quantity", "공급가액": "supply_amount", "세액": "vat"}


def price_block_header(row) -> dict[str, int] | None:
    """Column of each price word when the row is a price block header (단가 and at least two others)."""
    cols = {}
    for c, v in enumerate(row):
        if isinstance(v, str):
            f = PRICE_BLOCK_WORDS.get(re.sub(r"\s+", "", v))
            if f and f not in cols:
                cols[f] = c
    return cols if "unit_price" in cols and len(cols) >= 3 else None


def find_matrix_corner(kind: str, rows: list[list]):
    """Row whose first filled cell is a client/date style label followed by >=2 unmapped text labels."""
    for r in range(min(SCAN_ROWS, len(rows))):
        first = [(c, v) for c, v in enumerate(rows[r]) if not is_empty(v)]
        fl = [(c, v) for c, v in first if isinstance(v, str)]  # numeric cells in the row are a side block, not labels
        if len(fl) >= 3 and first[0] == fl[0] and map_std(kind, fl[0][1]) in ("client", "shop", "date") \
                and sum(1 for _, v in fl[1:] if not map_std(kind, v)) >= 2:
            return r, fl
    return None


def parse_matrix_sheet(kind, rows, ncol, active, merged, file_no, sheet_no, fhash, folder, sheet_name, file_name):
    """Horizontal table: dates run down the corner column, clients or routes run across the header row.
    Judged horizontal when (1) a corner row exists (find_matrix_corner), (2) every header label has a number in
    its column span below, (3) at least 20% of data rows carry a date in the corner column.
    Unpivot: one record per non-empty cell (date, original header, value). Zeros outside label columns are dropped
    and counted. Returns (records, counts, info), or None when the sheet is not horizontal."""
    found = find_matrix_corner(kind, rows)
    if found is None:
        return None
    r0, fl = found
    c0 = fl[0][0]
    labels = [(c, str(v).strip()) for c, v in fl[1:]]
    spans = []
    for c, _ in labels:
        end = c
        for (a, b, x, y) in merged:
            if a <= r0 + 1 <= x and b <= c + 1 <= y:
                end = max(end, y - 1)
        spans.append((c, min(end, ncol - 1)))
    hend = r0 + 1
    for (a, b, x, y) in merged:
        if a <= r0 + 1 <= x and b <= c0 + 1 <= y:
            hend = max(hend, x)
    data_rows = [r for r in range(hend, len(rows)) if n_filled(rows[r]) > 0]
    if not data_rows:
        return None
    label_cols = set()
    colkey: dict[int, str] = {}
    for (c, a_end), (_, text) in zip(spans, labels):
        for cc in range(c, a_end + 1):
            label_cols.add(cc)
            colkey.setdefault(cc, text)
    core = [(a, b) for (a, b), (_, t) in zip(spans, labels) if not map_std(kind, t)]
    has_num = [any(_num(rows[r][cc]) for r in data_rows for cc in range(a, b + 1)) for a, b in core]
    covered = bool(core) and sum(has_num) / len(core) >= 0.8
    datefrac = sum(1 for r in data_rows
                   if parse_date(rows[r][c0])[1] == "ok" or _DAY_ONLY.match(str(rows[r][c0]))) / len(data_rows)
    if not covered or datefrac < 0.2:
        return None
    counts = Counter({"source": len(rows), "header": hend})
    info = {"status": "matrix", "mapped": [], "extra_keys": Counter(), "bad_cells": Counter(), "has_date": True,
            "table_kind": "matrix", "day_only": Counter(), "merged_fill": 0, "sumcols": Counter(), "records": 0,
            "labels": len(labels), "zero_dropped": 0, "rowsum_checked": 0, "rowsum_mismatch": 0, "footer_unknown": 0,
            "unlabeled_total": 0, "price_unmatched": 0, "price_rows": []}
    # label columns whose header is a standard word other than client (the row-sum column) are checked, not unpivoted
    std_cols = {cc for cc, t in colkey.items() if map_std(kind, t) not in (None, "client")}
    client_cols = label_cols - std_cols
    rowsum_col = None
    for cc in sorted(std_cols):
        if map_std(kind, colkey[cc]) == "total_amount":
            rowsum_col = cc
            break
    if rowsum_col is None and std_cols:
        rowsum_col = min(std_cols)
    pre = " ".join(str(v) for rr in rows[:r0] for v in rr if not is_empty(v))
    ym, ym_src = infer_ym(pre, sheet_name, file_name)
    out = []
    footer = []  # (row index, name without whitespace, row)
    price_cols, price_lines = None, []  # price block header columns; (row index, name, row) of its client lines
    colsum: Counter = Counter()  # running kg per client column, to spot a total row that has no label
    cur, basis = None, ""
    total_seen = False
    for r in range(hend, len(rows)):
        row = rows[r]
        if n_filled(row) == 0:
            counts["blank"] += 1
            continue
        if is_total_row(row, ncol):
            counts["total"] += 1
            total_seen = True
            continue
        if price_cols is not None:  # everything under the price block header belongs to the block
            counts["footer"] += 1
            v0 = row[c0]
            if isinstance(v0, str) and not is_empty(v0) and parse_date(v0)[1] != "ok":
                price_lines.append((r, re.sub(r"\s+", "", v0), row))
            continue
        pc = price_block_header(row)
        if pc is not None:
            price_cols, total_seen = pc, True
            counts["footer"] += 1
            continue
        v0 = row[c0]
        if total_seen and is_empty(v0):
            counts["footer"] += 1  # lines under the totals without a label (deposit records, notes) are not trips
            continue
        # total row without a label: every client cell equals the kg above it / 1000 (sheet formula SUM(..)/1000)
        sums = [(float(row[c]), colsum[c] / 1000) for c in client_cols if _num(row[c])]
        if is_empty(v0) and sums and any(v for v, _ in sums) and all(abs(v - s) <= 0.001 for v, s in sums):
            counts["total"] += 1
            info["unlabeled_total"] += 1
            total_seen = True
            continue
        row_label = None
        if not is_empty(v0):
            d, k = parse_date(v0)
            dm = _DAY_ONLY.match(v0) if isinstance(v0, str) else None
            if total_seen and isinstance(v0, str) and k != "ok" and dm is None:
                footer.append((r, re.sub(r"\s+", "", v0), row))  # tail lines under the total row
                counts["footer"] += 1
                continue
            if k == "ok":
                cur, basis = d.date().isoformat(), "cell"
            elif dm and ym:
                try:
                    cur, basis = pd.Timestamp(ym[0], ym[1], int(dm.group(1))).date().isoformat(), "day_only+" + ym_src
                    info["day_only"][ym_src] += 1
                except ValueError:
                    cur, basis = None, ""
            else:
                row_label = json_value(v0)
        if rowsum_col is not None and _num(row[rowsum_col]):
            part = sum(float(row[cc]) for cc in client_cols if _num(row[cc]))
            info["rowsum_checked"] += 1
            if abs(part - float(row[rowsum_col])) > 1:
                info["rowsum_mismatch"] += 1
        n_before = len(out)
        for c in active:
            if c == c0 or c in std_cols or is_empty(row[c]):
                continue
            v = row[c]
            if _num(v) and float(v) == 0.0 and c not in label_cols:
                info["zero_dropped"] += 1
                continue
            key = colkey.get(c) or f"col_{c + 1}"
            extra = {"header": key, "value": json_value(v), "col": c + 1, "outside_label": c not in label_cols}
            if row_label is not None:
                extra["row_label"] = row_label
            is_client = c in client_cols
            if is_client and _num(v):
                colsum[c] += float(v)
            out.append({"source_folder": folder, "source_file_no": file_no, "source_sheet_no": sheet_no,
                        "source_row_no": r + 1, "file_hash": fhash, "table_kind": "matrix", "date": cur,
                        "date_basis": (basis if cur else ""), "client": key if is_client else None,
                        "weight_kg": float(v) if is_client and _num(v) else None,
                        "extra": json.dumps(extra, ensure_ascii=False)})
            info["extra_keys"][safe_label(key)] += 1
        if len(out) > n_before:
            counts["loaded"] += 1
        else:
            counts["blank"] += 1
    info["records"] = len(out)
    months = Counter(rec["date"][:7] for rec in out if rec["date"])
    ymonth = months.most_common(1)[0][0] if months else None
    # footer blocks: price line starts a block; the amount lines under it belong to it
    blocks = []
    for r, name, row in footer:
        if name.startswith("단가(회사인정)"):
            blocks.append({"basis": "company", "lines": {"unit_price": (r, row)}})
        elif name.startswith("단가(발행단가)"):
            blocks.append({"basis": "invoice", "lines": {"unit_price": (r, row)}})
        elif name == "차이금액":
            blocks.append({"basis": "diff", "lines": {"total_amount": (r, row)}})
        else:
            field = {"공급가액": "supply_amount", "부가세": "vat"}.get(name)
            if name == "회사받은금액" and blocks and blocks[-1]["basis"] == "company":
                field = "total_amount"
            if name == "청구한금액" and blocks and blocks[-1]["basis"] == "invoice":
                field = "total_amount"
            if field and blocks and blocks[-1]["basis"] != "diff" and field not in blocks[-1]["lines"]:
                blocks[-1]["lines"][field] = (r, row)
            else:
                info["footer_unknown"] += 1
    for blk in blocks:
        for (a, b), (_, text) in zip(spans, labels):
            if a not in client_cols:
                continue
            rec = {"source_folder": folder, "source_file_no": file_no, "source_sheet_no": sheet_no,
                   "file_hash": fhash, "year_month": ymonth, "client": text, "price_basis": blk["basis"]}
            for f in ("unit_price", "supply_amount", "vat", "total_amount"):
                rec[f] = None
                if f in blk["lines"]:
                    vals = [x for x in blk["lines"][f][1][a:b + 1] if _num(x)]
                    rec[f] = float(vals[0]) if vals else None
            if all(rec[f] is None for f in ("unit_price", "supply_amount", "vat", "total_amount")):
                continue
            rec["source_row_nos"] = json.dumps(sorted(r + 1 for r, _ in blk["lines"].values()))
            info["price_rows"].append(rec)
    # price block: a line names its client; when the name differs from the header (쌍용벌크운반비 vs 쌍용(P/C)),
    # its quantity is matched to the one client whose column total in tons is the same
    client_labels = [(a, b, text) for (a, b), (_, text) in zip(spans, labels) if a in client_cols]
    for r, name, row in price_lines:
        def cell(f):
            c = price_cols.get(f)
            return float(row[c]) if c is not None and _num(row[c]) else None
        qty = cell("quantity")
        if (cell("unit_price") is None and qty is None) or name == "차액" or "입금" in name:
            continue  # a note line under the block (difference, deposit date), not a client line
        hit = [text for _, _, text in client_labels if re.sub(r"\s+", "", text) == name]
        if not hit and qty:
            hit = [text for a, b, text in client_labels
                   if abs(sum(colsum[cc] for cc in range(a, b + 1)) / 1000 - qty) <= 0.001]
        if len(hit) != 1:
            info["price_unmatched"] += 1
            info.setdefault("price_unmatched_lines", []).append((r + 1, name, len(hit)))
            continue
        rec = {"source_folder": folder, "source_file_no": file_no, "source_sheet_no": sheet_no, "file_hash": fhash,
               "year_month": ymonth, "client": hit[0], "price_basis": "company", "unit_price": cell("unit_price"),
               "supply_amount": cell("supply_amount"), "vat": cell("vat"), "total_amount": None,
               "source_row_nos": json.dumps([r + 1])}
        if rec["unit_price"] is None and rec["supply_amount"] is None:
            continue
        info["price_rows"].append(rec)
    return out, counts, info


# ---------------------------------------------------------------- summary tables
def sheet_numbers(rows, min_abs: float = 100.0):
    return [float(v) for r in rows for v in r if _num(v) and abs(float(v)) >= min_abs]


def match_ratio(numbers: list[float], sums: list[float], tol: float = 1.0):
    """Return (matched, total): numbers that equal some column sum within tol."""
    arr = np.array(sorted(sums))
    matched = 0
    for x in numbers:
        if len(arr):
            i = int(np.searchsorted(arr, x))
            near = min((abs(arr[j] - x) for j in (i - 1, i) if 0 <= j < len(arr)), default=1e18)
            if near <= tol:
                matched += 1
    return matched, len(numbers)


def summary_rows(rows, file_no, sheet_no, fhash, folder):
    """All non-blank rows of a confirmed summary sheet, every cell kept in extra."""
    out, counts = [], Counter({"source": len(rows)})
    for r, row in enumerate(rows):
        if n_filled(row) == 0:
            counts["blank"] += 1
            continue
        extra = {f"col_{c + 1}": json_value(v) for c, v in enumerate(row) if not is_empty(v)}
        out.append({"source_folder": folder, "source_file_no": file_no, "source_sheet_no": sheet_no,
                    "source_row_no": r + 1, "file_hash": fhash, "table_kind": "summary", "date": None,
                    "date_basis": "", "extra": json.dumps(extra, ensure_ascii=False)})
        counts["summary"] += 1
    return out, counts


def reconciled(counts: Counter) -> bool:
    return counts["source"] == (counts["loaded"] + counts["blank"] + counts["total"] + counts["header"]
                                + counts["skipped_driving"] + counts["summary"] + counts["footer"]
                                + counts["quarantined"])
