import numpy as np
import pytest

from src.control.fb_sweep import forward_backward_sweep


@pytest.fixture
def params():
    return {
        "beta": 0.5,
        "sigma": 0.2,
        "gamma": 0.1,
        "rho": 1.0,
        "fM": 0.8,
        "fS": 0.2,
        "gamma_M": 0.1,
        "gamma_S": 0.1,
        "h_rate": 0.05,
        "gamma_H": 0.05,
        "delta": 0.02,
        "gamma_ICU": 0.03,
        "mu": 0.005,
        "mu_icu": 0.15,
        "N": 1000000,
        "eta": 0.3,
        "C4": 10.0
    }

@pytest.fixture
def x0(params):
    N = params["N"]
    return np.array([N * 0.9, N * 0.05, 1000, 500, 100, 50, 0, 0])

@pytest.fixture
def W():
    return np.diag([1.0, 0.5, 0.8])

def test_convergence_simple_case(x0, params, W):
    # Low R0 scenario (beta=0.1, gamma=0.1 -> R0=1) -> u should stay low
    params["beta"] = 0.05 # Very low
    # Override x0 to have very few infecteds to prevent max-control
    N = params["N"]
    x0_low = np.array([N * 0.99, N * 0.001, 10, 5, 0, 0, 0, 0])
    # Very high C3 to heavily penalize control
    result = forward_backward_sweep(x0_low, 2.0, params, 1.0, 5.0, 1000.0, W, n_iter=100)
    # u should be near 0 because cost of control > benefit
    assert np.all(result.u < 0.1)

def test_convergence_high_R0(x0, params, W):
    # High R0 scenario -> u should be high
    params["beta"] = 2.0
    result = forward_backward_sweep(x0, 2.0, params, 10.0, 50.0, 0.1, W, n_iter=100)
    assert np.any(result.u > 0.5)

def test_control_bounds(x0, params, W):
    result = forward_backward_sweep(x0, 5.0, params, 1.0, 1.0, 0.01, W, n_iter=10)
    assert np.all(result.u >= 0.0)
    assert np.all(result.u <= 1.0)

def test_cost_calculation(x0, params, W):
    result = forward_backward_sweep(x0, 5.0, params, 1.0, 5.0, 2.0, W, n_iter=5)
    assert result.final_cost > 0
    # D column is index 7
    assert result.x[7, -1] >= 0
