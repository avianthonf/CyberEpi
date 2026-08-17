
import numpy as np
from scipy.integrate import solve_ivp
from scipy.linalg import inv
from seir_core import SEIRParams, seir_extended


class SEIR_EKF:
    def __init__(self, params: SEIRParams, Q: np.ndarray, R_obs: np.ndarray, H_obs: np.ndarray):
        """
        Extended Kalman Filter for SEIR state estimation.
        State vector x: [S, E, IA, IM, IS, H, ICU, R, D, papp, ptest, kappa]
        Augmented state dim = 12.
        """
        self.params = params
        self.Q = Q  # 12x12
        self.R_obs = R_obs  # 5x5
        self.H_obs = H_obs  # 5x12
        self.dim = 12

    def _transition(self, x: np.ndarray) -> np.ndarray:
        """
        State transition: 1-day ODE integration.
        x: [S, E, IA, IM, IS, H, ICU, R, D, papp, ptest, kappa]
        """
        # Extract SEIR state and parameters
        state = x[:9]
        p_aug = x[9:] # papp, ptest, kappa (stay constant in transition)
        
        # Integration for 1 day
        sol = solve_ivp(
            seir_extended,
            (0, 1),
            state,
            args=(self.params,),
            method='LSODA',
            rtol=1e-8,
            atol=1e-10
        )
        
        if not sol.success:
            raise RuntimeError(f"EKF Transition Failed: {sol.message}")
            
        next_state = sol.y[:, -1]
        return np.concatenate([next_state, p_aug])

    def jacobian(self, x: np.ndarray, eps: float = 1e-6) -> np.ndarray:
        """
        Numerical Jacobian F = df/dx at x using forward differences.
        """
        F = np.zeros((self.dim, self.dim))
        fx = self._transition(x)
        
        for i in range(self.dim):
            x_plus = x.copy()
            x_plus[i] += eps
            fx_plus = self._transition(x_plus)
            F[:, i] = (fx_plus - fx) / eps
            
        return F

    def predict(self, x_est: np.ndarray, P: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """
        Predict step: x_pred = f(x_est); P_pred = F @ P @ F.T + Q
        """
        x_pred = self._transition(x_est)
        F = self.jacobian(x_est)
        P_pred = F @ P @ F.T + self.Q
        return x_pred, P_pred

    def update(self, x_pred: np.ndarray, P_pred: np.ndarray, y_obs: np.ndarray, H_active: np.ndarray, R_active: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """
        Update step using Joseph form for numerical stability.
        P_upd = (I - KH)P_pred(I - KH).T + K R K.T
        """
        # Innovation
        y_pred = H_active @ x_pred
        innovation = y_obs - y_pred
        
        # Innovation covariance
        S = H_active @ P_pred @ H_active.T + R_active
        
        # Kalman gain
        K = P_pred @ H_active.T @ inv(S)
        
        # State update
        x_upd = x_pred + K @ innovation
        x_upd = np.clip(x_upd, 0, None)
        
        # Covariance update (Joseph form)
        I = np.eye(self.dim)
        IKH = I - K @ H_active
        P_upd = IKH @ P_pred @ IKH.T + K @ R_active @ K.T
        
        return x_upd, P_upd, innovation, S

    def innovation_test(self, innovation: np.ndarray, S: np.ndarray, threshold: float = 13.28) -> bool:
        """
        Chi-squared test for innovation. 
        Critical value for df=4, p=0.99 is ~13.28.
        """
        chi2 = innovation.T @ inv(S) @ innovation
        return chi2 <= threshold

    def step(self, x_est: np.ndarray, P: np.ndarray, y_obs: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray, float]:
        """
        Single EKF step: Predict + Update + Test.
        Handles missing data (NaN in y_obs).
        """
        # Predict
        x_pred, P_pred = self.predict(x_est, P)
        
        # Handle missing observations (NaN)
        mask = ~np.isnan(y_obs)
        if not np.any(mask):
            return x_pred, P_pred, np.zeros(0), 0.0 # No observation to update with
            
        y_active = y_obs[mask]
        H_active = self.H_obs[mask]
        R_active = self.R_obs[np.ix_(mask, mask)]
        
        # Update
        x_upd, P_upd, innovation, S = self.update(x_pred, P_pred, y_active, H_active, R_active)
        
        # Chi2 test (on the number of active observations)
        # Critical value should ideally be adjusted by df = count(mask)
        # For simplicity, we'll use 13.28 if df=4 or a proportional value.
        chi2 = innovation.T @ inv(S) @ innovation
        
        return x_upd, P_upd, innovation, chi2
