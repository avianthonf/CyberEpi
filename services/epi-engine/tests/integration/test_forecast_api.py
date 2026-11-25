import uuid

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from src.db.models import EpiParams


@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16-alpine") as postgres:
        yield postgres


@pytest.fixture(scope="session")
def redis_container():
    with RedisContainer("redis:7-alpine") as redis:
        yield redis


@pytest_asyncio.fixture
async def mock_redis(redis_container):
    """Override the unit-suite Redis mock with an actual container client."""
    import redis.asyncio as aioredis

    client = aioredis.from_url(
        f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}/0",
        decode_responses=True,
    )
    try:
        yield client
    finally:
        await client.aclose()


@pytest_asyncio.fixture
async def api_client(postgres_container, redis_container, mock_redis, monkeypatch):
    # Build URLs for the fresh containers
    db_url = (
        postgres_container.get_connection_url()
        .replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        .replace("postgresql://", "postgresql+asyncpg://")
    )
    redis_url = f"redis://{redis_container.get_container_host_ip()}:{redis_container.get_exposed_port(6379)}/0"

    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("REDIS_URL", redis_url)

    from src.config import settings

    monkeypatch.setattr(settings, "redis_url", redis_url)
    monkeypatch.setattr(settings, "database_url", db_url)

    # Create tables directly (avoids requiring alembic to run against the fresh container)
    from src.db.models import Base

    engine = create_async_engine(db_url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    import src.db.connection as db_connection
    from src import main

    monkeypatch.setattr(db_connection, "engine", engine)
    monkeypatch.setattr(
        db_connection,
        "AsyncSessionLocal",
        async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False),
    )
    monkeypatch.setattr(main.app.state, "redis", mock_redis, raising=False)

    from src.auth import get_current_user

    async def _override_auth():
        return {"sub": str(uuid.uuid4()), "realm_access": {"roles": ["physician", "admin"]}}

    main.app.dependency_overrides[get_current_user] = _override_auth

    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client

    main.app.dependency_overrides.clear()
    await engine.dispose()


async def _seed_region(db_url: str, region_id: str) -> None:
    """Insert a region's SEIR parameters directly."""
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        params = EpiParams(
            id=uuid.uuid4(),
            region_id=region_id,
            source="manual_override",
            beta=0.6,
            sigma=0.25,
            gamma=0.1,
            rho=0.5,
            fA=0.3,
            fM=0.5,
            fS=0.2,
            alpha=0.1,
            h_rate=0.05,
            delta=0.02,
            mu=0.01,
            mu_icu=0.05,
            gamma_A=0.1,
            gamma_M=0.1,
            gamma_S=0.1,
            gamma_H=0.1,
            gamma_ICU=0.1,
            papp=0.12,
            N_pop=1000000,
        )
        session.add(params)
        await session.commit()
    await engine.dispose()


@pytest.mark.asyncio
async def test_forecast_returns_200_with_valid_region(api_client, postgres_container):
    db_url = (
        postgres_container.get_connection_url()
        .replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        .replace("postgresql://", "postgresql+asyncpg://")
    )
    region_id = "state-initial"
    await _seed_region(db_url, region_id)

    response = await api_client.get(f"/api/v1/regions/{region_id}/forecast?horizon_days=7")
    assert response.status_code == 200
    data = response.json()
    # Real ForecastResponse contract
    assert data["region_id"] == region_id
    assert data["horizon_days"] == 7
    assert "trajectory" in data
    assert "S" in data["trajectory"]
    assert len(data["trajectory"]["t"]) == 8  # 0..7 days


@pytest.mark.asyncio
async def test_param_update_invalidates_cache(api_client, postgres_container):
    """Updating region params changes the params hash, so the old cached
    forecast is no longer served."""
    db_url = (
        postgres_container.get_connection_url()
        .replace("postgresql+psycopg2://", "postgresql+asyncpg://")
        .replace("postgresql://", "postgresql+asyncpg://")
    )
    region_id = "cache-check"
    await _seed_region(db_url, region_id)

    # First forecast populates cache
    r1 = await api_client.get(f"/api/v1/regions/{region_id}/forecast?horizon_days=7")
    assert r1.status_code == 200
    hash1 = r1.json()["params_hash"]

    # Update params (beta changes → new hash → old cache invalid)
    engine = create_async_engine(db_url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        result = await session.execute(select(EpiParams).where(EpiParams.region_id == region_id))
        row = result.scalar_one()
        row.beta = 0.9
        await session.commit()
    await engine.dispose()

    r2 = await api_client.get(f"/api/v1/regions/{region_id}/forecast?horizon_days=7")
    assert r2.status_code == 200
    hash2 = r2.json()["params_hash"]
    assert hash1 != hash2
