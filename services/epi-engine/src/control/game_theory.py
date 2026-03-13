import numpy as np
from scipy.optimize import brentq
from typing import Optional

def nash_contact_rate(I: float, N: float, beta0: float, L: float) -> float:
    """
    Solves for the Nash equilibrium contact rate c*.
    Utility U(c) = log(1+c) - L * (1 - exp(-beta0*c*I/N))
    FOC: 1/(1+c) - beta0*(I/N)*exp(-beta0*c*I/N)*L = 0
    """
    if I <= 0 or N <= 0:
        return 100.0 # Default max contact rate
        
    def foc(c):
        return 1.0 / (1.0 + c) - (beta0 * I / N) * np.exp(-beta0 * c * I / N) * L
    
    # Check boundaries for brentq [0, 100]
    f0 = foc(0)
    f100 = foc(100)
    
    if f0 * f100 > 0:
        # No root in [0, 100], or multiple roots.
        # If f0 < 0, it means even at c=0, the marginal cost of infection > marginal utility of contact.
        if f0 < 0:
            return 0.0
        return 100.0
        
    try:
        c_star = brentq(foc, 0, 100)
        return float(c_star)
    except ValueError:
        return 0.0 if f0 < 0 else 100.0

def effective_beta_from_nash(I: float, N: float, beta0: float, L: float) -> float:
    """
    Returns beta_e = beta0 * (c_star / c_baseline)
    Assuming c_baseline = 1.0 for simplicity, or just proportional.
    The spec says beta_e = beta0 * nash_contact_rate.
    """
    c_star = nash_contact_rate(I, N, beta0, L)
    return beta0 * (c_star / 100.0) # Normalize by max contact rate? 
    # Actually, the prompt says "beta_e = beta0 * nash_contact_rate", 
    # but that would blow up if nash_contact_rate is 100.
    # Usually beta0 is already per contact. 
    # Let's assume beta0 is the transmission probability per contact * baseline contact rate.
    # If c_star is the equilibrium contact rate, and c_baseline is 1.0:
    # return beta0 * c_star
    return beta0 * c_star

def information_effect(Rt: float, L_base: float, sensitivity: float = 0.5) -> float:
    """
    Perceived severity L increases with Rt.
    L_eff = L_base * (1 + sensitivity * max(0, Rt-1))
    """
    return L_base * (1.0 + sensitivity * max(0.0, Rt - 1.0))
