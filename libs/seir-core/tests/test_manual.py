import numpy as np
from scipy.integrate import solve_ivp

from seir_core.seir import SEIRParams, seir_base
from seir_core.utils import compute_Rt


def test_seir_manual_requirements():
    N = 100000
    beta = 0.3
    gamma = 0.1
    sigma = 0.2
    y0 = np.array([N-10, 0, 10, 0], dtype=float) # S, E, I, R
    t_span = (0, 100)
    t_eval = np.linspace(0, 100, 101)

    # Solve
    sol = solve_ivp(
        seir_base,
        t_span,
        y0,
        args=(beta, sigma, gamma, N),
        t_eval=t_eval,
        method='RK45'
    )

    assert sol.success

    # Verify S decreases monotonically
    S = sol.y[0]
    assert np.all(np.diff(S) <= 0)

    # Verify conservation law (S+E+I+R = N)
    total = np.sum(sol.y, axis=0)
    assert np.allclose(total, N)

    # Verify peak infection timing (check if I > 0 at some point)
    I = sol.y[2]
    assert np.max(I) > 10

def test_numerical_stability():
    N = 100000
    beta = 0.3
    gamma = 0.1
    sigma = 0.2
    y0 = np.array([N-10, 0, 10, 0], dtype=float)

    sol = solve_ivp(
        seir_base,
        (0, 100),
        y0,
        args=(beta, sigma, gamma, N),
        method='RK45'
    )

    assert not np.any(np.isnan(sol.y))
    assert not np.any(np.isinf(sol.y))

def test_Rt_estimation():
    params = SEIRParams(
        beta=2.5, sigma=1.0, gamma=1.0, rho=1.0, # Just making a simple case where R0=beta=2.5
        fA=1.0, fM=0.0, fS=0.0, alpha=0.0,
        h_rate=0.0, delta=0.0, mu=0.0, mu_icu=0.0,
        gamma_A=1.0, gamma_M=1.0, gamma_S=1.0,
        gamma_H=1.0, gamma_ICU=1.0, papp=1.0, N_pop=100000
    )

    # S = N, R0 = 2.5
    assert np.isclose(compute_Rt(params, 100000, 100000), 2.5)

    # S = N * (0.8/2.5) = N * 0.32
    assert np.isclose(compute_Rt(params, 32000, 100000), 0.8)

def test_edge_cases():
    # Zero population: input validation fails fast with a clear error
    import pytest

    y0 = np.array([0, 0, 0, 0], dtype=float)
    with pytest.raises(ValueError, match="Population N"):
        solve_ivp(seir_base, (0, 1), y0, args=(0.3, 0.2, 0.1, 0))

    # Negative parameters: rejected by input validation
    N = 100000
    y0 = np.array([N - 10, 0, 10, 0], dtype=float)
    with pytest.raises(ValueError, match="non-negative"):
        solve_ivp(seir_base, (0, 1), y0, args=(-0.3, 0.2, 0.1, N))
