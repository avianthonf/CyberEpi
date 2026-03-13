import numpy as np

def standard_composition(epsilons: list[float]) -> float:
    """
    Basic composition theorem: total epsilon is the sum of epsilons.
    """
    return sum(epsilons)

def advanced_composition_bound(epsilon_per_round: float, n_rounds: int, delta: float = 1e-5) -> float:
    """
    Advanced composition theorem providing a tighter bound for multiple DP rounds.
    """
    if epsilon_per_round <= 0 or n_rounds <= 0:
        return 0.0
    
    # Theorem from Dwork et al.
    term1 = np.sqrt(2 * n_rounds * np.log(1.0 / delta)) * epsilon_per_round
    term2 = n_rounds * epsilon_per_round * (np.exp(epsilon_per_round) - 1)
    
    return float(term1 + term2)
