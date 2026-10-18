"""Cell-level scoring of the editing algorithm against injected errors, plus leave-one-error-type-out checks.

Cell = one value in (distance, cumulative_distance, date). Positive = erroneous cell.
  recall           TP / (TP + FN)           flagged = a cell the algorithm changed
  precision        TP / (TP + FP)
  F1               harmonic mean
  repair precision cells restored correctly / all changed cells (changing a sound cell counts as wrong, unresolved excluded)
A numeric fix is correct when it lands within the meter tolerance (display unit of C + display unit of D) of the clean value.
"""
from __future__ import annotations

import io
import itertools
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common import load_config, path_from, write_text  # noqa: E402
from pipeline.edit_driving import BASELINE, EditConfig, edit  # noqa: E402
from pipeline.make_dummy import SETTINGS, gen_clean, inject, inject_man_distance  # noqa: E402

COLS = ["distance", "cumulative_distance", "date"]


def f1(r, p):
    return 0.0 if (r + p) == 0 else 2 * r * p / (r + p)


def run_and_score(clean: pd.DataFrame, dirty: pd.DataFrame, truth: pd.DataFrame, cfg: EditConfig, kind_for_units: str | None = None):
    fixed, corr, unres, info = edit(dirty, cfg)
    cl = clean.set_index("row_id")
    veh = clean.set_index("row_id")["vehicle"]
    pos = {int(r): k for k, r in enumerate(clean["row_id"])}
    tol = info["tol"]
    flagged = {(int(r.row_id), r.column): r for r in corr.itertuples()}
    tset = {(int(r.row_id), r.column): r for r in truth.itertuples()}
    truth_rows = sorted({int(r) for r in truth["row_id"]})
    truth_type_at = {int(r.row_id): r.error_type for r in truth.itertuples()}

    def correct(key, r):
        rid, col = key
        if col == "date":
            return pd.Timestamp(r.new_value) == pd.Timestamp(cl.at[rid, "date"])
        t = tol.get(veh.at[rid], 1.0)
        return abs(float(r.new_value) - float(cl.at[rid, col])) <= t + 1e-9

    # attribute false positives to the nearest injected error row (same vehicle, within 3 rows)
    def attribute(rid):
        k = pos[rid]
        best = None
        for tr in truth_rows:
            if veh.at[tr] != veh.at[rid]:
                continue
            dist = abs(pos[tr] - k)
            if dist <= 3 and (best is None or dist < best[0]):
                best = (dist, truth_type_at[tr])
        return best[1] if best else "(no nearby injected error)"

    per = {}
    types = sorted(set(truth["error_type"]))
    for t in types + ["(no nearby injected error)"]:
        per[t] = {"n": 0, "tp": 0, "fn": 0, "fp": 0, "correct": 0, "unresolved_hit": 0}
    unres_rows = set()
    if len(unres):
        for s in unres["row_ids"]:
            unres_rows.update(int(x) for x in str(s).split())
    for key, tr in tset.items():
        d = per[tr.error_type]
        d["n"] += 1
        if key in flagged:
            d["tp"] += 1
            d["correct"] += int(correct(key, flagged[key]))
        else:
            d["fn"] += 1
            d["unresolved_hit"] += int(key[0] in unres_rows)
    fp_total = 0
    for key, r in flagged.items():
        if key not in tset:
            t = attribute(key[0])
            per[t]["fp"] += 1
            fp_total += 1
    tp = sum(d["tp"] for d in per.values())
    fn = sum(d["fn"] for d in per.values())
    correct_all = sum(d["correct"] for d in per.values())
    n_changed = len(flagged)
    rec = tp / (tp + fn) if tp + fn else 0.0
    pre = tp / (tp + fp_total) if tp + fp_total else 0.0
    rp = correct_all / n_changed if n_changed else 0.0
    rows = []
    for t, d in per.items():
        r_t = d["tp"] / d["n"] if d["n"] else float("nan")
        p_t = d["tp"] / (d["tp"] + d["fp"]) if d["tp"] + d["fp"] else float("nan")
        rp_t = d["correct"] / (d["tp"] + d["fp"]) if d["tp"] + d["fp"] else float("nan")
        rows.append({"type": t, "n": d["n"], "tp": d["tp"], "fn": d["fn"], "fp": d["fp"], "recall": r_t, "precision": p_t,
                     "f1": f1(r_t, p_t) if d["n"] else float("nan"), "repair_precision": rp_t, "fn_in_unresolved": d["unresolved_hit"]})
    n_cells = int(clean["distance"].notna().sum() + clean["cumulative_distance"].notna().sum() + clean["date"].notna().sum())
    clean_cells = n_cells - len(tset)
    # warnings: cells the editor pointed at without changing them (chain violations, abnormal dates, soft-relation breaks)
    warn = set()
    if len(unres):
        for r in unres.itertuples():
            cols_w = ["date"] if r.column == "date" else ["distance", "cumulative_distance"]
            for x in str(r.row_ids).split():
                for c in cols_w:
                    if int(x) in cl.index and pd.notna(cl.at[int(x), c]):
                        warn.add((int(x), c))
    for w in info.get("soft_warnings", []):
        warn.add((w["row_id"], "distance"))
    by_col = {}
    for c in COLS:
        keys = [k for k in tset if k[1] == c]
        fixed_k = [k for k in keys if k in flagged]
        ok_k = [k for k in fixed_k if correct(k, flagged[k])]
        warned_k = [k for k in keys if k not in flagged and k in warn]
        by_col[c] = {"injected": len(keys), "fixed_correct": len(ok_k), "fixed_wrong": len(fixed_k) - len(ok_k), "warned": len(warned_k),
                     "silent": len(keys) - len(fixed_k) - len(warned_k),
                     "sound_changed": sum(1 for k in flagged if k[1] == c and k not in tset),
                     "sound_warned": sum(1 for k in warn if k[1] == c and k not in tset and k not in flagged)}
    overall = {"by_col": by_col, "warned": len(warn - set(flagged)), "warned_sound": sum(v["sound_warned"] for v in by_col.values()),
               "clean_cells": clean_cells, "fix_on_clean": fp_total / clean_cells if clean_cells else 0.0, "n": len(tset), "tp": tp, "fn": fn, "fp": fp_total, "recall": rec, "precision": pre, "f1": f1(rec, pre),
               "repair_precision": rp, "changed": n_changed, "unresolved_groups": len(unres[unres.get("column", pd.Series(dtype=str)).astype(str).str.contains("distance")]) if len(unres) else 0}
    return overall, pd.DataFrame(rows), corr, unres, info


