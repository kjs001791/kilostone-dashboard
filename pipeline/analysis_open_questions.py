"""Open-question analysis for the driving logs. Prints counts, ratios and size buckets only.

Q1: are the two 2020 Daewoo files (same dates in both) different vehicles?
Q2: are the quarantined sheets unrelated to driving logs?
Raw paths come from pipeline/config.toml. No values, coordinates, sheet names or client names are printed or written.
"""
from __future__ import annotations

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
    ROOT, is_empty, list_excel, load_config, parse_date, parse_number, raw_subdir, write_text,
)
from pipeline import parse_driving as pdv  # noqa: E402

warnings.filterwarnings("ignore")
TOL = 1.1
OUT_JSON = ROOT / "pipeline" / "profiles" / "open_questions_result.json"


def bucket(x: float) -> str:
    x = abs(x)
    for lim, name in ((0.0005, "0"), (1.1, "<=1.1km"), (10, "1.1-10km"), (100, "10-100km"), (1000, "100-1000km"),
                      (10000, "1000-10000km")):
        if x <= lim:
            return name
    return ">=10000km"


# ------------------------------------------------------------------ Q1
def q1(cfg):
    folder = raw_subdir(cfg, "driving")
    (files, rows, recon, *_rest) = pdv.parse_folder(folder)
    df = pdv.to_frame(rows)
    rc = pd.DataFrame(recon)
    df["date"] = pd.to_datetime(df["date"])
    d = df[(df["vehicle"] == "Daewoo")].copy()
    res = {"daewoo_rows": int(len(d)), "daewoo_files": int(d["source_file"].nunique())}
    nf = d.groupby("date")["source_file"].nunique()
    shared_dates = nf[nf > 1].index
    res["dates_in_multiple_files"] = int(len(shared_dates))
    sh = d[d["date"].isin(shared_dates)]
    res["shared_by_year"] = {str(k): int(v) for k, v in sh.groupby(sh["date"].dt.year)["date"].nunique().items()}
    res["max_files_per_shared_date"] = int(nf[nf > 1].max())
    # file profile: the files that hold shared dates
    prof = []
    for no, x in sh.groupby("source_file"):
        full = d[d["source_file"] == no]
        prof.append((int(no), len(full), int(full["source_sheet_no"].nunique())))
    big = max(prof, key=lambda t: t[1])
    res["files_with_shared_dates"] = len(prof)
    res["hub_file"] = {"rows": big[1], "sheets": big[2], "years": sorted(int(y) for y in d[d.source_file == big[0]]["date"].dt.year.unique())}
    res["other_files_rows_quartiles"] = [float(v) for v in np.quantile([t[1] for t in prof if t[0] != big[0]], [0, .5, 1])]
    pair_counter = Counter()
    for dt_, g in sh.groupby("date"):
        pair_counter[tuple(sorted(int(v) for v in g["source_file"].unique()))] += 1
    hub_pairs = {k: v for k, v in pair_counter.items() if big[0] in k}
    res["pairs"] = {"total_pairs": len(pair_counter), "pairs_with_hub": len(hub_pairs),
                    "dates_in_hub_pairs": int(sum(hub_pairs.values())), "dates_in_other_pairs": int(sum(v for k, v in pair_counter.items() if big[0] not in k))}
    cols = ["fuel_efficiency", "distance", "cumulative_distance", "consumed_fuel", "refuel", "reurea"]
    hub = d[d["source_file"] == big[0]].drop_duplicates("date", keep="first").set_index("date")
    res["dup_dates_inside_hub_file"] = int(d[d["source_file"] == big[0]]["date"].duplicated().sum())

    def compare(pairs_files):
        out = Counter(); lv_all = []; per_col_null = Counter(); per_col_val = Counter()
        same_pos = 0
        for f in pairs_files:
            other = d[d["source_file"] == f].drop_duplicates("date", keep="first").set_index("date")
            for dt_ in other.index.intersection(hub.index):
                a, b = other.loc[dt_], hub.loc[dt_]
                null_dir = Counter(); val_diff = []
                for c in cols:
                    va, vb = a[c], b[c]
                    if pd.isna(va) and pd.isna(vb):
                        continue
                    if pd.isna(va) != pd.isna(vb):
                        null_dir["monthly_has_hub_blank" if pd.isna(vb) else "hub_has_monthly_blank"] += 1
                        per_col_null[c] += 1
                    elif abs(float(va) - float(vb)) > 1e-9:
                        val_diff.append(c); per_col_val[c] += 1
                if val_diff:
                    out["date_value_conflict(both filled, different)"] += 1
                elif null_dir:
                    out["date_blank_on_one_side_only"] += 1
                    for k in null_dir:
                        out["blank_direction:" + k] += 1
                else:
                    out["date_identical_or_both_blank"] += 1
                    if a["source_row_no"] == b["source_row_no"] and a["source_sheet_no"] == b["source_sheet_no"]:
                        same_pos += 1
                if pd.notna(a["cumulative_distance"]) and pd.notna(b["cumulative_distance"]):
                    lv_all.append(float(a["cumulative_distance"]) - float(b["cumulative_distance"]))
        return out, lv_all, per_col_null, per_col_val, same_pos

    o, lv, pcn, pcv, sp = compare([k[0] if k[1] == big[0] else k[1] for k in hub_pairs])
    res["hub_vs_monthly_dates"] = dict(o)
    res["cells_blank_on_one_side_by_column"] = dict(pcn)
    res["cells_with_conflicting_values_by_column"] = dict(pcv)
    res["cum_level_diff_where_both_filled"] = {"n": len(lv), "buckets": dict(Counter(bucket(x) for x in lv))}
    res["identical_dates_at_same_sheet_and_row_position"] = int(sp)

    # inside-file chain consistency
    def chain(x):
        x = x.dropna(subset=["cumulative_distance", "distance"]).drop_duplicates("date", keep=False).sort_values("date")
        gap = x["date"].diff().dt.days
        dc = x["cumulative_distance"].diff()
        m = gap == 1
        ok = ((dc[m] - x["distance"][m]).abs() <= TOL)
        return int(m.sum()), int(ok.sum())

    n, k = chain(d[d["source_file"] == big[0]])
    res["chain_hub_file"] = {"consecutive_pairs": n, "within_tol": k, "ratio": round(k / n, 4) if n else None}
    mon = [f for f in {k[0] if k[1] == big[0] else k[1] for k in hub_pairs}]
    n = k = 0
    for f in mon:
        a_, b_ = chain(d[d["source_file"] == f]); n += a_; k += b_
    res["chain_monthly_files_each_alone"] = {"files": len(mon), "consecutive_pairs": n, "within_tol": k, "ratio": round(k / n, 4) if n else None}
    # chain after merging monthly files + hub into one series (dedupe identical dates), what a single vehicle would have to satisfy
    merged = pd.concat([d[d["source_file"] == big[0]]] + [d[d["source_file"] == f] for f in mon])
    merged = merged.sort_values(["date", "cumulative_distance"], na_position="last").drop_duplicates("date", keep="first")
    n, k = chain(merged)
    res["chain_merged_one_series"] = {"consecutive_pairs": n, "within_tol": k, "ratio": round(k / n, 4) if n else None}
    # chain across files' boundary: last row of each monthly file vs first row of next month inside hub
    # non-hub shared dates (2021, 2022)
    other_pairs = [k for k in pair_counter if big[0] not in k]
    oc = Counter(); olv = []
    for a_no, b_no in other_pairs:
        A = d[d["source_file"] == a_no].drop_duplicates("date").set_index("date"); B = d[d["source_file"] == b_no].drop_duplicates("date").set_index("date")
        for dt_ in A.index.intersection(B.index):
            ra, rb = A.loc[dt_], B.loc[dt_]
            same_ = all((pd.isna(ra[c]) and pd.isna(rb[c])) or (pd.notna(ra[c]) and pd.notna(rb[c]) and abs(ra[c] - rb[c]) <= 1e-9) for c in cols)
            oc["identical" if same_ else "different"] += 1
            if not same_ and pd.notna(ra["cumulative_distance"]) and pd.notna(rb["cumulative_distance"]):
                olv.append(float(ra["cumulative_distance"] - rb["cumulative_distance"]))
    res["non_hub_shared_dates"] = {"n_pairs": len(other_pairs), **dict(oc), "cum_level_diff_buckets_on_different": dict(Counter(bucket(x) for x in olv))}
    # raw-level: do rows in the hub file at blank dates still have date but no numbers?
    hub_all = d[d["source_file"] == big[0]]
    res["hub_rows_with_all_measures_blank"] = int(hub_all[cols].isna().all(axis=1).sum())
    res["hub_rows_total"] = int(len(hub_all))
    return res


