import numpy as np
from typing import Dict, Tuple

def poststratify(app_reports: Dict[str, Tuple[int, int]], census_counts: Dict[str, int]) -> Tuple[float, float]:
    """
    Population-level prevalence estimate using post-stratification.
    app_reports: {stratum_id: (n_positive_reports, n_total_users_in_stratum)}
    census_counts: {stratum_id: N_d} (Total population in stratum)
    
    Returns: (I_hat, variance)
    I_hat = sum_d( p_hat_d * N_d )
    Var[I_hat] = sum_d( N_d^2 * p_hat_d*(1-p_hat_d)/n_d )
    """
    i_hat = 0.0
    variance = 0.0
    
    for stratum, n_d in census_counts.items():
        if stratum in app_reports:
            pos, total = app_reports[stratum]
            if total > 0:
                p_hat_d = pos / total
                i_hat += p_hat_d * n_d
                
                # Binomial variance in the sample
                # Var(p_hat_d) = p*(1-p)/n
                var_p_d = (p_hat_d * (1 - p_hat_d)) / total
                variance += (n_d**2) * var_p_d
                
    return i_hat, variance