def fmt(x):
    return "-" if x is None or (isinstance(x, float) and np.isnan(x)) else f"{x:.3f}"


def table_md(per: pd.DataFrame, overall: dict) -> str:
    lines = ["| error type | injected cells | caught (TP) | missed (FN) | false alarms (FP) | recall | precision | F1 | repair precision | missed but in unresolved |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in per.itertuples():
        lines.append(f"| {r.type} | {r.n} | {r.tp} | {r.fn} | {r.fp} | {fmt(r.recall)} | {fmt(r.precision)} | {fmt(r.f1)} | {fmt(r.repair_precision)} | {r.fn_in_unresolved} |")
    o = overall
    lines.append(f"| **all** | {o['n']} | {o['tp']} | {o['fn']} | {o['fp']} | {fmt(o['recall'])} | {fmt(o['precision'])} | {fmt(o['f1'])} | {fmt(o['repair_precision'])} | |")
    lines += ["", f"Sound cells changed (false alarms / sound cells): {o['fp']} / {o['clean_cells']} = {100 * o['fix_on_clean']:.3f}% (limit 0.5%)."]
    return "\n".join(lines)


def compare_md(rows) -> str:
    lines = ["| setting | injected cells | auto-fixed cells | fixed correctly | sound cells changed | warned cells (not changed) | warned sound cells | unresolved groups |",
             "|---|---|---|---|---|---|---|---|"]
    for name, o in rows:
        correct_n = sum(v["fixed_correct"] for v in o["by_col"].values())
        lines.append(f"| {name} | {o['n']} | {o['changed']} | {correct_n} | {o['fp']} ({100 * o['fix_on_clean']:.3f}%) | {o['warned']} | {o['warned_sound']} | {o['unresolved_groups']} |")
    return "\n".join(lines)


def by_col_md(rows) -> str:
    lines = ["| setting | column | injected | fixed correctly | fixed wrongly | warned only | silent | sound cells changed | sound cells warned |", "|---|---|---|---|---|---|---|---|---|"]
    for name, o in rows:
        for c, v in o["by_col"].items():
            lines.append(f"| {name} | {c} | {v['injected']} | {v['fixed_correct']} | {v['fixed_wrong']} | {v['warned']} | {v['silent']} | {v['sound_changed']} | {v['sound_warned']} |")
    return "\n".join(lines)


def no_cumulative_score(clean, seed, cfg_edit):
    """Vehicles whose rows carry no cumulative distance have no chain check. Inject wrong daily distances into their working days and see
    what the two relations do: fix (correctly or not), warn only, or stay silent."""
    dirty, truth = inject_man_distance(clean, seed)
    fixed, corr, _, info = edit(dirty, cfg_edit)
    warned = {w["row_id"] for w in info["soft_warnings"]}
    t_rows = {int(r) for r in truth["row_id"]}
    cl = clean.set_index("row_id")
    sel = dirty[dirty["cumulative_distance"].isna() & (dirty["distance"] > 0)]
    sound = {int(r) for r in sel["row_id"]} - t_rows
    veh = cl["vehicle"]
    fixed_rows = {int(r.row_id): r for r in corr.itertuples()} if len(corr) else {}
    ok = sum(1 for rid, r in fixed_rows.items() if rid in t_rows and abs(float(r.new_value) - float(cl.at[rid, "distance"])) <= info["tol"].get(veh.at[rid], 1.0) + 1e-9)
    n_fixed_t = len(t_rows & set(fixed_rows))
    w_only = len((t_rows & warned) - set(fixed_rows))
    return {"injected": len(t_rows), "fixed": n_fixed_t, "fixed_correct": ok, "warned_only": w_only, "silent": len(t_rows) - n_fixed_t - w_only,
            "sound_rows": len(sound), "sound_changed": len(sound & set(fixed_rows)), "sound_warned": len((sound & warned) - set(fixed_rows)),
            "fix_counts": dict(info["fix_counts"])}


def no_cumulative_md(r) -> str:
    return (f"Rows injected {r['injected']}: fixed {r['fixed']} (correct {r['fixed_correct']}), warned only {r['warned_only']}, silent {r['silent']}. "
            f"Sound working-day rows {r['sound_rows']}: changed {r['sound_changed']}, warned {r['sound_warned']}. "
            f"Row decisions of the distance fix on the whole table: {r['fix_counts']}.")


# ------------------------------------------------------------------ tuning space and leave-one-type-out
KINDS = ["transpose", "drop", "insert", "replace"]


def config_space(policy: str = "combined"):
    out = []
    for r in range(len(KINDS), -1, -1):  # most general first
        for sub in itertools.combinations(KINDS, r):
            for mc in (True, False):
                out.append(EditConfig(typo_kinds=frozenset(sub), use_mincell=mc, policy=policy))
    return out


def objective(overall):
    return overall["f1"] * overall["repair_precision"]


def tune(clean, dirty, truth):
    best, best_cfg, best_o = None, None, None
    for cfg in config_space():
        o, *_ = run_and_score(clean, dirty, truth, cfg)
        v = objective(o)
        if best is None or v > best + 1e-9:  # ties keep the earlier (more general) config
            best, best_cfg, best_o = v, cfg, o
    return best_cfg, best_o


def describe(cfg: EditConfig) -> str:
    return f"typo kinds {sorted(cfg.typo_kinds)}, min-cell pass {'on' if cfg.use_mincell else 'off'}"


def leave_one_out(clean, seed, kind):
    s = SETTINGS[kind]
    mix = s["mix"]
    res = []
    d_all, t_all = inject(clean, seed + 11, kind)
    base_cfg, _ = tune(clean, d_all, t_all)
    for held in mix:
        if mix[held] == 0:
            continue
        rest = {k: v for k, v in mix.items() if k != held}
        d_tune, t_tune = inject(clean, seed + 21, kind, mix=rest)
        cfg_t, o_t = tune(clean, d_tune, t_tune)
        d_held, t_held = inject(clean, seed + 31, kind, mix={held: 1})
        o_h, per_h, *_ = run_and_score(clean, d_held, t_held, cfg_t)
        o_b, per_b, *_ = run_and_score(clean, d_held, t_held, base_cfg)
        row_h = per_h[per_h["type"] == held].iloc[0]
        row_b = per_b[per_b["type"] == held].iloc[0]
        res.append({"held": held, "n": int(row_h["n"]), "cfg": describe(cfg_t),
                    "recall_held": row_h["recall"], "rp_held": o_h["repair_precision"], "fp_held": o_h["fp"],
                    "recall_base": row_b["recall"], "rp_base": o_b["repair_precision"], "fp_base": o_b["fp"]})
    return base_cfg, pd.DataFrame(res)


def loo_md(base_cfg, df):
    lines = [f"Setting tuned on all types: {describe(base_cfg)}.", "",
             "| held-out type | cells | setting tuned without it | recall (held-out setting) | repair precision | false alarms | recall (all-type setting) | repair precision | false alarms |",
             "|---|---|---|---|---|---|---|---|---|"]
    for r in df.itertuples():
        lines.append(f"| {r.held} | {r.n} | {r.cfg} | {fmt(r.recall_held)} | {fmt(r.rp_held)} | {r.fp_held} | {fmt(r.recall_base)} | {fmt(r.rp_base)} | {r.fp_base} |")
    return "\n".join(lines)


# ------------------------------------------------------------------ parser score
def parser_score(clean: pd.DataFrame, folder: Path):
    from pipeline.parse_driving import parse_folder, to_frame

    files, rows, recon, qf, unmatched, bad, vsrc, mism, n_sheets, n_parsed = parse_folder(folder)
    got = to_frame(rows)
    got["date"] = pd.to_datetime(got["date"])
    cl = clean.copy()
    cl["date"] = pd.to_datetime(cl["date"])
    m = cl.merge(got, on=["vehicle", "date"], how="left", suffixes=("", "_p"), indicator=True)
    out = {"files": len(files), "expected_rows": len(cl), "parsed_rows": len(got), "matched_rows": int((m["_merge"] == "both").sum()),
           "unbalanced_sheets": int(sum(1 for r in recon if not r["balanced"])), "cols": {}}
    both = m[m["_merge"] == "both"]
    for c in ["fuel_efficiency", "speed", "time_h", "distance", "cumulative_distance", "consumed_fuel", "refuel", "reurea",
              "fuel_rate_per_hour", "consumed_fuel_idle", "consumed_fuel_pto", "time_idle_h", "time_pto_h"]:
        a, b = both[c], both[c + "_p"]
        tolv = 1 / 120 if c.startswith("time") else 1e-6
        both_nan = a.isna() & b.isna()
        close = ((a - b).abs() <= tolv)
        ok = int((both_nan | close).sum())
        out["cols"][c] = (ok, len(both))
    return out


def parser_md(ps):
    lines = [f"Workbooks {ps['files']}, expected rows {ps['expected_rows']}, parsed rows {ps['parsed_rows']}, rows matched on (vehicle, date) {ps['matched_rows']}, unbalanced sheets {ps['unbalanced_sheets']}.", "",
             "| column | cells equal / compared |", "|---|---|"]
    for c, (ok, n) in ps["cols"].items():
        lines.append(f"| {c} | {ok} / {n} |")
    return "\n".join(lines)


# ------------------------------------------------------------------ entry
LEGACY = EditConfig(policy="legacy", use_mincell=True)  # the round 2 editor with the setting the real run used


def main(argv) -> int:
    cfg = load_config()
    reports = path_from(cfg, "reports_dir")
    fx = path_from(cfg, "fixtures_dir")
    marker = reports / ".test_scored"
    do_test = "--test" in argv
    seed_test = cfg["seeds"]["test"]
    if do_test and marker.exists() and f"seed {seed_test}" in marker.read_text(encoding="utf-8"):
        print(f"test seed {seed_test} was already scored once. Make a new seed in config.toml and say so in the report. Refusing.")
        return 2
    t0 = time.time()
    clean_dev = gen_clean(cfg["seeds"]["dev"], "dev")
    dirty_dev, truth_dev = inject(clean_dev, cfg["seeds"]["dev"] + 1, "dev")
    parts = ["# Dummy evaluation (driving log), round 3", "",
             "Generated by `pipeline/evaluate.py`. Cell = one value in distance, cumulative_distance or date. Positive = erroneous cell. "
             "Before = the round 2 editor (`policy=\"legacy\"`). After = the round 3 editor (`policy=\"combined\"`): every round 2 rule unchanged, plus one rule on rows the "
             "cumulative-distance chain cannot check: the daily distance is changed when fuel efficiency x fuel and speed x time point at the same distance and exactly one "
             "typing-slip variant of the written value agrees with both; otherwise warn only. That rule changes no column but the daily distance. Both are scored on the same data.", "",
             "## 1. Parser round trip (dev clean table scattered into three workbook layouts, then parsed back)", ""]
    ps = parser_score(clean_dev, fx / "xlsx_dummy")
    parts += [parser_md(ps), ""]
    o_b, per_b, *_ = run_and_score(clean_dev, dirty_dev, truth_dev, LEGACY)
    base_cfg, _o = tune(clean_dev, dirty_dev, truth_dev)
    o, per, *_ = run_and_score(clean_dev, dirty_dev, truth_dev, base_cfg)
    parts += ["## 2. Dev set", "", f"Seed {cfg['seeds']['dev']}, rows {len(clean_dev)}, injected cells {len(truth_dev)}. Setting of the after editor, chosen on this set: {describe(base_cfg)}.", "",
              compare_md([("before (round 2 editor)", o_b), ("after (round 3 editor)", o)]), "",
              by_col_md([("before", o_b), ("after", o)]), "",
              "After, by error type:", "", table_md(per, o), "", "Before, by error type:", "", table_md(per_b, o_b), ""]
    print("dev before:", fmt(o_b["recall"]), "fp", o_b["fp"], " dev after:", fmt(o["recall"]), "fp", o["fp"], "changed", o["changed"], "warned", o["warned"], f"{time.time() - t0:.0f}s")
    base_loo, loo = leave_one_out(clean_dev, cfg["seeds"]["dev"], "dev")
    parts += ["## 3. Leave one error type out (dev data, after editor)", "",
              "For each type: tune the setting (typo kinds) on data injected without that type, then score data injected with only that type. "
              "The right-hand block uses the setting tuned on all types, for comparison. A tie keeps the more general setting.", "", loo_md(base_loo, loo), ""]
    print("leave-one-out done", f"{time.time() - t0:.0f}s")
    nc_dev = no_cumulative_score(clean_dev, cfg["seeds"]["dev"] + 7, base_cfg)
    parts += ["## 4. Rows without a cumulative distance (dev)", "", "Daily distance errors injected into rows that carry no cumulative distance, so only the two relations can see them.", "", no_cumulative_md(nc_dev), ""]
    print("no-cumulative dev:", {k: v for k, v in nc_dev.items() if k != "fix_counts"})
    if do_test:
        clean_t = gen_clean(seed_test, "test")
        dirty_t, truth_t = inject(clean_t, seed_test + 1, "test")
        o_tb, per_tb, *_ = run_and_score(clean_t, dirty_t, truth_t, LEGACY)
        o_t, per_t, *_ = run_and_score(clean_t, dirty_t, truth_t, base_cfg)
        nc_t = no_cumulative_score(clean_t, seed_test + 7, base_cfg)
        parts += ["## 5. Test set (scored once, setting fixed from the dev set)", "",
                  f"Seed {seed_test}, rows {len(clean_t)}, injected cells {len(truth_t)}. This is the third test set. The second one (seed 5120311) was scored in round 2 and is retired. "
                  "Different series length, display units, gap rate, error rate, spacing and mix. `digit_add` appears only here. No setting was changed after looking at this section.", "",
                  f"Setting used: {describe(base_cfg)}.", "",
                  compare_md([("before (round 2 editor)", o_tb), ("after (round 3 editor)", o_t)]), "",
                  by_col_md([("before", o_tb), ("after", o_t)]), "",
                  "After, by error type:", "", table_md(per_t, o_t), "", "Before, by error type:", "", table_md(per_tb, o_tb), "",
                  "Rows without a cumulative distance (test):", "", no_cumulative_md(nc_t), ""]
        write_text(marker, "test scored once" + chr(10) + f"seed {seed_test}" + chr(10))
        for nm, oo in (("before", o_tb), ("after", o_t)):
            print(f"TEST {nm}: injected {oo['n']} changed {oo['changed']} correct {sum(v['fixed_correct'] for v in oo['by_col'].values())} sound_changed {oo['fp']}/{oo['clean_cells']} "
                  f"({100 * oo['fix_on_clean']:.4f}%) warned {oo['warned']} warned_sound {oo['warned_sound']}")
        print("TEST by column after:", o_t["by_col"])
        print("TEST no-cumulative:", {k: v for k, v in nc_t.items() if k != "fix_counts"})
    write_text(reports / ("dummy_eval.md" if do_test else "dummy_eval_dev_only.md"), chr(10).join(parts) + chr(10))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as e:
        print("failed, exception class:", type(e).__name__, str(e)[:200])
        raise
