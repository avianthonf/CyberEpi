"""CyberEpi-PHASE_SHIFT (SYNTHESIS §5 item 1; B1, source [10 §7 item 1]).

Base: equal linear pool of EAKF and GBQR, shadow.mix_linear_pool (our own pool;
the FluSight ensemble is published after the deadline and is never used).

Phase: from as-of admissions at the reference date. Let L be the newest week
published by R-7 (pick_vintage) and g = (log1p y_L - log1p y_{L-3}) / 3 on the
log1p scale. Rising if g > +0.05, declining if g < -0.05, else peak.

Shift: an additive log1p-scale shift per (phase, horizon), applied to every
quantile of the base pool, so quantile ordering is preserved.

Table estimation (estimate(), dev seasons 2023-24 and 2024-25 only):
  - Base proxy used for estimation: persistence, log1p(y_L) for every horizon.
    Dev-season EAKF/GBQR outputs are not in the repo, so the shift is estimated
    on this proxy, not on MIX_LP. The table is a phase correction to trend
    extrapolation, and is not verified on MIX_LP.
  - Error e = log1p(truth at ref+7h) - log1p(y_L), with truth = latest vintage.
  - Cell (phase, h) = median e over both seasons pooled. Required: at least
    MIN_ROWS rows in each season, and the two single-season medians share a sign
    (LOSO: each season checks the other). Otherwise the cell is 0.
  - Never 2025-26 or later.

Diagnostics: module-level `last_diagnostics` (one row per location). Written to
ctx.diagnostics_dir/phase_shift-<ref>.csv if that attribute exists.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_BT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BT not in sys.path:
    sys.path.insert(0, _BT)

from run_vintage import WEEK, load_vintages, pick_vintage, series_at  # noqa: E402
from shadow import KEY, mix_linear_pool  # noqa: E402

LAG = 3
RISE, DECL = 0.05, -0.05
PHASES = ("rising", "peak", "declining")
HORIZONS = (0, 1, 2, 3)
DEV_SEASONS = (2023, 2024)  # season start years
MIN_ROWS = 20
SEASON_MONTHS = (10, 11, 12, 1, 2, 3, 4, 5)

# ---- frozen table: log1p-scale additive shift, rows = phase, columns = horizon 0..3 ----
SHIFT = {
    "rising": (0.0, 0.0, 0.0, 0.0),
    "peak": (0.0, 0.0, 0.0, 0.0),
    "declining": (0.0, 0.0, 0.0, 0.0),
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


def proxy_rows() -> pd.DataFrame:
    """Dev-season rows: as-of phase, persistence error per horizon. Dev seasons only."""
    v = load_vintages()
    truth = {(l, t): o for l, t, o in
             v.sort_values("as_of")[["location", "target_end_date", "observation"]].itertuples(index=False)}
    locs = sorted(v["location"].unique())
    rows = []
    for ref in pd.date_range("2023-10-01", "2025-05-31", freq="W-SAT"):
        if ref.month not in SEASON_MONTHS or season_start(ref) not in DEV_SEASONS:
            continue
        for loc in locs:
            g, as_of, last, why = growth_asof(loc, ref)
            if why:
                continue
            s = series_at(as_of, loc, last)
            base = np.log1p(float(s.iloc[-1]))
            for h in HORIZONS:
                t = truth.get((loc, ref + h * WEEK))
                if t is None or pd.isna(t):
                    continue
                rows.append({"season": season_start(ref), "ref": ref, "location": loc, "horizon": h,
                             "phase": phase_of(g), "err": np.log1p(float(t)) - base})
    return pd.DataFrame(rows)


def estimate(rows: pd.DataFrame) -> tuple[dict, pd.DataFrame]:
    """Frozen-table estimator and LOSO sign report. Returns (table, loso_report)."""
    table, report = {}, []
    for p in PHASES:
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
