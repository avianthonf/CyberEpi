import numpy as np
from typing import Dict, Any

def seir_controlled(t: float, x: np.ndarray, u: np.ndarray, params: Dict[str, Any]) -> np.ndarray:
    """
    Controlled SEIR ODE system (8-dimensional).
    
    States x:
    [0] S: Susceptible
    [1] E: Exposed
    [2] IM: Infectious (Mild/Asymptomatic)
    [3] IS: Infectious (Severe)
    [4] H: Hospitalized
    [5] ICU: Intensive Care Unit
    [6] R: Recovered
    [7] D: Deceased
    
    Controls u (all in [0, 1]):
    u[0]: u1 - Social isolation compliance
    u[1]: u2 - Vaccination rate (fraction of S per day)
    u[2]: u3 - Mask mandate compliance
    
    Params:
    beta: Transmission rate
    sigma: 1/Latency period
    rho: Relative infectiousness of mild cases
    fM, fS: Fractions of mild/severe cases (fM + fS = 1)
    gamma_M, gamma_S: Recovery rates
    h_rate: Hospitalization rate of severe cases
    gamma_H: Recovery rate of hospitalized cases
    delta: ICU admission rate
    gamma_ICU: Recovery rate of ICU cases
    mu: Death rate in H
    mu_icu: Death rate in ICU
    N: Total population
    eta: 0.3 (Mask efficacy)
    """
    S, E, IM, IS, H, ICU, R, D = x
    u1, u2, u3 = u
    
    beta = params.get('beta', 0.5)
    sigma = params.get('sigma', 0.2)
    rho = params.get('rho', 1.0)
    fM = params.get('fM', 0.8)
    fS = params.get('fS', 0.2)
    gamma_M = params.get('gamma_M', 0.1)
    gamma_S = params.get('gamma_S', 0.1)
    h_rate = params.get('h_rate', 0.05)
    gamma_H = params.get('gamma_H', 0.05)
    delta = params.get('delta', 0.02)
    gamma_ICU = params.get('gamma_ICU', 0.03)
    mu = params.get('mu', 0.005)
    mu_icu = params.get('mu_icu', 0.15)
    N = params.get('N', 1000000)
    eta = params.get('eta', 0.3)
    
    # Effective transmission rate with controls
    # beta_e = beta0 * (1 - u1) * (1 - eta * u3)
    beta_e = beta * (1.0 - u1) * (1.0 - eta * u3)
    
    # Infection term
    lambda_val = beta_e * (rho * IM + IS) / N if N > 0 else 0.0
    
    # ODE System
    dS = -lambda_val * S - u2 * S # u2 is the vaccination rate
    dE = lambda_val * S - sigma * E
    dIM = fM * sigma * E - gamma_M * IM
    dIS = fS * sigma * E - (gamma_S + h_rate) * IS
    dH = h_rate * IS - (gamma_H + delta + mu) * H
    dICU = delta * H - (gamma_ICU + mu_icu) * ICU
    dR = gamma_M * IM + gamma_S * IS + gamma_H * H + gamma_ICU * ICU + u2 * S
    dD = mu * H + mu_icu * ICU
    
    return np.array([dS, dE, dIM, dIS, dH, dICU, dR, dD])
