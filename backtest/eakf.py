"""Ensemble Square-Root Filter (Whitaker & Hamill 2002) for SEIR+W(+c).

Observation streams:
  1. Weekly incident hospital admissions = W accumulated over the week.
  2. Weekly NSSP ED ILI fraction ~ c * I / N with c = exp(LC) jointly
     estimated in log space.

Square-root deterministic updates (EnSRF), sequential per scalar obs.
Observational nonlinearity enters via ensemble cross-covariances — no
linearization, so both streams support the "corrected filter" goal.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from seir_fast import DIM, LB, LC, LHIR, E, FluParams, I, R, S, W, integrate


@dataclass
class EakfConfig:
    n_members: int = 300
    sd_beta: float = 0.03         # daily sd of log-beta random walk
    sd_hir: float = 0.005         # daily sd of log-HIR random walk
    sd_lc: float = 0.01           # daily sd of log-c random walk
    r_rel: float = 0.30           # admissions obs noise, relative
    r_floor: float = 4.0          # admissions obs noise floor (counts)
    r_ili_rel: float = 0.10       # ILI obs noise, relative
    r_ili_floor: float = 5e-4     # ILI obs noise floor (fraction)
    inflation: float = 1.01       # multiplicative anomaly inflation pre-update
    use_ili: bool = True
    s_obs: float = 0.10           # quantile jitter on emitted forecasts
    sd_beta_fwd: float = 0.03     # per-day log-beta drift during forecasts
    lag0_sd_mult: float = 1.0     # admissions obs SD multiplier for the newest (lag-0) week; 1.0 = off
    ed_intercept: float = 0.0     # fixed ED baseline b in the ED observation c*I/N + b; 0.0 = off
    beta_revert_hl_wk: float = 0.0  # forward log-beta mean-reversion half-life (weeks); 0.0 = off
    beta_anchor: str = "trailing6"  # reversion target: "trailing6" (mean posterior log-beta, last 6 weeks) or "season"
    delay_mean_days: float = 0.0  # forward infection-to-admission Erlang-2 delay mean (days); 0.0 = off
    depletion_gamma: float = 1.0  # forward extra S depletion: log-beta += (gamma-1)*dlog(S); 1.0 = off
    seed: int = 0


class EAKF:
    def __init__(self, params: FluParams, cfg: EakfConfig):
        self.p = params
        self.cfg = cfg
        self.rng = np.random.default_rng(cfg.seed)
        self.X = self._init_ensemble()

    # ---- initialization --------------------------------------------------
    def _init_ensemble(self) -> np.ndarray:
        c = self.cfg
        m = c.n_members
        x = np.zeros((m, DIM))
        x[:, S] = self.p.N_pop * self.rng.uniform(0.96, 0.995, m)
        x[:, E] = self.p.N_pop * self.rng.uniform(0, 2e-6, m)
        x[:, I] = self.p.N_pop * self.rng.uniform(0, 2e-6, m)
        x[:, LB] = self.rng.normal(np.log(0.5), 0.25, m)
        x[:, LHIR] = self.rng.normal(np.log(0.008), 0.5, m)
        x[:, LC] = self.rng.normal(np.log(1.0), 0.3, m)
        return self._clip(x)

    def _clip(self, x: np.ndarray) -> np.ndarray:
        n = self.p.N_pop
        x[:, S] = np.clip(x[:, S], 0.0, n)
        for j in (E, I, R, W):
            x[:, j] = np.clip(x[:, j], 0.0, None)
        return x

    # ---- forecast --------------------------------------------------------
    def forecast_week(self) -> None:
        x = self.X
        for _ in range(7):
            x = integrate(x, 1, self.p)[0]
            x[:, LB] += self.rng.normal(0.0, self.cfg.sd_beta, len(x))
            x[:, LHIR] += self.rng.normal(0.0, self.cfg.sd_hir, len(x))
            x[:, LC] += self.rng.normal(0.0, self.cfg.sd_lc, len(x))
        self.X = self._clip(x)

    # ---- generic EnSRF scalar update -------------------------------------
    def _ensrf_update(self, x: np.ndarray, ens: np.ndarray, y: float,
                      r_var: float) -> tuple[np.ndarray, dict]:
        m = len(x)
        x_mean = x.mean(axis=0)
        # pre-update multiplicative inflation of anomalies
        x = x_mean + self.cfg.inflation * (x - x_mean)
        x_mean = x.mean(axis=0)

        ybar = float(ens.mean())
        pyy = float(ens.var(ddof=1))
        if pyy <= 1e-14:
            return x, {"ybar": ybar, "pyy": pyy, "chi2": np.nan, "skipped": True}
        cov_xy = ((x - x_mean).T @ (ens - ybar)) / (m - 1)
        k_gain = cov_xy / (pyy + r_var)
        alpha = 1.0 / (1.0 + np.sqrt(r_var / (pyy + r_var)))
        innov = y - ybar
        new_mean = x_mean + k_gain * innov
        x = new_mean + (x - x_mean) - np.outer(ens - ybar, k_gain) * alpha
        chi2 = float(innov**2 / (pyy + r_var))
        return x, {"ybar": ybar, "pyy": pyy, "chi2": chi2, "skipped": False}

    # ---- observation updates ----------------------------------------------
    def update_admissions(self, y: float | None, sd_mult: float = 1.0) -> dict | None:
        if y is None or not np.isfinite(y):
            return None
        r_var = max((self.cfg.r_rel * y) ** 2, self.cfg.r_floor**2)
        if sd_mult != 1.0:
            r_var *= sd_mult**2
        x, info = self._ensrf_update(self.X, self.X[:, W].copy(), float(y), r_var)
        self.X = self._clip(x)
        return info

    def update_ili(self, y_ili: float | None) -> dict | None:
        if y_ili is None or not np.isfinite(y_ili):
            return None
        ens = np.exp(self.X[:, LC]) * self.X[:, I] / self.p.N_pop
        if self.cfg.ed_intercept != 0.0:
            ens = ens + self.cfg.ed_intercept
        r_var = max((self.cfg.r_ili_rel * y_ili) ** 2, self.cfg.r_ili_floor**2)
        x, info = self._ensrf_update(self.X, ens, float(y_ili), r_var)
        self.X = self._clip(x)
        return info

    def reset_week(self) -> None:
        self.X[:, W] = 0.0

    def step_week(self, y_adm: float | None, y_ili: float | None = None, adm_sd_mult: float = 1.0) -> dict:
        """Full week: forecast 7 days, admissions update, ILI update, W reset."""
        self.forecast_week()
        adm = self.update_admissions(y_adm, adm_sd_mult)
        ili = self.update_ili(y_ili) if self.cfg.use_ili else None
        self.reset_week()
        return {"adm": adm, "ili": ili}

    # ---- diagnostics -------------------------------------------------------
    def mean_rt(self) -> float:
        beta = np.exp(self.X[:, LB])
        return float(np.mean(beta * (self.X[:, S] / self.p.N_pop) / self.p.gamma))

    def mean_hir(self) -> float:
        return float(np.mean(np.exp(self.X[:, LHIR])))

    def mean_c(self) -> float:
        return float(np.mean(np.exp(self.X[:, LC])))
