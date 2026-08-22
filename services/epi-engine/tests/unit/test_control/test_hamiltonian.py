import numpy as np
import pytest

from src.control.controlled_seir import seir_controlled
from src.control.hamiltonian import compute_dH_du, compute_dH_dx


@pytest.fixture
def params():
    return {
        "beta": 0.5, "sigma": 0.2, "gamma": 0.1, "rho": 1.0,
        "fM": 0.8, "fS": 0.2, "gamma_M": 0.1, "gamma_S": 0.1,
        "h_rate": 0.05, "gamma_H": 0.05, "delta": 0.02,
        "gamma_ICU": 0.03, "mu": 0.005, "mu_icu": 0.15,
        "N": 1000000, "eta": 0.3
    }

def test_gradient_finite_difference(params):
    np.random.seed(42)
    x = np.array([900000, 50000, 10000, 5000, 1000, 500, 0, 0])
    u = np.array([0.5, 0.1, 0.3])
    lam = np.random.randn(8)
    C1, C2, C3 = 1.0, 5.0, 2.0
    W = np.diag([1.0, 0.5, 0.8])

    # 1. Test dH/du
    dH_du_analytical = compute_dH_du(x, lam, u, C3, W, params)

    def H_func(u_temp):
        # L = C1*(IM+IS)^2 + C2*(H+ICU) + C3*u.T@W@u
        L = C1*(x[2]+x[3])**2 + C2*(x[4]+x[5]) + C3 * (u_temp @ W @ u_temp)
        f = seir_controlled(0, x, u_temp, params)
        return L + np.dot(lam, f)

    eps = 1e-6
    dH_du_numerical = np.zeros(3)
    for i in range(3):
        u_plus = u.copy()
        u_plus[i] += eps
        u_minus = u.copy()
        u_minus[i] -= eps
        dH_du_numerical[i] = (H_func(u_plus) - H_func(u_minus)) / (2 * eps)

    np.testing.assert_allclose(dH_du_analytical, dH_du_numerical, rtol=1e-4)

def test_dH_dx_structure(params):
    x = np.array([900000, 50000, 10000, 5000, 1000, 500, 0, 0])
    u = np.array([0.5, 0.1, 0.3])
    lam = np.zeros(8) # If lam=0, dH/dx = dL/dx
    C1, C2 = 1.0, 5.0

    minus_dH_dx = compute_dH_dx(x, lam, u, C1, C2, params)
    # minus_dH_dx = -dL/dx
    # dL/dx = [0, 0, 2*C1*(IM+IS), 2*C1*(IM+IS), C2, C2, 0, 0]
    expected_dL_dx = np.zeros(8)
    expected_dL_dx[2] = 2 * C1 * (10000 + 5000)
    expected_dL_dx[3] = 2 * C1 * (10000 + 5000)
    expected_dL_dx[4] = C2
    expected_dL_dx[5] = C2

    np.testing.assert_allclose(minus_dH_dx, -expected_dL_dx)
