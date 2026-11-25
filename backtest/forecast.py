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
from seir_fast import LB, FluParams, W, integrate


def forecast_quantiles(
    X: np.ndarray,
    p: FluParams,
    horizons: tuple[int, ...] = (0, 1, 2, 3),
    s_obs: float = 0.10,
    sd_beta_fwd: float = 0.05,
    rng: np.random.Generator | None = None,
) -> dict[int, np.ndarray]:
    """Return {horizon: quantile array aligned to STANDARD_QUANTILES}.

    Integrate forward in 7-day blocks; between blocks log_beta performs a
    random walk with per-day sd `sd_beta_fwd` (dispersion during forecast).
    Weekly admission samples = W increment within each block; multiplicative
    jitter exp(N(0, s_obs)) represents reporting noise/overdispersion.
    """
    rng = rng or np.random.default_rng(0)
    x = X.copy()
    x[:, W] = 0.0
    out: dict[int, np.ndarray] = {}
    for h in sorted(hh for hh in horizons if hh >= 0):
        for _ in range(7):
            x = integrate(x, 1, p)[0]
            if sd_beta_fwd > 0:
                x[:, LB] += rng.normal(0.0, sd_beta_fwd, len(x))
        adm = np.maximum(x[:, W], 0.0)
        adm = adm * np.exp(rng.normal(0.0, s_obs, len(adm)))
        out[h] = np.maximum(np.round(np.quantile(adm, STANDARD_QUANTILES)), 0.0)
        x[:, W] = 0.0
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
) -> list[dict]:
    """Emit hubverse-format rows for one location at one origin date."""
    rng = rng or np.random.default_rng(0)
    rows: list[dict] = []
    qs = forecast_quantiles(X, p, horizons=(0, 1, 2, 3), s_obs=s_obs,
                            sd_beta_fwd=sd_beta_fwd, rng=rng)

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
