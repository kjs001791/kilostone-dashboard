"""Statistical data editing for the driving log (deterministic, no ML, no external calls).

Processing order (AGREED-2026-10-18 section 2 [na]):
  1. tolerance      violations within the meter display units are not errors
  2. fixed rules    abnormal dates; value copied from the previous day
  3. typo inversion back-solve the value each cell must have, keep only values a typing slip can produce, apply only if unique
  4. minimum cells  smallest set of cells (<= 2) that makes the window consistent, applied only if unique
  5. unresolved     everything else goes to the human review list

Relations (window = consecutive cumulative-distance readings and the daily distances between them):
  equality   C_i - C_p = sum of D over the rows between, when the dates are consecutive and every D is present
  inequality otherwise: C_i - C_p >= sum of known D  (days without records only add distance)
Tolerance = display unit of C + display unit of D (inferred from decimals, per vehicle).

Second round additions (all switchable in EditConfig; baseline = every new switch off):
  tiebreaks    when several one-cell (or two-cell) answers fit, narrow them in order: typo tier (transposition, keyboard-neighbour
               digit on numpad or top row, missing or extra digit rank above any other digit), plausible size (robust per-vehicle cap
               from the median and MAD of the daily distance), agreement with the soft relations, rows copied from the day before,
               and an old value that is itself an outlier. A unique answer is never vetoed by these; they only break ties.
  zero copy    a daily distance of 0 repeated from a rest day can be a copied value too
  copy rows    a row that repeats two or more columns of the previous day is a copy suspect and is tried first
  wide window  a gap in dates is not free: the unseen days add at most (missing days x cap) to the cumulative distance
  soft rules   fuel efficiency x fuel = distance, speed x time = distance. Warn only, never change a value
  guards       a change no larger than the tolerance is not a fix (it is meter noise); a cumulative distance that equals the day before
               is a copy only when the same row has a daily distance (on a rest day it must equal the day before)
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from itertools import product
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.common import infer_decimals  # noqa: E402

EPOCH = np.datetime64("1970-01-01", "D")
D_MAX = 2000.0


ALL_TIEBREAKS = ("tier", "plaus", "soft", "copy", "outlier")


@dataclass(frozen=True)
class EditConfig:
    typo_kinds: frozenset = frozenset({"transpose", "drop", "insert", "replace"})
    use_date: bool = True
    use_copy: bool = True
    use_typo: bool = True
    use_mincell: bool = True
    group_cell_cap: int = 12
    date_jump_days: int = 20
    # second round switches (BASELINE turns them all off and reproduces the first round)
    tiebreaks: tuple = ALL_TIEBREAKS
    zero_copy: bool = True
    copy_rows: bool = True
    wide_window: bool = True
    soft_rules: bool = True
    guards: bool = True
    # third round: "combined" = every second round rule unchanged + the two-relation distance fix (SoftRules.fix_distance) on the rows the
    # cumulative-distance chain cannot check. "legacy" = the second round editor alone, kept for before/after scoring.
    policy: str = "combined"


BASELINE = dict(tiebreaks=(), zero_copy=False, copy_rows=False, wide_window=False, soft_rules=False, guards=False)


# ------------------------------------------------------------------ typo model
# Keyboard neighbours of a digit on the numeric keypad (8 around, diagonals included) and on the number row above the letters.
_PAD = {7: (0, 0), 8: (0, 1), 9: (0, 2), 4: (1, 0), 5: (1, 1), 6: (1, 2), 1: (2, 0), 2: (2, 1), 3: (2, 2), 0: (3, 0.5)}
_ROW = "1234567890"


def _build_neighbours() -> dict:
    out = {d: set() for d in range(10)}
    for d, (r, c) in _PAD.items():
        for e, (rr, cc) in _PAD.items():
            if e != d and abs(rr - r) <= 1 and abs(cc - c) <= 1.01:
                out[d].add(e)
    for i, ch in enumerate(_ROW):
        for j in (i - 1, i + 1):
            if 0 <= j < 10:
                out[int(ch)].add(int(_ROW[j]))
    return out


KEY_NEIGHBOURS = _build_neighbours()
KEY_NEIGHBOURS_PAD_ONLY = {d: {e for e in KEY_NEIGHBOURS[d] if abs(_PAD[e][0] - _PAD[d][0]) <= 1 and abs(_PAD[e][1] - _PAD[d][1]) <= 1.01} for d in range(10)}


def typo_tiers(n: int, kinds, keyboard: bool = True) -> dict:
    """Integers one typing slip away from n, mapped to a tier (1 = likeliest slip, 2 = any other digit)."""
    s = str(n)
    out: dict = {}

    def add(v: int, tier: int):
        if v != n and (v not in out or tier < out[v]):
            out[v] = tier

    if "transpose" in kinds:
        for k in range(len(s) - 1):
            if s[k] != s[k + 1]:
                add(int(s[:k] + s[k + 1] + s[k] + s[k + 2:]), 1)
    if "drop" in kinds:  # the typed value lacks a digit the true value has
        for k in range(len(s) + 1):
            for d in "0123456789":
                if k == 0 and d == "0":
                    continue
                add(int(s[:k] + d + s[k:]), 1)
    if "insert" in kinds and len(s) > 1:  # the typed value has an extra digit
        for k in range(len(s)):
            add(int(s[:k] + s[k + 1:]), 1)
    if "replace" in kinds:
        for k in range(len(s)):
            near = KEY_NEIGHBOURS[int(s[k])] if keyboard else set()
            for d in range(10):
                if d != int(s[k]):
                    add(int(s[:k] + str(d) + s[k + 1:]), 1 if d in near else 2)
    return out


def typo_neighbors(n: int, kinds) -> set:
    """Integers one typing slip away from n (non-negative integer, decimal point ignored). First round form, no tiers."""
    return set(typo_tiers(n, kinds, keyboard=False))


# ------------------------------------------------------------------ soft rules
class SoftRules:
    """Fuel efficiency x fuel = distance and speed x time = distance for one vehicle, in chain order.

    A relation is used only when the vehicle's own rows satisfy it (share >= SHARE); otherwise the columns mean something else here.
    The tolerance is the rounding of the displayed digits of each factor, times 1.5.
    """
    SHARE = 0.75
    MIN_ROWS = 30

    def __init__(self, g: pd.DataFrame, ud: float):
        n = len(g)

        def col(name):
            return pd.to_numeric(g[name], errors="coerce").to_numpy(dtype=float) if name in g else np.full(n, np.nan)

        self.fuel, self.fe, self.spd, self.tim = col("consumed_fuel"), col("fuel_efficiency"), col("speed"), col("time_h")
        self.D = col("distance")
        self.ud = ud

        def unit(x):
            x = x[~np.isnan(x)]
            return 10.0 ** -infer_decimals(x) if len(x) else 1.0

        self.u_fuel, self.u_fe, self.u_spd = unit(self.fuel), unit(self.fe), unit(self.spd)
        self.valid = {1: False, 2: False}
        self.stats = {}
        self.center = {1: 0.0, 2: 0.0}  # typical relative gap of the product from the distance (e.g. time includes idling)
        self.width = {1: 0.0, 2: 0.0}   # 4 x robust spread of that gap
        for rel in (1, 2):
            gaps = []
            for k in range(n):
                prod = self._product(rel, k)
                if prod is not None and not np.isnan(self.D[k]) and self.D[k] > 0:
                    gaps.append(prod / self.D[k] - 1.0)
            if len(gaps) >= self.MIN_ROWS:
                gaps = np.array(gaps)
                self.center[rel] = float(np.median(gaps))
                self.width[rel] = 4.0 * 1.4826 * float(np.median(np.abs(gaps - self.center[rel])))
        for rel in (1, 2):
            ok = d = 0
            for k in range(n):
                if np.isnan(self.D[k]) or self.D[k] <= 0:
                    continue
                st = self._rel(rel, k, self.D[k])
                if st != 0:
                    d += 1
                    ok += int(st > 0)
            self.stats[rel] = (d, ok)
            self.valid[rel] = d >= self.MIN_ROWS and ok / d >= self.SHARE

    def _product(self, rel, k):
        if rel == 1:
            f, e = self.fuel[k], self.fe[k]
            return None if (np.isnan(f) or np.isnan(e) or f <= 0 or e <= 0) else f * e
        t, sp = self.tim[k], self.spd[k]
        return None if (np.isnan(t) or np.isnan(sp) or t <= 0 or sp <= 0) else sp * t

    def expect(self, rel, k):
        """(distance the relation points at, tolerance) for row k, or None when a factor of the relation is missing on that row."""
        prod = self._product(rel, k)
        if prod is None:
            return None
        if rel == 1:
            f, e = self.fuel[k], self.fe[k]
            tol = 1.5 * (0.5 * self.ud + 0.5 * self.u_fe * f + 0.5 * self.u_fuel * e)
        else:
            t, sp = self.tim[k], self.spd[k]
            tol = 1.5 * (0.5 * self.ud + 0.5 * self.u_spd * t + sp / 120.0)
        expected = prod / (1.0 + self.center[rel])
        return expected, max(tol, self.width[rel] * expected)

    def _rel(self, rel, k, v):
        ex = self.expect(rel, k)
        if ex is None:
            return 0
        return 1 if abs(ex[0] - v) <= ex[1] + 1e-9 else -1

    def fix_distance(self, k, kinds):
        """Decide the daily distance of row k from the two relations. Returns (status, new value or None).

        A value is changed only when both relations are usable on this vehicle and row, the written value breaks at least one, the two relations
        point at the same distance (their gap is within the sum of their tolerances), and exactly one typing-slip variant of the written
        value agrees with both. Every other case returns a status and no value: the caller warns and leaves the cell alone.
        """
        v = self.D[k]
        if np.isnan(v) or v <= 0:
            return "no_distance", None
        if not (self.valid[1] and self.valid[2]):
            return "relation_not_valid", None
        e1, e2 = self.expect(1, k), self.expect(2, k)
        if e1 is None or e2 is None:
            return "one_relation_only", None
        ok1, ok2 = abs(e1[0] - v) <= e1[1] + 1e-9, abs(e2[0] - v) <= e2[1] + 1e-9
        if ok1 and ok2:
            return "consistent", None
        if abs(e1[0] - e2[0]) > e1[1] + e2[1] + 1e-9:
            return "relations_disagree", None
        n = v / self.ud
        if abs(n - round(n)) > 1e-6:
            return "off_unit_grid", None
        fit = []
        for m in typo_tiers(int(round(n)), kinds):
            c = m * self.ud
            if c > 0 and abs(e1[0] - c) <= e1[1] + 1e-9 and abs(e2[0] - c) <= e2[1] + 1e-9:
                fit.append(round(c, 6))
        if len(fit) == 1:
            return "fix", fit[0]
        return ("no_candidate" if not fit else "several_candidates"), None

    def status(self, k, v):
        """-1 a valid relation contradicts the value, +1 the valid relations agree, 0 nothing to say."""
        res = 0
        for rel in (1, 2):
            if not self.valid[rel] or v is None or np.isnan(v):
                continue
            st = self._rel(rel, k, v)
            if st < 0:
                return -1
            res = max(res, st)
        return res

    def warn_rows(self, D):
        out = []
        for k in range(len(D)):
            if np.isnan(D[k]):
                continue
            for rel in (1, 2):
                if self.valid[rel] and self._rel(rel, k, D[k]) < 0:
                    out.append((k, rel))
        return out


REL_NAME = {1: "fuel_efficiency_x_fuel", 2: "speed_x_time"}


# ------------------------------------------------------------------ chain model
BIG = 1e18


class Chain:
    def __init__(self, ids, days, C, D, has_values, unit_c, unit_d, cfg, aux=None):
        self.ids, self.days = ids, days
        self.C, self.D = C.copy(), D.copy()
        self.orig_C, self.orig_D = C.copy(), D.copy()
        self.has_values = has_values
        self.uc, self.ud = unit_c, unit_d
        self.tol = unit_c + unit_d
        self.cfg = cfg
        aux = aux or {}
        self.cap = aux.get("cap") if cfg.wide_window and aux.get("cap") else None  # largest plausible daily distance
        self.soft = aux.get("soft") if cfg.soft_rules else None
        self.copy_sus = aux.get("copy_sus") if cfg.copy_rows else None
        n = len(ids)
        anchors = [k for k in range(n) if not np.isnan(C[k])]
        self.spans = []
        for p, i in zip(anchors[:-1], anchors[1:]):
            rng = range(p + 1, i + 1)
            cont = all(days[k] - days[k - 1] == 1 for k in rng)
            exact = cont and all(not np.isnan(D[k]) for k in rng)
            hid = 0.0
            if not exact:
                unseen = (days[i] - days[p] - (i - p)) + sum(1 for k in rng if np.isnan(D[k]))
                hid = unseen * self.cap if self.cap else BIG
            self.spans.append({"p": p, "i": i, "exact": exact, "hid": hid})
        self.c_spans = {}
        self.d_span = {}
        for si, s in enumerate(self.spans):
            self.c_spans.setdefault(s["p"], []).append(si)
            self.c_spans.setdefault(s["i"], []).append(si)
            for k in range(s["p"] + 1, s["i"] + 1):
                self.d_span[k] = si

    def resid(self, si):
        s = self.spans[si]
        seg = self.D[s["p"] + 1: s["i"] + 1]
        return self.C[s["i"]] - self.C[s["p"]] - float(np.nansum(seg))

    def violated(self, si):
        s = self.spans[si]
        r = self.resid(si)
        if s["exact"]:
            return abs(r) > self.tol + 1e-9
        return r < -self.tol - 1e-9 or r > self.tol + s["hid"] + 1e-9

    def cell_spans(self, cell):
        kind, k = cell
        if kind == "C":
            return self.c_spans.get(k, [])
        return [self.d_span[k]] if k in self.d_span else []

    def get(self, cell):
        return self.C[cell[1]] if cell[0] == "C" else self.D[cell[1]]

    def put(self, cell, v):
        if cell[0] == "C":
            self.C[cell[1]] = v
        else:
            self.D[cell[1]] = v

    def unit(self, cell):
        return self.uc if cell[0] == "C" else self.ud

    def groups(self):
        viol = [si for si in range(len(self.spans)) if self.violated(si)]
        out, cur = [], []
        for si in viol:
            if cur and self.spans[cur[-1]]["i"] == self.spans[si]["p"]:
                cur.append(si)
            else:
                if cur:
                    out.append(cur)
                cur = [si]
        if cur:
            out.append(cur)
        return out

    def cells_of(self, group):
        cells = []
        for si in group:
            s = self.spans[si]
            for c in (("C", s["p"]), ("C", s["i"])):
                if c not in cells:
                    cells.append(c)
            for k in range(s["p"] + 1, s["i"] + 1):
                if not np.isnan(self.D[k]):
                    cells.append(("D", k))
        return cells

    def formulas(self, cell, group):
        out = []
        for si in self.cell_spans(cell):
            if si in group and self.violated(si):
                r = self.resid(si)
                cur = self.get(cell)
                if cell[0] == "C":
                    out.append(cur - r if cell[1] == self.spans[si]["i"] else cur + r)
                else:
                    out.append(cur + r)
        return out

    def to_int(self, cell, v):
        return int(round(v / self.unit(cell)))

    def _range_ok(self, cell, v):
        """After putting v, every span that touches the cell holds (used where a date gap leaves only a range)."""
        old = self.get(cell)
        self.put(cell, v)
        ok = all(not self.violated(si) for si in self.cell_spans(cell))
        self.put(cell, old)
        return ok

    def candidates(self, cell, formula, mode):
        """{value: tier}. Tier 0 copy, 1 likely slip, 2 other digit, 3 minimum-cell."""
        cur = self.get(cell)
        unit = self.unit(cell)
        lo = 0.0
        hi = D_MAX if cell[0] == "D" else 1e9
        if mode == "copy":
            k = cell[1]
            arr = self.C if cell[0] == "C" else self.D
            if k == 0 or np.isnan(arr[k - 1]) or arr[k - 1] != cur:
                return {}
            if self.cfg.guards and cell[0] == "C" and not (self.D[k] > self.tol):
                return {}
            if cur <= 0 and not (cell[0] == "D" and self.cfg.zero_copy):
                return {}
            vals = {round(formula / unit) * unit: 0}
        elif mode == "typo":
            n = self.to_int(cell, cur)
            if n < 0:
                return {}
            wide = self.cap is not None and any((not self.spans[si]["exact"]) and self.violated(si) for si in self.cell_spans(cell))
            vals = {}
            for m, tier in typo_tiers(n, self.cfg.typo_kinds).items():
                u = m * unit
                if abs(u - formula) <= self.tol + 1e-9 or (wide and lo <= u <= hi and self._range_ok(cell, u)):
                    vals[u] = tier
        else:  # mincell
            vals = {round(formula / unit) * unit: 3}
        floor = self.tol if self.cfg.guards else 1e-9
        return {round(v, 6): t for v, t in sorted(vals.items()) if lo <= v <= hi and abs(v - cur) > floor + 1e-9}

    def touched_ok(self, cells, group):
        seen = set(group)
        for c in cells:
            seen.update(self.cell_spans(c))
        return all(not self.violated(si) for si in seen)

    def score(self, group):
        return sum(abs(self.resid(si)) for si in group)

    # ---- evidence used to break ties
    def implaus_value(self, cell, v):
        """How many neighbouring relations make the value implausible (daily distance above the cap, or a negative or too large step)."""
        if self.cap is None:
            return 0
        kind, k = cell
        if kind == "D":
            return int(v > self.cap)
        cnt = 0
        n = len(self.C)
        kp = next((j for j in range(k - 1, -1, -1) if not np.isnan(self.C[j])), None)
        kn = next((j for j in range(k + 1, n) if not np.isnan(self.C[j])), None)
        if kp is not None:
            inc, dd = v - self.C[kp], self.days[k] - self.days[kp]
            cnt += int(inc < -self.tol or inc > dd * self.cap + self.tol)
        if kn is not None:
            inc, dd = self.C[kn] - v, self.days[kn] - self.days[k]
            cnt += int(inc < -self.tol or inc > dd * self.cap + self.tol)
        return cnt

    def evidence(self, changes, tier):
        """Key vector of one answer, evaluated while its values are in place. Smaller is better in every component."""
        new_impl = old_out = sus = incons = cons = 0
        for cell, old, new in changes:
            new_impl += self.implaus_value(cell, new)
            old_out += self.implaus_value(cell, old)
            if cell[0] == "D":
                if self.copy_sus is not None and self.copy_sus[cell[1]]:
                    sus += 1
                if self.soft is not None:
                    st = self.soft.status(cell[1], new)
                    incons += int(st < 0)
                    cons += int(st > 0)
        return {"tier": tier, "plaus": new_impl, "soft": (incons, -cons), "copy": -sus, "outlier": -old_out}

    def solve_group(self, group, mode):
        cells = self.cells_of(group)
        if mode == "copy" and self.copy_sus is not None:
            sus = [c for c in cells if c[0] == "D" and self.copy_sus[c[1]]]
            if sus:
                cells = sus
        sols = {}  # frozenset of cells -> (score, change list, evidence)

        def record(changes, tier):
            key = frozenset(c for c, _, _ in changes)
            sc = self.score(group) + 1e-6 * sum(abs(n - o) for _, o, n in changes)
            if key not in sols or sc < sols[key][0]:
                sols[key] = (sc, list(changes), self.evidence(changes, tier))

        # one cell
        for cell in cells:
            old = self.get(cell)
            for f in self.formulas(cell, group):
                for v, tier in self.candidates(cell, f, mode).items():
                    self.put(cell, v)
                    if self.touched_ok([cell], group):
                        record([(cell, old, v)], tier)
                    self.put(cell, old)
        if sols:
            return self._pick(sols)
        if mode == "copy" or len(cells) > self.cfg.group_cell_cap:
            return None
        # two cells, sequential
        for a in cells:
            olda = self.get(a)
            for fa in self.formulas(a, group):
                for va, ta in self.candidates(a, fa, mode).items():
                    self.put(a, va)
                    rest = [si for si in group if self.violated(si)]
                    if rest:
                        for b in cells:
                            if b == a:
                                continue
                            oldb = self.get(b)
                            for fb in self.formulas(b, rest):
                                for vb, tb in self.candidates(b, fb, mode).items():
                                    self.put(b, vb)
                                    if self.touched_ok([a, b], group):
                                        record([(a, olda, va), (b, oldb, vb)], ta + tb)
                                    self.put(b, oldb)
                    self.put(a, olda)
        if sols:
            return self._pick(sols)
        return None

    def _pick(self, sols):
        items = list(sols.values())
        if len(items) == 1:
            return items[0][1]
        for name in self.cfg.tiebreaks:
            best = min(it[2][name] for it in items)
            items = [it for it in items if it[2][name] == best]
            if len(items) == 1:
                return items[0][1]
        return None


# ------------------------------------------------------------------ date repair
def repair_dates(df: pd.DataFrame, cfg: EditConfig, log: list, unresolved: list, fix: bool = True):
    """Fixed rule for abnormal dates. Neighbours are taken in sheet order. With fix=False nothing is changed: every abnormal date is a warning."""
    d = pd.to_datetime(df["date"])
    new = d.copy()
    bad_unresolved = set()
    for _, grp in df.groupby(["source_file", "source_sheet_no"], sort=False):
        grp = grp.sort_values("source_row_no", kind="stable")
        idx = list(grp.index)
        vals = [d.loc[i] for i in idx]
        n = len(idx)
        days = np.array([(v.to_datetime64().astype("datetime64[D]") - EPOCH).astype(int) if pd.notna(v) else -10**9 for v in vals])
        abnormal = [False] * n
        for k in range(n):
            if pd.isna(vals[k]):
                abnormal[k] = True
                continue
            nb = [days[j] for j in range(max(0, k - 3), min(n, k + 4)) if j != k and days[j] > -10**8]
            if len(nb) >= 2 and abs(days[k] - np.median(nb)) > cfg.date_jump_days:
                abnormal[k] = True
        for k in range(n):
            if not abnormal[k]:
                continue
            prev = next((vals[j] for j in range(k - 1, -1, -1) if not abnormal[j]), None)
            nxt = next((vals[j] for j in range(k + 1, n) if not abnormal[j]), None)
            cand = []
            if prev is not None and nxt is not None and (nxt - prev).days == 2:
                cand = [prev + pd.Timedelta(days=1)]
            elif pd.notna(vals[k]):
                for y in {x.year for x in (prev, nxt) if x is not None}:
                    try:
                        c = vals[k].replace(year=y)
                    except ValueError:
                        continue
                    if (prev is None or c > prev) and (nxt is None or c < nxt):
                        cand.append(c)
            cand = sorted(set(cand))
            if not fix:
                bad_unresolved.add(idx[k])
                unresolved.append({"row_ids": str(int(df.loc[idx[k], "row_id"])), "column": "date", "reason": "abnormal_date_warning"})
            elif len(cand) == 1:
                new.loc[idx[k]] = cand[0]
                log.append({"row_id": int(df.loc[idx[k], "row_id"]), "column": "date", "old_value": vals[k], "new_value": cand[0],
                            "rule": "date_fixed_rule", "confidence": "high"})
            else:
                bad_unresolved.add(idx[k])
                unresolved.append({"row_ids": str(int(df.loc[idx[k], "row_id"])), "column": "date", "reason": "abnormal_date_not_unique"})
    return new, bad_unresolved


# ------------------------------------------------------------------ chain evidence
CAP_FACTOR = 1.5  # daily distance cap = factor x (median + 3.5 / 0.6745 x MAD) of the vehicle's nonzero daily distances


def chain_aux(g: pd.DataFrame, D: np.ndarray, ud: float) -> dict:
    """Per-vehicle evidence for the chain: distance cap, soft relations, rows that repeat the previous day."""
    out: dict = {}
    nz = D[~np.isnan(D)]
    nz = nz[nz > 0]
    if len(nz) >= 20:
        med = float(np.median(nz))
        mad = float(np.median(np.abs(nz - med)))
        if mad > 0:
            out["cap"] = CAP_FACTOR * (med + 3.5 / 0.6745 * mad)
    n = len(g)
    out["soft"] = SoftRules(g, ud)

    def col(name):
        return pd.to_numeric(g[name], errors="coerce").to_numpy(dtype=float) if name in g else np.full(n, np.nan)

    cols = [col(c) for c in ("consumed_fuel", "time_h", "fuel_efficiency", "speed")]
    sus = np.zeros(n, bool)
    for k in range(1, n):
        if np.isnan(D[k]) or np.isnan(D[k - 1]) or D[k] <= 0 or D[k] != D[k - 1]:
            continue
        others = sum(1 for a in cols if not np.isnan(a[k]) and not np.isnan(a[k - 1]) and a[k] > 0 and a[k] == a[k - 1])
        sus[k] = others >= 1
    out["copy_sus"] = sus
    return out


MEASURE_COLS = ["distance", "cumulative_distance", "consumed_fuel", "fuel_efficiency", "speed", "time_h", "refuel", "reurea"]


# ------------------------------------------------------------------ distance fix (third round)
def fix_distances(df: pd.DataFrame, bad_dates: set, cfg: EditConfig, log: list, info: dict, covered_ids: set) -> None:
    """New rule: fix the daily distance from fuel efficiency x fuel and speed x time. See SoftRules.fix_distance.
    Applied only to rows the cumulative-distance chain does not cover (row_id not in covered_ids); no other column is changed.

    Which checks a vehicle's rows can take part in is decided by the columns the rows hold, not by the name of the vehicle.
    """
    counts: dict = {}
    for veh, g in df.groupby("vehicle", sort=False):
        g = g[~g.index.isin(bad_dates) & g["date"].notna()]
        g = g.sort_values(["date", "source_file", "source_sheet_no", "source_row_no"], kind="stable")
        dd = pd.to_numeric(g["distance"], errors="coerce").to_numpy(dtype=float)
        have = lambda c: c in g and bool(pd.to_numeric(g[c], errors="coerce").notna().any())  # noqa: E731
        info["checks"][veh] = [name for name, ok in (("cumulative_distance", have("cumulative_distance")),
                                                     ("fuel_efficiency_x_fuel", have("fuel_efficiency") and have("consumed_fuel")),
                                                     ("speed_x_time", have("speed") and have("time_h"))) if ok]
        if len(g) < SoftRules.MIN_ROWS or np.isnan(dd).all():
            continue
        ud = 10.0 ** -infer_decimals(dd[~np.isnan(dd)])
        info.setdefault("unit_d", {})[veh] = (None, ud)
        sr = SoftRules(g, ud)
        idx = list(g.index)
        for k in range(len(g)):
            rid = int(g["row_id"].iloc[k])
            if rid in covered_ids:
                continue
            status, val = sr.fix_distance(k, cfg.typo_kinds)
            info["fix_status"][rid] = status
            counts[status] = counts.get(status, 0) + 1
            if status == "fix":
                old = float(df.at[idx[k], "distance"])
                df.at[idx[k], "distance"] = val
                log.append({"row_id": rid, "column": "distance", "old_value": old, "new_value": val,
                            "rule": "distance_two_relations", "confidence": "high"})
    info["fix_counts"] = counts


# ------------------------------------------------------------------ main entry
def edit(df_in: pd.DataFrame, cfg: EditConfig = EditConfig()):
    """Return (fixed frame, corrections frame, unresolved frame, info dict).

    df_in needs: row_id, vehicle, date, distance, cumulative_distance, source_file, source_sheet_no, source_row_no.
    """
    df = df_in.copy().reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date"])
    log, unresolved = [], []
    bad_dates = set()
    legacy = True  # the second round rules (date, copy, typo, min-cell) stay on in every policy
    new_rule = cfg.policy == "combined"
    if cfg.use_date:
        newdate, bad_dates = repair_dates(df, cfg, log, unresolved, fix=legacy)
        df["date"] = newdate
    info = {"tol": {}, "units": {}, "dup_identical": 0, "dup_conflict": 0, "fix_status": {}, "fix_counts": {}, "checks": {}}
    pos = {int(r): k for k, r in enumerate(df["row_id"])}
    # the same vehicle and date twice (overlapping files): identical rows count once, conflicting rows leave the chain
    excluded = set(bad_dates)
    ok = df[df["date"].notna() & ~df.index.isin(bad_dates)]
    for (veh, day), g in ok.groupby(["vehicle", "date"], sort=False):
        if len(g) < 2:
            continue
        vals = g[["distance", "cumulative_distance"]].round(6)
        # same day in two files (one is a re-typed copy of the other, blanks differ): no cell holds two different values -> merge, blanks filled
        conflict = any(vals[c].dropna().nunique() > 1 for c in vals.columns)
        if not conflict:
            keep = g[MEASURE_COLS].notna().sum(axis=1).idxmax()
            for c in MEASURE_COLS:
                if pd.isna(df.at[keep, c]):
                    other = g[c].dropna()
                    if len(other):
                        df.at[keep, c] = other.iloc[0]
            info["dup_identical"] += len(g) - 1
            info["dup_merged"] = info.get("dup_merged", 0) + int(any(g[c].isna().any() and g[c].notna().any() for c in MEASURE_COLS))
            excluded.update(i for i in g.index if i != keep)
        else:
            info["dup_conflict"] += len(g)
            excluded.update(g.index)
            unresolved.append({"row_ids": " ".join(str(int(x)) for x in g["row_id"]), "column": "distance/cumulative_distance",
                               "reason": "same_date_conflicting_rows", "n_spans": 0, "vehicle": veh})
    bad_dates = excluded
    info["excluded_rows"] = {int(df.at[i, "row_id"]) for i in excluded}
    covered_ids: set = set()
    for veh, g in df.groupby("vehicle", sort=False):
        g = g[~g.index.isin(bad_dates) & g["date"].notna()]
        g = g.sort_values(["date", "source_file", "source_sheet_no", "source_row_no"], kind="stable")
        if len(g) < 3:
            continue
        ids = g["row_id"].to_numpy()
        days = np.array([(x.astype("datetime64[D]") - EPOCH).astype(int) for x in g["date"].to_numpy()])
        C = pd.to_numeric(g["cumulative_distance"], errors="coerce").to_numpy(dtype=float)
        D = pd.to_numeric(g["distance"], errors="coerce").to_numpy(dtype=float)
        hv = g["has_values"].to_numpy() if "has_values" in g else np.ones(len(g), bool)
        if np.isnan(C).all():
            continue
        uc = 10.0 ** -infer_decimals(C[~np.isnan(C)])
        ud = 10.0 ** -infer_decimals(D[~np.isnan(D)]) if (~np.isnan(D)).any() else 1.0
        info["units"][veh] = (uc, ud)
        info["tol"][veh] = uc + ud
        ch = Chain(ids, days, C, D, hv, uc, ud, cfg, aux=chain_aux(g, D, ud))
        covered_ids.update(int(ids[k]) for k in ch.d_span)
        ex = [abs(ch.resid(i)) for i, sp in enumerate(ch.spans) if sp["exact"]]
        t = ch.tol
        info.setdefault("spans", {})[veh] = {
            "rows_in_chain": len(ids), "spans": len(ch.spans), "exact": len(ex), "inequality": len(ch.spans) - len(ex),
            "violated_before": sum(1 for i in range(len(ch.spans)) if ch.violated(i)),
            "resid_le_tol": sum(1 for r in ex if r <= t + 1e-9), "resid_1_2_tol": sum(1 for r in ex if t < r <= 2 * t + 1e-9),
            "resid_2_5_tol": sum(1 for r in ex if 2 * t < r <= 5 * t + 1e-9), "resid_gt_5_tol": sum(1 for r in ex if r > 5 * t + 1e-9),
            "resid_le_half_tol": sum(1 for r in ex if r <= t / 2 + 1e-9),
        }
        modes = []
        if cfg.use_copy:
            modes.append(("copy", "copy_previous_day"))
        if cfg.use_typo:
            modes.append(("typo", "typo_inversion"))
        if cfg.use_mincell:
            modes.append(("mincell", "min_cells"))
        logged = {}
        for mode, rule in modes:
            snapC, snapD = ch.C.copy(), ch.D.copy()
            for _ in range(50):
                progressed = False
                for grp in ch.groups():
                    res = ch.solve_group(grp, mode)
                    if not res:
                        continue
                    for cell, old, new in res:
                        ch.put(cell, new)
                    progressed = True
                if not progressed:
                    break
            for cur_arr, snap, orig, col in ((ch.C, snapC, ch.orig_C, "cumulative_distance"), (ch.D, snapD, ch.orig_D, "distance")):
                for k in np.nonzero(np.abs(np.nan_to_num(cur_arr) - np.nan_to_num(snap)) > 1e-9)[0]:
                    logged[(int(ids[k]), col)] = {"row_id": int(ids[k]), "column": col, "old_value": orig[k], "new_value": cur_arr[k],
                                                  "rule": rule, "confidence": "high" if mode != "mincell" else "medium"}
        log.extend(logged.values())
        for grp in ch.groups():
            cells = ch.cells_of(grp)
            unresolved.append({"row_ids": " ".join(str(int(ids[k])) for _, k in sorted({(c[0], c[1]) for c in cells}, key=lambda x: x[1])),
                               "column": "distance/cumulative_distance",
                               "reason": "equality_violated_no_unique_fix" if ch.spans[grp[0]]["exact"] else "inequality_violated_no_unique_fix",
                               "n_spans": len(grp), "vehicle": veh})
        for k in range(len(ids)):
            r = pos[int(ids[k])]
            df.at[r, "cumulative_distance"] = ch.C[k] if not np.isnan(ch.C[k]) else np.nan
            df.at[r, "distance"] = ch.D[k] if not np.isnan(ch.D[k]) else np.nan
    if new_rule:
        fix_distances(df, bad_dates, cfg, log, info, covered_ids)
    corr = pd.DataFrame(log, columns=["row_id", "column", "old_value", "new_value", "rule", "confidence"])
    unres = pd.DataFrame(unresolved)
    # soft rules: warn only (never changes a value). Runs on every vehicle, also those without a cumulative distance (MAN).
    info["soft"], info["soft_warnings"] = {}, []
    if cfg.soft_rules:
        for veh, g in df.groupby("vehicle", sort=False):
            g = g[~g.index.isin(bad_dates) & g["date"].notna()].sort_values(["date", "source_file", "source_sheet_no", "source_row_no"], kind="stable")
            dd = pd.to_numeric(g["distance"], errors="coerce").to_numpy(dtype=float)
            if len(g) < SoftRules.MIN_ROWS or np.isnan(dd).all():
                continue
            sr = SoftRules(g, 10.0 ** -infer_decimals(dd[~np.isnan(dd)]))
            info["soft"][veh] = {REL_NAME[r]: {"defined": sr.stats[r][0], "consistent": sr.stats[r][1], "valid": bool(sr.valid[r])} for r in (1, 2)}
            ids_g = g["row_id"].to_numpy()
            for k, rel in sr.warn_rows(dd):
                info["soft_warnings"].append({"row_id": int(ids_g[k]), "vehicle": veh, "rule": REL_NAME[rel],
                                              "fix_status": info["fix_status"].get(int(ids_g[k]), "")})
    for veh, (_, ud_) in info.get("unit_d", {}).items():
        info["tol"].setdefault(veh, ud_)
    return df, corr, unres, info
