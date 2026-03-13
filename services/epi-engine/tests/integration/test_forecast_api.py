import pytest
import pytest_asyncio
import httpx
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer
import os
import time
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres

@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer("redis:7-alpine") as redis:
        yield redis

@pytest_asyncio.fixture
async def api_client(postgres_container, redis_container):
    # Override settings for test environment
    db_url = postgres_container.get_connection_url().replace("postgresql+psycopg2://", "postgresql+asyncpg://").replace("postgresql://", "postgresql+asyncpg://")
    redis_url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}/0"
    
    os.environ["DATABASE_URL"] = db_url
    os.environ["REDIS_URL"] = redis_url
    
    from src.config import settings
    settings.redis_url = redis_url
    settings.database_url = db_url
    
    # In a real app, we'd use a test version of the FastAPI app
    # For now, we'll just test the logic or use a mock client
    from src.main import app
    
    # Override Redis connection to use the testcontainer instance, overcoming import-order caching
    import redis.asyncio as aioredis
    app.state.redis = aioredis.from_url(redis_url)
    
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

@pytest.mark.asyncio
async def test_forecast_returns_200_with_valid_region(api_client):
    # 1. Seed a region (default is seeded by migration, but we might need to run migrations)
    # Since we're using a fresh container, we'd need to run alembic upgrade head
    
    # For this task, we'll assume the startup task or a manual seed works
    response = await api_client.get("/api/v1/regions/state-initial/forecast")
    assert response.status_code == 200
    data = response.json()
    assert "forecast" in data
    assert "points" in data["forecast"]

@pytest.mark.asyncio
async def test_param_update_invalidates_cache(api_client):
    # Placeholder for cache invalidation logic test
    pass
