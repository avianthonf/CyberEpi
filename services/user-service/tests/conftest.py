"""Shared test fixtures for user-service."""

from __future__ import annotations

import base64
import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_jwt(payload: dict[str, Any]) -> str:
    """Create a fake JWT token with the given payload."""
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "typ": "JWT"}).encode()).rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    signature = base64.urlsafe_b64encode(b"fakesig").rstrip(b"=").decode()
    return f"{header}.{body}.{signature}"


@pytest.fixture
def valid_token() -> str:
    return _make_jwt(
        {
            "sub": "test-user-id",
            "exp": time.time() + 3600,
            "realm_access": {"roles": ["patient"]},
        }
    )


@pytest.fixture
def physician_token() -> str:
    return _make_jwt(
        {
            "sub": "test-physician-id",
            "exp": time.time() + 3600,
            "realm_access": {"roles": ["physician"]},
        }
    )


@pytest.fixture
def expired_token() -> str:
    return _make_jwt(
        {
            "sub": "test-user-id",
            "exp": time.time() - 3600,
            "realm_access": {"roles": ["patient"]},
        }
    )


@pytest.fixture
def malformed_token() -> str:
    return "not.a.valid.jwt.token"


@pytest.fixture
def mock_db():
    """Mock async database session."""
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.get = AsyncMock(return_value=None)
    r.setex = AsyncMock()
    r.aclose = AsyncMock()
    return r
