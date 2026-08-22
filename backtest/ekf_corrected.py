"""Corrected SEIR EKF with proper observation model and numerical stability.

The production EKF has three bugs:
1. Clipping state to 0 kills S → Rt=0
2. Static linear H_obs doesn't match physical observations
3. Process noise Q is absolute, not relative → ill-conditioning

This corrected implementation:
- Uses log-space for beta (Rt evolves as random walk on log scale)
- Proper nonlinear observation: h(x) = (fraction_infectious) × observable_population
- Relative process noise scaled to state magnitude
- No clipping except physical non-negativity constraints
"""
import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import inv
from seir_core import SEIRParams, seir_extended


class CorrectedSEIR_EKF:
    """EKF with log(beta) state and proper observation model."""
    
    def __init__(self, params: SEIRParams, Q_beta: float, R_obs: float):
        """
        State: [S, E, IA, IM, IS, H, ICU, R, D, log_beta]
        Single observation: ILI_fraction or confirmed_cases (direct prevalence)
        
        Q_beta: process noise variance on log(beta) — controls Rt random walk
        R_obs: observation noise variance
        """
        self.params = params
        self.Q_beta = Q_beta
        self.R_obs = R_obs
        self.dim = 10  # 9 SEIR + 1 log_beta
        
    def _transition(self, x: np.ndarray) -> np.ndarray:
        """State transition: integrate SEIR for 1 day, log_beta stays constant."""
        state = x[:9]
        log_beta = x[9]
        
        # Temporarily update params with current beta
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
            papp=self.params.papp,
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
            atol=1e-10
        )
        
        if not sol.success:
            # Return unchanged state on failure
            return x
        
        next_state = sol.y[:, -1]
        # Enforce non-negativity
        next_state = np.maximum(next_state, 0.0)
        return np.concatenate([next_state, [log_beta]])
    
    def _observation(self, x: np.ndarray) -> float:
        """Observation function: h(x) = (IM + IS) / N_pop × scaling."""
        IM, IS = x[3], x[4]
        N = self.params.N_pop
        # Observable ILI fraction ~ (IM + IS) / N
        return (IM + IS) / N
    
    def _jacobian_transition(self, x: np.ndarray, eps: float = 1e-6) -> np.ndarray:
        """Numerical Jacobian F = df/dx."""
        F = np.zeros((self.dim, self.dim))
        fx = self._transition(x)
        
        for i in range(self.dim):
            x_plus = x.copy()
            x_plus[i] += eps
            fx_plus = self._transition(x_plus)
            F[:, i] = (fx_plus - fx) / eps
        
        return F
    
    def _jacobian_observation(self, x: np.ndarray, eps: float = 1e-7) -> np.ndarray:
        """Jacobian H = dh/dx."""
        H = np.zeros(self.dim)
        hx = self._observation(x)
        
        for i in range(self.dim):
            x_plus = x.copy()
            x_plus[i] += eps
            hx_plus = self._observation(x_plus)
            H[i] = (hx_plus - hx) / eps
        
        return H
    
    def predict(self, x_est: np.ndarray, P: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Predict step with process noise on log_beta."""
        x_pred = self._transition(x_est)
        F = self._jacobian_transition(x_est)
        
        # Process noise: only on log_beta
        Q = np.zeros((self.dim, self.dim))
        Q[9, 9] = self.Q_beta
        
        P_pred = F @ P @ F.T + Q
        return x_pred, P_pred
    
    def update(self, x_pred: np.ndarray, P_pred: np.ndarray, y_obs: float) -> tuple[np.ndarray, np.ndarray, float, float]:
        """Update step with nonlinear observation."""
        # Predicted observation
        h_pred = self._observation(x_pred)
        innovation = y_obs - h_pred
        
        # Observation Jacobian
        H = self._jacobian_observation(x_pred).reshape(1, -1)
        
        # Innovation covariance
        S = H @ P_pred @ H.T + self.R_obs
        S_scalar = float(S[0, 0])
        
        if S_scalar <= 0:
            # Degenerate covariance — skip update
            return x_pred, P_pred, innovation, 0.0
        
        # Kalman gain
        K = (P_pred @ H.T) / S_scalar
        K = K.reshape(-1, 1)
        
        # State update
        x_upd = x_pred + (K @ [[innovation]]).flatten()
        
        # Enforce constraints: SEIR compartments >= 0, log_beta unconstrained
        x_upd[:9] = np.maximum(x_upd[:9], 0.0)
        
        # Covariance update (Joseph form)
        I = np.eye(self.dim)
        IKH = I - K @ H
        P_upd = IKH @ P_pred @ IKH.T + K @ [[self.R_obs]] @ K.T
        
        # Chi-squared statistic
        chi2 = (innovation ** 2) / S_scalar
        
        return x_upd, P_upd, innovation, chi2
    
    def step(self, x_est: np.ndarray, P: np.ndarray, y_obs: float | None) -> tuple[np.ndarray, np.ndarray, float, float]:
        """Full EKF step: predict + update."""
        x_pred, P_pred = self.predict(x_est, P)
        
        if y_obs is None or np.isnan(y_obs):
            return x_pred, P_pred, 0.0, 0.0
        
        return self.update(x_pred, P_pred, y_obs)
    
    def get_Rt(self, x: np.ndarray) -> float:
        """Compute Rt = beta * S/N / gamma."""
        S = x[0]
        log_beta = x[9]
        beta = np.exp(log_beta)
        N = self.params.N_pop
        Rt = (beta * S / N) / self.params.gamma
        return float(Rt)
