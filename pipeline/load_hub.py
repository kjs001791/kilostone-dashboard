"""Load the 2nd-layer CSV files into the 3rd-layer PostgreSQL hub (schema `hub`, db/schema.sql).

build_frames(parsed_dir, review_dir) is a pure transformation (CSV -> DataFrames, no DB).
write_db(dsn, frames) recreates the schema and inserts the frames in dependency order.

Console output: counts, table names and reason codes only. No values, no names.
The DB password comes from the libpq password file, never from this code.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common import ROOT, load_config, path_from, write_csv  # noqa: E402

SCHEMA_SQL = ROOT / "db" / "schema.sql"
VEHICLE_CSV = ROOT / "pipeline" / "dim_vehicle.csv"
NAME_MERGE_CSV = ROOT / "pipeline" / "name_merge.csv"
NAME_MERGE_COLS = ["kind", "alias_normalized", "canonical"]
DUMMY_DIR = ROOT / "tests" / "fixtures" / "hub_dummy"
DEFAULT_DSN = "postgresql+psycopg://postgres@localhost:5432/kilostone"
DSN_ENV = "KILOSTONE_PG_DSN"

REASONS = ["no_date", "date_out_of_range", "summary_table", "matrix_outside_label", "no_measure", "duplicate_older_file", "duplicate_price", "price_not_loaded",
           "vehicle_unknown", "duplicate_identical", "duplicate_conflict", "no_values"]

# frame name -> insert order (frames whose name starts with "_" are reports, not tables)
TABLE_ORDER = ["vehicle", "place", "place_alias", "client", "client_alias", "route", "product", "driving",
               "driving_correction", "delivery", "maintenance", "quarantine"]
ID_COLUMNS = {"place": "place_id", "client": "client_id", "route": "route_id", "product": "product_id", "driving": "driving_id",
              "driving_correction": "correction_id", "delivery": "delivery_id", "maintenance": "maintenance_id",
              "quarantine": "quarantine_id"}
JSON_COLUMNS = {"delivery": ["flags"], "driving": ["flags"], "quarantine": ["payload"]}

DRIVING_VALUE_COLS = ["distance", "cumulative_distance", "consumed_fuel", "fuel_efficiency", "speed", "time_h", "refuel", "reurea",
                      "fuel_rate_per_hour", "consumed_fuel_idle", "consumed_fuel_pto", "time_idle_h", "time_pto_h"]
DELIVERY_COLS = ["delivery_id", "date", "vehicle_id", "client_id", "route_id", "origin_place_id", "dest_place_id", "item", "weight_kg",
                 "trips", "unit_price", "supply_amount", "vat", "total_amount", "grain", "source_kind", "source_file_no",
                 "source_sheet_no", "source_row_no", "source_col", "quantity", "amount", "note", "amount_source", "weight_basis",
                 "flags"]
INT_COLS = ["source_file_no", "source_sheet_no", "source_row_no", "source_col", "client_id", "route_id", "origin_place_id",
            "dest_place_id", "origin_place_id", "place_id", "driving_id", "model_year"]


# ---------------------------------------------------------------- names
_STRIP_WORDS = ("(주)", "주식회사", "(유)")


def normalize_name(raw) -> str:
    """Whitespace removed, (주) ㈜ 주식회사 (유) removed, full-width brackets to half-width. Empty string when nothing is left."""
    if raw is None or (isinstance(raw, float) and np.isnan(raw)):
        return ""
    s = unicodedata.normalize("NFKC", str(raw))  # full-width brackets -> half-width, ㈜ -> (주)
    s = re.sub(r"\s+", "", s)
    for w in _STRIP_WORDS:
        s = s.replace(w, "")
    return s


def _load_merge(path: Path) -> dict:
    """(kind, normalized alias) -> normalized canonical."""
    if not Path(path).exists():
        return {}
    m = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    out = {}
    for kind, alias, canon in zip(m.get("kind", []), m.get("alias_normalized", []), m.get("canonical", [])):
        a, c = normalize_name(alias), normalize_name(canon)
        if kind in ("client", "place") and a and c:
            out[(kind, a)] = c
    return out


def _ensure_merge_header(path: Path) -> None:
    if not Path(path).exists():
        write_csv(pd.DataFrame(columns=NAME_MERGE_COLS), Path(path))


class NameBook:
    """Raw names -> normalized key -> merged key -> integer id. Counts occurrences for the name list."""

    def __init__(self, kind: str, merge: dict):
        self.kind, self.merge = kind, merge
        self.raw_count: Counter = Counter()  # raw alias -> rows

    def add(self, series: pd.Series) -> None:
        for v, n in series.dropna().astype(str).value_counts().items():
            if normalize_name(v):
                self.raw_count[v] += int(n)

    def key(self, raw) -> str:
        n = normalize_name(raw)
        return self.merge.get((self.kind, n), n) if n else ""

    def tables(self):
        """Return (entity frame, alias frame, key->id, name list frame)."""
        groups: dict[str, list] = {}
        for raw in self.raw_count:
            groups.setdefault(self.key(raw), []).append(raw)
        idcol = f"{self.kind}_id"
        keys = sorted(groups)
        ids = {k: i for i, k in enumerate(keys, start=1)}
        names = []
        for k in keys:
            members = groups[k]
            own = [r for r in members if normalize_name(r) == k] or members
            names.append(sorted(own, key=lambda r: (-self.raw_count[r], r))[0].strip())
        ent = pd.DataFrame({idcol: [ids[k] for k in keys], "name": names})
        alias = pd.DataFrame([{"alias": r, idcol: ids[k]} for k in keys for r in sorted(groups[k])],
                             columns=["alias", idcol])
        by_norm: dict[str, list] = {}
        for raw in self.raw_count:
            by_norm.setdefault(normalize_name(raw), []).append(raw)
        nl = pd.DataFrame([{"kind": self.kind, "normalized": n, "alias_count": len(rs),
                            "row_count": sum(self.raw_count[r] for r in rs)} for n, rs in sorted(by_norm.items())],
                          columns=["kind", "normalized", "alias_count", "row_count"])
        return ent, alias, ids, nl


# ---------------------------------------------------------------- helpers
def _read(path: Path, **kw) -> pd.DataFrame:
    return pd.read_csv(path, encoding="utf-8-sig", **kw)


def _num(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _text(s: pd.Series) -> pd.Series:
    return s.where(s.notna(), None).map(lambda v: None if v is None or (isinstance(v, str) and not v.strip()) else v)


def _jsonable(v):
    if v is None or v is pd.NaT:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        return None if np.isnan(v) else float(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (pd.Timestamp,)):
        return v.date().isoformat()
    if hasattr(v, "isoformat"):
        return v.isoformat()
    return v


def _payload(row: pd.Series) -> dict:
    return {str(k): _jsonable(v) for k, v in row.items()}


def _src(row: pd.Series, file_col="source_file_no") -> tuple:
    def g(c):
        v = row.get(c)
        return None if v is None or pd.isna(v) else int(v)
    return g(file_col), g("source_sheet_no"), g("source_row_no")


def _load_vehicles(path: Path) -> pd.DataFrame:
    v = pd.read_csv(path, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    v = v[v["vehicle_id"].str.strip() != ""].copy()
    for c in ("brand", "model", "color", "note"):
        v[c] = v[c].replace("", None) if c in v else None
    v["model_year"] = pd.to_numeric(v.get("model_year"), errors="coerce").astype("Int64")
    v["service_start"] = pd.to_datetime(v["service_start"].replace("", None), errors="coerce")
    v["service_end"] = pd.to_datetime(v["service_end"].replace("", None), errors="coerce")
    return v[["vehicle_id", "brand", "model", "model_year", "color", "service_start", "service_end", "note"]].reset_index(drop=True)


def _vehicle_by_date(vehicles: pd.DataFrame, dates: pd.Series) -> pd.Series:
    """vehicle_id when exactly one service period holds the date, else None."""
    d = pd.to_datetime(dates, errors="coerce")
    hits = pd.DataFrame(index=dates.index)
    for r in vehicles.itertuples():
        ok = d.notna()
        if pd.notna(r.service_start):
            ok &= d >= r.service_start
        if pd.notna(r.service_end):
            ok &= d <= r.service_end
        hits[r.vehicle_id] = ok
    n = hits.sum(axis=1) if len(vehicles) else pd.Series(0, index=dates.index)
    out = pd.Series([None] * len(dates), index=dates.index, dtype=object)
    if len(vehicles):
        first = hits.idxmax(axis=1)
        out[n == 1] = first[n == 1]
    return out


def out_of_range(dates: pd.Series, first_day, last_day) -> pd.Series:
    """True where a date is before the first vehicle's service start or after today. Empty dates are not out of range."""
    ts = pd.to_datetime(dates)
    return ts.notna() & ((ts < pd.Timestamp(first_day)) | (ts > pd.Timestamp(last_day)))


