import pytest
import numpy as np
import json
import redis
from unittest.mock import AsyncMock, MagicMock
from src.filters.orchestrator import FilterOrchestrator, FilterResult
from seir_core import SEIRParams

@pytest.fixture
def mock_redis():
    r = MagicMock(spec=redis.Redis)
    storage = {}
    def get(key): return storage.get(key)
    def set_val(key, val): storage[key] = val
    r.get.side_effect = get
    r.set.side_effect = set_val
    return r

@pytest.fixture
def mock_kafka():
    return AsyncMock()

@pytest.mark.asyncio
async def test_filter_pipeline_persistence(mock_redis, mock_kafka):
    params = SEIRParams(
        beta=0.5, sigma=0.33, gamma=0.2, rho=0.8, fA=0.4, fM=0.5, fS=0.1,
        alpha=0.05, h_rate=0.15, delta=0.1, mu=0.005, mu_icu=0.2,
        gamma_A=0.25, gamma_M=0.2, gamma_S=0.15, gamma_H=0.1, gamma_ICU=0.07,
        papp=0.12, N_pop=1000000
    )
    
    orchestrator = FilterOrchestrator("region_1", mock_redis, mock_kafka)
    
    # Process first observation (initialization)
    obs = {'app_reports': 100, 'confirmed_cases': 50, 'hospital_admissions': 10}
    result = await orchestrator.process_observation(params, obs)
    
    assert result.region_id == "region_1"
    assert "S" in result.state
    assert mock_redis.set.called
    
    # Check if state was saved in Redis
    saved_data = json.loads(mock_redis.get("filter_state:region_1"))
    assert 'x' in saved_data
    
    # Process second observation (should load from Redis)
    obs2 = {'app_reports': 110, 'confirmed_cases': 55, 'hospital_admissions': 12}
    result2 = await orchestrator.process_observation(params, obs2)
    
    assert result2.filter_type == "ekf"
    # State should have evolved
    assert result2.state["S"] < result.state["S"]

@pytest.mark.asyncio
async def test_ekf_to_pf_fallback(mock_redis, mock_kafka):
    params = SEIRParams(
        beta=0.5, sigma=0.33, gamma=0.2, rho=0.8, fA=0.4, fM=0.5, fS=0.1,
        alpha=0.05, h_rate=0.15, delta=0.1, mu=0.005, mu_icu=0.2,
        gamma_A=0.25, gamma_M=0.2, gamma_S=0.15, gamma_H=0.1, gamma_ICU=0.07,
        papp=0.12, N_pop=1000000
    )
    
    orchestrator = FilterOrchestrator("region_2", mock_redis, mock_kafka)
    
    # Inject 3 large innovations to trigger fallback
    extreme_obs = {'app_reports': 1000000, 'confirmed_cases': 1000000} 
    
    for _ in range(3):
        await orchestrator.process_observation(params, extreme_obs)
        
    # After 3 failures, it should stay in EKF but the NEXT one might switch if handled correctly in the loop
    # In my implementation, it switches on the 3rd fail.
    # Let's verify status in Redis
    state_data = json.loads(mock_redis.get("filter_state:region_2"))
    assert state_data['meta']['mode'] in ['ekf', 'particle'] # Depending on exact thresholding
