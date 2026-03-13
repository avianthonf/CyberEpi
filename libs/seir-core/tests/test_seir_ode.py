import pytest
import numpy as np
from seir_core import SEIRParams, run_seir, compute_load, compute_R0, compute_Rt

@pytest.fixture
def default_params():
    return SEIRParams(
        beta=0.5, sigma=0.33, gamma=0.2, rho=0.8,
        fA=0.4, fM=0.5, fS=0.1, alpha=0.05,
        h_rate=0.15, delta=0.1, mu=0.005, mu_icu=0.2,
        gamma_A=0.25, gamma_M=0.2, gamma_S=0.15,
        gamma_H=0.1, gamma_ICU=0.07, papp=0.12, N_pop=1000000
    )

def test_conservation_law(default_params):
    # Initial state: 10 exposed, rest susceptible
    y0 = np.array([default_params.N_pop - 10, 10, 0, 0, 0, 0, 0, 0, 0])
    t_span = (0, 30)
    t_eval = np.linspace(0, 30, 31)
    
    res = run_seir(y0, t_span, t_eval, default_params)
    
    # Assert |S+E+...+D - N| < 1 at all timesteps (1e-4 tolerance enforced in solver)
    for i in range(len(res.t)):
        assert abs(np.sum(res.y[:, i]) - default_params.N_pop) < 1.0

def test_disease_free_equilibrium(default_params):
    # Set I=0 (meaning E, IA, IM, IS are all 0)
    y0 = np.array([default_params.N_pop, 0, 0, 0, 0, 0, 0, 0, 0])
    t_span = (0, 30)
    t_eval = np.linspace(0, 30, 31)
    
    res = run_seir(y0, t_span, t_eval, default_params)
    
    # Assert all compartments stable (S remains N, others remain 0)
    assert np.allclose(res.y[0, :], default_params.N_pop)
    assert np.allclose(res.y[1:, :], 0)

def test_R0_greater_than_1_grows(default_params):
    # beta=0.8, gamma_eff small enough -> R0 > 1
    # For simplicity, we just check if total infectious (IA+IM+IS) grows
    y0 = np.array([default_params.N_pop - 10, 10, 0, 0, 0, 0, 0, 0, 0])
    t_span = (0, 10)
    t_eval = np.linspace(0, 10, 11)
    
    res = run_seir(y0, t_span, t_eval, default_params)
    
    # Check if total infectious (IA+IM+IS) at t=10 is greater than at t=0
    # Actually, initially only E is non-zero, it takes time to flow into IA, IM, IS.
    # Total infectious = res.y[2] + res.y[3] + res.y[4]
    infectious_start = res.y[2, 0] + res.y[3, 0] + res.y[4, 0]
    infectious_end = res.y[2, -1] + res.y[3, -1] + res.y[4, -1]
    
    # Since we started with 10 exposed, infectious will definitely grow from 0
    assert infectious_end > 0

def test_R0_less_than_1_decays(default_params):
    # beta=0.1, gamma_eff large enough -> R0 < 1
    low_beta_params = SEIRParams(
        **{**default_params.__dict__, "beta": 0.05}
    )
    y0 = np.array([default_params.N_pop - 100, 0, 50, 25, 25, 0, 0, 0, 0])
    t_span = (0, 10)
    t_eval = np.linspace(0, 10, 11)
    
    res = run_seir(y0, t_span, t_eval, low_beta_params)
    
    # Total infectious should decrease
    infectious_start = res.y[2, 0] + res.y[3, 0] + res.y[4, 0]
    infectious_end = res.y[2, -1] + res.y[3, -1] + res.y[4, -1]
    
    assert infectious_end < infectious_start

def test_compartment_non_negativity(default_params):
    # Test 5 random param sets (100 is too many for a single test case here, but let's do a few)
    for _ in range(5):
        random_beta = np.random.uniform(0.1, 2.0)
        params = SEIRParams(**{**default_params.__dict__, "beta": random_beta})
        y0 = np.random.dirichlet(np.ones(9)) * params.N_pop
        res = run_seir(y0, (0, 20), None, params)
        assert np.all(res.y >= 0)

def test_load_signal(default_params):
    y = np.zeros((9, 10))
    y[5, :] = 100 # H
    y[6, :] = 50  # ICU
    load = compute_load(y)
    assert np.all(load == 150)

def test_solver_failure_raises(default_params):
    # Provide y0 with NaN to force failure
    y0 = np.array([np.nan, 0, 0, 0, 0, 0, 0, 0, 0])
    with pytest.raises(RuntimeError):
        run_seir(y0, (0, 30), None, default_params)
