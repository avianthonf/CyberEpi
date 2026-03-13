import pytest
import httpx
from fastapi.testclient import TestClient
from src.main import app
from src.auth import get_current_user
import numpy as np

from unittest.mock import AsyncMock, patch
from src.dp.budget import BudgetTracker

@pytest.fixture
def auth_client():
    async def override_get_current_user():
        return {"sub": "123", "realm_access": {"roles": ["patient", "admin", "physician"]}}
    
    app.dependency_overrides[get_current_user] = override_get_current_user
    
    # Mock Redis and BudgetTracker
    mock_redis = AsyncMock()
    mock_redis.eval.return_value = 1 # Success for budget consumption
    mock_redis.get.return_value = "1.0" # Budget remaining
    
    app.state.redis = mock_redis
    app.state.budget_tracker = BudgetTracker(mock_redis, max_budget=1.0)
    
    with patch("src.main.redis.from_url", return_value=mock_redis):
        with TestClient(app) as c:
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
    
    # 1. Upload 3 gradients (min_clients=3)
    for _ in range(3):
        res = client.post("/api/v1/fl/upload_gradient", json={
            "round_id": 1,
            "gradient": [0.1] * 10,
            "n_samples": 100,
            "user_id": "user_abc"
        })
        assert res.status_code == 200
    
    # 2. Trigger aggregation
    res = client.post("/api/v1/fl/trigger_aggregation")
    assert res.status_code == 200
    data = res.json()
    assert len(data["new_update"]) == 10
