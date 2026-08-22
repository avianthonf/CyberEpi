from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SEIRParams:
    beta: float  # Infection rate
    sigma: float # Rate of progression to infectious state
    gamma: float # Recovery rate (base)
    rho: float   # Relative infectiousness of symptomatic vs asymptomatic
    fA: float    # Fraction asymptomatic
    fM: float    # Fraction mild
    fS: float    # Fraction severe
    alpha: float # Rate of progression from mild to severe
    h_rate: float # Hospitalization rate from severe
    delta: float # Rate of progression from hospital to ICU
    mu: float    # Death rate from severe (non-ICU)
    mu_icu: float # Death rate from ICU
    gamma_A: float # Recovery rate (asymptomatic)
    gamma_M: float # Recovery rate (mild)
    gamma_S: float # Recovery rate (severe)
    gamma_H: float # Recovery rate (hospital)
    gamma_ICU: float # Recovery rate (ICU)
    papp: float    # Proportionality factor for clinical load
    N_pop: int    # Total population
    L_perceived: float = 0.0 # Perceived loss for behavioral response (Chapter 7.3)
    eta_mask: float = 0.3    # Mask efficiency (Chapter 7.2)

    def __post_init__(self):
        if self.N_pop <= 0:
            raise ValueError(f"N_pop must be greater than 0, got {self.N_pop}")

        for field in self.__dataclass_fields__:
            val = getattr(self, field)
            if isinstance(val, (int, float)) and field != 'N_pop' and val < 0:
                raise ValueError(f"Parameter {field} must be non-negative, got {val}")

def behavioral_contact_factor(I_frac: float, L: float) -> float:
    """
    Computes the Nash Equilibrium contact reduction factor (Chapter 7.3).
    Based on U(c) = log(1+c) and Poisson infection probability.
    """
    if L <= 0 or I_frac <= 0:
        return 1.0
    return 1.0 / (1.0 + 5.0 * I_frac * L)

def seir_extended(t: float, y: np.ndarray, params: SEIRParams, u: np.ndarray = None) -> np.ndarray:
    """
    Extended 9-compartment SEIR ODE system with Control and Behavioral Feedback.
    """
    S, E, IA, IM, IS, H, ICU, R, D = y
    N = params.N_pop

    # Control variables (u1: isolation, u2: vaccination, u3: masks)
    u1, u2, u3 = u if u is not None else (0.0, 0.0, 0.0)

    # Chapter 7.3: Behavioral Response
    I_total_frac = (IA + IM + IS) / N
    c_factor = behavioral_contact_factor(I_total_frac, params.L_perceived)

    # Chapter 7.2: Effective Transmission
    beta_eff = params.beta * c_factor * (1 - u1) * (1 - params.eta_mask * u3)

    # Force of infection
    force_of_infection = beta_eff * (IA + params.rho * IM + params.rho * IS) / N

    dSdt = -force_of_infection * S - (u2 * S)
    dEdt = force_of_infection * S - params.sigma * E

    dIAdt = params.fA * params.sigma * E - params.gamma_A * IA
    dIMdt = params.fM * params.sigma * E - params.gamma_M * IM - params.alpha * IM
    dISdt = params.fS * params.sigma * E + params.alpha * IM - params.gamma_S * IS - params.mu * IS - params.h_rate * IS

    dHdt = params.h_rate * IS - params.gamma_H * H - params.delta * H
    dICUdt = params.delta * H - params.gamma_ICU * ICU - params.mu_icu * ICU

    dRdt = (
        params.gamma_A * IA + params.gamma_M * IM + params.gamma_S * IS
        + params.gamma_H * H + params.gamma_ICU * ICU + (u2 * S)
    )
    dDdt = params.mu * IS + params.mu_icu * ICU

    return np.array([dSdt, dEdt, dIAdt, dIMdt, dISdt, dHdt, dICUdt, dRdt, dDdt])

