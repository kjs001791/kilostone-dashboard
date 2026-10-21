"""One-off check of the unit of weight_ton in the parsed revenue file (kilogram vs ton).
Prints counts by digit length of the integer part only; no values. Rows of matrix sheets are excluded."""
from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common import load_config, path_from  # noqa: E402


def bucket(x: float) -> str:
    n = len(str(int(abs(x))))
    return "0-2 digits" if n <= 2 else "3 digits" if n == 3 else "4 digits" if n == 4 else "5+ digits"


def main() -> int:
    cfg = load_config()
    path = path_from(cfg, "parsed_dir") / "revenue.csv"
    df = pd.read_csv(path, encoding="utf-8-sig", usecols=["table_kind", "weight_ton"], low_memory=False)
    w = pd.to_numeric(df.loc[df["table_kind"] != "matrix", "weight_ton"], errors="coerce").dropna()
    c = Counter(bucket(x) for x in w)
    print("non-empty weight_ton (non-matrix rows):", len(w))
    for k in ("0-2 digits", "3 digits", "4 digits", "5+ digits"):
        print(f"integer part {k}: {c.get(k, 0)}")
    return 0


def safe_main() -> int:
    try:
        return main()
    except Exception as e:  # message may carry values: class name only
        print("failed, exception class:", type(e).__name__)
        return 1


if __name__ == "__main__":
    sys.exit(safe_main())
