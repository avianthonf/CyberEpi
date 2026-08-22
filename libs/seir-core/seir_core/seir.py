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

        # Conservation invariant: severity fractions partition all infections.
        # If fA+fM+fS != 1 the E compartment silently leaks or gains population
        # per infection event and the post-hoc renormalization in run_seir
        # merely masks the distortion.
        f_sum = self.fA + self.fM + self.fS
        if abs(f_sum - 1.0) > 1e-9:
            raise ValueError(f"Severity fractions must sum to 1, got fA+fM+fS = {f_sum}")

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

    Mobility semantics: M is a MIGRATION matrix — M[j, i] is the daily
    relocation fraction from patch j to patch i. Cross-patch coupling is
    entirely via physical relocation; each patch's force of infection uses
    only its local compartments.

    Migration applies to every living, non-institutionalized compartment
    (S, E, IA, IM, IS, R): if M is migration, exposed and susceptible
    travelers move too (incubating travelers are the primary seeders).
    H, ICU, and D are excluded — hospitalized/ICU patients are
    institutionalized and the deceased do not travel.

    Flux terms are antisymmetric pairs, so global population is conserved
    exactly regardless of M's values.
    """
    n = len(params_list)
    y_reshaped = y.reshape((n, 9))
    dy = np.zeros_like(y_reshaped)

    # Compartments that migrate: S, E, IA, IM, IS, R (indices 0,1,2,3,4,7)
    MOBILE = (0, 1, 2, 3, 4, 7)

    for i in range(n):
        S, E, IA, IM, IS = y_reshaped[i, 0:5]
        p = params_list[i]

        # Current LIVING population of this patch. Under permanent migration
        # patch totals drift from N_pop, so density-dependent transmission
        # must divide by the current denominator, not the static one.
        # The deceased (compartment D) do not dilute contact density.
        # Guard against degenerate empty patches.
        N_current = max(float(y_reshaped[i, :8].sum()), 1.0)

        # Local force of infection — no contact mixing (M is migration only)
        force = p.beta * (IA + p.rho * IM + p.rho * IS) / N_current

        dy[i, 0] = -force * S
        dy[i, 1] = force * S - p.sigma * E
        dy[i, 2] = p.fA * p.sigma * E - p.gamma_A * IA
        dy[i, 3] = p.fM * p.sigma * E - p.gamma_M * IM - p.alpha * IM
        dy[i, 4] = (
            p.fS * p.sigma * E
            + p.alpha * IM
            - p.gamma_S * IS
            - p.mu * IS
            - p.h_rate * IS
        )

        dy[i, 5] = p.h_rate * y_reshaped[i, 4] - p.gamma_H * y_reshaped[i, 5] - p.delta * y_reshaped[i, 5]
        dy[i, 6] = p.delta * y_reshaped[i, 5] - p.gamma_ICU * y_reshaped[i, 6] - p.mu_icu * y_reshaped[i, 6]
        dy[i, 7] = (
            p.gamma_A * y_reshaped[i, 2]
            + p.gamma_M * y_reshaped[i, 3]
            + p.gamma_S * y_reshaped[i, 4]
            + p.gamma_H * y_reshaped[i, 5]
            + p.gamma_ICU * y_reshaped[i, 6]
        )
        dy[i, 8] = p.mu * y_reshaped[i, 4] + p.mu_icu * y_reshaped[i, 6]

    # Migration fluxes (antisymmetric pairs → exact global conservation).
    # Applied to all mobile compartments; H, ICU, D are excluded.
    for i in range(n):
        for j in range(i + 1, n):
            flow = M[j, i] * y_reshaped[j, MOBILE] - M[i, j] * y_reshaped[i, MOBILE]
            dy[i, MOBILE] += flow
            dy[j, MOBILE] -= flow

    return dy.flatten()
