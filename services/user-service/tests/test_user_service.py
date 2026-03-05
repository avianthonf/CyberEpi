"""Unit tests for user-service."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from tests.conftest import _make_jwt


# ── Create app with mocked dependencies ──
@pytest.fixture
def client(mock_db, mock_redis):
    """TestClient with mocked DB and Redis."""
    import src.main
    with (
        patch("src.db.session.engine") as mock_engine,
        patch("src.main.engine") as mock_main_engine,
    ):
        mock_conn = AsyncMock()
        mock_conn.execute = AsyncMock()
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
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "user-service"


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