def seir_base(t: float, y: np.ndarray, beta: float, sigma: float, gamma: float, N: int) -> np.ndarray:
    """
    Standard SEIR model with parameter validation.
    """
    if N <= 0:
        raise ValueError(f"Population N must be > 0, got {N}")
    if beta < 0 or sigma < 0 or gamma < 0:
        raise ValueError("Parameters must be non-negative")
    """
    Base 4-compartment SEIR ODE system.
    """
    S, E, I, R = y
    dSdt = -beta * S * I / N
    dEdt = beta * S * I / N - sigma * E
    dIdt = sigma * E - gamma * I
    dRdt = gamma * I
    return np.array([dSdt, dEdt, dIdt, dRdt])

def seir_metapopulation(t: float, y: np.ndarray, params_list: list[SEIRParams], M: np.ndarray) -> np.ndarray:
    """
    Vectorized Spatial Metapopulation SEIR (Chapter 6.1).
    """
    n = len(params_list)
    y_reshaped = y.reshape((n, 9))
    dy = np.zeros_like(y_reshaped)

    for i in range(n):
        local_y = y_reshaped[i]
        IA_eff, IM_eff, IS_eff = local_y[2], local_y[3], local_y[4]

        for j in range(n):
            if i == j:
                continue
            IA_eff += M[j, i] * y_reshaped[j, 2]
            IM_eff += M[j, i] * y_reshaped[j, 3]
            IS_eff += M[j, i] * y_reshaped[j, 4]

        beta_i, N_i = params_list[i].beta, params_list[i].N_pop
        force_i = beta_i * (IA_eff + params_list[i].rho * IM_eff + params_list[i].rho * IS_eff) / N_i

        dy[i, 0] = -force_i * y_reshaped[i, 0]
        dy[i, 1] = force_i * y_reshaped[i, 0] - params_list[i].sigma * y_reshaped[i, 1]
        dy[i, 2] = params_list[i].fA * params_list[i].sigma * y_reshaped[i, 1] - params_list[i].gamma_A * y_reshaped[i, 2]
        dy[i, 3] = (
            params_list[i].fM * params_list[i].sigma * y_reshaped[i, 1]
            - params_list[i].gamma_M * y_reshaped[i, 3]
            - params_list[i].alpha * y_reshaped[i, 3]
        )
        dy[i, 4] = (
            params_list[i].fS * params_list[i].sigma * y_reshaped[i, 1]
            + params_list[i].alpha * y_reshaped[i, 3]
            - params_list[i].gamma_S * y_reshaped[i, 4]
            - params_list[i].mu * y_reshaped[i, 4]
            - params_list[i].h_rate * y_reshaped[i, 4]
        )

        for j in range(n):
            if i == j:
                continue
            dy[i, 2] += M[j, i] * y_reshaped[j, 2] - M[i, j] * y_reshaped[i, 2]
            dy[i, 3] += M[j, i] * y_reshaped[j, 3] - M[i, j] * y_reshaped[i, 3]
            dy[i, 4] += M[j, i] * y_reshaped[j, 4] - M[i, j] * y_reshaped[i, 4]

        dy[i, 5] = (
            params_list[i].h_rate * y_reshaped[i, 4]
            - params_list[i].gamma_H * y_reshaped[i, 5]
            - params_list[i].delta * y_reshaped[i, 5]
        )
        dy[i, 6] = (
            params_list[i].delta * y_reshaped[i, 5]
            - params_list[i].gamma_ICU * y_reshaped[i, 6]
            - params_list[i].mu_icu * y_reshaped[i, 6]
        )
        dy[i, 7] = (
            params_list[i].gamma_A * y_reshaped[i, 2]
            + params_list[i].gamma_M * y_reshaped[i, 3]
            + params_list[i].gamma_S * y_reshaped[i, 4]
            + params_list[i].gamma_H * y_reshaped[i, 5]
            + params_list[i].gamma_ICU * y_reshaped[i, 6]
        )
        dy[i, 8] = params_list[i].mu * y_reshaped[i, 4] + params_list[i].mu_icu * y_reshaped[i, 6]

    return dy.flatten()