def _quarantine_row(target: str, reason: str, row: pd.Series, file_col="source_file_no") -> dict:
    f, s, r = _src(row, file_col)
    return {"target_table": target, "reason": reason, "source_file_no": f, "source_sheet_no": s, "source_row_no": r,
            "payload": _payload(row)}


def _to_ts(s: pd.Series) -> pd.Series:
    return pd.to_datetime(s, errors="coerce")


# ---------------------------------------------------------------- build
def build_frames(parsed_dir, review_dir, vehicle_csv=None, merge_csv=None) -> dict:
    parsed_dir, review_dir = Path(parsed_dir), Path(review_dir)
    vehicle_csv = Path(vehicle_csv) if vehicle_csv else VEHICLE_CSV
    merge_csv = Path(merge_csv) if merge_csv else NAME_MERGE_CSV
    merge = _load_merge(merge_csv)
    vehicles = _load_vehicles(vehicle_csv)
    first_service = pd.to_datetime(vehicles["service_start"]).min().date()

    rev = _read(parsed_dir / "revenue.csv", dtype={"file_hash": str}, low_memory=False)
    price_in = _read(parsed_dir / "revenue_client_price.csv", dtype={"file_hash": str}, low_memory=False)
    maint = _read(parsed_dir / "maintenance.csv", dtype={"file_hash": str}, low_memory=False)
    drv = _read(parsed_dir / "driving_edited.csv", low_memory=False)
    corr_path = review_dir / "driving_corrections.csv"
    corr_in = _read(corr_path) if corr_path.exists() else pd.DataFrame(columns=["행 번호"])
    fc = _read(parsed_dir / "file_correspondence.csv", dtype={"file_hash": str})

    # ---- names
    books = {"client": NameBook("client", merge), "place": NameBook("place", merge)}
    books["client"].add(rev["client"])
    books["client"].add(price_in["client"])
    books["place"].add(rev["origin"] if "origin" in rev else pd.Series(dtype=object))
    books["place"].add(rev["destination"] if "destination" in rev else pd.Series(dtype=object))
    client_ent, client_alias, client_ids, nl_c = books["client"].tables()
    place_ent, place_alias, place_ids, nl_p = books["place"].tables()
    name_list = pd.concat([nl_c, nl_p], ignore_index=True)
    place_ent["region_code"] = None
    place_ent["lat"] = None
    place_ent["lon"] = None
    client_ent["business_no"] = None
    client_ent["place_id"] = None

    def cid(v):
        k = books["client"].key(v) if isinstance(v, str) else ""
        return client_ids.get(k) if k else None

    def pid(v):
        k = books["place"].key(v) if isinstance(v, str) else ""
        return place_ids.get(k) if k else None

    quarantine: list[dict] = []

    # ---- product
    p = price_in.copy().reset_index(drop=True)
    p["_client_id"] = p["client"].map(cid)
    ym = p["year_month"].astype(str).str.slice(0, 7)
    p["_ym"] = ym.where(p["year_month"].notna() & ym.str.match(r"^\d{4}-\d{2}$"), None)
    basis = p["price_basis"].astype(str)
    bad = (~basis.isin(["company", "invoice"])) | p["_ym"].isna() | p["_client_id"].isna()
    for _, r in p[bad].iterrows():
        quarantine.append(_quarantine_row("product", "price_not_loaded", r))
    p = p[~bad].copy()
    p["valid_from"] = pd.to_datetime(p["_ym"] + "-01")
    p["valid_to"] = p["valid_from"] + pd.offsets.MonthEnd(0)
    dup = p.duplicated(["_client_id", "price_basis", "valid_from"], keep="first")
    for _, r in p[dup].iterrows():
        quarantine.append(_quarantine_row("product", "duplicate_price", r))
    p = p[~dup].reset_index(drop=True)
    product = pd.DataFrame({
        "product_id": range(1, len(p) + 1), "client_id": p["_client_id"].astype(int), "route_id": None, "item": None,
        "price_basis": p["price_basis"], "unit": "ton", "unit_price": _num(p["unit_price"]),
        "valid_from": p["valid_from"].dt.date, "valid_to": p["valid_to"].dt.date,
        "sheet_supply_amount": _num(p["supply_amount"]), "sheet_vat": _num(p["vat"]), "sheet_total_amount": _num(p["total_amount"]),
        "source_file_no": _num(p["source_file_no"]), "source_sheet_no": _num(p["source_sheet_no"]),
        "source_row_no": p["source_row_nos"].map(_first_row_no),
    })
    # matrix revenue = tons x the month's price: the invoice price, else the company price (2015-2019 sheets have only that)
    month_price = {}
    for b in ("invoice", "company"):
        pb = product[(product["price_basis"] == b) & product["unit_price"].notna()]
        month_price[b] = {(c, str(v)[:7]): u for c, v, u in zip(pb["client_id"], pb["valid_from"], pb["unit_price"])}

    # ---- delivery
    d = rev.copy().reset_index(drop=True)
    d["_date"] = _to_ts(d["date"])
    d["_client_id"] = d["client"].map(cid)
    kind = d["table_kind"].astype(str)
    is_matrix = kind == "matrix"
    extra = d["extra"].map(lambda t: json.loads(t) if isinstance(t, str) and t.strip() else {})
    outside = extra.map(lambda e: bool(e.get("outside_label"))) & is_matrix
    reason = pd.Series([None] * len(d), dtype=object)
    reason[kind == "summary"] = "summary_table"
    reason[reason.isna() & d["_date"].isna()] = "no_date"
    reason[reason.isna() & out_of_range(d["_date"], first_service, dt.date.today())] = "date_out_of_range"
    reason[reason.isna() & is_matrix & (outside | d["_client_id"].isna())] = "matrix_outside_label"
    # a row with nothing measured (no weight, amount, quantity or trips) is a list or a note, not a delivery
    measured = pd.Series(False, index=d.index)
    for c in ("weight_ton", "weight_kg", "supply_amount", "amount", "total_amount", "quantity", "trips"):
        if c in d:
            measured |= _num(d[c]).notna()
    reason[reason.isna() & ~measured] = "no_measure"
    # older revenue-only workbooks: a row whose (date, client, kind) is also in the shared workbooks is a copy
    rev_h = set(fc.loc[fc["folder"] == "revenue", "file_hash"])
    drv_h = set(fc.loc[fc["folder"] == "driving", "file_hash"])
    only_h, shared_h = rev_h - drv_h, rev_h & drv_h
    key = list(zip(d["_date"], d["_client_id"], is_matrix))
    ok_now = reason.isna() & d["_client_id"].notna()
    shared_keys = {k for k, f, o in zip(key, d["file_hash"], ok_now) if o and f in shared_h}
    is_dup = pd.Series([bool(o and f in only_h and k in shared_keys) for k, f, o in zip(key, d["file_hash"], ok_now)], index=d.index)
    reason[reason.isna() & is_dup] = "duplicate_older_file"
    for _, r in rev[reason.notna().to_numpy()].assign(_reason=reason[reason.notna()].to_numpy()).iterrows():
        quarantine.append(_quarantine_row("delivery", r["_reason"], r.drop("_reason")))
    keep = d[reason.isna()].copy()
    ex = extra[reason.isna()]
    keep_matrix = is_matrix[reason.isna()]
    # route
    both = pd.Series([pid(o) for o in keep["origin"]], index=keep.index) if "origin" in keep else pd.Series([None] * len(keep), index=keep.index)
    dest = pd.Series([pid(o) for o in keep["destination"]], index=keep.index) if "destination" in keep else pd.Series([None] * len(keep), index=keep.index)
    pairs = sorted({(int(a), int(b)) for a, b in zip(both, dest) if pd.notna(a) and pd.notna(b)})
    route_ids = {pr: i for i, pr in enumerate(pairs, start=1)}
    route = pd.DataFrame({"route_id": list(route_ids.values()), "origin_place_id": [a for a, _ in pairs],
                          "dest_place_id": [b for _, b in pairs], "std_round_trip_km": None, "station_no": None},
                         columns=["route_id", "origin_place_id", "dest_place_id", "std_round_trip_km", "station_no"])
    # weight, amount
    w_ton = _num(keep["weight_ton"]) if "weight_ton" in keep else pd.Series(np.nan, index=keep.index)
    w_kg_in = _num(keep["weight_kg"]) if "weight_kg" in keep else pd.Series(np.nan, index=keep.index)
    weight = pd.Series(np.nan, index=keep.index)
    basis_w = pd.Series([None] * len(keep), index=keep.index, dtype=object)
    flags = pd.Series([None] * len(keep), index=keep.index, dtype=object)
    t = ~keep_matrix
    big = t & (w_ton >= 1000)
    small = t & (w_ton < 100)
    mid = t & w_ton.notna() & ~big & ~small
    weight[big] = w_ton[big]
    basis_w[big] = "kg"
    weight[small] = w_ton[small] * 1000
    basis_w[small] = "ton_x1000"
    for i in keep.index[mid]:
        flags[i] = {"weight_unit_ambiguous": True}
    weight[keep_matrix] = w_kg_in[keep_matrix]
    basis_w[keep_matrix & w_kg_in.notna()] = "matrix_kg"
    supply = _num(keep["supply_amount"]) if "supply_amount" in keep else pd.Series(np.nan, index=keep.index)
    amount_src = pd.Series([None] * len(keep), index=keep.index, dtype=object)
    amount_src[t & supply.notna()] = "sheet"
    unit_price = _num(keep["unit_price"]) if "unit_price" in keep else pd.Series(np.nan, index=keep.index)
    ymv = keep["_date"].dt.strftime("%Y-%m")
    for i in keep.index[keep_matrix]:
        if pd.isna(weight[i]):
            continue
        for b in ("invoice", "company"):
            up = month_price[b].get((keep.at[i, "_client_id"], ymv[i]))
            if up is not None and pd.notna(up):
                supply[i] = float(weight[i]) / 1000.0 * float(up)
                amount_src[i] = "computed_" + b
                break
            unit_price[i] = up
        else:
            supply[i] = np.nan
    cnt = lambda c: _num(keep[c]) if c in keep else pd.Series(np.nan, index=keep.index)  # noqa: E731
    txt = lambda c: _text(keep[c]) if c in keep else pd.Series([None] * len(keep), index=keep.index, dtype=object)  # noqa: E731
    delivery = pd.DataFrame({
        "date": keep["_date"].dt.date, "vehicle_id": _vehicle_by_date(vehicles, keep["_date"]),
        "client_id": keep["_client_id"], "route_id": [route_ids.get((int(a), int(b))) if pd.notna(a) and pd.notna(b) else None for a, b in zip(both, dest)],
        "origin_place_id": both, "dest_place_id": dest, "item": txt("item"), "weight_kg": weight, "trips": cnt("trips"),
        "unit_price": unit_price, "supply_amount": supply, "vat": cnt("vat").where(~keep_matrix),
        "total_amount": cnt("total_amount").where(~keep_matrix),
        "grain": np.where(keep_matrix, "client_day", "row"), "source_kind": np.where(keep_matrix, "matrix", "table"),
        "source_file_no": _num(keep["source_file_no"]), "source_sheet_no": _num(keep["source_sheet_no"]),
        "source_row_no": _num(keep["source_row_no"]),
        "source_col": [e.get("col") if m else None for e, m in zip(ex, keep_matrix)],
        "quantity": cnt("quantity"), "amount": cnt("amount"), "note": txt("note"), "amount_source": amount_src,
        "weight_basis": basis_w, "flags": flags,
    }, index=keep.index).reset_index(drop=True)
    delivery.insert(0, "delivery_id", range(1, len(delivery) + 1))
    delivery = delivery[DELIVERY_COLS]

    # ---- driving
    dv = drv.copy().reset_index(drop=True)
    dv["_date"] = _to_ts(dv["date"])
    vid = dv["vehicle_id"].map(lambda v: v.strip() if isinstance(v, str) else None) if "vehicle_id" in dv else pd.Series([None] * len(dv))
    vid = vid.where(vid.isin(set(vehicles["vehicle_id"])), None)
    hv = dv["has_values"].map(lambda v: str(v).strip().lower() not in ("false", "0", "no")) if "has_values" in dv else pd.Series(True, index=dv.index)
    for c in DRIVING_VALUE_COLS:
        dv[c] = _num(dv[c]) if c in dv else np.nan
    dr = pd.Series([None] * len(dv), dtype=object)
    dr[dv["_date"].isna()] = "no_date"
    dr[dr.isna() & vid.isna()] = "vehicle_unknown"
    dr[dr.isna() & ~hv] = "no_values"
    live = dr.isna()
    sig = dv[DRIVING_VALUE_COLS].round(6).astype(object).where(dv[DRIVING_VALUE_COLS].notna(), None)
    sig_t = pd.Series([tuple(r) for r in sig.itertuples(index=False)], index=dv.index)
    grp: dict = {}
    for i in dv.index[live]:
        grp.setdefault((vid[i], dv.at[i, "_date"]), []).append(i)
    for members in grp.values():
        if len(members) < 2:
            continue
        if len({sig_t[i] for i in members}) == 1:
            for i in members[1:]:
                dr[i] = "duplicate_identical"
        else:
            for i in members:
                dr[i] = "duplicate_conflict"
    for i in dv.index[dr.notna()]:
        quarantine.append(_quarantine_row("driving", dr[i], drv.iloc[i], file_col="source_file"))
    kd = dv[dr.isna()].copy().reset_index(drop=True)
    kd_vid = vid[dr.isna()].reset_index(drop=True)
    driving = pd.DataFrame({
        "driving_id": range(1, len(kd) + 1), "vehicle_id": kd_vid, "date": kd["_date"].dt.date, "user_id": None,
        **{c: kd[c] for c in DRIVING_VALUE_COLS},
        "source_file_no": _num(kd["source_file"]) if "source_file" in kd else np.nan,
        "source_sheet_no": _num(kd["source_sheet_no"]) if "source_sheet_no" in kd else np.nan,
        "source_row_no": _num(kd["source_row_no"]) if "source_row_no" in kd else np.nan,
        "entered_via": "excel", "flags": None,
    })
    row_to_driving = dict(zip(_num(kd["row_id"]).astype("Int64").tolist(), driving["driving_id"].tolist())) if "row_id" in kd else {}

    # ---- driving_correction
    c = corr_in
    unlinked = 0
    corr_rows = []
    if len(c) and "행 번호" in c:
        cols = list(c.columns)

        def col(row, name):
            return row[name] if name in cols else None

        for _, row in c.iterrows():
            rid = pd.to_numeric(row["행 번호"], errors="coerce")
            did = row_to_driving.get(int(rid)) if pd.notna(rid) else None
            if did is None:
                unlinked += 1
                continue
            corr_rows.append({"driving_id": did, "column_name": col(row, "칸"), "original_value": _as_text(col(row, "원래 값")),
                              "corrected_value": _as_text(col(row, "고친 값")), "rule": _as_text(col(row, "적용 규칙")),
                              "reason": _as_text(col(row, "규칙 설명")), "corrected_by": "pipeline"})
    driving_correction = pd.DataFrame(corr_rows, columns=["driving_id", "column_name", "original_value", "corrected_value", "rule",
                                                          "reason", "corrected_by"])
    driving_correction.insert(0, "correction_id", range(1, len(driving_correction) + 1))

    # ---- maintenance
    m = maint.copy().reset_index(drop=True)
    m["_date"] = _to_ts(m["date"])
    mt = lambda c_: _text(m[c_]) if c_ in m else pd.Series([None] * len(m), dtype=object)  # noqa: E731
    mn = lambda c_: _num(m[c_]) if c_ in m else pd.Series(np.nan, index=m.index)  # noqa: E731
    maintenance = pd.DataFrame({
        "maintenance_id": range(1, len(m) + 1), "date": m["_date"].dt.date, "vehicle_id": _vehicle_by_date(vehicles, m["_date"]),
        "item": mt("item"), "shop": mt("shop"), "quantity": mn("quantity"), "unit_price": mn("unit_price"), "cost": mn("cost"),
        "odometer_km": mn("odometer_km"), "note": mt("note"), "source_file_no": mn("source_file_no"),
        "source_sheet_no": mn("source_sheet_no"), "source_row_no": mn("source_row_no"),
    })

    q = pd.DataFrame(quarantine, columns=["target_table", "reason", "source_file_no", "source_sheet_no", "source_row_no", "payload"])
    q.insert(0, "quarantine_id", range(1, len(q) + 1))

    vehicle = vehicles.copy()
    for c_ in ("service_start", "service_end"):
        vehicle[c_] = vehicle[c_].dt.date
    frames = {
        "vehicle": vehicle, "place": place_ent[["place_id", "name", "region_code", "lat", "lon"]], "place_alias": place_alias,
        "client": client_ent[["client_id", "name", "business_no", "place_id"]], "client_alias": client_alias, "route": route,
        "product": product, "driving": driving, "driving_correction": driving_correction, "delivery": delivery,
        "maintenance": maintenance, "quarantine": q, "_name_list": name_list,
    }
    frames["_recon"] = reconciliation(frames, {"revenue.csv": (len(rev), "delivery"), "revenue_client_price.csv": (len(price_in), "product"),
                                               "maintenance.csv": (len(maint), "maintenance"), "driving_edited.csv": (len(drv), "driving"),
                                               "driving_corrections.csv": (len(c) if "행 번호" in c else 0, "driving_correction")},
                                      unlinked)
    return frames


