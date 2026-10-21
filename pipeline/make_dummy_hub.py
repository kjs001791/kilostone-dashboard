"""Fake 2nd-layer CSV files for the hub loader (pipeline/load_hub.py), API tests and screen tests.

make_hub_dummy(out_dir) writes revenue.csv, revenue_client_price.csv, revenue_file_map.csv, file_correspondence.csv,
maintenance.csv, driving_edited.csv, driving_corrections.csv, dim_vehicle.csv and an empty name_merge.csv.
All names and values are made up. Period 2024-01 .. 2025-02 (14 months), vehicles V03 and V04, four clients with
spelling variants, matrix and table rows, price rows, driving rows with duplicate and missing cases, a few maintenance lines.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common import write_csv  # noqa: E402
from pipeline.revenue_common import KEY_COLS, STD_COLS  # noqa: E402

OUT_DEFAULT = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "hub_dummy"
MONTHS = [f"2024-{m:02d}" for m in range(1, 13)] + ["2025-01", "2025-02"]
H_TABLE, H_MATRIX, H_OLD, H_DRV = "dummyhash_tab", "dummyhash_mat", "dummyhash_old", "dummyhash_drv"
CLIENT_A = ["가나물산(주)", "(주)가나물산", "가나 물산", "㈜가나물산"]
CLIENT_B = ["다라건설 주식회사", "다라건설"]
CLIENT_C = ["마바자원"]
CLIENT_D = ["사아산업(유)", "(유)사아산업"]
PLACES = {"항": ["강릉항", "강릉 항"], "창고": ["서울창고", "서울 창고"], "터미널": ["부산터미널"]}
INVOICE_PRICE = {"A": 50000, "B": 40000, "C": 30000, "D": 20000}
REV_COLS = KEY_COLS + ["table_kind"] + STD_COLS["revenue"] + ["date_basis", "merged_fill", "extra"]
MAINT_COLS = KEY_COLS + ["table_kind"] + STD_COLS["maintenance"] + ["date_basis", "merged_fill", "extra"]
PRICE_COLS = ["source_folder", "source_file_no", "source_sheet_no", "file_hash", "year_month", "client", "price_basis", "unit_price",
              "supply_amount", "vat", "total_amount", "source_row_nos"]
DRIVING_COLS = ["row_id", "source_file", "source_sheet_no", "source_row_no", "vehicle", "date", "fuel_efficiency", "speed", "time_h",
                "distance", "cumulative_distance", "consumed_fuel", "refuel", "reurea", "fuel_rate_per_hour", "consumed_fuel_idle",
                "consumed_fuel_pto", "time_idle_h", "time_pto_h", "vehicle_id", "has_values"]


def revenue_rows() -> tuple[list[dict], list[dict]]:
    rows, price = [], []
    n = {"tab": 0, "mat": 0, "old": 0}
    fileno = {"tab": 1, "mat": 2, "old": 3}

    def add(h, kind, rec, counter):
        n[counter] += 1
        base = {"source_folder": "revenue", "source_file_no": fileno[counter], "source_sheet_no": 1,
                "source_row_no": n[counter], "file_hash": h, "table_kind": kind, "date_basis": "cell"}
        base.update(rec)
        rows.append(base)

    def add_price(h, fno, ym, client, basis, unit, sup, vat, tot, rown):
        price.append({"source_folder": "revenue", "source_file_no": fno, "source_sheet_no": 1, "file_hash": h, "year_month": ym,
                      "client": client, "price_basis": basis, "unit_price": unit, "supply_amount": sup, "vat": vat,
                      "total_amount": tot, "source_row_nos": json.dumps(rown)})

    for i, ym in enumerate(MONTHS):
        scale = [25.5, 24500, 500][i % 3]  # tons, kilograms, ambiguous
        for who, names, wt in (("A", CLIENT_A, scale), ("B", CLIENT_B, scale), ("C", CLIENT_C, 30.0)):
            add(H_TABLE, "date+client+origin+destination+weight_ton+supply_amount", {
                "date": f"{ym}-05", "client": names[i % len(names)], "origin": PLACES["항"][i % 2], "destination": PLACES["창고"][i % 2],
                "item": "철근", "weight_ton": wt, "trips": 1, "unit_price": INVOICE_PRICE[who], "supply_amount": 1000000 + 1000 * i,
                "vat": 100000, "total_amount": 1100000 + 1000 * i, "note": ("비고" if i == 0 else None)}, "tab")
        for who, names, kg in (("A", CLIENT_A, 20000), ("B", CLIENT_B, 10000), ("D", CLIENT_D, 5000)):
            add(H_MATRIX, "matrix", {"date": f"{ym}-10", "client": names[i % len(names)], "weight_kg": kg,
                                     "extra": json.dumps({"header": names[0], "value": kg, "col": 3, "outside_label": False},
                                                         ensure_ascii=False)}, "mat")
        for who, names in (("A", CLIENT_A), ("B", CLIENT_B)):
            if who == "B" and ym == "2025-02":
                continue  # no invoice price this month: matrix revenue stays empty
            add_price(H_MATRIX, 2, ym, names[i % len(names)], "invoice", INVOICE_PRICE[who], 500000, 50000, 550000, [40, 41, 42])
        add_price(H_MATRIX, 2, ym, CLIENT_A[0], "company", 48000, 480000, 48000, 528000, [43, 44])
    # a month with a company price only (the 2015-2019 sheets): matrix revenue falls back to it
    add_price(H_MATRIX, 2, MONTHS[0], CLIENT_D[0], "company", 30000, None, None, None, [45])
    # vehicle period edge: 2024-06-30 is the last day of V03, 2024-07-01 the first day of V04
    for day in ("2024-06-30", "2024-07-01"):
        add(H_TABLE, "date+client+weight_ton+supply_amount", {"date": day, "client": CLIENT_C[0], "weight_ton": 20.0,
                                                               "supply_amount": 600000}, "tab")
    # a table row without date, a matrix cell outside the label columns, a summary row
    add(H_TABLE, "date+client+weight_ton", {"date": None, "client": CLIENT_C[0], "weight_ton": 10.0}, "tab")
    # a price list read as a table: a date and places but nothing measured
    add(H_TABLE, "date+origin+destination+unit_price", {"date": "2024-03-01", "origin": PLACES["항"][0],
                                                         "destination": PLACES["창고"][0], "unit_price": 1000}, "tab")
    add(H_MATRIX, "matrix", {"date": "2024-03-10", "client": None, "weight_kg": None,
                             "extra": json.dumps({"header": "합 계", "value": 99, "col": 9, "outside_label": True}, ensure_ascii=False)}, "mat")
    add(H_MATRIX, "summary", {"date": None, "extra": json.dumps({"col_1": 1}, ensure_ascii=False)}, "mat")
    # older revenue-only workbook: two copies of rows already in the shared workbooks, one new row
    add(H_OLD, "date+client+origin+destination+weight_ton+supply_amount", {
        "date": "2024-03-05", "client": CLIENT_A[0], "weight_ton": 25.5, "supply_amount": 1002000}, "old")
    add(H_OLD, "matrix", {"date": "2024-01-10", "client": CLIENT_B[1], "weight_kg": 10000,
                          "extra": json.dumps({"header": CLIENT_B[0], "value": 10000, "col": 4, "outside_label": False})}, "old")
    add(H_OLD, "date+client+weight_ton+supply_amount", {"date": "2025-03-01", "client": CLIENT_A[0], "weight_ton": 20.0,
                                                          "supply_amount": 900000}, "old")
    # price rows that cannot load: same key as an earlier invoice row, a diff row, a row without month
    add_price(H_OLD, 3, MONTHS[0], CLIENT_A[2], "invoice", 99999, None, None, None, [7])
    add_price(H_OLD, 3, MONTHS[1], CLIENT_A[0], "diff", None, None, None, 1000, [8])
    add_price(H_OLD, 3, None, CLIENT_B[0], "invoice", 1, None, None, None, [9])
    return rows, price


def driving_rows() -> tuple[list[dict], list[dict]]:
    rows = []

    def add(vid, day, dist, cum, fuel, has=True, vehicle=None):
        rid = len(rows) + 1
        rows.append({"row_id": rid, "source_file": 1, "source_sheet_no": 1, "source_row_no": rid, "vehicle": vehicle or vid,
                     "date": day, "fuel_efficiency": (round(dist / fuel, 2) if has else None), "speed": (45.0 if has else None),
                     "time_h": (8.0 if has else None), "distance": (dist if has else None), "cumulative_distance": (cum if has else None),
                     "consumed_fuel": (fuel if has else None), "vehicle_id": vid, "has_values": has})

    cum = 100000.0
    for d in range(27, 31):  # rows 1-4, V03
        cum += 200.0
        add("V03", f"2024-06-{d}", 200.0, cum, 80.0)
    for d in range(1, 6):  # rows 5-9, V04 (row 6 = 07-02, row 7 = 07-03)
        cum += 250.0
        add("V04", f"2024-07-{d:02d}", 250.0, cum, 90.0)
    add("V04", "2024-07-02", rows[5]["distance"], rows[5]["cumulative_distance"], rows[5]["consumed_fuel"])  # row 10: identical copy of row 6
    add("V04", "2024-07-03", 999.0, 5.0, 10.0)  # row 11: conflicting copy of row 7
    add(None, "2024-07-04", 100.0, 1.0, 10.0, vehicle="Unknown")  # row 12: no vehicle id
    add("V04", "2024-07-06", 0, 0, 0, has=False)  # row 13: no values
    corr = [
        {"행 번호": 2, "칸": "distance", "원래 값": 2000.0, "고친 값": 200.0, "적용 규칙": "typo_digit", "규칙 설명": "자릿수 오타"},
        {"행 번호": 8, "칸": "cumulative_distance", "원래 값": 5.0, "고친 값": 101400.0, "적용 규칙": "chain", "규칙 설명": "누적 거리 사슬"},
        {"행 번호": 10, "칸": "distance", "원래 값": 1.0, "고친 값": 2.0, "적용 규칙": "typo_digit", "규칙 설명": "격리된 행"},
    ]
    return rows, corr


def make_hub_dummy(out_dir=None) -> Path:
    out = Path(out_dir) if out_dir else OUT_DEFAULT
    out.mkdir(parents=True, exist_ok=True)
    rev, price = revenue_rows()
    write_csv(pd.DataFrame(rev, columns=REV_COLS), out / "revenue.csv")
    write_csv(pd.DataFrame(price, columns=PRICE_COLS), out / "revenue_client_price.csv")
    fmap = [{"folder": "revenue", "file_no": i, "file_name": f"dummy{i}.xlsx", "file_hash": h, "read_as_file_no": i, "duplicate_of": ""}
            for i, h in ((1, H_TABLE), (2, H_MATRIX), (3, H_OLD))]
    write_csv(pd.DataFrame(fmap), out / "revenue_file_map.csv")
    fc = [{"folder": "revenue", "file_no": 1, "file_name": "dummy1.xlsx", "file_hash": H_TABLE, "in_driving": True, "in_revenue": True},
          {"folder": "revenue", "file_no": 2, "file_name": "dummy2.xlsx", "file_hash": H_MATRIX, "in_driving": True, "in_revenue": True},
          {"folder": "revenue", "file_no": 3, "file_name": "dummy3.xlsx", "file_hash": H_OLD, "in_driving": False, "in_revenue": True},
          {"folder": "driving", "file_no": 1, "file_name": "dummy1.xlsx", "file_hash": H_TABLE, "in_driving": True, "in_revenue": True},
          {"folder": "driving", "file_no": 2, "file_name": "dummy2.xlsx", "file_hash": H_MATRIX, "in_driving": True, "in_revenue": True},
          {"folder": "driving", "file_no": 3, "file_name": "dummy4.xlsx", "file_hash": H_DRV, "in_driving": True, "in_revenue": False}]
    write_csv(pd.DataFrame(fc), out / "file_correspondence.csv")
    maint = []
    lines = [("2024-02-10", "엔진오일"), ("2024-06-30", "타이어"), ("2024-07-01", "브레이크"), (None, "점검"), ("2018-01-01", "도장")]
    for i, (day, item) in enumerate(lines, start=1):
        maint.append({"source_folder": "maintenance", "source_file_no": 1, "source_sheet_no": 1, "source_row_no": i,
                      "file_hash": "dummyhash_mnt", "table_kind": "date+item+cost", "date": day, "item": item, "shop": "가짜정비소",
                      "quantity": 1, "unit_price": 100000 * i, "cost": 100000 * i, "odometer_km": 100000 + i, "note": None,
                      "date_basis": "cell"})
    write_csv(pd.DataFrame(maint, columns=MAINT_COLS), out / "maintenance.csv")
    drv, corr = driving_rows()
    write_csv(pd.DataFrame(drv, columns=DRIVING_COLS), out / "driving_edited.csv")
    write_csv(pd.DataFrame(corr), out / "driving_corrections.csv")
    veh = pd.DataFrame([
        {"vehicle_id": "V03", "brand": "Daewoo", "model": None, "model_year": None, "color": "하늘색", "service_start": "2019-04-01",
         "service_end": "2024-06-30", "title_words": None, "note": "가짜 운행 기간"},
        {"vehicle_id": "V04", "brand": "Scania", "model": None, "model_year": None, "color": "흰색", "service_start": "2024-07-01",
         "service_end": None, "title_words": None, "note": "가짜 운행 기간"}])
    write_csv(veh, out / "dim_vehicle.csv")
    write_csv(pd.DataFrame(columns=["kind", "alias_normalized", "canonical"]), out / "name_merge.csv")
    return out


if __name__ == "__main__":
    p = make_hub_dummy(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
    print("hub dummy written:", len(list(p.glob("*.csv"))), "files")
