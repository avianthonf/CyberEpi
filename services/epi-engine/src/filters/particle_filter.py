import numpy as np
from scipy.stats import norm
from seir_core import SEIRParams, seir_extended
from scipy.integrate import solve_ivp
from typing import Tuple

class ParticleFilter:
    def __init__(self, Np: int, params: SEIRParams, Q: np.ndarray, R_obs: np.ndarray, H_obs: np.ndarray):
        """
        Particle Filter (SMC) for state estimation.
        State vector x: [S, E, IA, IM, IS, H, ICU, R, D, papp, ptest, kappa]
        """
        self.Np = Np
        self.params = params
        self.Q = Q
        self.R_obs = R_obs
        self.H_obs = H_obs
        self.dim = 12
        self.particles = None
        self.weights = np.ones(Np) / Np

    def initialize(self, x0_mean: np.ndarray, P0: np.ndarray):
        """Initialize particles from N(x0_mean, P0)"""
        self.particles = np.random.multivariate_normal(x0_mean, P0, self.Np)
        self.particles = np.clip(self.particles, 0, None)
        self.weights = np.ones(self.Np) / self.Np

    def propagate(self):
        """Propagate particles through the SEIR model and add process noise Q"""
        for i in range(self.Np):
            # Transition
            state = self.particles[i, :9]
            params_aug = self.particles[i, 9:]
            
            sol = solve_ivp(
                seir_extended, (0, 1), state, args=(self.params,),
                method='LSODA'
            )
            if sol.success:
                self.particles[i, :9] = sol.y[:, -1]
            
            # Add process noise
            noise = np.random.multivariate_normal(np.zeros(self.dim), self.Q)
            self.particles[i] += noise
            
        self.particles = np.clip(self.particles, 0, None)

    def weight(self, y_obs: np.ndarray):
        """Compute weights using Likelihood N(y; H*x, R_obs)"""
        mask = ~np.isnan(y_obs)
        y_active = y_obs[mask]
        H_active = self.H_obs[mask]
        R_active = self.R_obs[np.ix_(mask, mask)]
        
        log_weights = np.zeros(self.Np)
        for i in range(self.Np):
            y_pred = H_active @ self.particles[i]
            # multivariate normal logpdf
            diff = y_active - y_pred
            # Simplified: assuming R is diagonal and using total variance
            var = np.diag(R_active)
            log_lik = -0.5 * np.sum((diff**2) / var + np.log(2 * np.pi * var))
            log_weights[i] = log_lik
            
        # Avoid overflow: subtract max log_weight
        max_log = np.max(log_weights)
        self.weights = np.exp(log_weights - max_log)
        self.weights /= np.sum(self.weights)

    def effective_n(self) -> float:
        """Effective sample size Neff = 1 / sum(weights^2)"""
        return 1.0 / np.sum(self.weights**2)

    def resample(self):
        """Stratified resampling"""
        if self.effective_n() > self.Np / 2:
            return

        cumulative_weights = np.cumsum(self.weights)
        u = (np.arange(self.Np) + np.random.rand(self.Np)) / self.Np
        indices = np.searchsorted(cumulative_weights, u)
        
        self.particles = self.particles[indices]
        self.weights = np.ones(self.Np) / self.Np

    def liu_west_smooth(self, a: float = 0.98):
        """Kernel smoothing for parameter particles (Liu-West)"""
        # Only apply to parameter indices [9, 10, 11]
        param_idx = [9, 10, 11]
        m = np.average(self.particles[:, param_idx], axis=0, weights=self.weights)
        V = np.cov(self.particles[:, param_idx], rowvar=False, aweights=self.weights)
        
        h2 = 1 - a**2
        for i in range(self.Np):
            mu_i = a * self.particles[i, param_idx] + (1 - a) * m
            self.particles[i, param_idx] = np.random.multivariate_normal(mu_i, h2 * V)
            
        self.particles = np.clip(self.particles, 0, None)

    def estimate(self) -> Tuple[np.ndarray, np.ndarray]:
        """Return state estimate (mean) and variance"""
        x_hat = np.average(self.particles, axis=0, weights=self.weights)
        # Variance calculation
        diff = self.particles - x_hat
        var = np.average(diff**2, axis=0, weights=self.weights)
        return x_hat, var

    def step(self, y_obs: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """Full PF step: Propagate + Weight + Resample + Smooth"""
        self.propagate()
        if not np.all(np.isnan(y_obs)):
            self.weight(y_obs)
            self.resample()
            self.liu_west_smooth()
        return self.estimate()
