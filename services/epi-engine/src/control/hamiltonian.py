from collections.abc import Callable
from typing import Any

import numpy as np

from .controlled_seir import seir_controlled


def compute_jacobian_x(
    f: Callable[[float, np.ndarray, np.ndarray, dict[str, Any]], np.ndarray],
    t: float,
    x: np.ndarray,
    u: np.ndarray,
    params: dict[str, Any],
    eps: float = 1e-6
) -> np.ndarray:
    """Numerical Jacobian of f(t, x, u, params) wrt x."""
    dim = len(x)
    J = np.zeros((dim, dim))
    for i in range(dim):
        x_plus = x.copy()
        x_minus = x.copy()
        x_plus[i] += eps
        x_minus[i] -= eps
        f_plus = f(t, x_plus, u, params)
        f_minus = f(t, x_minus, u, params)
        J[:, i] = (f_plus - f_minus) / (2 * eps)
    return J

def compute_jacobian_u(
    f: Callable[[float, np.ndarray, np.ndarray, dict[str, Any]], np.ndarray],
    t: float,
    x: np.ndarray,
    u: np.ndarray,
    params: dict[str, Any],
    eps: float = 1e-6
) -> np.ndarray:
    """Numerical Jacobian of f(t, x, u, params) wrt u."""
    dim_x = len(x)
    dim_u = len(u)
    J = np.zeros((dim_x, dim_u))
    for i in range(dim_u):
        u_plus = u.copy()
        u_minus = u.copy()
        u_plus[i] += eps
        u_minus[i] -= eps
        f_plus = f(t, x, u_plus, params)
        f_minus = f(t, x, u_minus, params)
        J[:, i] = (f_plus - f_minus) / (2 * eps)
    return J

def compute_dH_dx(
    x: np.ndarray,
    lam: np.ndarray,
    u: np.ndarray,
    C1: float,
    C2: float,
    params: dict[str, Any],
    t: float = 0.0
) -> np.ndarray:
    """
    Returns -dH/dx = -(dL/dx + lam @ dF/dx).
    L = C1*(IM+IS)^2 + C2*(H+ICU)
    x = [S, E, IM, IS, H, ICU, R, D]
    """
    S, E, IM, IS, H, ICU, R, D = x

    # partial L / partial x
    dL_dx = np.zeros(8)
    dL_dx[2] = 2 * C1 * (IM + IS)  # IM
    dL_dx[3] = 2 * C1 * (IM + IS)  # IS
    dL_dx[4] = C2                 # H
    dL_dx[5] = C2                 # ICU

    # partial F / partial x
    dF_dx = compute_jacobian_x(seir_controlled, t, x, u, params)

    # -dH/dx = -(dL/dx + lam.T @ dF/dx)
    return -(dL_dx + lam @ dF_dx)

def compute_dH_du(
    x: np.ndarray,
    lam: np.ndarray,
    u: np.ndarray,
    C3: float,
    W: np.ndarray,
    params: dict[str, Any],
    t: float = 0.0
) -> np.ndarray:
    """
    Returns dH/du = dL/du + (dF/du).T @ lam.
    L_control = C3 * u.T @ W @ u
    """
    # partial L / partial u
    # L_u = C3 * (w1*u1^2 + w2*u2^2 + w3*u3^2)
    # dL/du = 2 * C3 * W @ u
    dL_du = 2 * C3 * W @ u

    # partial F / partial u
    dF_du = compute_jacobian_u(seir_controlled, t, x, u, params)

    # dH/du = dL/du + dF_du.T @ lam
    return dL_du + dF_du.T @ lam
