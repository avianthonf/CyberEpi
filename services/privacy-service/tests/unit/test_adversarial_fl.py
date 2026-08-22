import numpy as np

from src.federated.aggregator import FedAvgAggregator


def test_fedavg_poisoning_protection():
    model_dim = 5
    aggregator = FedAvgAggregator(model_dim=model_dim, min_clients=3)

    # 2 honest clients with similar gradients
    g1 = np.array([0.1, 0.1, 0.1, 0.1, 0.1])
    g2 = np.array([0.12, 0.08, 0.11, 0.09, 0.1])

    # 1 malicious client with a poisoning gradient
    malicious_g = np.array([100.0, -100.0, 50.0, 0.0, 0.0])

    aggregator.receive_gradient(g1)
    aggregator.receive_gradient(g2)
    aggregator.receive_gradient(malicious_g)

    # Aggregate with clipping C=1.0
    # Malicious gradient should be clipped to unit norm
    result = aggregator.aggregate(C=1.0, epsilon=1000.0) # Low noise

    # The result should be closer to the honest mean (~0.1) than the malicious one
    # Without clipping, the mean would be ~33.
    assert np.all(np.abs(result) < 2.0)
    assert np.mean(result) < 1.0

def test_fedavg_all_malicious_boundary():
    model_dim = 2
    aggregator = FedAvgAggregator(model_dim=model_dim, min_clients=2)

    # Very large gradients
    aggregator.receive_gradient(np.array([1e6, 1e6]))
    aggregator.receive_gradient(np.array([-1e6, -1e6]))

    result = aggregator.aggregate(C=1.0, epsilon=1000.0)

    # Should still be bounded by clipping and noise
    assert np.linalg.norm(result) < 5.0 # Some slack for low-noise DP
