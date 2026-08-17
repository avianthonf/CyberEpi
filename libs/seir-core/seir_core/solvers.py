import numpy as np
from scipy.integrate import solve_ivp
from typing import Tuple, Optional
from dataclasses import dataclass
from .seir import SEIRParams, seir_extended

@dataclass
class SolverResult:
    t: np.ndarray
    y: np.ndarray
    message: str

from prometheus_client import Histogram
import time

ODE_SOLVE_DURATION = Histogram(
    "ode_solve_duration_seconds",
    "Time spent solving ODE system",
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 2.5, 5.0, 10.0]
)

def run_seir(
    y0: np.ndarray,
    t_span: Tuple[float, float],
    t_eval: Optional[np.ndarray],
    params: SEIRParams
) -> SolverResult:
    """
    Solves the extended SEIR ODE system using LSODA.
    Ensures population conservation and non-negativity.
    """
    start_time = time.perf_counter()
    try:
        sol = solve_ivp(
            seir_extended,
            t_span,
            y0,
            args=(params,),
            method='LSODA',
            rtol=1e-8,
            atol=1e-10,
            t_eval=t_eval
        )
    except Exception as e:
        raise RuntimeError(f"Solver failed with exception: {str(e)}") from e
    finally:
        ODE_SOLVE_DURATION.observe(time.perf_counter() - start_time)

    if not sol.success:
        raise RuntimeError(f"Solver failed: {sol.message}")

    # Clip all compartments to >= 0 post-integration
    y_clipped = np.maximum(sol.y, 0)

    # Enforce population conservation: sum(y) = N per time step.
    # Guard against complete die-off (sum == 0) which would otherwise
    # produce silent NaN/Inf.
    N = params.N_pop
    sums = y_clipped.sum(axis=0)
    safe_sums = np.where(sums > 0, sums, 1.0)
    y_final = (y_clipped / safe_sums) * N

    return SolverResult(
        t=sol.t,
        y=y_final,
        message=sol.message
    )
