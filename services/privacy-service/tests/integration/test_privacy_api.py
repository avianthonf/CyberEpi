from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.auth import get_current_user
from src.main import app


@pytest.fixture
def auth_client():
    async def override_get_current_user():
        return {"sub": "123", "realm_access": {"roles": ["patient", "admin", "physician"]}}

    app.dependency_overrides[get_current_user] = override_get_current_user

    # Mock Redis and the persistent budget tracker
    mock_redis = AsyncMock()
    mock_redis.eval.return_value = 1
    mock_redis.get.return_value = "1.0"

    mock_tracker = AsyncMock()
    mock_tracker.consume.return_value = True
    mock_tracker.get_remaining.return_value = 1.0

    app.state.redis = mock_redis
    app.state.budget_tracker = mock_tracker

    # Create isolated async SQLite engine for aggregator persistence
    from src.db.models import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    # Setup DB tables
    import asyncio

    async def setup_db():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(setup_db())

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Prevent the lifespan from connecting to a real Redis or DB
    # Mock initialize_from_db but provide the real SQLite session_maker
    async def mock_init_from_db():
        # This mock is called during lifespan; we inject session_maker here
        from src.api.routers.fl import aggregator

        aggregator.session_maker = session_maker

    with (
        patch("src.main.connect_redis", return_value=mock_redis),
        patch("src.main.PersistentBudgetTracker", return_value=mock_tracker),
        patch("src.main.command.upgrade"),
        patch("src.api.routers.fl.aggregator.initialize_from_db", side_effect=mock_init_from_db),
        TestClient(app) as c,
    ):
        # Reset aggregator state after lifespan has run
        from src.api.routers.fl import aggregator

        aggregator.current_round_id = 1
        aggregator.current_round_gradients = []
        aggregator.current_round_clients = set()
        aggregator.completed_models = {}

        yield c

    # Cleanup
    asyncio.run(engine.dispose())
    app.dependency_overrides.clear()


def test_dp_publish_endpoint(auth_client):
    client = auth_client
    payload = {"stat_type": "Rt", "value": 1.2, "region_id": "region_123", "epsilon": 1.0}
    response = client.post("/internal/dp/publish", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "noised_value" in data
    assert data["noised_value"] != 1.2  # Should be noised
    assert data["sensitivity"] == 1.0 / 7.0


def test_fl_upload_pipeline(auth_client):
    client = auth_client

    # 1. Upload 3 gradients from distinct authenticated principals (min_clients=3)
    for i in range(3):
        # Override auth to return distinct principal per upload
        # Use default argument to capture loop variable
        def make_override(user_id=f"user_{i}"):
            async def override_user():
                return {"sub": user_id, "realm_access": {"roles": ["patient"]}}

            return override_user

        app.dependency_overrides[get_current_user] = make_override()

        res = client.post(
            "/api/v1/fl/upload_gradient",
            json={
                "round_id": 1,
                "gradient": [0.1] * 10,
                "n_samples": 100,
                "user_id": "ignored_body_field",
            },
        )
        assert res.status_code == 200, f"Upload {i} failed: {res.text}"

    # Duplicate submission from the same authenticated principal rejected
    async def dup_override():
        return {"sub": "user_0", "realm_access": {"roles": ["patient"]}}

    app.dependency_overrides[get_current_user] = dup_override

    res = client.post(
        "/api/v1/fl/upload_gradient",
        json={
            "round_id": 1,
            "gradient": [0.1] * 10,
            "n_samples": 100,
            "user_id": "ignored",
        },
    )
    assert res.status_code == 409

    # 2. Restore staff auth for trigger
    async def staff_override():
        return {"sub": "admin_123", "realm_access": {"roles": ["physician", "admin"]}}

    app.dependency_overrides[get_current_user] = staff_override

    res = client.post("/api/v1/fl/trigger_aggregation")
    assert res.status_code == 200
    data = res.json()
    assert len(data["new_update"]) == 10
