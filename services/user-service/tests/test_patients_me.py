"""Tests for GET /api/v1/patients/me endpoint."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


@pytest_asyncio.fixture
async def async_client(mock_db, mock_redis):
    """AsyncClient with dependency overrides for authenticated tests."""
    with (
        patch("src.main.engine") as mock_main_engine,
        patch("src.main.connect_redis", return_value=mock_redis),
        patch("src.main.disconnect_redis", new=AsyncMock()),
    ):
        mock_main_engine.dispose = AsyncMock()
        from src.auth import get_current_user
        from src.db.session import get_db
        from src.main import app

        async def override_get_db():
            yield mock_db

        async def override_get_current_user():
            return {"sub": "test-user-id", "realm_access": {"roles": ["patient"]}}

        app.dependency_overrides[get_db] = override_get_db
        app.dependency_overrides[get_current_user] = override_get_current_user

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()


class TestGetCurrentPatient:
    """Tests for /patients/me authenticated profile resolution."""

    @pytest.mark.asyncio
    async def test_authenticated_patient_gets_own_profile(self, async_client, mock_db):
        """Authenticated patient can fetch their own profile via /me."""
        from shared.models import Patient

        now = datetime.now(UTC)
        patient_id = uuid.uuid4()
        patient = Patient(
            id=patient_id,
            keycloak_id="test-user-id",
            first_name="Test",
            last_name="User",
            email="test@example.com",
            risk_tier="low",
            created_at=now,
            updated_at=now,
        )

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = patient
        mock_db.execute.return_value = mock_result

        resp = await async_client.get("/api/v1/patients/me")

        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(patient_id)
        assert data["keycloak_id"] == "test-user-id"
        assert data["email"] == "test@example.com"

    @pytest.mark.asyncio
    async def test_unregistered_keycloak_user_returns_404(self, async_client, mock_db):
        """Keycloak user without patient record gets 404."""
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result

        resp = await async_client.get("/api/v1/patients/me")

        assert resp.status_code == 404
        detail = resp.json()["detail"].lower()
        assert "not found" in detail
        assert "registration" in detail

    @pytest.mark.asyncio
    async def test_unauthenticated_request_returns_401(self, mock_db, mock_redis):
        """Unauthenticated request to /me returns 401."""
        with (
            patch("src.main.engine") as mock_main_engine,
            patch("src.main.connect_redis", return_value=mock_redis),
            patch("src.main.disconnect_redis", new=AsyncMock()),
        ):
            mock_main_engine.dispose = AsyncMock()
            from src.db.session import get_db
            from src.main import app

            async def override_get_db():
                yield mock_db

            app.dependency_overrides[get_db] = override_get_db

            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.get("/api/v1/patients/me")
                assert resp.status_code in (401, 403)

            app.dependency_overrides.clear()
