"""CyberEpi-PHASE_SHIFT (SYNTHESIS §5 item 1; B1, source [10 §7 item 1]).

Base: equal linear pool of EAKF and GBQR, shadow.mix_linear_pool (our own pool;
the FluSight ensemble is published after the deadline and is never used).

Phase: from as-of admissions at the reference date. Let L be the newest week
published by R-7 (pick_vintage) and g = (log1p y_L - log1p y_{L-3}) / 3 on the
log1p scale. Rising if g > +0.05, declining if g < -0.05, else peak.

Shift: an additive log1p-scale shift per (phase, horizon), applied to every
quantile of the base pool, so quantile ordering is preserved.

Table estimation (estimate(), dev seasons 2023-24 and 2024-25 only):
  - Source: as-of dev-season MIX_LP forecasts,
    backtest/results/dev_members/<ref>-CyberEpi-MIX_LP.csv (57 reference dates;
    regenerate with backtest/dev_members.py). This is the same pool run() shifts.
  - Error e = log1p(truth) - log1p(pool median), truth = latest vintage;
    e > 0 means the pool is low. Phase per (ref, location) by the rule above.
  - Cell (phase, h) = median e over both seasons pooled, rounded to 3 dp.
    Required: at least MIN_ROWS rows in each season, and the two single-season
    medians share a sign (LOSO: each season checks the other). Otherwise 0.
  - Never 2025-26 or later. Rows: 12,078 (2023-24: 6,354; 2024-25: 5,724).

Frozen LOSO record (median e; 2023-24 | 2024-25 -> shift):
  rising     h0 +0.033|+0.213 -> +0.111  h1 +0.051|+0.362 -> +0.163
             h2 +0.087|+0.497 -> +0.254  h3 +0.134|+0.633 -> +0.387
  peak       h0  0.000|+0.197 -> 0 (no sign)  h1 +0.033|+0.248 -> +0.105
             h2  0.000|+0.327 -> 0 (no sign)  h3  0.000|+0.405 -> 0 (no sign)
  (2023-24 peak medians are exactly 0 with errors split evenly, e.g. h2 109
  above / 110 below, only 5-16 exact ties: no direction rather than a sign flip.)
  declining  h0 +0.066|+0.175 -> +0.128  h1 +0.087|+0.249 -> +0.173
             h2 +0.095|+0.357 -> +0.222  h3 +0.031|+0.405 -> +0.248
Phase-free comparator (estimate_horizon_only): +0.113, +0.161, +0.226, +0.288,
all sign-stable (2023-24 +0.04..+0.08; 2024-25 +0.19..+0.51). Phase residual
beyond that season x horizon level (median, 2023-24 | 2024-25): rising
+0.005|+0.069, peak -0.043|-0.030, declining +0.012|-0.037 (sign flips). The
table is mostly a level shift driven by 2024-25; phase adds little.
Reproduce: estimate(pool_rows()).

Diagnostics: module-level `last_diagnostics` (one row per location). Written to
ctx.diagnostics_dir/phase_shift-<ref>.csv if that attribute exists.
"""
from __future__ import annotations

import glob
import os
import sys

import numpy as np
import pandas as pd

_BT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BT not in sys.path:
    sys.path.insert(0, _BT)

from run_vintage import load_vintages, pick_vintage, series_at  # noqa: E402
from shadow import KEY, mix_linear_pool  # noqa: E402

LAG = 3
RISE, DECL = 0.05, -0.05
PHASES = ("rising", "peak", "declining")
HORIZONS = (0, 1, 2, 3)
DEV_SEASONS = (2023, 2024)  # season start years
MIN_ROWS = 20

DEV_DIR = os.path.join(_BT, "results", "dev_members")
# ---- frozen table: log1p-scale additive shift, rows = phase, columns = horizon 0..3 ----
SHIFT = {
    "rising": (0.111, 0.163, 0.254, 0.387),
    "peak": (0.0, 0.105, 0.0, 0.0),
    "declining": (0.128, 0.173, 0.222, 0.248),
}

last_diagnostics: pd.DataFrame = pd.DataFrame()


def season_start(ref: pd.Timestamp) -> int:
    return ref.year if ref.month >= 10 else ref.year - 1


def phase_of(g: float) -> str:
    if g > RISE:
        return "rising"
    if g < DECL:
        return "declining"
    return "peak"


def growth_asof(loc: str, ref: pd.Timestamp):
    """(growth, as_of, last_week, reason) from as-of data; growth is NaN on failure."""
    pick = pick_vintage(ref)
    if pick is None:
        return np.nan, pd.NaT, pd.NaT, "no as-of vintage"
    as_of, last = pick
    s = series_at(as_of, loc, last)
    if len(s) < LAG + 1 or s.iloc[-(LAG + 1):].isna().any():
        return np.nan, as_of, last, "missing last weeks"
    ly = np.log1p(s.iloc[-(LAG + 1):].to_numpy(float))
    return (ly[-1] - ly[0]) / LAG, as_of, last, ""