# ------------------------------------------------------------------ Q2
def sheet_features(df: pd.DataFrame) -> dict:
    n_r, n_c = df.shape
    cnt = Counter()
    date_cols = Counter()
    ndate = 0
    for c in range(n_c):
        col = df.iloc[:, c].tolist()
        for v in col:
            if is_empty(v):
                continue
            if parse_date(v)[1] == "ok" and not isinstance(v, (int, float, np.integer, np.floating)):
                cnt["D"] += 1
                date_cols[c] += 1
                continue
            _, k = parse_number(v)
            if k == "ok":
                cnt["N"] += 1
            else:
                cnt["S"] += 1
    tot = sum(cnt.values()) or 1
    dcol = date_cols.most_common(1)[0][0] if date_cols else -1
    filled_rows = int((df.notna().sum(axis=1) > 0).sum())
    return {
        "rows": int(filled_rows), "cols": int(df.dropna(axis=1, how="all").shape[1]),
        "n_share": cnt["N"] / tot, "s_share": cnt["S"] / tot, "d_share": cnt["D"] / tot,
        "date_cells": int(cnt["D"]), "date_col_pos": int(dcol), "n_date_cols": len(date_cols),
        "fill_density": float(tot / max(1, filled_rows * max(1, df.dropna(axis=1, how="all").shape[1]))),
    }


