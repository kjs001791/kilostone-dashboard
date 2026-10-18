"""Run the editing algorithm on the parsed real driving table and write the review files.

Reads data/parsed/driving.csv (written by parse_driving.py). Writes under data/review/ (values, not for Claude)
and reports/ (counts and scores only). Console output: counts and scores only.
"""
from __future__ import annotations

import io
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common import KOREAN, decimals_hist, infer_decimals, load_config, path_from, write_csv, write_text  # noqa: E402
from pipeline.edit_driving import BASELINE, EditConfig, edit  # noqa: E402
from pipeline.evaluate import describe, fmt, run_and_score, table_md  # noqa: E402
from pipeline.make_dummy import SETTINGS, inject  # noqa: E402

RULE_KO = {
    "date_fixed_rule": "이상 날짜를 같은 시트의 앞뒤 행으로 맞춤",
    "copy_previous_day": "전날 값을 그대로 베낀 것으로 보고 앞뒤 값에서 되짚어 고침",
    "typo_inversion": "숫자 오타(자리 바꿈, 자리 누락, 자리 추가, 다른 숫자)로 설명되는 값이 하나뿐이라 고침",
    "min_cells": "고칠 칸이 가장 적은 답이 하나뿐이라 고침",
    "distance_two_relations": "연비 x 연료와 속도 x 시간이 같은 값을 가리키고 오타 후보가 하나뿐이라 주행거리를 고침(누적거리 검사를 못 하는 행)",
}
SOFT_KO = {"fuel_efficiency_x_fuel": "연비 x 연료소모량이 주행거리와 안 맞음(경고만, 값은 안 고침)",
           "speed_x_time": "속도 x 시간이 주행거리와 안 맞음(경고만, 값은 안 고침)"}
COL_KO = {"distance": KOREAN["distance"], "cumulative_distance": KOREAN["cumulative_distance"], "date": KOREAN["date"]}
CONF_KO = {"high": "높음", "medium": "보통"}
REASON_KO = {
    "same_date_conflicting_rows": "같은 날짜가 두 곳에 있고 값이 다름(차가 두 대이거나 겹친 파일일 수 있음)",
    "equality_violated_no_unique_fix": "누적거리와 주행거리 합이 안 맞고 고칠 답이 하나로 안 정해짐",
    "inequality_violated_no_unique_fix": "날짜가 끊긴 구간에서 누적거리가 덜 늘었고 고칠 답이 하나로 안 정해짐",
    "abnormal_date_not_unique": "날짜가 이상한데 앞뒤 행으로 하나로 못 정함",
}


def mad_stats(x: np.ndarray):
    x = x[~np.isnan(x)]
    if len(x) < 10:
        return None
    med = float(np.median(x))
    mad = float(np.median(np.abs(x - med)))
    return (med, mad) if mad > 0 else None


def modified_z(v, st):
    if st is None or v is None or np.isnan(v):
        return np.nan
    return 0.6745 * (v - st[0]) / st[1]


def add_z(fixed: pd.DataFrame, corr: pd.DataFrame, unres: pd.DataFrame) -> pd.DataFrame:
    touched = set(corr["row_id"].astype(int)) if len(corr) else set()
    ures = set()
    if len(unres):
        for s in unres["row_ids"]:
            ures.update(int(x) for x in str(s).split())
    f = fixed.sort_values(["vehicle", "date", "source_file", "source_sheet_no", "source_row_no"], kind="stable").copy()
    f["normal"] = ~f["row_id"].isin(touched | ures)
    prev_c = f.groupby("vehicle")["cumulative_distance"].shift(1)
    prev_d = f.groupby("vehicle")["date"].shift(1)
    consecutive = (f["date"] - prev_d).dt.days == 1
    f["incr"] = np.where(consecutive, f["cumulative_distance"] - prev_c, np.nan)
    stats = {}
    for veh, g in f[f["normal"]].groupby("vehicle"):
        d = g["distance"].to_numpy(float)
        inc = g["incr"].to_numpy(float)
        stats[veh] = {"distance": mad_stats(d[d > 0]), "cumulative_distance": mad_stats(inc[inc > 0])}
    fi = f.set_index("row_id")
    zs = []
    for r in corr.itertuples():
        veh = fi.at[r.row_id, "vehicle"]
        if r.column == "distance":
            z = modified_z(float(fi.at[r.row_id, "distance"]), stats.get(veh, {}).get("distance"))
        elif r.column == "cumulative_distance":
            z = modified_z(float(fi.at[r.row_id, "incr"]) if not pd.isna(fi.at[r.row_id, "incr"]) else np.nan, stats.get(veh, {}).get("cumulative_distance"))
        else:
            z = np.nan
        zs.append(z)
    out = corr.copy()
    out["z"] = zs
    return out, f, stats


