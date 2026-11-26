"""CyberEpi-BOCD_MIX (SYNTHESIS §5 item 2; source [10 §7 item 2]).

Phase-aware two-member mixture of our own submitted forecasts.

Per location, as of reference date R (weeks through T = R-7 are observed):
  1. g_t = (log1p y_t - log1p y_{t-3}) / 3 on the as-of admissions series, from the
     start of the season (Oct 1 of the season year, with 3 lag weeks before it).
  2. Adams-MacKay BOCD on g with a constant hazard 1/HAZARD_LAMBDA and a Normal-Gamma
     model (Student-t predictive).
  3. w = P(changepoint in the last 2 weeks) = P(r_T <= 1 | x_1..T), the run-length
     posterior mass on a run that started at T or T-1.
  4. "continues" = equal-weight linear pool of CyberEpi-EAKF and CyberEpi-GBQR as
     submitted (shadow.mix_linear_pool).
     "turned" = the same pool with each quantile multiplied by exp(delta_h),
     delta_h = -2 * TURN_KAPPA * g_R * L_h, where L_h = weeks from T to the target end
     (h + 1), i.e. the 3-week slope reversed in sign over the horizon.
  5. Mixed CDF F = (1 - w) F_continues + w F_turned, inverted on the quantile grid,
     as mix_linear_pool does.

Frozen constants (derived 2026-11-26 on dev seasons 2023-24 and 2024-25 only, as-of
vintages via run_vintage.pick_vintage/series_at; no 2025-26 or later data used; script
was a throwaway under /tmp):
  - HAZARD_LAMBDA = 10 weeks: summed one-step BOCD predictive log-likelihood over the
    106 dev series (location x season, growth as of each season's last dev origin)
    on grid {2,4,8,10,20,40,80}: -833, -310, -137, -119 (best), -122, -173, -241.
  - PRIOR_MU0 = 0.04546, PRIOR_BETA0 = 0.09991: pooled dev growth mean and variance;
    PRIOR_KAPPA0 = PRIOR_ALPHA0 = 1 (weak prior on the mean and the scale).
  - TURN_KAPPA = 1.0 (full sign reversal of the 3-week slope, the spec's literal
    "turned" member). Dev least-squares fraction -sum((d - gL) x) / sum(x^2), with
    x = 2 w gL, d = realised log change from the vintage's last observed week to the
    target, L = weeks from that last week to the target: pooled 1.27 (clipped
    to [0, 1] = 1); LOSO 2023-24 0.90, 2024-25 2.02; by horizon 0.88, 1.14, 1.29,
    1.41. Positive in both folds. Vintages are stale (last < ref-7) on 21% of dev
    rows, so L is measured from `last`. Data: time-series.csv as-of vintages through
    run_vintage.pick_vintage/series_at (covers both dev seasons); target-data-archive
    is not used. No member forecasts were used in the freeze.
  Integrator: this is the main open risk to the B2 verdict.

Diagnostics: run_with_diagnostics returns (forecasts, per-location weights); the
integrator should write the weights to forecasts/shadow/diagnostics/.

Missing inputs (no submitted EAKF/GBQR file) raise. A location with fewer than
MIN_WEEKS growth weeks, or with a missing value in the last 4 observed weeks,
falls back to w = 0 (continues only) and is flagged in diagnostics.
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
from scipy.special import gammaln

_BT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BT not in sys.path:
    sys.path.insert(0, _BT)

from run_vintage import pick_vintage, series_at  # noqa: E402
from shadow import LEVELS, mix_linear_pool, to_long, wide  # noqa: E402

# ---- frozen constants (see header) ----
HAZARD_LAMBDA = 10.0
PRIOR_MU0 = 0.045461462977948834
PRIOR_KAPPA0 = 1.0
PRIOR_ALPHA0 = 1.0
PRIOR_BETA0 = 0.09990981741359571
TURN_KAPPA = 1.0

MIN_WEEKS = 8
LAG = 3


def season_start(ref: pd.Timestamp) -> pd.Timestamp:
    year = ref.year if ref.month >= 10 else ref.year - 1
    return pd.Timestamp(year=year, month=10, day=1)


def bocd_run_posterior(x: np.ndarray, lam: float, mu0: float, k0: float, a0: float, b0: float) -> np.ndarray:
    """Run-length posterior P(r_T = k | x_1..T), k = 0..T, after the last observation.

    Adams-MacKay BOCD, constant hazard 1/lam, Normal-Gamma prior, Student-t predictive.
    (P(r_t = 0) alone is always exactly 1/lam under a constant hazard, so the
    changepoint signal is read from the run-length posterior, not from r_t = 0.)
    """
    H = 1.0 / lam
    mu = np.array([mu0]); kap = np.array([k0]); al = np.array([a0]); be = np.array([b0])
    logp = np.zeros(1)
    for xt in x:
        df = 2.0 * al
        scale = np.sqrt(be * (kap + 1.0) / (al * kap))
        z = (xt - mu) / scale
        logpred = (gammaln((df + 1) / 2) - gammaln(df / 2) - 0.5 * np.log(df * np.pi)
                   - np.log(scale) - (df + 1) / 2 * np.log1p(z * z / df))
        joint = logp + logpred
        cp = np.logaddexp.reduce(joint + np.log(H))
        new = np.concatenate([[cp], joint + np.log1p(-H)])
        logp = new - np.logaddexp.reduce(new)
        mu_n = (kap * mu + xt) / (kap + 1.0)
        be_n = be + kap * (xt - mu) ** 2 / (2.0 * (kap + 1.0))
        mu = np.concatenate([[mu0], mu_n])
        kap = np.concatenate([[k0], kap + 1.0])
        al = np.concatenate([[a0], al + 0.5])
        be = np.concatenate([[b0], be_n])
    return np.exp(logp)


def growth(log_y: np.ndarray) -> np.ndarray:
    """3-week log growth per week; element k is the growth ending at index k + LAG."""
    return (log_y[LAG:] - log_y[:-LAG]) / LAG


def location_weight(loc: str, ref: pd.Timestamp) -> dict:
    """Per-location BOCD weight and recent growth as of ref. Returns a diagnostics dict."""
    pick = pick_vintage(ref)
    if pick is None:
        raise RuntimeError(f"no as-of admissions vintage usable at {ref.date()}")
    as_of, last = pick
    s0 = season_start(ref)
    grid_start = s0 - pd.Timedelta(weeks=LAG)
    s = series_at(as_of, loc, last)
    s = s[s.index >= grid_start] if len(s) else s
    rec = {"location": loc, "reference_date": str(ref.date()), "as_of": str(as_of.date()),
           "last_week": str(last.date()), "fallback": False, "reason": "", "growth_R": np.nan,
           "p_run_le1": np.nan, "weight": 0.0}
    if len(s) < 4 or s.iloc[-4:].isna().any():
        rec.update(fallback=True, reason="missing last 4 weeks")
        return rec
    ly = np.log1p(s.interpolate(limit_direction="both").to_numpy(float))
    if ly.size - LAG < MIN_WEEKS:
        rec.update(fallback=True, reason=f"fewer than {MIN_WEEKS} growth weeks")
        return rec
    g = growth(ly)
    post = bocd_run_posterior(g, HAZARD_LAMBDA, PRIOR_MU0, PRIOR_KAPPA0, PRIOR_ALPHA0, PRIOR_BETA0)
    w = float(post[:2].sum())  # run length <= 1: a changepoint at T or T-1
    rec.update(growth_R=float(g[-1]), p_run_le1=w, weight=w)
    return rec


def _mix_row(qc: np.ndarray, qt: np.ndarray, w: float) -> np.ndarray:
    """Quantiles of (1-w) F_c + w F_t via the piecewise-linear CDF, as mix_linear_pool."""
    if w <= 0:
        return qc.copy()
    grid = np.unique(np.concatenate([qc, qt]))
    fc = np.interp(grid, np.sort(qc), LEVELS)
    ft = np.interp(grid, np.sort(qt), LEVELS)
    cdf = np.maximum.accumulate((1 - w) * fc + w * ft)
    return np.interp(LEVELS, cdf + np.arange(len(cdf)) * 1e-12, grid)


def _build(ref: pd.Timestamp, ctx) -> tuple[pd.DataFrame, pd.DataFrame]:
    cont = wide(mix_linear_pool(ctx.ref, ctx))  # raises if EAKF/GBQR missing
    te = pd.to_datetime(cont.index.get_level_values("target_end_date"))
    locs = cont.index.get_level_values("location").astype(str)
    diag = {}
    out = np.empty(cont.shape)
    qc_all = cont.to_numpy(float)
    for loc in pd.unique(locs):
        diag[loc] = location_weight(loc, ref)
    for i in range(len(qc_all)):
        d = diag[locs[i]]
        # weeks from the vintage's last observed week (g_R ends there) to the target
        L = max((te[i] - pd.Timestamp(d["last_week"])).days / 7.0, 0.0)
        if d["weight"] <= 0:
            out[i] = qc_all[i]
            continue
        delta = -2.0 * TURN_KAPPA * d["growth_R"] * L
        out[i] = _mix_row(qc_all[i], qc_all[i] * np.exp(delta), d["weight"])
    mixed = pd.DataFrame(out, index=cont.index, columns=cont.columns)
    diag_df = pd.DataFrame(list(diag.values()))
    return to_long(mixed), diag_df


def run_with_diagnostics(ref: str, ctx) -> tuple[pd.DataFrame, pd.DataFrame]:
    return _build(pd.Timestamp(ref), ctx)


def run(ref: str, ctx) -> pd.DataFrame:
    df, _ = _build(pd.Timestamp(ref), ctx)
    return df
