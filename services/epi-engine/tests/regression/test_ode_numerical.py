import json
import os

import numpy as np
import pytest
from seir_core import SEIRParams, run_seir


@pytest.fixture
def golden_data():
    golden_path = os.path.join(os.path.dirname(__file__), "golden_output.json")
    with open(golden_path) as f:
        return json.load(f)

def test_ode_numerical_regression(golden_data):
    # Same params as when generating golden
    params = SEIRParams(
        beta=0.5, sigma=0.33, gamma=0.2, rho=1.0,
        fA=0.4, fM=0.5, fS=0.1, alpha=0.05,
        h_rate=0.15, delta=0.1, mu=0.005, mu_icu=0.2,
        gamma_A=0.2, gamma_M=0.2, gamma_S=0.2,
        gamma_H=0.2, gamma_ICU=0.2, papp=0.12, N_pop=1000000
    )
    y0 = np.array([999990, 10, 0, 0, 0, 0, 0, 0, 0])
    t_span = (0, 30)
    t_eval = np.linspace(0, 30, 31)

    res = run_seir(y0, t_span, t_eval, params)

    # Assert max absolute error < 1e-6 vs. golden
    golden_y = np.array(golden_data["y"])
    max_err = np.max(np.abs(res.y - golden_y))
    assert max_err < 1e-6
