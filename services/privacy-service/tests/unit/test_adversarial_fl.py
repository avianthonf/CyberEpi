import numpy as np
import pytest

from src.federated.aggregator import FedAvgAggregator


@pytest.mark.asyncio
async def test_fedavg_poisoning_protection():
    model_dim = 5
    aggregator = FedAvgAggregator(model_dim=model_dim, min_clients=3)

    # 2 honest clients with similar gradients
    g1 = np.array([0.1, 0.1, 0.1, 0.1, 0.1])
    g2 = np.array([0.12, 0.08, 0.11, 0.09, 0.1])

    # 1 malicious client with a poisoning gradient
    malicious_g = np.array([100.0, -100.0, 50.0, 0.0, 0.0])

    aggregator.receive_gradient(g1, client_id="c1")
    aggregator.receive_gradient(g2, client_id="c2")
    aggregator.receive_gradient(malicious_g, client_id="c3")

    # Aggregate with clipping C=1.0
    # Malicious gradient should be clipped to unit norm
    result = await aggregator.aggregate(C=1.0, epsilon=1000.0)  # Low noise

    # The result should be closer to the honest mean (~0.1) than the malicious one
    # Without clipping, the mean would be ~33.
    assert np.all(np.abs(result) < 2.0)


@pytest.mark.asyncio
async def test_fedavg_rejects_over_norm_limit():
    """Gradients with norm > 1e6 must be rejected per user's validation."""
    model_dim = 2
    aggregator = FedAvgAggregator(model_dim=model_dim, min_clients=2)

    # norm([1e6, 1e6]) = 1e6 * sqrt(2) ≈ 1.414e6 > 1e6 threshold
    with pytest.raises(ValueError, match="norm"):
        aggregator.receive_gradient(np.array([1e6, 1e6]), client_id="c1")

    # Just below limit should be accepted and clipped
    # norm([7e5, 7e5]) = 7e5 * sqrt(2) ≈ 9.9e5 < 1e6
    aggregator.receive_gradient(np.array([7e5, 7e5]), client_id="c1")
    aggregator.receive_gradient(np.array([-7e5, -7e5]), client_id="c2")

    result = await aggregator.aggregate(C=1.0, epsilon=1000.0)

    # Should still be bounded by clipping
    assert np.linalg.norm(result) < 5.0
    # Should still be bounded by clipping and noise
    assert np.linalg.norm(result) < 5.0  # Some slack for low-noise DP
