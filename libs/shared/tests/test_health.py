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


@pytest.mark.asyncio
async def test_kafka_health_cached_brokers_fail():
    """Kafka health must detect broker failure via network fetch, not cached metadata."""
    from unittest.mock import AsyncMock, MagicMock

    app = FastAPI()
    app.state.redis = MagicMock()
    app.state.redis.ping = AsyncMock()

    # Mock producer with client where fetch times out (broker dead)
    producer = MagicMock()
    client = MagicMock()
    client.fetch_all_metadata = AsyncMock(side_effect=TimeoutError())
    producer.client = client
    app.state.kafka_producer = producer

    from shared.health import kafka_health_check

    router = build_health_router(Settings(), extra_checks={"kafka": kafka_health_check})
    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert "unhealthy: timeout" in data["detail"]["components"]["kafka"]


@pytest.mark.asyncio
async def test_kafka_health_network_failure():
    """Kafka health must detect network errors during metadata fetch."""
    from unittest.mock import AsyncMock, MagicMock

    app = FastAPI()
    app.state.redis = MagicMock()
    app.state.redis.ping = AsyncMock()

    # Mock producer with client where fetch raises connection error
    producer = MagicMock()
    client = MagicMock()
    client.fetch_all_metadata = AsyncMock(side_effect=ConnectionError("broker unreachable"))
    producer.client = client
    app.state.kafka_producer = producer

    from shared.health import kafka_health_check

    router = build_health_router(Settings(), extra_checks={"kafka": kafka_health_check})
    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert "broker unreachable" in data["detail"]["components"]["kafka"]


@pytest.mark.asyncio
async def test_kafka_health_recovery():
    """Kafka health must report healthy after successful metadata fetch."""
    from unittest.mock import AsyncMock, MagicMock

    app = FastAPI()
    app.state.redis = MagicMock()
    app.state.redis.ping = AsyncMock()

    # Mock producer with successful fetch returning metadata
    producer = MagicMock()
    client = MagicMock()

    # Mock returned ClusterMetadata with brokers
    metadata = MagicMock()
    metadata.brokers = MagicMock(return_value=[MagicMock(), MagicMock(), MagicMock()])
    client.fetch_all_metadata = AsyncMock(return_value=metadata)

    producer.client = client
    app.state.kafka_producer = producer

    from shared.health import kafka_health_check

    router = build_health_router(Settings(), extra_checks={"kafka": kafka_health_check})
    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert "healthy: 3 broker(s)" in data["components"]["kafka"]


@pytest.mark.asyncio
async def test_db_health_stalled_connect():
    """DB health must timeout on stalled connection acquisition."""
    import asyncio

    app = FastAPI()
    app.state.redis = MagicMock()
    app.state.redis.ping = AsyncMock()

    # Mock engine where connect() hangs
    engine = MagicMock()

    class HangingConnection:
        async def __aenter__(self):
            await asyncio.sleep(10)  # Hangs longer than 2s timeout
            raise RuntimeError("Should not reach here")

        async def __aexit__(self, *args):
            pass

    engine.connect = MagicMock(return_value=HangingConnection())

    router = build_health_router(Settings(), engine=engine)
    app.include_router(router)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/health")
        assert response.status_code == 503
        data = response.json()
        assert "unhealthy: timeout" in data["detail"]["components"]["database"]
