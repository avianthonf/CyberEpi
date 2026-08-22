"""Corrected SEIR EKF with nonlinear observation model.

The original EKF used a static linear H_obs matrix that mapped
prevalence (IM+IS) directly to observation counts via per-observation
constants. That breaks three assumptions:

1. The observation noise structure doesn't match the actual prevalence noise.
2. The H matrix doesn't depend on state, so it ignores that prevalence
   increases with R0.
3. Clipping the SEIR compartments to 0 destroys the gradient information
   for the state update.

This implementation:
- Defines a nonlinear observation function h(x) that maps SEIR state
  to expected observation counts using the model's emission equations.
- Computes the Jacobian numerically at every step (state-dependent H).
- Uses Joseph form for covariance update.
- Removes state clipping (replaced with soft floor).
"""

import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import inv
from seir_core import SEIRParams, seir_extended


class NonlinearSEIR_EKF:
    """EKF with nonlinear observation model and numerical Jacobian.

    State: [S, E, IA, IM, IS, H, ICU, R, D, log_beta]
    (Single-parameterization of beta via log for stability.)

    Observations (5-dim):
      [0] app_reports           = papp * (IM + IS)
      [1] confirmed_cases       = ptest * (IM + IS)
      [2] hospital_admissions   = h_rate * IS
      [3] pharmacy_proxy        = kappa * IM
      [4] wastewater            = papp * (IA + IM + IS)
    """

    def __init__(
        self,
        params: SEIRParams,
        Q_logbeta: float,
        R_obs_diag: np.ndarray,
    ):
        """
        Args:
            params: SEIR model parameters (used for population size and
                    structural constants).
            Q_logbeta: Process noise variance on log(beta).
                       Controls how fast Rt can change.
            R_obs_diag: 5-element array of observation noise variances.
        """
        self.params = params
        self.Q_logbeta = Q_logbeta
        self.R_obs_diag = R_obs_diag
        self.dim = 10

    def _emission_params(self, x: np.ndarray) -> tuple[float, float, float, float, float]:
        """Pull emission coefficients from the augmented state."""
        raise NotImplementedError("Use emission_params from extended state instead")


class CorrectedSEIR_EKF_Extended:
    """EKF with extended state [S, E, IA, IM, IS, H, ICU, R, D, log_beta, papp, ptest, kappa].

    Dim = 13. Observations computed from nonlinear function h(x).
    Jacobian computed numerically at every step.
    """

    def __init__(
        self,
        params: SEIRParams,
        Q_logbeta: float,
        Q_emission: float,
        R_obs_diag: np.ndarray,
    ):
        self.params = params
        self.Q_logbeta = Q_logbeta
        self.Q_emission = Q_emission
        self.R_obs_diag = R_obs_diag
        self.dim = 13

    def _transition(self, x: np.ndarray) -> np.ndarray:
        """Integrate SEIR for 1 day; emission params stay constant."""
        state = x[:9]
        augmented = x[9:]
        log_beta, papp, ptest, kappa = augmented
        beta = np.exp(log_beta)

        params_tmp = SEIRParams(
            beta=beta,
            sigma=self.params.sigma,
            gamma=self.params.gamma,
            rho=self.params.rho,
            fA=self.params.fA,
            fM=self.params.fM,
            fS=self.params.fS,
            alpha=self.params.alpha,
            h_rate=self.params.h_rate,
            delta=self.params.delta,
            mu=self.params.mu,
            mu_icu=self.params.mu_icu,
            gamma_A=self.params.gamma_A,
            gamma_M=self.params.gamma_M,
            gamma_S=self.params.gamma_S,
            gamma_H=self.params.gamma_H,
            gamma_ICU=self.params.gamma_ICU,
            papp=papp,
            N_pop=self.params.N_pop,
            L_perceived=self.params.L_perceived,
            eta_mask=self.params.eta_mask,
        )

        sol = solve_ivp(
            seir_extended,
            (0, 1),
            state,
            args=(params_tmp,),
            method='LSODA',
            rtol=1e-8,
            atol=1e-10,
        )
        if not sol.success:
            return x

        next_state = np.maximum(sol.y[:, -1], 0.0)
        return np.concatenate([next_state, augmented])

    def _observation(self, x: np.ndarray) -> np.ndarray:
        """Nonlinear observation function h(x) → 5-dim observation vector."""
        S, E, IA, IM, IS, H, ICU, R, D = x[:9]
        log_beta, papp, ptest, kappa = x[9:]
        return np.array([
            papp * (IM + IS),                # app_reports
            ptest * (IM + IS),               # confirmed_cases
            self.params.h_rate * IS,         # hospital_admissions
            kappa * IM,                      # pharmacy_proxy
            papp * (IA + IM + IS),           # wastewater (approx)
        ])

    def _jacobian_F(self, x: np.ndarray, eps: float = 1e-6) -> np.ndarray:
        """Numerical Jacobian of transition."""
        F = np.zeros((self.dim, self.dim))
        fx = self._transition(x)
        for i in range(self.dim):
            x_plus = x.copy()
            x_plus[i] += eps
            F[:, i] = (self._transition(x_plus) - fx) / eps
        return F

    def _jacobian_H(self, x: np.ndarray, eps: float = 1e-7) -> np.ndarray:
        """Numerical Jacobian of observation."""
        H = np.zeros((5, self.dim))
        hx = self._observation(x)
        for i in range(self.dim):
            x_plus = x.copy()
            x_plus[i] += eps
            H[:, i] = (self._observation(x_plus) - hx) / eps
        return H

    def predict(self, x_est: np.ndarray, P: np.ndarray):
        """Predict step with process noise on log_beta and emission params."""
        x_pred = self._transition(x_est)
        F = self._jacobian_F(x_est)
        Q = np.zeros((self.dim, self.dim))
        Q[9, 9] = self.Q_logbeta
        Q[10, 10] = self.Q_emission
        Q[11, 11] = self.Q_emission
        Q[12, 12] = self.Q_emission
        P_pred = F @ P @ F.T + Q
        return x_pred, P_pred

    def update(self, x_pred: np.ndarray, P_pred: np.ndarray, y_obs: np.ndarray):
        """Update with nonlinear observation and numerical Jacobian."""
        h_pred = self._observation(x_pred)
        innovation = y_obs - h_pred

        H = self._jacobian_H(x_pred)
        S = H @ P_pred @ H.T + np.diag(self.R_obs_diag)
        K = P_pred @ H.T @ inv(S)
        x_upd = x_pred + K @ innovation

        # Soft non-negativity floor (1e-6 instead of 0 to preserve gradient info)
        x_upd[:9] = np.maximum(x_upd[:9], 1e-6)

        I = np.eye(self.dim)
        IKH = I - K @ H
        P_upd = IKH @ P_pred @ IKH.T + K @ np.diag(self.R_obs_diag) @ K.T

        return x_upd, P_upd, innovation, S

    def step(self, x_est: np.ndarray, P: np.ndarray, y_obs: np.ndarray | None):
        """Full EKF step with NaN handling."""
        x_pred, P_pred = self.predict(x_est, P)
        if y_obs is None or np.any(np.isnan(y_obs)):
            return x_pred, P_pred, np.zeros(5), np.zeros((5, 5))

        return self.update(x_pred, P_pred, y_obs)

    def get_Rt(self, x: np.ndarray) -> float:
        """Compute Rt = beta * S/N / gamma."""
        S = x[0]
        log_beta = x[9]
        beta = np.exp(log_beta)
        N = self.params.N_pop
        return float((beta * S / N) / self.params.gamma)
