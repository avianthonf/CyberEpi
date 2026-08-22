import numpy as np

from src.dp.mechanisms import (
    gaussian_mechanism,
    laplace_mechanism,
    vector_gaussian_mechanism,
)


def test_laplace_noise_calibration():
    sensitivity = 1.0
    epsilon = 0.5
    values = []
    # Test with 10,000 samples for statistical significance
    for _ in range(10000):
        values.append(laplace_mechanism(100.0, sensitivity, epsilon))

    # Laplace(0, b) variance is 2*b^2, std is b*sqrt(2)
    b = sensitivity / epsilon # 2.0
    expected_std = b * np.sqrt(2) # ~2.82
    actual_std = np.std(values)

    assert 100.0 - 1.0 < np.mean(values) < 100.0 + 1.0
    assert expected_std - 0.5 < actual_std < expected_std + 0.5

def test_gaussian_noise_calibration():
    sensitivity = 1.0
    epsilon = 1.0
    delta = 1e-5
    values = []
    for _ in range(10000):
        values.append(gaussian_mechanism(50.0, sensitivity, epsilon, delta))

    sigma = np.sqrt(2 * np.log(1.25 / delta)) * sensitivity / epsilon
    actual_std = np.std(values)

    assert 50.0 - 1.0 < np.mean(values) < 50.0 + 1.0
    assert sigma - 0.5 < actual_std < sigma + 0.5

def test_gradient_clipping():
    # Random large gradient
    grad = np.array([10.0, 5.0, 20.0])
    clip_norm = 1.0
    # The clip mechanism inside vector_gaussian_mechanism is tested indirectly
    # We'll just check if it works for now
    result = vector_gaussian_mechanism(grad, clip_norm, 1000.0, 1e-5)  # High epsilon -> low noise
    assert np.linalg.norm(result) < clip_norm + 0.1  # Should be close to clip_norm