def _as_text(v):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    return str(v)


def _first_row_no(v):
    try:
        lst = json.loads(v) if isinstance(v, str) else None
        return lst[0] if lst else np.nan
    except (ValueError, TypeError):
        return np.nan


def reconciliation(frames: dict, inputs: dict, unlinked_corr: int) -> pd.DataFrame:
    """input rows = loaded rows + quarantined rows (+ unlinked rows for driving_correction)."""
    q = frames["quarantine"]
    rows = []
    for fname, (n_in, table) in inputs.items():
        loaded = len(frames[table])
        quar = int((q["target_table"] == table).sum())
        unl = unlinked_corr if table == "driving_correction" else 0
        rows.append({"input_file": fname, "target_table": table, "input_rows": n_in, "loaded_rows": loaded,
                     "quarantined_rows": quar, "unlinked_rows": unl, "diff": n_in - loaded - quar - unl})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- DB
def resolve_dsn(dsn: str | None = None) -> str:
    return dsn or os.environ.get(DSN_ENV) or DEFAULT_DSN


def _db_ready(df: pd.DataFrame, table: str) -> pd.DataFrame:
    out = df.copy()
    for c in out.columns:
        if c in INT_COLS:
            out[c] = pd.Series([None if v is None or (not isinstance(v, str) and pd.isna(v)) else int(v) for v in out[c]],
                               index=out.index, dtype=object)
    out = out.astype(object).where(out.notna(), None)
    return out