def collect(folder: Path, group: str, only_files=None):
    out = []
    for fno, f in enumerate(list_excel(folder), start=1):
        try:
            book = pd.read_excel(f, sheet_name=None, header=None, dtype=object)
        except Exception:
            continue
        for sno, (_, df) in enumerate(book.items(), start=1):
            if len(df) > 5000 or df.shape[1] > 200:
                df = df.iloc[:5000, :200]
            try:
                info_status = None
                if group == "driving":
                    _, _, info = pdv.parse_sheet(df, fno, sno)
                    info_status = info["status"]
                    veh = info["vehicle"]
                else:
                    veh = None
                ft = sheet_features(df)
            except Exception:
                continue
            ft.update({"group": group, "file": fno, "sheet": sno, "status": info_status, "vehicle": veh})
            out.append(ft)
    return out


FEATS = ["rows", "cols", "n_share", "s_share", "d_share", "date_col_pos", "fill_density"]


def q2(cfg):
    recs = collect(raw_subdir(cfg, "driving"), "driving")
    rev = raw_subdir(cfg, "revenue")
    mnt = raw_subdir(cfg, "maintenance")
    recs += collect(rev, "revenue") if rev else []
    recs += collect(mnt, "maintenance") if mnt else []
    f = pd.DataFrame(recs)
    res = {"sheets_total": int(len(f))}
    drv = f[f.group == "driving"]
    res["driving_sheets_by_status"] = drv["status"].value_counts().to_dict()
    q = drv[drv.status.isin(["unknown_layout", "no_data_row"])]
    ok = drv[drv.status == "ok"]
    res["quarantined"] = {"n": int(len(q)), "by_status": q["status"].value_counts().to_dict(), "files": int(q["file"].nunique())}
    # file membership
    files_q = set(q["file"])
    files_ok = set(ok["file"])
    res["quarantined_file_membership"] = {
        "files_with_quarantined": len(files_q),
        "of_which_also_have_ok_driving_sheet": len(files_q & files_ok),
        "files_only_quarantined": len(files_q - files_ok),
        "files_only_ok": len(files_ok - files_q),
        "sheets_per_quarantined_file_quartiles": [float(x) for x in np.quantile(q.groupby("file").size(), [0, .5, 1])],
        "single_sheet_files_among_quarantined": int((q.groupby("file").size() == 1).sum()),
    }
    # file number ranges
    res["file_no_range"] = {"quarantined": [int(q.file.min()), int(q.file.max())],
                            "ok": [int(ok.file.min()), int(ok.file.max())] if len(ok) else None}
    # feature summaries
    def summ(x):
        return {c: [round(float(v), 3) for v in np.quantile(x[c], [.1, .5, .9])] for c in FEATS} | {"n": int(len(x))}
    res["features_p10_p50_p90"] = {
        "quarantined": summ(q),
        "driving_ok_all": summ(ok),
        **{f"driving_ok_{v}": summ(ok[ok.vehicle == v]) for v in ok.vehicle.unique() if (ok.vehicle == v).sum() >= 5},
        "revenue": summ(f[f.group == "revenue"]),
        "maintenance": summ(f[f.group == "maintenance"]),
    }
    # nearest-neighbour group for each quarantined sheet (standardised features, leave nothing out: quarantined not in reference)
    ref = pd.concat([
        ok.assign(ref=("drv_" + ok.vehicle.astype(str))),
        f[f.group == "revenue"].assign(ref="revenue"),
        f[f.group == "maintenance"].assign(ref="maintenance"),
    ])
    Xr = ref[FEATS].copy()
    Xr["rows"] = np.log1p(Xr["rows"]); Xr["cols"] = np.log1p(Xr["cols"])
    mu, sd = Xr.mean(), Xr.std().replace(0, 1)
    Zr = ((Xr - mu) / sd).values
    Xq = q[FEATS].copy()
    Xq["rows"] = np.log1p(Xq["rows"]); Xq["cols"] = np.log1p(Xq["cols"])
    Zq = ((Xq - mu) / sd).values
    labels = ref["ref"].values
    votes = Counter()
    k = 5
    for z in Zq:
        dist = np.sqrt(((Zr - z) ** 2).sum(axis=1))
        idx = np.argsort(dist)[:k]
        votes[Counter(labels[idx]).most_common(1)[0][0]] += 1
    res["knn5_nearest_group_of_quarantined"] = dict(votes)
    # nearest per reference-family (drv_* merged)
    fam = Counter()
    for z in Zq:
        dist = np.sqrt(((Zr - z) ** 2).sum(axis=1))
        idx = np.argsort(dist)[:k]
        fam[Counter("driving" if str(labels[i]).startswith("drv_") else labels[i] for i in idx).most_common(1)[0][0]] += 1
    res["knn5_family"] = dict(fam)
    # sanity: leave-one-out of driving-ok sheets against revenue/maintenance/other drv (does the metric separate?)
    corr = 0
    sub = ref[ref.ref.str.startswith("drv_")].sample(min(150, int(ref.ref.str.startswith("drv_").sum())), random_state=1)
    for i in sub.index if False else range(len(sub)):
        pass
    loo_ok = 0
    refl = ref.reset_index(drop=True)
    samp = refl[refl.ref.str.startswith("drv_")].sample(min(150, int(refl.ref.str.startswith("drv_").sum())), random_state=1)
    for i, row in samp.iterrows():
        dist = np.sqrt(((Zr - Zr[i]) ** 2).sum(axis=1)); dist[i] = 1e9
        idx = np.argsort(dist)[:k]
        fam_l = Counter("driving" if str(labels[j]).startswith("drv_") else labels[j] for j in idx).most_common(1)[0][0]
        loo_ok += int(fam_l == "driving")
    res["loo_driving_sheets_classified_as_driving"] = {"tested": int(len(samp)), "correct": loo_ok}
    revs = refl[refl.ref == "revenue"].sample(min(150, int((refl.ref == "revenue").sum())), random_state=1)
    loo_r = 0
    for i, row in revs.iterrows():
        dist = np.sqrt(((Zr - Zr[i]) ** 2).sum(axis=1)); dist[i] = 1e9
        idx = np.argsort(dist)[:k]
        fam_l = Counter("driving" if str(labels[j]).startswith("drv_") else labels[j] for j in idx).most_common(1)[0][0]
        loo_r += int(fam_l == "revenue")
    res["loo_revenue_sheets_classified_as_revenue"] = {"tested": int(len(revs)), "correct": loo_r}
    # structural split of quarantined: date cells and layout shape
    res["quarantined_shape"] = {
        "date_cells_per_sheet_quartiles": [float(x) for x in np.quantile(q["date_cells"], [.1, .5, .9])],
        "date_col_pos_counts": q["date_col_pos"].value_counts().head(5).to_dict(),
        "n_date_cols_counts": q["n_date_cols"].value_counts().head(5).to_dict(),
        "sheets_with_1plus_numeric_share_over_0.3": int((q.n_share > 0.3).sum()),
    }
    return res, q


