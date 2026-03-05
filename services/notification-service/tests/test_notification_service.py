"""Unit tests for notification-service."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(mock_db, mock_redis):
    with (
        patch("src.db.session.engine") as mock_engine,
        patch("src.main.engine") as mock_main_engine,
        patch("src.main.AIOKafkaConsumer"),
        patch("src.main._consume_alerts", new_callable=AsyncMock),
    ):
        mock_conn = AsyncMock()
        mock_engine.begin = MagicMock(return_value=AsyncMock(__aenter__=AsyncMock(return_value=mock_conn), __aexit__=AsyncMock()))
        mock_engine.dispose = AsyncMock()
        mock_main_engine.begin = mock_engine.begin
        mock_main_engine.dispose = mock_engine.dispose

        from src.main import app

        app.state.redis = mock_redis
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"
        assert resp.json()["service"] == "notification-service"


class TestAuthRequired:
    def test_send_without_auth_returns_401(self, client):
        resp = client.post(
            "/api/v1/notifications/send",
            json={
                "patient_id": str(uuid.uuid4()),
                "title": "Test",
                "body": "Test notification",
            },
        )
        assert resp.status_code in (401, 403)

    def test_sse_without_auth_returns_401(self, client):
        resp = client.get(f"/api/v1/physicians/{uuid.uuid4()}/alerts/stream")
        assert resp.status_code in (401, 403)


class TestInvalidToken:
    def test_expired_token_returns_401(self, client, expired_token):
        resp = client.post(
            "/api/v1/notifications/send",
            headers={"Authorization": f"Bearer {expired_token}"},
            json={"patient_id": str(uuid.uuid4()), "title": "T", "body": "B"},
        )
        assert resp.status_code == 401
