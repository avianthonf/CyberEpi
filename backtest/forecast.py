"""FluSight-format forecast generation from a filter ensemble.

Given filter ensemble X at the Sunday starting the week ending at
reference_date R (i.e. data processed through week R-7):
  horizon -1 -> week ending R-7 : near-deterministic, last observed value
  horizon 0  -> week ending R   : nowcast (7-day block)
  horizon 1..3: forecast blocks ending R+7, R+14, R+21
"""
from __future__ import annotations

import numpy as np
from hub_data import PRIMARY_TARGET, STANDARD_QUANTILES
from seir_fast import LB, FluParams, S, W, integrate


def delay_kernel(mean_days: float, max_lag: int = 30) -> np.ndarray:
    """Discrete Erlang-2 infection-to-admission kernel on lags 0..max_lag (continuous mean `mean_days`)."""
    theta = mean_days / 2.0
    edges = np.arange(max_lag + 2, dtype=float) / theta
    cdf = 1.0 - np.exp(-edges) * (1.0 + edges)
    k = np.diff(cdf)
    return k / k.sum()


def forecast_quantiles(
    X: np.ndarray,
    p: FluParams,
    horizons: tuple[int, ...] = (0, 1, 2, 3),
    s_obs: float = 0.10,
    sd_beta_fwd: float = 0.05,
    rng: np.random.Generator | None = None,
    beta_revert_hl_wk: float = 0.0,
    lb_anchor: float | None = None,
    delay_mean_days: float = 0.0,
    depletion_gamma: float = 1.0,
    hist: np.ndarray | None = None,
) -> dict[int, np.ndarray]:
    """Return {horizon: quantile array aligned to STANDARD_QUANTILES}.

    Integrate forward in 7-day blocks; between blocks log_beta performs a
    random walk with per-day sd `sd_beta_fwd` (dispersion during forecast).
    Weekly admission samples = W increment within each block; multiplicative
    jitter exp(N(0, s_obs)) represents reporting noise/overdispersion.
    beta_revert_hl_wk > 0 pulls log_beta toward `lb_anchor` (a recent or
    seasonal level from the filter history) after each day's noise, with that
    half-life in weeks (0 = off).
    delay_mean_days > 0 convolves daily admission incidence with an Erlang-2
    delay kernel; pre-origin days come from `hist` (M, days, oldest first) if given, else repeat the first forward day's
    incidence (0 = off). depletion_gamma != 1 adds (gamma-1)*dlog(S) to
    log_beta each forward day, i.e. extra depletion relative to the origin
    (1 = off).
    """
    rng = rng or np.random.default_rng(0)
    x = X.copy()
    x[:, W] = 0.0
    revert_k = 1.0 - 0.5 ** (1.0 / (7.0 * beta_revert_hl_wk)) if beta_revert_hl_wk > 0 else 0.0
    if revert_k > 0 and lb_anchor is None:
        raise ValueError("beta_revert_hl_wk > 0 needs lb_anchor")
    kern = delay_kernel(delay_mean_days) if delay_mean_days > 0 else None
    depl = depletion_gamma != 1.0
    hs = sorted(hh for hh in horizons if hh >= 0)
    daily_inc: list[np.ndarray] = []
    out: dict[int, np.ndarray] = {}
    for h in hs:
        for _ in range(7):
            w0 = x[:, W].copy() if kern is not None else None
            ls0 = np.log(np.maximum(x[:, S], 1.0)) if depl else None
            x = integrate(x, 1, p)[0]
            if sd_beta_fwd > 0:
                x[:, LB] += rng.normal(0.0, sd_beta_fwd, len(x))
            if revert_k > 0:
                x[:, LB] += (lb_anchor - x[:, LB]) * revert_k
            if depl:
                x[:, LB] += (depletion_gamma - 1.0) * (np.log(np.maximum(x[:, S], 1.0)) - ls0)
            if kern is not None:
                daily_inc.append(x[:, W] - w0)
        if kern is None:
            adm = np.maximum(x[:, W], 0.0)
            adm = adm * np.exp(rng.normal(0.0, s_obs, len(adm)))
            out[h] = np.maximum(np.round(np.quantile(adm, STANDARD_QUANTILES)), 0.0)
        x[:, W] = 0.0
    if kern is not None:
        inc = np.maximum(np.array(daily_inc), 0.0)  # (days, M)
        n_lag = len(kern)
        pre = np.repeat(inc[:1], n_lag - 1, axis=0) if hist is None else hist[:, -(n_lag - 1):].T
        pad = np.concatenate([pre, inc])
        delayed = np.stack([kern @ pad[t + n_lag - 1 - np.arange(n_lag)] for t in range(len(inc))])
        for i, h in enumerate(hs):
            adm = delayed[7 * i:7 * i + 7].sum(axis=0)
            adm = adm * np.exp(rng.normal(0.0, s_obs, len(adm)))
            out[h] = np.maximum(np.round(np.quantile(adm, STANDARD_QUANTILES)), 0.0)
    return out


def emit_rows(
    X: np.ndarray,
    p: FluParams,
    location: str,
    reference_date,
    last_obs_week_value: float | None = None,
    s_obs: float = 0.10,
    sd_beta_fwd: float = 0.05,
    rng: np.random.Generator | None = None,
    beta_revert_hl_wk: float = 0.0,
    lb_anchor: float | None = None,
    delay_mean_days: float = 0.0,
    depletion_gamma: float = 1.0,
    hist: np.ndarray | None = None,
) -> list[dict]:
    """Emit hubverse-format rows for one location at one origin date."""
    rng = rng or np.random.default_rng(0)
    rows: list[dict] = []
    qs = forecast_quantiles(X, p, horizons=(0, 1, 2, 3), s_obs=s_obs,
                            sd_beta_fwd=sd_beta_fwd, rng=rng, beta_revert_hl_wk=beta_revert_hl_wk,
                            lb_anchor=lb_anchor, delay_mean_days=delay_mean_days,
                            depletion_gamma=depletion_gamma, hist=hist)

    ref = np.datetime64(reference_date).astype("datetime64[D]")
    if last_obs_week_value is not None:
        y = max(float(last_obs_week_value), 0.0)
        jit = np.exp(rng.normal(0.0, 0.05, 50_000))
        q_neg1 = np.quantile(y * jit, STANDARD_QUANTILES)
        ted = str((ref - np.timedelta64(7, "D")).astype("datetime64[D]"))
        rows.extend({
            "reference_date": str(ref), "target": PRIMARY_TARGET, "horizon": -1,
            "location": location, "target_end_date": ted,
            "output_type": "quantile", "output_type_id": f"{lev:g}",
            # hub requires integer values for wk inc flu hosp
            "value": max(round(v), 0),
        } for lev, v in zip(STANDARD_QUANTILES, q_neg1, strict=False))

    for h, q in qs.items():
        ted = str((ref + np.timedelta64(7 * h, "D")).astype("datetime64[D]"))
        rows.extend({
            "reference_date": str(ref), "target": PRIMARY_TARGET, "horizon": h,
            "location": location, "target_end_date": ted,
            "output_type": "quantile", "output_type_id": f"{lev:g}",
            "value": max(round(v), 0),
        } for lev, v in zip(STANDARD_QUANTILES, q, strict=False))
    return rows
