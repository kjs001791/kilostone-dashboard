"""Shared helpers for the KiloStone preprocessing pipeline.

Console output rule: counts, column names, types, error-kind counts and scores only.
Never print cell values, cell coordinates, sheet names or client names.
"""
from __future__ import annotations

import datetime as dt
import io
import re
import tomllib
from decimal import Decimal
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "pipeline" / "config.toml"


def load_config() -> dict:
    with io.open(CONFIG_PATH, "rb") as f:
        return tomllib.load(f)


def path_from(cfg: dict, key: str) -> Path:
    return ROOT / cfg["paths"][key]


def raw_subdir(cfg: dict, kind: str) -> Path | None:
    base = path_from(cfg, "raw_dir")
    for name in cfg["raw_subfolders"][kind]:
        p = base / name
        if p.is_dir():
            return p
    return None


def list_excel(folder: Path) -> list[Path]:
    files = [p for p in folder.rglob("*") if p.suffix.lower() in (".xlsx", ".xlsm", ".xls") and not p.name.startswith("~$")]
    return sorted(files)


# ---------------------------------------------------------------- columns
# standard column -> header aliases (whitespace removed before matching)
ALIASES = {
    "date": ["날짜", "일자"],
    "fuel_efficiency": ["1일평균연비", "평균연비", "연비", "km/l"],
    "speed": ["평균운행속도", "km/h"],
    "time": ["총운행시간", "운행시간", "구동시간_TOT", "h(TOT)"],
    "distance": ["1일주행거리", "총운행거리", "운행거리", "km(주행)", "트립미터_TOT", "트립미터TOT"],
    "cumulative_distance": ["누적주행거리", "누적운행거리", "누적키로수_TOT", "누적키로수", "총주행거리", "km(누적)"],
    "consumed_fuel": ["1일연료소모량", "연료소모량", "연비개요_TOT", "l(TOT)"],
    "refuel": ["연료주입량", "주입량", "경유_TOT", "l(경유)"],
    "reurea": ["요소수_TOT", "요소수주입량", "요소수주입", "요소수", "l(요소수)"],
    "fuel_rate_per_hour": ["l/h"],
    "consumed_fuel_idle": ["연비개요_IDL", "l(IDL)"],
    "consumed_fuel_pto": ["연비개요_PTO", "l(PTO)"],
    "time_idle": ["구동시간_IDL", "h(IDL)"],
    "time_pto": ["구동시간_PTO", "h(PTO)"],
}
NUMERIC_COLS = [
    "fuel_efficiency", "speed", "distance", "cumulative_distance", "consumed_fuel", "refuel", "reurea",
    "fuel_rate_per_hour", "consumed_fuel_idle", "consumed_fuel_pto",
]
TIME_COLS = ["time", "time_idle", "time_pto"]  # stored as hours (float) in standard file as <name>_h
STD_COLUMNS = [
    "row_id", "source_file", "source_sheet_no", "source_row_no", "vehicle", "date",
    "fuel_efficiency", "speed", "time_h", "distance", "cumulative_distance", "consumed_fuel", "refuel", "reurea",
    "fuel_rate_per_hour", "consumed_fuel_idle", "consumed_fuel_pto", "time_idle_h", "time_pto_h",
]
KOREAN = {
    "row_id": "행 번호", "source_file": "원본 파일 순번", "source_sheet_no": "원본 시트 순번", "source_row_no": "원본 행 번호",
    "vehicle": "차량 양식", "date": "날짜", "fuel_efficiency": "연비(km/l)", "speed": "평균 운행속도(km/h)",
    "time_h": "운행시간(시간)", "distance": "1일 주행거리(km)", "cumulative_distance": "누적 주행거리(km)",
    "consumed_fuel": "1일 연료소모량(l)", "refuel": "연료 주입량(l)", "reurea": "요소수(l)",
    "fuel_rate_per_hour": "시간당 연료(l/h)", "consumed_fuel_idle": "공회전 연료(l)", "consumed_fuel_pto": "PTO 연료(l)",
    "time_idle_h": "공회전 시간(시간)", "time_pto_h": "PTO 시간(시간)",
}


def clean_header(text) -> str:
    return re.sub(r"\s+", "", str(text)).replace(" ", "")


_ALIAS_FLAT = sorted(
    ((clean_header(a), std) for std, al in ALIASES.items() for a in al),
    key=lambda x: -len(x[0]),
)


def map_header(text) -> str | None:
    t = clean_header(text)
    if not t:
        return None
    for alias, std in _ALIAS_FLAT:
        if t == alias:
            return std
    for alias, std in _ALIAS_FLAT:
        if len(alias) >= 2 and alias in t:
            return std
    return None


# ---------------------------------------------------------------- cell parsing
def is_empty(v) -> bool:
    if v is None:
        return True
    if isinstance(v, float) and np.isnan(v):
        return True
    if v is pd.NaT:
        return True
    if isinstance(v, str) and not v.strip():
        return True
    return False


