import numpy as np
import pytest
from seir_core import SEIRParams

from src.filters.ekf import SEIR_EKF


@pytest.fixture
def ekf_setup():
    params = SEIRParams(
        beta=0.5, sigma=0.33, gamma=0.2, rho=0.8, fA=0.4, fM=0.5, fS=0.1,
        alpha=0.05, h_rate=0.15, delta=0.1, mu=0.005, mu_icu=0.2,
        gamma_A=0.25, gamma_M=0.2, gamma_S=0.15, gamma_H=0.1, gamma_ICU=0.07,
        papp=0.12, N_pop=1000000
    )
    Q = np.eye(12) * 1.0
    R = np.eye(4) * 1.0
    H = np.zeros((4, 12))
    H[0, 3:5] = 0.12 # papp
    H[1, 3:5] = 0.30 # ptest
    H[2, 5] = 1.0    # hospital
    H[3, 3] = 0.001  # pharmacy
    return SEIR_EKF(params, Q, R, H)

def test_ekf_predict_increases_uncertainty(ekf_setup):
    x = np.zeros(12)
    x[0] = 1000000
    P = np.eye(12)
    x_pred, P_pred = ekf_setup.predict(x, P)
    # Trace of covariance should increase after prediction due to Q
    assert np.trace(P_pred) > np.trace(P)

def test_ekf_update_decreases_uncertainty(ekf_setup):
    x_pred = np.zeros(12)
    x_pred[0] = 1000000
    P_pred = np.eye(12) * 10.0
    y_obs = np.array([10, 10, 10, 10])
    x_upd, P_upd, _, _ = ekf_setup.update(x_pred, P_pred, y_obs, ekf_setup.H_obs, ekf_setup.R_obs)
    # Measurement update should decrease uncertainty
    assert np.trace(P_upd) < np.trace(P_pred)

def test_ekf_state_non_negative_after_update(ekf_setup):
    x_pred = np.zeros(12)
    x_pred[0] = 1000000
    P_pred = np.eye(12)
    y_obs = np.array([-100, -100, -100, -100]) # Unphysical observation
    x_upd, _, _, _ = ekf_setup.update(x_pred, P_pred, y_obs, ekf_setup.H_obs, ekf_setup.R_obs)
    assert np.all(x_upd >= 0)

def test_innovation_chi2_test(ekf_setup):
    innovation = np.array([1.0, 1.0, 1.0, 1.0])
    S = np.eye(4)
    # chi2 = 4.0, benchmark is 13.28
    assert ekf_setup.innovation_test(innovation, S)

    innovation_extreme = np.array([10.0, 10.0, 10.0, 10.0])
    # chi2 = 400.0
    assert not ekf_setup.innovation_test(innovation_extreme, S)
def test_ekf_convergence(ekf_setup):
    # Initial state error
    x_true = np.zeros(12)
    x_true[0] = 900000
    x_true[3] = 10000 # IA

    x_est = np.zeros(12)
    x_est[0] = 1000000 # Wrong initial guess
    P_est = np.eye(12) * 1000.0

    # Generate synthetic observations from x_true
    y_obs = ekf_setup.H_obs @ x_true

    # Run multiple update steps
    for _ in range(10):
        # Predict
        x_est, P_est = ekf_setup.predict(x_est, P_est)
        # Update
        x_est, P_est, _, _ = ekf_setup.update(x_est, P_est, y_obs, ekf_setup.H_obs, ekf_setup.R_obs)

    # Verify that the estimate for Susceptible (index 0) moved toward true value
    assert abs(x_est[0] - x_true[0]) < abs(1000000 - x_true[0])
    # Total error should decrease
    assert np.linalg.norm(x_est - x_true) < np.linalg.norm(np.array([1000000, 0,0,0,0,0,0,0,0,0,0,0]) - x_true)
