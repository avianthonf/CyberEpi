import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

# Test JWT Signature Verification Logic (user-service)
from src.auth import get_current_user


@pytest.mark.asyncio
async def test_jwt_verification_failure(monkeypatch):
    """Verify that invalid tokens raise 401."""
    credentials = MagicMock()
    credentials.credentials = "invalid.token.here"

    # The shared auth closure captures a JWKSProvider; mock its fetch so the
    # token decode fails against an empty key set → 401.

    # Find the JWKS provider bound in the get_current_user closure.
    # We patch the module-level auth functions indirectly: easiest is to build
    # a fresh provider and swap the decode path via a dummy key set.
    async def mock_get_jwks():
        return {"keys": []}

    # Patch the provider method on the closure's captured instance.
    # Since build_auth_dependency created it, we expose it for testability.
    from shared.auth import JWKSProvider

    monkeypatch.setattr(JWKSProvider, "get_jwks", mock_get_jwks)

    with pytest.raises(HTTPException) as exc:
        await get_current_user(credentials)
    assert exc.value.status_code == 401


# Test Patient Ownership Logic (user-service)
from src.api.routers.patients import get_patient


@pytest.mark.asyncio
async def test_patient_ownership_enforcement():
    """Verify that users cannot access other patients' data."""
    patient_id = uuid.uuid4()
    user_keycloak_id = "user-123"
    other_keycloak_id = "user-456"

    # Mock DB patient
    mock_patient = MagicMock()
    mock_patient.id = patient_id
    mock_patient.keycloak_id = other_keycloak_id  # Different from requester

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_patient
    mock_db.execute.return_value = mock_result

    # Requester user (not staff)
    user_payload = {
        "sub": user_keycloak_id,
        "realm_access": {"roles": ["patient"]}
    }

    with pytest.raises(HTTPException) as exc:
        await get_patient(patient_id=patient_id, db=mock_db, _user=user_payload)

    assert exc.value.status_code == 403
    assert "permission" in exc.value.detail.lower()
