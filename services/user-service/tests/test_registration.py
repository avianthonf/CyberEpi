"""Registration endpoint tests: security, ownership, and contract validation."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(mock_db, mock_redis):
    """TestClient with mocked DB and Redis, overriding auth dependencies."""
    with (
        patch("src.main.engine") as mock_main_engine,
        patch("src.main.connect_redis", return_value=mock_redis),
        patch("src.main.disconnect_redis", new=AsyncMock()),
    ):
        mock_main_engine.dispose = AsyncMock()
        from src.auth import get_current_user
        from src.db.session import get_db
        from src.main import app

        # Override dependencies so authenticated endpoints work
        async def override_get_db():
            yield mock_db

        async def override_get_current_user():
            return {"sub": "test-user-id", "realm_access": {"roles": ["patient"]}}

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user

        with TestClient(app) as c:
            yield c

        app.dependency_overrides.clear()


class TestRegistrationSecurity:
    """Security: duplicate email must not leak existing account data."""

    def test_public_registration_rejects_physician_role(self, client):
        """Security: public registration endpoint must reject physician/admin roles."""
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "email": "physician@example.com",
                "password": "PhysicianPassword123!",
                "first_name": "Dr",
                "last_name": "Evil",
                "role": "physician",
            },
        )

        assert resp.status_code == 422
        detail = str(resp.json().get("detail", ""))
        assert "role" in detail.lower() or "pattern" in detail.lower()

    def test_public_registration_rejects_admin_role(self, client):
        """Security: public registration endpoint must reject admin role."""
        resp = client.post(
            "/api/v1/auth/register",
            json={
                "email": "admin@example.com",
                "password": "AdminPassword123!",
                "first_name": "Admin",
                "last_name": "Attempt",
                "role": "admin",
            },
        )

        assert resp.status_code == 422
        detail = str(resp.json().get("detail", ""))
        assert "role" in detail.lower() or "pattern" in detail.lower()

    @patch("src.api.routers.patients.httpx.AsyncClient")
    def test_duplicate_email_returns_409_without_disclosure(self, mock_httpx_client, client):
        """ISS-09 regression: duplicate email attempt must return 409,
        not 200/201 with existing patient's UUID/keycloak_id."""

        mock_client_instance = AsyncMock()
        mock_httpx_client.return_value.__aenter__.return_value = mock_client_instance

        # Mock admin token acquisition then Keycloak 409 (user exists)
        mock_client_instance.post.side_effect = [
            AsyncMock(status_code=200, json=lambda: {"access_token": "admin-token-test"}),
            AsyncMock(status_code=409),  # User creation conflict
        ]

        resp = client.post(
            "/api/v1/auth/register",
            json={
                "email": "existing@example.com",
                "password": "AttackerPassword123!",
                "first_name": "Attacker",
                "last_name": "Attempt",
                "role": "patient",
            },
        )

        assert resp.status_code == 409
        detail = resp.json()
        assert "already exists" in detail["detail"].lower()
        # Security: Must NOT return existing patient's id or keycloak_id
        assert "id" not in detail
        assert "keycloak_id" not in detail
