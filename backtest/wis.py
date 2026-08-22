"""Weighted Interval Score (WIS), matching the FluSight / hubEvals definition.

WIS(F, y) = 1/(K + 1/2) * [ (1/2)|y - m| + sum_k (alpha_k/2) * IS_{alpha_k}(l_k, u_k; y) ]

where m is the median, and interval k is the central (1 - alpha_k) interval.
IS_a(l, u; y) = (u - l) + (2/a)(l - y) * 1{y < l} + (2/a)(y - u) * 1{y > u}
"""
from __future__ import annotations

import numpy as np


def interval_score(lower: np.ndarray, upper: np.ndarray, alpha: float, y: np.ndarray) -> np.ndarray:
    width = upper - lower
    below = (y < lower) * (lower - y)
    above = (y > upper) * (y - upper)
    return width + (2.0 / alpha) * (below + above)


def weighted_interval_score(
    quantile_levels: np.ndarray, quantile_values: np.ndarray, y: float | np.ndarray,
) -> float | np.ndarray:
    """WIS over symmetric central intervals implied by quantiles.

    quantile_levels/values are 1-D, sorted ascending levels, including 0.5.
    y may be scalar or array broadcastable against columns of quantile_values
    when quantile_values is 2-D (n_items, n_levels).
    """
    ql = np.asarray(quantile_levels, dtype=float)
    qv = np.asarray(quantile_values, dtype=float)
    y = np.asarray(y, dtype=float)

    k_intervals = (ql < 0.5).sum()
    if not np.isin(0.5, ql):
        raise ValueError("median (0.5) quantile missing")

    med = qv[..., int(np.where(ql == 0.5)[0][0])]
    wis = 0.5 * np.abs(y - med)
    for k in range(k_intervals):
        tau_lo = ql[k]
        alpha = 2.0 * tau_lo
        lo, hi = qv[..., k], qv[..., len(ql) - 1 - k]
        wis = wis + (alpha / 2.0) * interval_score(lo, hi, alpha, y)
    return wis / (k_intervals + 0.5)


def coverage(quantile_levels: np.ndarray, quantile_values: np.ndarray,
             y: float | np.ndarray, alpha: float) -> float:
    """Central (1-alpha) interval coverage."""
    ql = np.asarray(quantile_levels, dtype=float)
    qv = np.asarray(quantile_values)
    lo_idx = int(np.where(np.isclose(ql, alpha / 2))[0][0])
    hi_idx = int(np.where(np.isclose(ql, 1 - alpha / 2))[0][0])
    lo, hi = qv[..., lo_idx], qv[..., hi_idx]
    return float(np.mean((y >= lo) & (y <= hi)))
