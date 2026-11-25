"""Integration test: forecast uses persisted filter state and cache invalidates on state updates.

Regression for bug where forecast always used bootstrap y0 instead of loading
current filtered state. Tests prove:
1. Forecast response initial compartments match stored FilterState
2. Cache returns stable response on repeated requests (same state version)
3. Changed persisted state causes new forecast with different initial condition

Uses real DB (SQLite) and actual API endpoints, no mock forwarding.
"""

import asyncio
import json
from datetime import UTC, datetime

import numpy as np
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import Base, EpiParams, FilterState, ForecastCache
from src.main import app


@pytest.fixture(scope="module")
async def test_db_engine():
    """Create test database with schema."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="module")
def test_session_factory(test_db_engine):
    """Session factory for test database."""
    return async_sessionmaker(test_db_engine, class_=AsyncSession, expire_on_commit=False)


@pytest.fixture
async def seeded_region(test_session_factory):
    """Seed test region with params and initial filter state."""
    async with test_session_factory() as session:
        # Seed EpiParams
        params = EpiParams(
            region_id="test-region-forecast",
            beta=0.5,
            sigma=0.2,
            gamma=0.1,
            rho=1.0,
            fA=0.3,
            fM=0.5,
            fS=0.2,
            alpha=0.1,
            h_rate=0.15,
            delta=0.05,
            mu=0.01,
            mu_icu=0.02,
            gamma_A=0.14,
            gamma_M=0.1,
            gamma_S=0.08,
            gamma_H=0.1,
            gamma_ICU=0.05,
            papp=0.12,
            N_pop=1_000_000,
            source="ekf_estimate",
        )
        session.add(params)

        # Seed FilterState with non-trivial compartment values
        # State: [S, E, IA, IM, IS, H, ICU, R, D, papp, ptest, kappa]
        initial_state = FilterState(
            region_id="test-region-forecast",
            filter_type="ekf",
            state_vector=[900_000.0, 50_000.0, 10_000.0, 8_000.0, 5_000.0, 2_000.0, 500.0, 20_000.0, 4_500.0, 0.12, 0.5, 0.1],
            covariance_matrix=[100.0] * 12,  # Simplified diagonal
            cusum_score=2.5,
            fail_count=0,
            last_observation=[100.0, 50.0, 10.0, 5.0, 1.0],
            last_innovation=[5.0, 2.0, 1.0, 0.5, 0.1],
            last_chi2=3.2,
            observation_history=[],
            updated_at=datetime.now(UTC),
        )
        session.add(initial_state)
        await session.commit()

        return "test-region-forecast", initial_state.updated_at.isoformat()


@pytest.mark.asyncio
async def test_forecast_uses_persisted_filter_state(test_session_factory, seeded_region):
    """Forecast initial compartments match stored FilterState, not bootstrap."""
    region_id, state_timestamp = seeded_region

    # Override app DB dependency
    from src.db.connection import get_db

    async def override_get_db():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Override auth
    from src.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {"sub": "test-user", "realm_access": {"roles": ["physician"]}}

    # Mock Redis (forecast will use DB-backed state loader)
    from unittest.mock import AsyncMock

    mock_redis = AsyncMock()
    mock_redis.get.return_value = None  # Force DB fallback
    mock_redis.setex = AsyncMock()
    app.state.redis = mock_redis

    # Enable inline mode to run forecast synchronously
    from src.config import settings

    settings.run_forecast_inline = True

    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.get(f"/api/v1/regions/{region_id}/forecast?horizon_days=14")

    assert response.status_code == 200
    data = response.json()

    # Verify trajectory exists
    assert "trajectory" in data
    trajectory = data["trajectory"]

    # Initial condition (t=0) should match FilterState, not bootstrap
    # FilterState: [900k, 50k, 10k, 8k, 5k, 2k, 500, 20k, 4.5k]
    # Bootstrap would be: [999990, 10, 0, 0, 0, 0, 0, 0, 0]

    S_initial = trajectory["S"][0]
    E_initial = trajectory["E"][0]
    IA_initial = trajectory["IA"][0]
    H_initial = trajectory["H"][0]

    # Should be close to FilterState values
    assert abs(S_initial - 900_000) < 10_000, f"S={S_initial} should match FilterState ~900k, not bootstrap ~1M"
    assert abs(E_initial - 50_000) < 10_000, f"E={E_initial} should match FilterState ~50k, not bootstrap 10"
    assert abs(IA_initial - 10_000) < 5_000, f"IA={IA_initial} should match FilterState ~10k, not bootstrap 0"
    assert abs(H_initial - 2_000) < 1_000, f"H={H_initial} should match FilterState ~2k, not bootstrap 0"

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_forecast_cache_stable_on_repeated_requests(test_session_factory, seeded_region):
    """Repeated forecast requests with same state return identical cached response."""
    region_id, state_timestamp = seeded_region

    # Setup overrides
    from src.db.connection import get_db

    async def override_get_db():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    from src.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {"sub": "test-user", "realm_access": {"roles": ["physician"]}}

    from unittest.mock import AsyncMock

    mock_redis = AsyncMock()
    redis_cache = {}

    async def mock_get(key):
        return redis_cache.get(key)

    async def mock_setex(key, ttl, value):
        redis_cache[key] = value

    mock_redis.get = mock_get
    mock_redis.setex = mock_setex
    app.state.redis = mock_redis

    from src.config import settings

    settings.run_forecast_inline = True

    async with AsyncClient(app=app, base_url="http://test") as client:
        # First request: cache miss, computes forecast
        response1 = await client.get(f"/api/v1/regions/{region_id}/forecast?horizon_days=14")
        assert response1.status_code == 200
        data1 = response1.json()

        # Second request: should hit cache
        response2 = await client.get(f"/api/v1/regions/{region_id}/forecast?horizon_days=14")
        assert response2.status_code == 200
        data2 = response2.json()

    # Responses should be identical (same trajectory, same generated_at timestamp)
    assert data1["trajectory"] == data2["trajectory"]
    assert data1["generated_at"] == data2["generated_at"]
    assert data1["params_hash"] == data2["params_hash"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_forecast_invalidates_when_state_updates(test_session_factory, seeded_region):
    """Changed filter state causes cache miss and new forecast with different initial condition."""
    region_id, _ = seeded_region

    # Setup overrides
    from src.db.connection import get_db

    async def override_get_db():
        async with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    from src.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: {"sub": "test-user", "realm_access": {"roles": ["physician"]}}

    from unittest.mock import AsyncMock

    mock_redis = AsyncMock()
    redis_cache = {}

    async def mock_get(key):
        return redis_cache.get(key)

    async def mock_setex(key, ttl, value):
        redis_cache[key] = value

    mock_redis.get = mock_get
    mock_redis.setex = mock_setex
    app.state.redis = mock_redis

    from src.config import settings

    settings.run_forecast_inline = True

    async with AsyncClient(app=app, base_url="http://test") as client:
        # First forecast with initial state
        response1 = await client.get(f"/api/v1/regions/{region_id}/forecast?horizon_days=14")
        assert response1.status_code == 200
        data1 = response1.json()
        S_before = data1["trajectory"]["S"][0]

    # Update FilterState with significantly different compartment values
    async with test_session_factory() as session:
        result = await session.execute(select(FilterState).where(FilterState.region_id == region_id))
        state = result.scalar_one()

        # Simulate epidemic progression: more infected, fewer susceptible
        state.state_vector = [
            800_000.0,
            80_000.0,
            20_000.0,
            15_000.0,
            10_000.0,
            5_000.0,
            1_000.0,
            60_000.0,
            10_000.0,
            0.12,
            0.5,
            0.1,
        ]
        state.updated_at = datetime.now(UTC)  # New timestamp → new cache version
        await session.commit()

        new_timestamp = state.updated_at.isoformat()

    async with AsyncClient(app=app, base_url="http://test") as client:
        # Second forecast after state update
        response2 = await client.get(f"/api/v1/regions/{region_id}/forecast?horizon_days=14")
        assert response2.status_code == 200
        data2 = response2.json()
        S_after = data2["trajectory"]["S"][0]

    # Initial S should have changed significantly (900k → 800k)
    assert abs(S_after - 800_000) < 10_000, f"S after update should be ~800k, got {S_after}"
    assert abs(S_before - S_after) > 50_000, f"S should differ significantly: before={S_before}, after={S_after}"

    # generated_at timestamps should differ (new computation, not cached)
    assert data1["generated_at"] != data2["generated_at"]

    app.dependency_overrides.clear()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
