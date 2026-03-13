import numpy as np
from scipy.integrate import solve_ivp
from typing import Dict, Any, List, Tuple, NamedTuple
from .controlled_seir import seir_controlled
from .hamiltonian import compute_dH_dx, compute_dH_du

class SweepResult(NamedTuple):
    t: np.ndarray
    x: np.ndarray
    u: np.ndarray
    lam: np.ndarray
    converged: bool
    iterations: int
    final_cost: float

def compute_cost(
    x: np.ndarray, # (dim_x, n_steps)
    u: np.ndarray, # (dim_u, n_steps)
    C1: float,
    C2: float,
    C3: float,
    W: np.ndarray,
    C4: float,
    dt: float
) -> float:
    """
    J = sum((C1*(IM+IS)^2 + C2*(H+ICU) + C3*(u@W@u)) * dt) + C4*D[-1]
    """
    IM = x[2, :]
    IS = x[3, :]
    H = x[4, :]
    ICU = x[5, :]
    D = x[7, :]
    
    # Running cost
    L = C1 * (IM + IS)**2 + C2 * (H + ICU)
    
    # Control cost
    # u is (3, n_steps). Cost is u.T @ (C3*W) @ u
    # We can do this element-wise for diagonal W
    u_cost = C3 * (W[0,0]*u[0,:]**2 + W[1,1]*u[1,:]**2 + W[2,2]*u[2,:]**2)
    
    total_J = np.sum(L + u_cost) * dt + C4 * D[-1]
    return float(total_J)

def forward_backward_sweep(
    x0: np.ndarray,
    T: float,
    params: Dict[str, Any],
    C1: float,
    C2: float,
    C3: float,
    W: np.ndarray,
    n_iter: int = 1000,
    tol: float = 1e-4,
    dt: float = 0.2
) -> SweepResult:
    """
    Solves the optimal control problem via Forward-Backward Sweep.
    """
    t_eval = np.arange(0, T + dt, dt)
    n_steps = len(t_eval)
    dim_x = 8
    dim_u = 3
    
    # Initialize control
    u = np.zeros((dim_u, n_steps))
    x = np.zeros((dim_x, n_steps))
    lam = np.zeros((dim_x, n_steps))
    
    lr = 0.01 # Learning rate for control update
    C4 = params.get('C4', 10.0)
    
    converged = False
    
    for iteration in range(n_iter):
        u_old = u.copy()
        
        # 1. Forward Sweep: integrate state
        def f_forward(t, y):
            # Interpolate u at t
            idx = int(round(t / dt))
            idx = min(idx, n_steps - 1)
            u_current = u[:, idx]
            return seir_controlled(t, y, u_current, params)
        
        sol_x = solve_ivp(f_forward, (0, T), x0, t_eval=t_eval, method='RK45', rtol=1e-3, atol=1e-3)
        x = sol_x.y
        
        # 2. Backward Sweep: integrate costate
        # lam(T) = [0, 0, 0, 0, 0, 0, 0, C4]
        lam_T = np.zeros(dim_x)
        lam_T[7] = C4
        
        def f_backward(t, y):
            # Backward: t goes from T to 0
            # Interpolate x and u at t
            idx = int(round(t / dt))
            idx = min(idx, n_steps - 1)
            x_current = x[:, idx]
            u_current = u[:, idx]
            return compute_dH_dx(x_current, y, u_current, C1, C2, params, t)
        
        # We integrate from T to 0. solve_ivp can handle this.
        sol_lam = solve_ivp(f_backward, (T, 0), lam_T, t_eval=t_eval[::-1], method='RK45', rtol=1e-3, atol=1e-3)
        # sol_lam.y is in reverse time [T, ..., 0]
        lam = sol_lam.y[:, ::-1] # Flip back to [0, ..., T]
        
        # 3. Update Control
        # u[k] = clip(u[k] - lr * dH/du[k], 0, 1)
        for k in range(n_steps):
            dH_du = compute_dH_du(x[:, k], lam[:, k], u[:, k], C3, W, params, t_eval[k])
            u[:, k] = np.clip(u[:, k] - lr * dH_du, 0, 1)
            
        # 4. Check Convergence
        diff = np.max(np.abs(u - u_old))
        if diff < tol:
            converged = True
            break
            
    final_cost = compute_cost(x, u, C1, C2, C3, W, C4, dt)
    
    return SweepResult(t_eval, x, u, lam, converged, iteration + 1, final_cost)
