"""Vectorized SEIR + parameter states for ensemble filtering.

State per unit (8 dims):
    S, E, I, R, log_beta, log_hir, W, log_c
where W = weekly incident hospital admissions accumulator:
    dW/dt = hir * (sigma * E)   # HIR = hospitalization:infection ratio
and c = exp(log_c) couples the ILI observation stream:
    ili_frac ~ c * I / N   (Weekly NSSP ED ILI percentage)

Weekly admissions observed on ground = increment of W over an epi week.
W is reset to 0 at the start of each new week AFTER the weekly update.

The ensemble xt: (M, 8). Integration is a single solve_ivp over the stacked
(M*8,) system with a vectorized RHS — O(M * rhs_cost) numpy ops per call.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.integrate import solve_ivp

# indices
S, E, I, R, LB, LHIR, W, LC = range(8)
DIM = 8


@dataclass(frozen=True)
class FluParams:
    sigma: float = 1.0 / 1.2    # latent ~1.2 days
    gamma: float = 1.0 / 3.8    # infectious ~3.8 days
    N_pop: float = 1e6


def rhs_flat(t: float, y: np.ndarray, n_members: int, n_pop: float,
             p: FluParams) -> np.ndarray:
    """Flat stacked RHS for solve_ivp: y is (M*7,) float."""
    x = y.reshape(n_members, DIM)
    beta = np.exp(x[:, LB])
    foi = beta * x[:, I] / n_pop                    # force of infection
    out = np.empty_like(x)
    out[:, S] = -foi * x[:, S]
    out[:, E] = foi * x[:, S] - p.sigma * x[:, E]
    out[:, I] = p.sigma * x[:, E] - p.gamma * x[:, I]
    out[:, R] = p.gamma * x[:, I]
    out[:, LB] = 0.0
    out[:, LHIR] = 0.0
    out[:, W] = np.exp(x[:, LHIR]) * p.sigma * x[:, E]
    out[:, LC] = 0.0
    return out.ravel()


def integrate(x: np.ndarray, n_days: int, p: FluParams,
              daily: bool = False, rtol: float = 1e-6, atol: float = 1e-8) -> np.ndarray:
    """Integrate ensemble x (M,7) forward n_days.

    daily=False → final state (M,7);  daily=True → daily trajectory (n_days, M, 7).
    """
    m = x.shape[0]
    y0 = x.ravel()
    if daily:
        t_eval = np.arange(1, n_days + 1, dtype=float)
    else:
        t_eval = [float(n_days)]
    sol = solve_ivp(
        rhs_flat, (0.0, float(n_days)), y0, args=(m, p.N_pop, p),
        method="RK45", t_eval=t_eval, rtol=rtol, atol=atol,
    )
    if not sol.success:
        raise RuntimeError(f"SEIR integration failed: {sol.message}")
    y = sol.y.T if daily else sol.y[:, -1].reshape(1, m, DIM)
    out = y.reshape(len(t_eval), m, DIM)
    # physical floors
    out[..., S] = np.clip(out[..., S], 0.0, None)
    out[..., E] = np.clip(out[..., E], 0.0, None)
    out[..., I] = np.clip(out[..., I], 0.0, None)
    out[..., R] = np.clip(out[..., R], 0.0, None)
    return out


def weekly_admissions(x: np.ndarray, p: FluParams) -> np.ndarray:
    """Instantaneous weekly admission flow as ensemble forecast of W increment:
    resets W then integrates 7 days; returns the W increment vector (M,)."""
    xt = x.copy()
    xt[:, W] = 0.0
    return integrate(xt, 7, p)[0, :, W]


def rt(x: np.ndarray, p: FluParams) -> np.ndarray:
    """Per-member effective Rt = beta *(S/N) / gamma."""
    return np.exp(x[:, LB]) * (x[:, S] / p.N_pop) / p.gamma
