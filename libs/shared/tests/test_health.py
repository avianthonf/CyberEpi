
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from shared.config import Settings
from shared.health import build_health_router


@pytest.mark.asyncio
async def test_health_router_unhealthy():
    # Pass no components, so it should be healthy?
    # Wait, redis is added by default.
    app = FastAPI()
    router = build_health_router(Settings())
    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 503

@pytest.mark.asyncio
async def test_health_router_healthy():
    app = FastAPI()

    # Mocking redis check by replacing it in extra_checks is not directly supported
    # as _redis_healthy is hardcoded.
    # But I can mock app.state.redis
    app.state.redis = MagicMock()
    app.state.redis.ping = AsyncMock()

    router = build_health_router(Settings())
    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 200