def write_db(dsn: str | None, frames: dict) -> dict:
    """Recreate schema hub from db/schema.sql, insert every table frame, reset the serial sequences. Returns rows written per table."""
    from sqlalchemy import MetaData, Table, create_engine, text
    from sqlalchemy.dialects.postgresql import JSONB

    engine = create_engine(resolve_dsn(dsn))
    ddl = SCHEMA_SQL.read_text(encoding="utf-8")
    written = {}
    try:
        with engine.begin() as con:
            raw = con.connection.driver_connection
            with raw.cursor() as cur:
                cur.execute(ddl)
            for name in TABLE_ORDER:
                df = frames[name]
                written[name] = len(df)
                if not len(df):
                    continue
                # column types come from the created table, so an all-empty column is not sent as text
                table = Table(name, MetaData(), schema="hub", autoload_with=con)
                dtype = {c.name: c.type for c in table.columns if c.name in df.columns}
                dtype.update({c: JSONB for c in JSON_COLUMNS.get(name, [])})
                _db_ready(df, name).to_sql(name, con, schema="hub", if_exists="append", index=False, method="multi", chunksize=1000,
                                           dtype=dtype)
            for name, idc in ID_COLUMNS.items():
                con.execute(text(f"SELECT setval(pg_get_serial_sequence('hub.\"{name}\"', '{idc}'), "
                                 f"COALESCE((SELECT max({idc}) FROM hub.\"{name}\"), 1), "
                                 f"(SELECT max({idc}) FROM hub.\"{name}\") IS NOT NULL)"))
    finally:
        engine.dispose()
    return written


