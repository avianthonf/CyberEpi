"""CyberEpi-ETS_DECL: damped log-trend comparator for the declining phase (SYNTHESIS §5 item 3, B3).

Model, per location, at reference date R (all inputs as published by R):
  y_t   = log1p(admissions) on the as-of series through R-7 (interior gaps interpolated).
  b     = (y_T - y_{T-K}) / K, the K-week slope (T = last observed week).
  mu_s  = y_T + b * sum_{i=1..s} PHI**i, the damped trend forecast s = h+1 weeks ahead.
  Quantiles: mu_s + sqrt(s) * Q_tau, where Q_tau are empirical quantiles of this model's own
  one-step as-of errors over the two seasons before R. The error for past reference date r is
  e_r = y_r (as first published by r+7) - mu_r (forecast from the vintage published by r).
  Output: expm1, clipped at 0, sorted within each row, hub long format for horizons 0-3.

Frozen constants (derivation):
  PHI = 0.9: fixed by specification (SYNTHESIS §5 item 3); not tuned.
  K = 5 weeks: chosen from {3, 4, 5} by the lowest mean absolute error of the damped point
    forecast (log1p, horizons 0-3) on as-of replays of the dev seasons 2023-24 and 2024-25 only.
    2025-26 and later were not used.
  sqrt(s) scaling of the one-step error quantiles: a random-walk-consistent assumption for
    multi-step widths, fixed in advance; the spec asks for one-step errors only.
  MIN_WEEKS = 30: minimum observed weeks in the as-of series (specification fail-safe).
  The error window is the two seasons before R (specification); no tuned window.

Requires backtest/ on sys.path (as shadow.py is run). Raises on missing inputs.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

_BT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BT not in sys.path:
    sys.path.insert(0, _BT)

from hub_data import PRIMARY_TARGET, load_locations  # noqa: E402
from run_flusight import SEASONS  # noqa: E402
from run_vintage import WEEK, pick_vintage, series_at  # noqa: E402
from shadow import KEY, LEVELS, to_long  # noqa: E402

PHI = 0.9
K = 5
MIN_WEEKS = 30
HORIZONS = range(4)


def _season_of(ref: pd.Timestamp) -> str:
    for name, (lo, hi) in SEASONS.items():
        if pd.Timestamp(lo) <= ref <= pd.Timestamp(hi):
            return name
    raise ValueError(f"reference date {ref.date()} outside known seasons")


def _previous_two_seasons(ref: pd.Timestamp) -> list[str]:
    names = list(SEASONS)
    i = names.index(_season_of(ref))
    if i < 2:
        raise ValueError(f"need two previous seasons before {ref.date()}")
    return names[i - 2:i]


def _log_series(as_of: pd.Timestamp, loc: str, last_week: pd.Timestamp) -> np.ndarray:
    """log1p of the as-of series through last_week; interior gaps interpolated."""
    s = series_at(as_of, loc, last_week)
    if s.empty or pd.isna(s.iloc[-1]):
        raise RuntimeError(f"no as-of observation for {loc} at {last_week.date()}")
    y = np.log1p(s.astype(float).clip(lower=0))
    return y.interpolate(limit_area="inside").to_numpy(float)


def _slope(y: np.ndarray) -> float:
    return (y[-1] - y[-K - 1]) / K


def _forecast_log(y: np.ndarray) -> float:
    """Damped one-step-ahead log1p point forecast from the as-of series y."""
    return y[-1] + PHI * _slope(y)


def _error_pool(ref: pd.Timestamp, loc: str) -> np.ndarray:
    """One-step as-of errors for `loc` at each past reference date in the two previous seasons.

    For past reference date r: forecast mu from the vintage published by r (newest week r-7),
    truth = week r as first published by r+7 (the newest week of that vintage).
    """
    seasons = _previous_two_seasons(ref)
    lo = min(pd.Timestamp(SEASONS[s][0]) for s in seasons)
    hi = max(pd.Timestamp(SEASONS[s][1]) for s in seasons)
    out = []
    for r in pd.date_range(lo, hi, freq="W-SAT"):
        p_now, p_next = pick_vintage(r), pick_vintage(r + WEEK)
        if p_now is None or p_next is None or p_next[1] != r:
            continue
        y = _log_series(p_now[0], loc, p_now[1])
        if np.isfinite(y).sum() < MIN_WEEKS or not np.isfinite(y[-K - 1:]).all():
            continue
        truth = _log_series(p_next[0], loc, r)[-1]
        if not np.isfinite(truth):
            continue
        out.append(truth - _forecast_log(y))
    if not out:
        raise RuntimeError(f"no error history for {loc} before {ref.date()}")
    return np.asarray(out)


def _location_quantiles(ref: pd.Timestamp, loc: str) -> np.ndarray:
    """Count-scale quantile matrix (len(HORIZONS), len(LEVELS)) for one location."""
    pick = pick_vintage(ref)
    if pick is None:
        raise RuntimeError(f"no as-of vintage at {ref.date()}")
    as_of, last = pick
    y = _log_series(as_of, loc, last)
    if np.isfinite(y).sum() < MIN_WEEKS:
        raise RuntimeError(f"{loc}: fewer than {MIN_WEEKS} observed weeks")
    if len(y) < K + 1 or not np.isfinite(y[-K - 1:]).all():
        raise RuntimeError(f"{loc}: no complete trend window at {ref.date()}")
    yt, b = y[-1], _slope(y)
    q = np.quantile(_error_pool(ref, loc), LEVELS)
    rows = []
    for h in HORIZONS:
        s = h + 1
        mu = yt + b * sum(PHI ** i for i in range(1, s + 1))
        rows.append(np.sort(np.expm1(np.maximum(mu + np.sqrt(s) * q, 0.0))))
    return np.vstack(rows)


def run(ref: str, ctx) -> pd.DataFrame:
    rd = pd.Timestamp(ref)
    locs = load_locations()["location"].astype(str).tolist()
    frames = []
    for loc in locs:
        mat = _location_quantiles(rd, loc)
        for h in HORIZONS:
            tend = (rd + h * WEEK).strftime("%Y-%m-%d")
            idx = pd.MultiIndex.from_tuples([(ref, PRIMARY_TARGET, h, tend, loc)], names=KEY)
            cols = pd.Index(LEVELS.round(3), name="output_type_id")
            frames.append(pd.DataFrame([mat[h]], columns=cols, index=idx))
    return to_long(pd.concat(frames))
