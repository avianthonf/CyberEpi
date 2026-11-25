
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from fastapi import Request
from fastapi.security import HTTPAuthorizationCredentials
from shared.auth import JWKSProvider, build_auth_dependency
from shared.config import Settings
from shared.db import create_session_factory
from shared.health import _db_healthy, _redis_healthy
from shared.kafka import connect_kafka, connect_redis, disconnect_kafka, disconnect_redis
from sqlalchemy import text

# Credentials for the master realm (admin-cli client always exists)
CLIENT_ID = "admin-cli"
REALM = "master"
KEYCLOAK_URL = "http://127.0.0.1:8080"
TOKEN_URL = f"{KEYCLOAK_URL}/realms/{REALM}/protocol/openid-connect/token"

@pytest.fixture
def settings():
    return Settings(
        database_url="postgresql+asyncpg://cyberepi:devpassword@127.0.0.1:5432/cyberepi",
        redis_url="redis://127.0.0.1:6379/0",
        kafka_bootstrap_servers="127.0.0.1:9092",
        keycloak_url=KEYCLOAK_URL,
        keycloak_realm=REALM,
        keycloak_client_id=CLIENT_ID,
        keycloak_client_secret="",
    )

@pytest.mark.asyncio
async def test_db_connection(settings):
    engine, _ = create_session_factory(settings)
    async with engine.begin() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
    await engine.dispose()

@pytest.mark.asyncio
async def test_redis_connection(settings):
    client = await connect_redis(settings)
    await client.set("test_key", "test_value")
    val = await client.get("test_key")
    assert val == "test_value"
    await disconnect_redis(client)

@pytest.mark.asyncio
async def test_kafka_connection(settings):
    producer = await connect_kafka(settings)
    await disconnect_kafka(producer)

@pytest.mark.asyncio
async def test_auth_token_verification(settings):
    # Obtain a real JWT token from Keycloak (using master realm)
    # Note: client_credentials might not work for admin-cli without a user
    # Actually admin-cli usually uses password grant. Let's try password grant
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "grant_type": "password",
                "client_id": CLIENT_ID,
                "username": "admin",
                "password": "admin",
            },
        )
        response.raise_for_status()
        token = response.json()["access_token"]

    assert token is not None

    # Verify it using shared.auth
    JWKSProvider(settings)
    credentials = HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)

    get_current_user, _ = build_auth_dependency(settings)

    payload = await get_current_user(credentials)
    assert payload is not None
    assert payload["typ"] == "Bearer"

@pytest.mark.asyncio
async def test_health_checks():
    # Redis Health
    mock_request = MagicMock(spec=Request)
    mock_request.app.state.redis = AsyncMock()
    mock_request.app.state.redis.ping = AsyncMock(return_value=True)
    healthy, _ = await _redis_healthy(mock_request)
    assert healthy is True

    # DB Health
    mock_engine = MagicMock()
    mock_conn = AsyncMock()
    # Mocking AsyncContextManager
    mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.connect.return_value.__aexit__ = AsyncMock(return_value=None)
    mock_conn.execute = AsyncMock(return_value=MagicMock())

    healthy, _ = await _db_healthy(mock_engine)
    assert healthy is True