def real_injected_eval(fixed_df: pd.DataFrame, corr, unres, info, cfg, cfg_edit):
    """Cut maximal runs of consecutive rows that pass every relation (no correction, no unresolved), inject errors, score."""
    touched = set(corr["row_id"].astype(int)) if len(corr) else set()
    ures = set()
    if len(unres):
        for s in unres["row_ids"]:
            ures.update(int(x) for x in str(s).split())
    f = fixed_df.sort_values(["vehicle", "date", "source_file", "source_sheet_no", "source_row_no"], kind="stable").reset_index(drop=True)
    runs = []
    for veh, g in f.groupby("vehicle", sort=False):
        if veh not in info["tol"]:
            continue
        tol = info["tol"][veh]
        g = g[g["cumulative_distance"].notna() & g["distance"].notna() & ~g["row_id"].isin(touched | ures | info["excluded_rows"])]
        cur = []
        prev = None
        for r in g.itertuples():
            gapdays = (r.date - prev.date).days if prev is not None else 0
            diff = r.cumulative_distance - prev.cumulative_distance if prev is not None else 0.0
            # consecutive days must satisfy the equation; a gap in dates must satisfy the inequality (C advances at least by D)
            ok = prev is not None and gapdays >= 1 and ((gapdays == 1 and abs(diff - r.distance) <= tol + 1e-9) or (gapdays > 1 and diff - r.distance >= -tol - 1e-9))
            if ok:
                cur.append(r)
            else:
                if len(cur) >= 10:
                    runs.append(cur)
                cur = [r]
            prev = r
        if len(cur) >= 10:
            runs.append(cur)
    if not runs:
        return None
    rows = []
    for k, run in enumerate(runs, start=1):
        for j, r in enumerate(run):
            rows.append({"vehicle": r.vehicle, "date": r.date, "distance": r.distance, "cumulative_distance": r.cumulative_distance,
                         "consumed_fuel": getattr(r, "consumed_fuel", np.nan), "fuel_efficiency": getattr(r, "fuel_efficiency", np.nan),
                         "speed": getattr(r, "speed", np.nan), "time_h": getattr(r, "time_h", np.nan),
                         "source_file": k, "source_sheet_no": 1, "source_row_no": j + 1, "has_values": True})
    clean = pd.DataFrame(rows)
    clean["row_id"] = range(1, len(clean) + 1)
    units = {v: (info["units"][v][0], info["units"][v][1]) for v in info["units"]}
    dirty, truth = inject(clean, cfg["seeds"]["real_inject"], "dev", error_rate=0.12, spacing=4, units_override=units,
                          mix={k: v for k, v in SETTINGS["dev"]["mix"].items()})
    o, per, *_ = run_and_score(clean, dirty, truth, cfg_edit)
    return o, per, len(runs), len(clean), len(truth)


