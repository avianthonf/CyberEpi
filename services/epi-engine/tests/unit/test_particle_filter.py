import numpy as np
import pytest
from seir_core import SEIRParams

from src.filters.particle_filter import ParticleFilter


@pytest.fixture
def pf_setup():
    params = SEIRParams(
        beta=0.5, sigma=0.33, gamma=0.2, rho=0.8, fA=0.4, fM=0.5, fS=0.1,
        alpha=0.05, h_rate=0.15, delta=0.1, mu=0.005, mu_icu=0.2,
        gamma_A=0.25, gamma_M=0.2, gamma_S=0.15, gamma_H=0.1, gamma_ICU=0.07,
        papp=0.12, N_pop=1000000
    )
    Q = np.eye(12) * 1.0
    R = np.eye(4) * 1.0
    H = np.zeros((4, 12))
    H[0, 3:5] = 0.12
    return ParticleFilter(100, params, Q, R, H) # Np=100 for fast tests

def test_pf_initialise_np_particles(pf_setup):
    x0 = np.zeros(12)
    x0[0] = 1000000
    P0 = np.eye(12)
    pf_setup.initialize(x0, P0)
    assert pf_setup.particles.shape == (100, 12)

def test_pf_weights_sum_to_one(pf_setup):
    x0 = np.zeros(12)
    x0[0] = 1000000
    pf_setup.initialize(x0, np.eye(12))
    pf_setup.weight(np.array([10, np.nan, np.nan, np.nan]))
    assert np.isclose(np.sum(pf_setup.weights), 1.0)

def test_pf_state_non_negative(pf_setup):
    x0 = np.zeros(12)
    x0[0] = 1000000
    pf_setup.initialize(x0, np.eye(12))
    for _ in range(5):
        pf_setup.step(np.array([10, np.nan, np.nan, np.nan]))
    x_hat, _ = pf_setup.estimate()
    assert np.all(x_hat >= 0)
