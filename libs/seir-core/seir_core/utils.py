import numpy as np
from .seir import SEIRParams

def compute_load(y: np.ndarray) -> np.ndarray:
    """
    Computes Hospital Load: Load(t) = H(t) + ICU(t)
    y: array of shape (9, T) where indices 5 and 6 are H and ICU
    """
    return y[5] + y[6]

def compute_R0(params: SEIRParams) -> float:
    """
    R0 calculation using the Next Generation Matrix (NGM) approach.
    Spectral radius rho(F * V^-1).
    """
    # Expected time spent in infectious states per infection
    # IA: fA / gamma_A
    # IM: fM / (gamma_M + alpha)
    # IS: (fS + fM * alpha / (gamma_M + alpha)) / (gamma_S + mu + h_rate)
    
    term_A = params.fA / params.gamma_A
    duration_M = 1.0 / (params.gamma_M + params.alpha)
    term_M = params.fM * duration_M
    term_S = (params.fS + params.fM * params.alpha * duration_M) / (params.gamma_S + params.mu + params.h_rate)
    
    # R0 = beta * (expected_time_IA + rho * expected_time_IM + rho * expected_time_IS)
    return params.beta * (term_A + params.rho * (term_M + term_S))

def compute_Rt(params: SEIRParams, S: float, N: float) -> float:
    """
    Compute Rt = R0 * S/N
    """
    return compute_R0(params) * S / N
