import numpy as np
import pytest

from seir_core import SEIRParams, compute_R0, run_seir


@pytest.fixture
def stable_params():
    return SEIRParams(
        beta=0.1, sigma=0.33, gamma=0.5, rho=0.8,
        fA=0.4, fM=0.5, fS=0.1, alpha=0.05,
        h_rate=0.15, delta=0.1, mu=0.005, mu_icu=0.2,
        gamma_A=0.25, gamma_M=0.2, gamma_S=0.15,
        gamma_H=0.1, gamma_ICU=0.07, papp=0.12, N_pop=1000000
    )

def test_DFE_stable_when_R0_lt_1(stable_params):
    # DFE is stable if R0 < 1
    r0 = compute_R0(stable_params)
    assert r0 < 1.0

    # Small perturbation from DFE
    y0 = np.array([stable_params.N_pop - 1, 1, 0, 0, 0, 0, 0, 0, 0])
    res = run_seir(y0, (0, 100), np.linspace(0, 100, 11), stable_params)

    # Infections should decay towards 0
    total_infectious = res.y[1:5, :].sum(axis=0)
    assert total_infectious[-1] < total_infectious[0]
    assert np.all(np.diff(total_infectious) <= 1e-5) # Monotonically decreasing (roughly)

def test_herd_immunity_threshold(stable_params):
    # R0 = beta / gamma_eff.
    # At equilibrium S* = N / R0.
    # Herd Immunity Threshold (HIT) = 1 - 1/R0.
    # If S/N < 1/R0, the disease should decay.

    # Increase beta to make R0 > 1
    params = SEIRParams(**{**stable_params.__dict__, "beta": 0.8})
    r0 = compute_R0(params)
    assert r0 > 1.0

    s_star_fraction = 1.0 / r0

    # Case 1: S/N > 1/R0 (Below HIT) -> disease grows
    y0_above = np.array([params.N_pop * (s_star_fraction + 0.1), 100, 0, 0, 0, 0, 0, 0, 0])
    res_above = run_seir(y0_above, (0, 10), np.linspace(0, 10, 11), params)
    total_inf_above = res_above.y[1:5, :].sum(axis=0)
    assert total_inf_above[-1] > total_inf_above[0]

    # Case 2: S/N < 1/R0 (Above HIT) -> disease decays
    y0_below = np.array([params.N_pop * (s_star_fraction - 0.1), 100, 0, 0, 0, 0, 0, 0, 0])
    res_below = run_seir(y0_below, (0, 10), np.linspace(0, 10, 11), params)
    total_inf_below = res_below.y[1:5, :].sum(axis=0)
    assert total_inf_below[-1] < total_inf_below[0]
