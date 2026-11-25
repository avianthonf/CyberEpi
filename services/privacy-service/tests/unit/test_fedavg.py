import numpy as np
import pytest

from src.federated.aggregator import FedAvgAggregator


@pytest.mark.asyncio
async def test_fedavg_aggregation_correct():
    model_dim = 5
    aggregator = FedAvgAggregator(model_dim=model_dim, min_clients=3)

    # 3 identical gradients
    g = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
    aggregator.receive_gradient(g, client_id="c1")
    aggregator.receive_gradient(g, client_id="c2")
    aggregator.receive_gradient(g, client_id="c3")

    # High epsilon to minimize noise for verification of mean
    result = await aggregator.aggregate(C=1.0, epsilon=1000.0)

    assert np.allclose(result, g, atol=0.1)


@pytest.mark.asyncio
async def test_fedavg_with_dp():
    model_dim = 10
    aggregator = FedAvgAggregator(model_dim=model_dim, min_clients=5)

    # 5 different gradients
    for i in range(5):
        aggregator.receive_gradient(np.ones(model_dim) * i, client_id=f"c{i}")

    # Normal epsilon -> noise should be present
    result = await aggregator.aggregate(C=1.0, epsilon=0.5)

    # Raw mean would be 2.0
    # DP mean should be different
    assert not np.array_equal(result, np.ones(model_dim) * 2.0)
    # But still in the ballpark
    assert np.mean(result) < 10.0


def test_aggregator_dimension_mismatch():
    aggregator = FedAvgAggregator(model_dim=3)
    with pytest.raises(ValueError):
        aggregator.receive_gradient(np.array([1, 2, 3, 4]), client_id="c1")
