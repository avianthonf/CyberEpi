import json

import numpy as np
from seir_core import SEIRParams, run_seir


def generate_golden():
    params = SEIRParams(
        beta=0.5, sigma=0.33, gamma=0.2, rho=1.0, # gamma=0.2 as base
        fA=0.4, fM=0.5, fS=0.1, alpha=0.05,
        h_rate=0.15, delta=0.1, mu=0.005, mu_icu=0.2,
        gamma_A=0.2, gamma_M=0.2, gamma_S=0.2, # All gammas = 0.2
        gamma_H=0.2, gamma_ICU=0.2, papp=0.12, N_pop=1000000
    )
    y0 = np.array([999990, 10, 0, 0, 0, 0, 0, 0, 0])
    t_span = (0, 30)
    t_eval = np.linspace(0, 30, 31)

    res = run_seir(y0, t_span, t_eval, params)

    golden_data = {
        "t": res.t.tolist(),
        "y": res.y.tolist()
    }

    with open("tests/regression/golden_output.json", "w") as f:
        json.dump(golden_data, f)
    print("Golden output generated.")

if __name__ == "__main__":
    import os
    os.makedirs("tests/regression", exist_ok=True)
    generate_golden()
