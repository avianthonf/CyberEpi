
import numpy as np


def laplace_mechanism(value: float, sensitivity: float, epsilon: float) -> float:
    """
    Adds Laplace noise to a scalar value.
    """
    if epsilon <= 0:
        raise ValueError("Epsilon must be positive.")
    noise = np.random.laplace(0, sensitivity / epsilon)
    return float(value + noise)

def gaussian_mechanism(
    value: float,
    sensitivity: float,
    epsilon: float,
    delta: float = 1e-5
) -> float:
    """
    Adds Gaussian noise to a scalar value.
    """
    if epsilon <= 0 or delta <= 0:
        raise ValueError("Epsilon and delta must be positive.")
    sigma = np.sqrt(2 * np.log(1.25 / delta)) * sensitivity / epsilon
    if not np.isfinite(sigma):
        raise ValueError("Gaussian noise scale is too large (sigma is non-finite)")
    noise = np.random.normal(0, sigma)
    result = float(value + noise)
    if not np.isfinite(result):
        raise ValueError("Gaussian mechanism output is non-finite")
    return result

def laplace_mechanism_array(
    values: np.ndarray | list[float],
    sensitivity: float,
    epsilon: float
) -> np.ndarray:
    """
    Applies Laplace noise independently to each element in an array.
    """
    values_arr = np.array(values)
    if epsilon <= 0:
        raise ValueError("Epsilon must be positive.")
    noise = np.random.laplace(0, sensitivity / epsilon, size=values_arr.shape)
    return values_arr + noise

def vector_gaussian_mechanism(
    gradient: np.ndarray,
    C: float,
    epsilon: float,
    delta: float = 1e-5
) -> np.ndarray:
    """
    Clips a gradient vector by L2 norm C and adds Gaussian noise.
    """
    if epsilon <= 0 or delta <= 0:
        raise ValueError("Epsilon and delta must be positive.")

    # 1. Gradient Clipping
    norm = np.linalg.norm(gradient)
    scaling_factor = min(1.0, C / (norm + 1e-10))
    g_clipped = gradient * scaling_factor

    # 2. Add Gaussian Noise
    sigma = np.sqrt(2 * np.log(1.25 / delta)) * C / epsilon
    noise = np.random.normal(0, sigma, size=gradient.shape)

    return g_clipped + noise
