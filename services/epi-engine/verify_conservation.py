import numpy as np
from src.filters.ekf import SEIR_EKF
from seir_core import SEIRParams

def verify_ekf_conservation():
    params = SEIRParams(
        beta=0.5, sigma=0.33, gamma=0.2, rho=0.8, fA=0.4, fM=0.5, fS=0.1,
        alpha=0.05, h_rate=0.15, delta=0.1, mu=0.005, mu_icu=0.2,
        gamma_A=0.25, gamma_M=0.2, gamma_S=0.15, gamma_H=0.1, gamma_ICU=0.07,
        papp=0.12, N_pop=1000000
    )
    Q = np.eye(12) * 0.01
    R = np.eye(4) * 1.0
    H = np.zeros((4, 12))
    H[0, 3:5] = 0.12
    ekf = SEIR_EKF(params, Q, R, H)
    
    x = np.zeros(12)
    x[0] = 1000000
    P = np.eye(12)
    
    for i in range(10):
        y_obs = np.array([10, 10, 10, 10]) if i % 2 == 0 else np.array([11, 11, 11, 11])
        x, P, _, _ = ekf.step(x, P, y_obs)
        total_pop = np.sum(x[:9])
        diff = abs(total_pop - 1000000)
        print(f"Step {i}: Total Pop = {total_pop:.2f}, Diff = {diff:.2f}")
        assert diff < 100, f"Conservation failed at step {i}: {diff}"

if __name__ == "__main__":
    verify_ekf_conservation()
    print("Conservation check passed.")
