"""Shared test fixtures for symptom-service."""

from __future__ import annotations

import base64
import json
import time
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


def _make_jwt(payload: dict[str, Any]) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "RS256"}).encode()).rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(b"fakesig").rstrip(b"=").decode()
    return f"{header}.{body}.{sig}"


@pytest.fixture
def valid_token() -> str:
    return _make_jwt({"sub": "test-user", "exp": time.time() + 3600, "realm_access": {"roles": ["patient"]}})


@pytest.fixture
def expired_token() -> str:
    return _make_jwt({"sub": "test-user", "exp": time.time() - 3600, "realm_access": {"roles": ["patient"]}})


@pytest.fixture
def mock_db():
    session = AsyncMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.flush = AsyncMock()
    session.execute = AsyncMock()
    session.add = MagicMock()
    return session


@pytest.fixture
def mock_redis():
    r = AsyncMock()
    r.ping = AsyncMock(return_value=True)
    r.get = AsyncMock(return_value=None)
    r.aclose = AsyncMock()
    return r


@pytest.fixture
def mock_kafka_producer():
    producer = AsyncMock()
    producer.send_and_wait = AsyncMock()
    return producer