def parse_number(v):
    """Return (value or None, kind) where kind in empty|ok|text."""
    if is_empty(v):
        return None, "empty"
    if isinstance(v, bool):
        return None, "text"
    if isinstance(v, (int, float, np.integer, np.floating)):
        return float(v), "ok"
    if isinstance(v, (dt.datetime, dt.date, dt.time, pd.Timestamp)):
        return None, "text"
    s = str(v).replace(",", "").strip()
    try:
        return float(s), "ok"
    except ValueError:
        return None, "text"


def parse_time_hours(v):
    """Return (hours or None, kind). '5.30' style = 5h30m, 'H:MM(:SS)', datetime.time, timedelta."""
    if is_empty(v):
        return None, "empty"
    if isinstance(v, dt.time):
        return v.hour + v.minute / 60 + v.second / 3600, "ok"
    if isinstance(v, dt.timedelta):
        return v.total_seconds() / 3600, "ok"
    if isinstance(v, (dt.datetime, pd.Timestamp)):
        return v.hour + v.minute / 60 + v.second / 3600, "ok"
    if isinstance(v, (int, float, np.integer, np.floating)):
        x = float(v)
        h = int(x)
        frac = round(x - h, 2)
        return h + int(round(frac * 100)) / 60, "ok"
    s = str(v).strip()
    if ":" in s:
        parts = s.split(":")
        try:
            nums = [int(p) for p in parts[:3]]
            return nums[0] + nums[1] / 60 + (nums[2] / 3600 if len(nums) > 2 else 0), "ok"
        except (ValueError, IndexError):
            return None, "text"
    m = re.search(r"(\d+)\D+(\d+)", s)
    if m:
        return int(m.group(1)) + int(m.group(2)) / 60, "ok"
    try:
        x = float(s)
        h = int(x)
        return h + int(round((x - h) * 100)) / 60, "ok"
    except ValueError:
        return None, "text"


_DATE_RE = re.compile(r"^\s*(\d{4})\s*[-./년]\s*(\d{1,2})\s*[-./월]\s*(\d{1,2})")


def parse_date(v):
    """Return (Timestamp or None, kind) kind in empty|ok|text."""
    if is_empty(v):
        return None, "empty"
    if isinstance(v, (dt.datetime, dt.date, pd.Timestamp)):
        try:
            return pd.Timestamp(v).normalize(), "ok"
        except (ValueError, OverflowError):
            return None, "text"
    if isinstance(v, (int, float, np.integer, np.floating)):
        x = float(v)
        if 20000 <= x <= 60000:
            return (pd.Timestamp("1899-12-30") + pd.Timedelta(days=int(x))).normalize(), "ok"
        return None, "text"
    s = str(v)
    m = _DATE_RE.match(s)
    if m:
        try:
            return pd.Timestamp(int(m.group(1)), int(m.group(2)), int(m.group(3))), "ok"
        except (ValueError, OverflowError):
            return None, "text"
    return None, "text"


TOTAL_WORDS = ("합계", "총계", "소계", "누계", "평균", "합 계", "총 계")


def looks_total(vals) -> bool:
    for v in vals:
        if isinstance(v, str):
            t = v.strip()
            if t and len(t) <= 10 and any(w in t for w in TOTAL_WORDS):
                return True
    return False


# ---------------------------------------------------------------- decimals / units
def decimals_of(x: float, cap: int = 4) -> int:
    d = Decimal(repr(round(float(x), cap))).normalize()
    exp = d.as_tuple().exponent
    return max(0, -exp) if isinstance(exp, int) else 0


def decimals_hist(values) -> dict:
    h = {"0": 0, "1": 0, "2": 0, "3+": 0}
    for x in values:
        d = decimals_of(x)
        h["3+" if d >= 3 else str(d)] += 1
    return h


def infer_decimals(values, min_share: float = 0.03) -> int:
    """Decimal places shown by the meter: the largest d such that >= min_share of values need d places."""
    vals = [float(x) for x in values if x is not None and not (isinstance(x, float) and np.isnan(x))]
    if not vals:
        return 0
    ds = [decimals_of(x) for x in vals]
    for d in (3, 2, 1):
        if sum(1 for k in ds if k >= d) / len(ds) >= min_share:
            return d
    return 0


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with io.open(path, "w", encoding="utf-8") as f:
        f.write(text)


_SAFE_HDR = re.compile(r"(km|키로|거리|연비|연료|요소|경유|시간|속도|주행|누적|합계|합 계|TOT|IDL|PTO|비고|날짜|일자|주입|소모|l/h)", re.I)


def safe_label(text: str) -> str:
    """Header text may be printed only if it looks like a measurement column. Anything else could be a client name."""
    t = str(text)
    return t[:20] if _SAFE_HDR.search(t) else f"<other:{len(t)}chars>"
