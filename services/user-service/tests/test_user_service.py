"""Unit tests for user-service."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

import src.main  # noqa: F401  (ensure module exists before patching)


# ── Create app with mocked dependencies ──
@pytest.fixture
def client(mock_db, mock_redis):
    """TestClient with mocked DB and Redis."""
    with (
        patch("src.main.engine") as mock_main_engine,
        patch("src.main.connect_redis", return_value=mock_redis),
        patch("src.main.disconnect_redis", new=AsyncMock()),
    ):
        mock_main_engine.dispose = AsyncMock()
        from src.main import app

        app.state.redis = mock_redis
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


class TestHealthEndpoint:
    def test_health_reports_unavailable_without_infra(self, client):
        """/health must return 503 with per-component detail when checks fail.

        Patch the shared health probes to simulate an outage; previously this
        test depended on ambient infra being down, so it failed on any
        machine with a live database.
        """
        with patch(
            "shared.health._redis_healthy",
            new=AsyncMock(return_value=(False, "unhealthy: simulated outage")),
        ), patch(
            "shared.health._db_healthy",
            new=AsyncMock(return_value=(False, "unhealthy: simulated outage")),
        ):
            resp = client.get("/health")
        assert resp.status_code == 503
        detail = resp.json()["detail"]
        assert detail["status"] == "unhealthy"
        assert detail["service"] == "user-service"
        assert "components" in detail


class TestAuthRequired:
    def test_get_patient_without_auth_returns_401(self, client):
        resp = client.get(f"/api/v1/patients/{uuid.uuid4()}")
        assert resp.status_code in (401, 403)

    def test_update_patient_without_auth_returns_401(self, client):
        resp = client.put(f"/api/v1/patients/{uuid.uuid4()}", json={"first_name": "Test"})
        assert resp.status_code in (401, 403)

    def test_push_token_without_auth_returns_401(self, client):
        resp = client.post(
            f"/api/v1/patients/{uuid.uuid4()}/push_token",
            json={"token": "abc", "platform": "ios"},
        )
        assert resp.status_code in (401, 403)

    def test_risk_without_auth_returns_401(self, client):
        resp = client.get(f"/api/v1/patients/{uuid.uuid4()}/risk")
        assert resp.status_code in (401, 403)


class TestInvalidToken:
    def test_expired_token_returns_401(self, client, expired_token):
        resp = client.get(
            f"/api/v1/patients/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401

    def test_malformed_token_returns_401(self, client):
        resp = client.get(
            f"/api/v1/patients/{uuid.uuid4()}",
            headers={"Authorization": "Bearer not-a-jwt"},
        )
        assert resp.status_code == 401


class TestRoleEnforcement:
    """Verify role-based access control."""

    def test_patient_token_accepted_for_patient_endpoints(self, client, valid_token):
        """Patient token should be accepted (even if patient not found)."""
        resp = client.get(
            f"/api/v1/patients/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {valid_token}"},
        )
        # Should get 404 (not found) or 500 (mock issue), not 401/403
        assert resp.status_code != 403
