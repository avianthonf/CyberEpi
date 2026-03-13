"""Simplified 4-compartment SEIR Metapopulation ODE."""

import numpy as np
from scipy.integrate import solve_ivp
from typing import Dict, List, Tuple

def metapop_rhs(t: float, y_flat: np.ndarray, params_list: List[Dict[str, float]], M: np.ndarray, n_patches: int) -> np.ndarray:
    """
    RHS for metapopulation SEIR model.
    y_flat: [S1, E1, I1, R1, S2, E2, I2, R2, ...]
    M: movement matrix where M[i,j] is fraction of population in patch i moving to j.
    """
    dydt = np.zeros_like(y_flat)
    
    # Reshape to (n_patches, 4)
    y = y_flat.reshape((n_patches, 4))
    S = y[:, 0]
    E = y[:, 1]
    I = y[:, 2]
    R = y[:, 3]
    N = S + E + I + R
    
    # Effective infectious density per patch
    # I_eff_i = (I_i + sum_j(M[j,i]*I_j)) / N_i
    # We use matrix multiplication for efficiency
    # M.T @ I gives the sum_j(M[j,i]*I_j) component if M[j,i] is flow from j to i
    
    # Calculate effective I across patches due to mobility
    # I_effective[i] = I[i] * (1 - sum_{j!=i} M[i,j]) + sum_{j!=i} M[j,i] * I[j]
    # If M[i,j] is the fraction of patch i population currently in patch j
    # Then I_effective in patch i is the sum of infectious people in patch i.
    # People in patch i come from patch i (those who stayed) and from other patches j.
    
    # M_stay[i] = 1 - sum_{j!=i} M[i,j]
    I_in_patch = np.zeros(n_patches)
    N_in_patch = np.zeros(n_patches)
    
    # For each patch i, who is there?
    # People from patch i who stayed: N[i] * (1 - sum_{j!=i} M[i,j])
    # People from patch j who are in patch i: N[j] * M[j,i]
    
    # Let's simplify M calculation. Assume M[i,j] is fraction of N[i] in patch j.
    # Total people in patch j: N_total_in_j = sum_i (N[i] * M[i,j])
    # Total infectious in patch j: I_total_in_j = sum_i (I[i] * M[i,j])
    
    I_total_in_patch = M.T @ I
    N_total_in_patch = M.T @ N
    
    # Avoid div by zero
    I_density = np.where(N_total_in_patch > 0, I_total_in_patch / N_total_in_patch, 0)
    
    for i in range(n_patches):
        p = params_list[i]
        beta = p['beta']
        sigma = p['sigma']
        gamma = p['gamma']
        
        # S_i people from patch i are distributed across patches j
        # In patch j, they encounter I_density[j]
        # Force of infection for people from patch i:
        # lambda_i = sum_j (M[i,j] * beta * I_density[j])
        lambda_i = beta * np.dot(M[i, :], I_density)
        
        dS = -lambda_i * S[i]
        dE = lambda_i * S[i] - sigma * E[i]
        dI = sigma * E[i] - gamma * I[i]
        dR = gamma * I[i]
        
        dydt[i*4 : i*4 + 4] = [dS, dE, dI, dR]
        
    return dydt

def run_metapop(
    y0_dict: Dict[str, List[float]],
    t_span: Tuple[float, float],
    t_eval: np.ndarray,
    params_dict: Dict[str, Dict[str, float]],
    M: np.ndarray,
    patch_ids: List[str]
) -> Dict[str, np.ndarray]:
    """Orchestrate metapopulation ODE run."""
    n_patches = len(patch_ids)
    y0 = np.zeros(n_patches * 4)
    params_list = []
    
    for i, pid in enumerate(patch_ids):
        y0[i*4 : i*4 + 4] = y0_dict[pid]
        params_list.append(params_dict[pid])
        
    sol = solve_ivp(
        metapop_rhs,
        t_span,
        y0,
        t_eval=t_eval,
        args=(params_list, M, n_patches),
        method='LSODA'
    )
    
    results = {}
    for i, pid in enumerate(patch_ids):
        # Extract [S, E, I, R] trajectories
        results[pid] = sol.y[i*4 : i*4 + 4, :]
        
    return results
