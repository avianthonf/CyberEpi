"""Unit tests for notification-service."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import src.main  # noqa: F401  (ensure module exists before patching)


@pytest.fixture
def client(mock_db, mock_redis):
    with (
        patch("src.main.engine") as mock_main_engine,
        patch("src.main.connect_redis", return_value=mock_redis),
        patch("src.main.disconnect_redis", new=AsyncMock()),
        patch("src.main.AIOKafkaConsumer"),
        patch("src.main._consume_alerts", new_callable=AsyncMock),
    ):
        mock_main_engine.dispose = AsyncMock()

        from src.main import app

        app.state.redis = mock_redis
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


class TestHealthEndpoint:
    def test_health_reports_unavailable_without_infra(self, client):
        """Without live DB/Redis, /health must return 503 with per-component detail."""
        resp = client.get("/health")
        assert resp.status_code == 503
        detail = resp.json()["detail"]
        assert detail["status"] == "unhealthy"
        assert detail["service"] == "notification-service"
        assert "components" in detail


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