def pool_rows(dev_dir: str = DEV_DIR) -> pd.DataFrame:
    """Dev-season rows: as-of phase, log1p error of the MIX_LP median vs latest-vintage truth."""
    v = load_vintages()
    truth = {(l, t): o for l, t, o in
             v.sort_values("as_of")[["location", "target_end_date", "observation"]].itertuples(index=False)}
    rows = []
    for f in sorted(glob.glob(os.path.join(dev_dir, "*-CyberEpi-MIX_LP.csv"))):
        df = pd.read_csv(f, dtype={"location": str}, parse_dates=["reference_date", "target_end_date"])
        ref = df["reference_date"].iloc[0]
        if season_start(ref) not in DEV_SEASONS:
            continue
        med = df[(df.output_type_id.round(3) == 0.5) & df.horizon.isin(HORIZONS)]
        phase = {}
        for r in med.itertuples(index=False):
            if r.location not in phase:
                g, _, _, why = growth_asof(r.location, ref)
                phase[r.location] = None if why else phase_of(g)
            t = truth.get((r.location, r.target_end_date))
            if phase[r.location] is None or t is None or pd.isna(t):
                continue
            rows.append({"season": season_start(ref), "ref": ref, "location": r.location,
                         "horizon": int(r.horizon), "phase": phase[r.location],
                         "err": np.log1p(float(t)) - np.log1p(max(float(r.value), 0.0))})
    return pd.DataFrame(rows)


def estimate_horizon_only(rows: pd.DataFrame) -> tuple[tuple, pd.DataFrame]:
    """Phase-free comparator: same LOSO rule, all phases pooled."""
    t, rep = estimate(rows.assign(phase="all"), phases=("all",))
    return t["all"], rep


def estimate(rows: pd.DataFrame, phases=PHASES) -> tuple[dict, pd.DataFrame]:
    """Frozen-table estimator and LOSO sign report. Returns (table, loso_report)."""
    table, report = {}, []
    for p in phases:
        table[p] = []
        for h in HORIZONS:
            per = {}
            for s in DEV_SEASONS:
                sub = rows[(rows.season == s) & (rows.phase == p) & (rows.horizon == h)]
                per[s] = (float(sub.err.median()) if len(sub) >= MIN_ROWS else np.nan, len(sub))
            both = rows[(rows.phase == p) & (rows.horizon == h)]
            m = [per[s][0] for s in DEV_SEASONS]
            signs_ok = bool(np.all(np.isfinite(m)) and np.sign(m[0]) == np.sign(m[1]) and m[0] != 0)
            val = round(float(both.err.median()), 3) if signs_ok and len(both) >= 2 * MIN_ROWS else 0.0
            table[p].append(val)
            report.append({"phase": p, "horizon": h, "median_2023_24": m[0], "n_2023_24": per[2023][1],
                           "median_2024_25": m[1], "n_2024_25": per[2024][1],
                           "loso_sign_stable": signs_ok, "shift": val})
    return {p: tuple(v) for p, v in table.items()}, pd.DataFrame(report)


def _shift_frame(ref: pd.Timestamp) -> pd.DataFrame:
    rows = []
    for loc in sorted(_locations_at(ref)):
        g, as_of, last, why = growth_asof(loc, ref)
        phase = phase_of(g) if not why else "peak"
        rec = {"reference_date": str(ref.date()), "location": loc, "as_of": str(as_of.date()) if not pd.isna(as_of) else "",
               "last_week": str(last.date()) if not pd.isna(last) else "", "growth": g, "phase": phase,
               "fallback": bool(why), "reason": why}
        for h in HORIZONS:
            rec[f"shift_h{h}"] = 0.0 if why else SHIFT[phase][h]
        rows.append(rec)
    return pd.DataFrame(rows)


def _locations_at(ref: pd.Timestamp):
    return load_vintages()["location"].unique()


def run(ref: str, ctx) -> pd.DataFrame:
    global last_diagnostics
    ref_ts = pd.Timestamp(ref)
    base = mix_linear_pool(ref, ctx).sort_values(["location", "horizon", "output_type_id"])
    diag = _shift_frame(ref_ts)
    last_diagnostics = diag
    d = getattr(ctx, "diagnostics_dir", None)
    if d:
        os.makedirs(d, exist_ok=True)
        diag.to_csv(os.path.join(d, f"phase_shift-{ref}.csv"), index=False)

    shift = {(r.location, h): getattr(r, f"shift_h{h}") for r in diag.itertuples(index=False)
             for h in HORIZONS}
    add = np.array([shift.get((l, h), 0.0) for l, h in zip(base["location"], base["horizon"])])
    out = base.copy()
    out["value"] = np.maximum(np.expm1(np.log1p(base["value"].to_numpy(float)) + add), 0.0)
    out["value"] = out.groupby(["location", "horizon"])["value"].transform(
        lambda x: np.maximum.accumulate(x.to_numpy()))
    return out[KEY[:2] + ["horizon", "target_end_date", "location", "output_type", "output_type_id", "value"]]