# ---------------------------------------------------------------- CLI
def print_summary(frames: dict) -> int:
    for name in TABLE_ORDER:
        print(f"table {name}: {len(frames[name])} rows")
    q = frames["quarantine"]
    by = q.groupby(["target_table", "reason"]).size() if len(q) else pd.Series(dtype=int)
    for (t, r), n in by.items():
        print(f"quarantine {t} {r}: {int(n)}")
    rc = frames["_recon"]
    for r in rc.itertuples():
        print(f"recon {r.input_file}: input {r.input_rows} = loaded {r.loaded_rows} + quarantined {r.quarantined_rows}"
              f" + unlinked {r.unlinked_rows}, diff {r.diff}")
    bad = int((rc["diff"] != 0).sum())
    print(f"reconciliation mismatches: {bad} of {len(rc)} input files")
    return bad


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Load 2nd-layer CSV files into the PostgreSQL hub (schema hub).")
    ap.add_argument("--dsn", help=f"SQLAlchemy URL (else env {DSN_ENV}, else the default local kilostone DB)")
    ap.add_argument("--dry-run", action="store_true", help="no DB: transform and reconcile only")
    ap.add_argument("--dummy", action="store_true", help="use tests/fixtures/hub_dummy (written if absent) instead of the real folders")
    args = ap.parse_args(argv)
    if args.dummy:
        from pipeline.make_dummy_hub import make_hub_dummy
        if not (DUMMY_DIR / "revenue.csv").exists():
            make_hub_dummy(DUMMY_DIR)
        parsed = review = DUMMY_DIR
        vehicle_csv = DUMMY_DIR / "dim_vehicle.csv"
        merge_csv = DUMMY_DIR / "name_merge.csv"
        report_dir = DUMMY_DIR
    else:
        cfg = load_config()
        parsed, review, report_dir = path_from(cfg, "parsed_dir"), path_from(cfg, "review_dir"), path_from(cfg, "reports_dir")
        vehicle_csv, merge_csv = VEHICLE_CSV, NAME_MERGE_CSV
        _ensure_merge_header(NAME_MERGE_CSV)
    frames = build_frames(parsed, review, vehicle_csv, merge_csv)
    write_csv(frames["_name_list"], parsed / "name_list.csv")
    write_csv(frames["_recon"], report_dir / "hub_load_reconciliation.csv")
    print("name_list rows:", len(frames["_name_list"]))
    bad = print_summary(frames)
    if not args.dry_run:
        written = write_db(args.dsn, frames)
        print("written to DB:", {k: v for k, v in written.items()})
    return 1 if bad else 0


def safe_main() -> int:
    try:
        return main()
    except Exception as e:  # exception text can carry cell values or the DSN
        print("failed, exception class:", type(e).__name__)
        return 1


if __name__ == "__main__":
    sys.exit(safe_main())