def col_sig(df: pd.DataFrame, n=11) -> str:
    out = []
    for c in range(min(n, df.shape[1])):
        cnt = Counter()
        for v in df.iloc[:, c].tolist():
            if is_empty(v):
                cnt["B"] += 1
            elif parse_date(v)[1] == "ok" and not isinstance(v, (int, float, np.integer, np.floating)):
                cnt["D"] += 1
            elif parse_number(v)[1] == "ok":
                cnt["N"] += 1
            else:
                cnt["S"] += 1
        out.append(cnt.most_common(1)[0][0] if cnt else "B")
    return "".join(out)


def signature_compare(cfg, q):
    """Column-type signature (N/S/D/B, 11 cols) of quarantined sheets vs revenue and driving-ok sheets, same function on all."""
    def sigs(folder, only=None, status_ok=False, fno_filter=None):
        out = Counter()
        for fno, f in enumerate(list_excel(folder), start=1):
            if only is not None and fno not in only:
                continue
            try:
                book = pd.read_excel(f, sheet_name=None, header=None, dtype=object)
            except Exception:
                continue
            for sno, (_, df) in enumerate(book.items(), start=1):
                if fno_filter is not None and (fno, sno) not in fno_filter:
                    continue
                out[col_sig(df.iloc[:3000, :40])] += 1
        return out

    drv_folder = raw_subdir(cfg, "driving")
    qkeys = set(zip(q.file, q.sheet))
    sq = sigs(drv_folder, fno_filter=qkeys)
    sr = sigs(raw_subdir(cfg, "revenue"))
    res = {}
    res["quarantined_distinct_signatures"] = len(sq)
    res["quarantined_top_signature_share"] = round(sq.most_common(1)[0][1] / sum(sq.values()), 3)
    rev_set = set(sr)
    res["quarantined_sheets_with_signature_also_in_revenue"] = int(sum(v for k, v in sq.items() if k in rev_set))
    # signature in driving-ok sheets
    drv_all = {}
    for fno, f in enumerate(list_excel(drv_folder), start=1):
        try:
            book = pd.read_excel(f, sheet_name=None, header=None, dtype=object)
        except Exception:
            continue
        for sno, (_, df) in enumerate(book.items(), start=1):
            if (fno, sno) in qkeys:
                continue
            drv_all[col_sig(df.iloc[:3000, :40])] = drv_all.get(col_sig(df.iloc[:3000, :40]), 0) + 1
    res["quarantined_sheets_with_signature_also_in_driving_ok"] = int(sum(v for k, v in sq.items() if k in drv_all))
    res["quarantined_sheets_with_signature_in_neither"] = int(sum(v for k, v in sq.items() if k not in drv_all and k not in rev_set))
    res["revenue_sheets_total"] = int(sum(sr.values()))
    return res


