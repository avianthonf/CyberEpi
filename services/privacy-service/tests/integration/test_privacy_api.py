from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from src.auth import get_current_user
from src.main import app


@pytest.fixture
def auth_client():
    async def override_get_current_user():
        return {"sub": "123", "realm_access": {"roles": ["patient", "admin", "physician"]}}

    app.dependency_overrides[get_current_user] = override_get_current_user

    # Mock Redis and the persistent budget tracker
    mock_redis = AsyncMock()
    mock_redis.eval.return_value = 1  # Success for budget consumption
    mock_redis.get.return_value = "1.0"  # Budget remaining

    mock_tracker = AsyncMock()
    mock_tracker.consume.return_value = True
    mock_tracker.get_remaining.return_value = 1.0

    app.state.redis = mock_redis
    app.state.budget_tracker = mock_tracker

    # Prevent the lifespan from connecting to a real Redis or instantiating
    # a real PersistentBudgetTracker (lifespan overwrites app.state on enter).
    with (
        patch("src.main.connect_redis", return_value=mock_redis),
        patch("src.main.PersistentBudgetTracker", return_value=mock_tracker),
        patch("src.main.command.upgrade"),  # no real DB in unit/integration tests
        TestClient(app) as c,
    ):
        yield c

    app.dependency_overrides.clear()

def test_dp_publish_endpoint(auth_client):
    client = auth_client
    payload = {
        "stat_type": "Rt",
        "value": 1.2,
        "region_id": "region_123",
        "epsilon": 1.0
    }
    response = client.post("/internal/dp/publish", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "noised_value" in data
    assert data["noised_value"] != 1.2 # Should be noised
    assert data["sensitivity"] == 1.0 / 7.0

def test_fl_upload_pipeline(auth_client):
    client = auth_client

    # 1. Upload 3 gradients from distinct clients (min_clients=3)
    for i in range(3):
        res = client.post("/api/v1/fl/upload_gradient", json={
            "round_id": 1,
            "gradient": [0.1] * 10,
            "n_samples": 100,
            "user_id": f"user_{i}",
        })
        assert res.status_code == 200

    # Duplicate submission from the same client in the same round is rejected.
    res = client.post("/api/v1/fl/upload_gradient", json={
        "round_id": 1,
        "gradient": [0.1] * 10,
        "n_samples": 100,
        "user_id": "user_0",
    })
    assert res.status_code == 409

    # 2. Trigger aggregation
    res = client.post("/api/v1/fl/trigger_aggregation")
    assert res.status_code == 200
    data = res.json()
    assert len(data["new_update"]) == 10