def main() -> int:
    cfg = load_config()
    parsed = path_from(cfg, "parsed_dir")
    review = path_from(cfg, "review_dir")
    reports = path_from(cfg, "reports_dir")
    df = pd.read_csv(parsed / "driving.csv", encoding="utf-8-sig", parse_dates=["date"])
    rc = pd.read_csv(parsed / "driving_reconciliation.csv", encoding="utf-8-sig")
    cfg_edit = EditConfig(use_mincell=False)  # round 3 setting chosen on the dev set (reports/dummy_eval.md section 2): all typo kinds, min-cell pass off
    # round 2 editor on the same table, for the before/after counts
    _, corr0, unres0, info0 = edit(df, EditConfig(policy="legacy", use_mincell=True))
    warn0 = {w["row_id"] for w in info0.get("soft_warnings", [])}
    rows0 = sum(len([x for x in str(r).split() if int(x) in set(df["row_id"])]) for r in unres0["row_ids"]) if len(unres0) else 0
    fixed, corr, unres, info = edit(df, cfg_edit)
    corr, f_sorted, zstats = add_z(fixed, corr, unres)
    write_csv(fixed, parsed / "driving_edited.csv")
    fi = fixed.set_index("row_id")
    # ---- corrections list
    c = corr.copy()
    if len(c):
        c = c.merge(df[["row_id", "source_file", "source_sheet_no", "source_row_no", "vehicle"]], on="row_id", how="left")
        c["날짜(고친 뒤)"] = c["row_id"].map(fi["date"])
        out = pd.DataFrame({
            "행 번호": c["row_id"], "원본 파일 순번": c["source_file"], "원본 시트 순번": c["source_sheet_no"], "원본 행 번호": c["source_row_no"],
            "차량 양식": c["vehicle"], "날짜(고친 뒤)": c["날짜(고친 뒤)"], "칸": c["column"], "칸 설명": c["column"].map(COL_KO),
            "원래 값": c["old_value"], "고친 값": c["new_value"], "적용 규칙": c["rule"], "규칙 설명": c["rule"].map(RULE_KO),
            "확실한 정도": c["confidence"].map(CONF_KO), "수정 Z 점수": c["z"].round(2),
            "Z 점수 3.5 초과": np.where(c["z"].abs() > 3.5, "예", np.where(c["z"].isna(), "해당 없음", "아니오")),
        })
    else:
        out = pd.DataFrame(columns=["행 번호"])
    write_csv(out, review / "driving_corrections.csv")
    # ---- review list
    parts = []
    base_cols = ["row_id", "source_file", "source_sheet_no", "source_row_no", "vehicle", "date", "distance", "cumulative_distance"]
    orig = df.set_index("row_id")
    if len(c):
        hi = c[c["z"].abs() > 3.5]
        for r in hi.itertuples():
            row = orig.loc[r.row_id]
            parts.append({"확인 사유": "고친 값의 수정 Z 점수가 3.5 초과", "행 번호": r.row_id, "원본 파일 순번": row["source_file"], "원본 시트 순번": row["source_sheet_no"],
                          "원본 행 번호": row["source_row_no"], "차량 양식": row["vehicle"], "날짜": row["date"], "1일 주행거리(km)": row["distance"],
                          "누적 주행거리(km)": row["cumulative_distance"], "비고": f"{COL_KO[r.column]} {r.old_value} -> {r.new_value}"})
    n_unres_rows = 0
    if len(unres):
        for r in unres.itertuples():
            for x in str(r.row_ids).split():
                rid = int(x)
                if rid not in orig.index:
                    continue
                row = orig.loc[rid]
                n_unres_rows += 1
                parts.append({"확인 사유": "미해결(고칠 답이 하나로 안 정해짐)", "행 번호": rid, "원본 파일 순번": row["source_file"], "원본 시트 순번": row["source_sheet_no"],
                              "원본 행 번호": row["source_row_no"], "차량 양식": row["vehicle"], "날짜": row["date"], "1일 주행거리(km)": row["distance"],
                              "누적 주행거리(km)": row["cumulative_distance"], "비고": REASON_KO.get(r.reason, r.reason)})
    listed = {int(x) for s_ in unres["row_ids"] for x in str(s_).split()} if len(unres) else set()
    n_warn = 0
    seen_w = set()
    for w in info.get("soft_warnings", []):
        if w["row_id"] in listed or w["row_id"] in seen_w or w["row_id"] not in orig.index:
            continue
        seen_w.add(w["row_id"])
        row = orig.loc[w["row_id"]]
        n_warn += 1
        parts.append({"확인 사유": "소프트 규칙 경고", "행 번호": w["row_id"], "원본 파일 순번": row["source_file"], "원본 시트 순번": row["source_sheet_no"],
                      "원본 행 번호": row["source_row_no"], "차량 양식": row["vehicle"], "날짜": row["date"], "1일 주행거리(km)": row["distance"],
                      "누적 주행거리(km)": row["cumulative_distance"], "비고": SOFT_KO.get(w["rule"], w["rule"])})
    touched = set(corr["row_id"]) if len(corr) else set()
    ures_ids = {int(x) for s in unres["row_ids"] for x in str(s).split()} if len(unres) else set()
    pool = df[~df["row_id"].isin(touched | ures_ids) & df["date"].notna() & df["distance"].notna()]
    rng = np.random.default_rng(cfg["seeds"]["real_inject"])
    pick = pool.iloc[rng.choice(len(pool), size=min(30, len(pool)), replace=False)] if len(pool) else pool
    for r in pick.itertuples():
        parts.append({"확인 사유": "정상으로 통과한 행(놓친 오류를 세기 위한 무작위 표본)", "행 번호": r.row_id, "원본 파일 순번": r.source_file, "원본 시트 순번": r.source_sheet_no,
                      "원본 행 번호": r.source_row_no, "차량 양식": r.vehicle, "날짜": r.date, "1일 주행거리(km)": r.distance,
                      "누적 주행거리(km)": r.cumulative_distance, "비고": ""})
    rv = pd.DataFrame(parts)
    write_csv(rv, review / "driving_review_list.csv")

    # ---- counts for the summary
    by_rule = Counter(corr["rule"]) if len(corr) else Counter()
    by_col = Counter(corr["column"]) if len(corr) else Counter()
    zdef = corr["z"].dropna() if len(corr) else pd.Series(dtype=float)
    aux = float((zdef.abs() > 3.5).mean()) if len(zdef) else float("nan")
    n_unres_groups = int(len(unres))
    unres_reasons = Counter(unres["reason"]) if len(unres) else Counter()
    print("unresolved by reason:", dict(unres_reasons))
    print("rows in:", len(df), " corrections:", len(corr), " by rule:", dict(by_rule), " by column:", dict(by_col))
    print("unresolved groups:", n_unres_groups, " rows:", n_unres_rows, " duplicates identical/conflict:", info["dup_identical"], info["dup_conflict"])
    print("aux metric (corrections with |M|>3.5 / with M defined):", fmt(aux), f"({int((zdef.abs() > 3.5).sum())}/{len(zdef)})")
    print("review list rows:", len(rv), " by reason:", dict(Counter(rv["확인 사유"])) if len(rv) else {})
    print("round 1 editor on the same table: corrections", len(corr0), " unresolved groups", len(unres0), " rows", rows0, "| round 2: corrections", len(corr), " groups", n_unres_groups, " rows", n_unres_rows)
    warn1 = {w["row_id"] for w in info.get("soft_warnings", [])}
    print("round 2 editor: auto-fixed cells", len(corr0), "(distance", int((corr0["column"] == "distance").sum()), ") soft-warning rows", len(warn0), "| round 3: auto-fixed cells", len(corr),
          "(distance", int((corr["column"] == "distance").sum()), ", by the two-relation rule", by_rule.get("distance_two_relations", 0), ") soft-warning rows", len(warn1))
    _, corr_on, unres_on, _ = edit(df, EditConfig(use_mincell=True))
    rows_on = sum(len([x for x in str(r).split() if int(x) in set(df["row_id"])]) for r in unres_on["row_ids"]) if len(unres_on) else 0
    print("same editor with the min-cell pass on (not the dev-chosen setting): corrections", len(corr_on), " unresolved groups", len(unres_on), " rows", rows_on)
    print("two-relation distance fix, row decisions:", info.get("fix_counts"))
    print("checks available by vehicle (from the columns the rows hold):", info.get("checks"))
    print("soft warning rows by fix status:", dict(Counter(w["fix_status"] for w in info.get("soft_warnings", []) if True)))
    print("same-day rows merged (blanks filled):", info.get("dup_merged", 0), " soft warning rows listed:", n_warn)
    print("tolerance by vehicle:", {k: round(v, 3) for k, v in info["tol"].items()})

    # ---- tolerance basis (decimals statistics) and summary report
    L = ["# 실제 실행 요약 (운행기록)", "", "`pipeline/parse_driving.py`, `pipeline/run_real.py` 의 실행 결과입니다. 이 문서에는 건수와 칸 이름과 점수만 있고 값은 없습니다.", "",
         "## 1. 파일별 대사 (시트 단위 합계)", ""]
    tot = {k: int(rc[k].sum()) for k in ("source_rows", "loaded", "excluded_blank", "excluded_total", "excluded_text", "quarantined")}
    L += [f"원천 행 {tot['source_rows']} = 적재 {tot['loaded']} + 제외(빈 행) {tot['excluded_blank']} + 제외(합계 행) {tot['excluded_total']} + 제외(숫자도 날짜도 없는 글자 행) {tot['excluded_text']} + 격리 {tot['quarantined']}. "
          f"합이 안 맞는 시트 {int((~rc['balanced']).sum())}개 (전체 시트 {len(rc)}개).", "",
          "| 시트 처리 결과 | 시트 수 | 원천 행 | 적재 | 격리 |", "|---|---|---|---|---|"]
    for st, g in rc.groupby("status"):
        L.append(f"| {st} | {len(g)} | {int(g['source_rows'].sum())} | {int(g['loaded'].sum())} | {int(g['quarantined'].sum())} |")
    L += ["", "격리 시트(`unknown_layout`, `no_data_row`)는 세 양식(MAN, 대우프리마, 스카니아)에 안 맞는 시트입니다. 이 폴더에는 날짜 아래가 날짜가 아닌 표(일자 칸과 글자 칸이 섞인 표)가 같이 있습니다. 추측해서 적재하지 않고 통째로 격리했습니다.", "",
          "| 차량 양식 | 적재 행 | 날짜 범위(연도) |", "|---|---|---|"]
    for veh, g in df.groupby("vehicle"):
        L.append(f"| {veh} | {len(g)} | {g['date'].dt.year.min()} ~ {g['date'].dt.year.max()} |")
    L += ["", "## 2. 허용 오차와 근거", "",
          "허용 오차 = 누적거리 표시 단위 + 주행거리 표시 단위 (합의 문서 2절, 9절 10번). 표시 단위는 칸별 소수 자릿수 통계에서 정합니다. "
          "소수 n째 자리가 0이 아닌 값이 전체의 3% 이상이면 그 자리까지 표시하는 칸으로 봅니다(`infer_decimals`).", "",
          "| 차량 양식 | 칸 | 값 개수 | 소수 0자리 | 1자리 | 2자리 | 3자리 이상 | 추정 소수 자릿수 | 표시 단위 |", "|---|---|---|---|---|---|---|---|---|"]
    for veh, g in df.groupby("vehicle"):
        for col in ("distance", "cumulative_distance"):
            x = g[col].dropna()
            if not len(x):
                L.append(f"| {veh} | {col} | 0 | - | - | - | - | - | - |")
                continue
            h = decimals_hist(x)
            d = infer_decimals(x)
            L.append(f"| {veh} | {col} | {len(x)} | {h['0']} | {h['1']} | {h['2']} | {h['3+']} | {d} | {10.0 ** -d:g} |")
    L += ["", "| 차량 양식 | 허용 오차(km) | 근거 |", "|---|---|---|"]
    for veh, t in info["tol"].items():
        if veh in info["units"]:
            uc, ud = info["units"][veh]
            L.append(f"| {veh} | {t:g} | 누적거리 단위 {uc:g} + 주행거리 단위 {ud:g} |")
        else:
            L.append(f"| {veh} | {t:g} | 누적거리 없음, 주행거리 단위 {t:g} (두 계산식 검사에만 씀) |")
    L += ["", "실측 어긋남 분포(날짜가 이어지고 주행거리가 모두 있는 구간에서 `누적거리 차이 - 주행거리 합` 의 절대값):", "",
          "| 차량 양식 | 구간 수(등식) | 허용 오차 이하 | 1~2배 | 2~5배 | 5배 초과 | 허용 오차 절반 이하 |", "|---|---|---|---|---|---|---|"]
    for veh, s in info.get("spans", {}).items():
        L.append(f"| {veh} | {s['exact']} | {s['resid_le_tol']} | {s['resid_1_2_tol']} | {s['resid_2_5_tol']} | {s['resid_gt_5_tol']} | {s['resid_le_half_tol']} |")
    L += ["", "허용 오차를 넓히지 않았습니다. 5배 초과 구간은 오류 후보이고 아래 3절에서 처리됩니다. 허용 오차 이하 구간이 대부분이 아니면 표시 단위 추정이 틀렸다는 뜻이므로 원인부터 찾아야 합니다.", "",
          "## 3. 오류 종류별 건수와 처리", ""]
    L += [f"- 고친 칸 {len(corr)}개: " + (", ".join(f"{RULE_KO.get(k, k)} {v}" for k, v in by_rule.items()) if by_rule else "없음"),
          f"- 고친 칸을 칸별로: " + (", ".join(f"{k} {v}" for k, v in by_col.items()) if by_col else "없음"),
          f"- 미해결 {n_unres_groups}묶음, 행으로 {n_unres_rows}개 (확인 목록에 올림). 이유별: " + ", ".join(f"{REASON_KO.get(k, k)} {v}묶음" for k, v in unres_reasons.items()),
          f"- 같은 차량과 날짜가 두 번 나온 행: 값이 같아 한 번만 센 것 {info['dup_identical']}개, 값이 달라 사슬에서 뺀 것 {info['dup_conflict']}개",
          "- 구간 검사 결과(차량별):"]
    for veh, s in info.get("spans", {}).items():
        L.append(f"  - {veh}: 사슬에 든 행 {s['rows_in_chain']}, 누적거리 구간 {s['spans']} (등식 {s['exact']}, 부등식 {s['inequality']}), 처리 전 위반 {s['violated_before']}")
    L += ["", "## 3-2. 2차 개선 전후 (같은 표, 같은 날 실행)", "",
          "| 구분 | 고친 칸 | 미해결 묶음 | 미해결 행 |", "|---|---|---|---|",
          f"| 1차 보고서 수치 | 24 | 116 | 247 |",
          f"| 1차 편집기를 이번 표에 다시 돌림(같은 날짜 병합 포함) | {len(corr0)} | {len(unres0)} | {rows0} |",
          f"| 2차 편집기 | {len(corr)} | {n_unres_groups} | {n_unres_rows} |", "",
          f"- 같은 차량·날짜가 두 파일에 있는 경우: 값이 한 곳에서만 비어 있고 충돌이 없으면 빈칸을 다른 쪽 값으로 채워 하나로 합칩니다(파일 76 이 월별 파일의 사본이라는 `reports/open_questions.md` 결과). 합친 날짜 {info.get('dup_merged', 0)}개, 충돌이라 미해결로 남긴 묶음 {info['dup_conflict'] and sum(1 for r in unres.itertuples() if r.reason == 'same_date_conflicting_rows')}개.",
          f"- 격리 시트 {int((rc['status'] != 'ok').sum())}개는 날짜 아래 값이 없거나 측정 칸과 운행기록 근거(제목의 운행 글자, 알려진 모델 낱말, 주행거리 칸)가 없어 격리 그대로입니다.",
          f"- 3차 규칙: 누적거리 검사를 못 하는 행에서 두 계산식(연비 x 연료, 속도 x 시간)이 같은 값을 가리키고 오타 후보가 하나뿐이면 주행거리를 고칩니다. 행 판정 건수: {info.get('fix_counts')}. 고친 칸 {by_rule.get('distance_two_relations', 0)}개. 다른 칸은 고치지 않습니다.",
          f"- 2차 편집기 소프트 경고 행 {len(warn0)}개, 3차 {len(warn1)}개.", "",
          "소프트 규칙(경고만, 값은 안 고침):", "", "| 차량 양식 | 관계 | 비교한 행 | 맞는 행 | 이 차량에서 쓰는가(75% 이상 맞음) |", "|---|---|---|---|---|"]
    for veh, d_ in info.get("soft", {}).items():
        for rel, x_ in d_.items():
            L.append(f"| {veh} | {rel} | {x_['defined']} | {x_['consistent']} | {'예' if x_['valid'] else '아니오'} |")
    L += ["", f"경고 행 {len({w['row_id'] for w in info.get('soft_warnings', [])})}개 중 다른 사유로 이미 목록에 있는 행을 뺀 {n_warn}개를 확인 목록에 올렸습니다.", "",
          f"## 4. 보조 지표", "",
          f"고친 값 중 수정 Z 점수 |M| > 3.5 비율: {fmt(aux)} ({int((zdef.abs() > 3.5).sum())}건 / Z 점수를 낼 수 있는 {len(zdef)}건). 0에 가까울수록 좋습니다. "
          "중앙값과 MAD 는 차량마다, 수정하지 않은 정상 행에서 구하고 운행 없는 날(0)은 뺐습니다. 누적거리를 고친 칸은 그 행의 하루 증가량으로 점수를 냈고 날짜를 고친 칸은 점수가 없습니다.", "",
          f"확인 목록 `data/review/driving_review_list.csv` {len(rv)}행 = |M| > 3.5 인 고친 값 + 미해결 {n_unres_rows}행 + 소프트 규칙 경고 {n_warn}행 + 정상 통과 행 무작위 {len(pick)}개.", ""]
    write_text(reports / "real_run_summary.md", "\n".join(L))

    # ---- step 3: errors injected into real runs that pass every check
    res = real_injected_eval(fixed, corr.drop(columns=["z"]) if "z" in corr else corr, unres, info, cfg, cfg_edit)
    if res is None:
        write_text(reports / "real_injected_eval.md", "# 실제 구간에 오류를 심은 점수\n\n모든 검사를 통과한 연속 구간(10행 이상)이 없어 돌리지 못했습니다.\n")
        print("real injected eval: no clean runs")
    else:
        o, per, n_runs, n_rows, n_inj = res
        txt = ["# 실제 구간에 오류를 심은 점수 (합의 문서 3절 3단계)", "",
               f"실제 데이터에서 모든 관계식을 통과하고 수정하지 않은 연속 구간(10행 이상) {n_runs}개, 행 {n_rows}개를 잘라 같은 오류 주입기로 오류 {n_inj}칸을 심고 같은 알고리즘({describe(cfg_edit)}, 고정 규칙 켬)으로 채점했습니다. "
               "허용 오차는 이 데이터에서 추정한 표시 단위의 합입니다. 값은 이 문서에 없습니다.", "", table_md(per, o), "",
               "주의: 더미와 같은 주입기를 쓰므로 실제 오타 분포와는 다를 수 있습니다. 구간 사이는 날짜가 끊겨 부등식만 검사됩니다.", ""]
        write_text(reports / "real_injected_eval.md", "\n".join(txt))
        print("real injected eval:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in o.items()}, "runs", n_runs, "rows", n_rows, "injected", n_inj)
    return 0


def safe_main() -> int:
    try:
        return main()
    except Exception as e:  # message may carry values
        print("failed, exception class:", type(e).__name__)
        return 1


if __name__ == "__main__":
    sys.exit(safe_main())