def q2_extra(cfg):
    """Folder overlap (content hash, nothing printed but counts) and what sits under the date label of no_data_row sheets."""
    import hashlib
    dr = list_excel(raw_subdir(cfg, "driving"))
    rv = list_excel(raw_subdir(cfg, "revenue"))
    h = lambda p: hashlib.md5(p.read_bytes()).hexdigest()
    hd = [h(p) for p in dr]
    hr = {h(p) for p in rv}
    res = {"driving_files": len(dr), "revenue_files": len(rv), "driving_files_byte_identical_to_a_revenue_file": int(sum(1 for x in hd if x in hr))}
    c = Counter()
    for fno, f in enumerate(dr, start=1):
        try:
            book = pd.read_excel(f, sheet_name=None, header=None, dtype=object)
        except Exception:
            continue
        for sno, (_, df) in enumerate(book.items(), start=1):
            hr_, dc = pdv.find_header(df)
            if hr_ is None or pdv.build_header(df, hr_, dc) is not None:
                continue
            kinds = Counter()
            for v in df.iloc[hr_ + 1:hr_ + 12, dc].tolist():
                if is_empty(v):
                    kinds["blank"] += 1
                else:
                    x, k = parse_number(v)
                    kinds["number" if k == "ok" else "text"] += 1
            c["no_data_row sheets: most common cell kind under date label = " + kinds.most_common(1)[0][0]] += 1
            blk = df.iloc[hr_ + 1:hr_ + 12, :]
            nn = sum(1 for j in range(blk.shape[1]) if sum(parse_number(v)[1] == "ok" for v in blk.iloc[:, j]) >= 3)
            c["no_data_row sheets with 3+ numeric columns"] += int(nn >= 3)
    res.update(dict(c))
    return res


def main() -> int:
    cfg = load_config()
    out = {}
    out["q1"] = q1(cfg)
    out["q2"], q = q2(cfg)
    out["q2_signature"] = signature_compare(cfg, q)
    out["q2_extra"] = q2_extra(cfg)
    io.open(OUT_JSON, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    return 0


def safe_main() -> int:
    try:
        return main()
    except Exception as e:  # exception text can carry cell values
        import traceback
        tb = traceback.extract_tb(e.__traceback__)
        print("failed, exception class:", type(e).__name__, "line:", tb[-1].lineno)
        return 1


if __name__ == "__main__":
    sys.exit(safe_main())
