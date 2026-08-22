"""Unit tests for prescription-service."""

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
        assert detail["service"] == "prescription-service"
        assert "components" in detail


class TestAuthRequired:
    def test_create_prescription_without_auth_returns_401(self, client):
        resp = client.post(
            "/api/v1/prescriptions",
            json={
                "patient_id": str(uuid.uuid4()),
                "drug_name": "Amoxicillin",
                "start_date": "2024-01-01",
            },
        )
        assert resp.status_code in (401, 403)

    def test_get_prescription_without_auth_returns_401(self, client):
        resp = client.get(f"/api/v1/prescriptions/{uuid.uuid4()}")
        assert resp.status_code in (401, 403)

    def test_list_prescriptions_without_auth_returns_401(self, client):
        resp = client.get(f"/api/v1/patients/{uuid.uuid4()}/prescriptions")
        assert resp.status_code in (401, 403)

    def test_scan_without_auth_returns_401(self, client):
        resp = client.post("/api/v1/medications/scan", json={"ocr_text": "Aspirin 500mg", "patient_id": str(uuid.uuid4())})
        assert resp.status_code in (401, 403)


class TestInvalidToken:
    def test_expired_token_returns_401(self, client, expired_token):
        resp = client.get(
            f"/api/v1/prescriptions/{uuid.uuid4()}",
            headers={"Authorization": f"Bearer {expired_token}"},
        )
        assert resp.status_code == 401

    def test_malformed_token_returns_401(self, client):
        resp = client.get(
            f"/api/v1/prescriptions/{uuid.uuid4()}",
            headers={"Authorization": "Bearer invalid"},
        )
        assert resp.status_code == 401
