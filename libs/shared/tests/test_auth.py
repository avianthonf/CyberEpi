"""Unit tests for shared auth module."""
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException
from jose import JWTError

from shared.auth import JWKSProvider, build_auth_dependency
from shared.config import Settings


@pytest.fixture
def mock_settings():
    return Settings(
        keycloak_url="http://localhost:8080",
        keycloak_realm="test-realm",
        dev_auth_mode=False,
    )


@pytest.fixture
def mock_jwks():
    return {
        "keys": [
            {
                "kid": "test-key-id",
                "kty": "RSA",
                "n": "test-modulus",
                "e": "AQAB",
            }
        ]
    }


@pytest.mark.asyncio
async def test_jwks_provider_caches(mock_settings, mock_jwks):
    """JWKSProvider should cache JWKS for TTL duration."""
    provider = JWKSProvider(mock_settings, ttl=60)

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_response = MagicMock()
        mock_response.json.return_value = mock_jwks
        mock_response.raise_for_status = MagicMock()
        mock_get.return_value = mock_response

        # First call should fetch
        jwks1 = await provider.get_jwks()
        assert jwks1 == mock_jwks
        assert mock_get.call_count == 1

        # Second call within TTL should use cache
        jwks2 = await provider.get_jwks()
        assert jwks2 == mock_jwks
        assert mock_get.call_count == 1  # Still 1


@pytest.mark.asyncio
async def test_jwks_provider_retries_on_failure(mock_settings):
    """JWKSProvider should retry on transient failures."""
    provider = JWKSProvider(mock_settings, max_retries=3)

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_get.side_effect = [
            Exception("Network error"),
            Exception("Network error"),
            MagicMock(json=lambda: {"keys": []}, raise_for_status=lambda: None),
        ]

        jwks = await provider.get_jwks()
        assert jwks == {"keys": []}
        assert mock_get.call_count == 3


@pytest.mark.asyncio
async def test_dev_auth_mode_bypass(mock_settings):
    """Dev auth mode should bypass JWT validation."""
    mock_settings.dev_auth_mode = True
    get_current_user, _ = build_auth_dependency(mock_settings)

    mock_credentials = MagicMock()
    mock_credentials.credentials = "fake-token"

    user = await get_current_user(mock_credentials)
    assert user["sub"] == "dev-user-id"
    assert "patient" in user["realm_access"]["roles"]


@pytest.mark.asyncio
async def test_invalid_token_raises_401(mock_settings, mock_jwks):
    """Invalid JWT should raise 401 Unauthorized."""
    get_current_user, _ = build_auth_dependency(mock_settings)

    mock_credentials = MagicMock()
    mock_credentials.credentials = "invalid-token"

    with patch.object(JWKSProvider, "get_jwks", return_value=mock_jwks):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(mock_credentials)

        assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_require_role_enforces_roles(mock_settings):
    """require_role should verify user has the required role."""
    _, require_role = build_auth_dependency(mock_settings)

    # User with admin role
    admin_user = {"sub": "user-1", "realm_access": {"roles": ["admin"]}}

    # Should pass for admin
    dependency = require_role("admin")
    result = await dependency(admin_user)
    assert result == admin_user

    # Should fail for patient role
    with pytest.raises(HTTPException) as exc_info:
        dependency = require_role("patient")
        await dependency(admin_user)

    assert exc_info.value.status_code == 403

@pytest.mark.asyncio
async def test_valid_token_accepted(mock_settings, mock_jwks):
    """Valid JWT should be accepted."""
    get_current_user, _ = build_auth_dependency(mock_settings)

    mock_credentials = MagicMock()
    mock_credentials.credentials = "valid-token"

    with (
        patch.object(JWKSProvider, "get_jwks", return_value=mock_jwks),
        patch("jose.jwt.decode", return_value={"sub": "user123"}),
    ):
        user = await get_current_user(mock_credentials)
        assert user["sub"] == "user123"

@pytest.mark.asyncio
async def test_expired_token_raises_401(mock_settings, mock_jwks):
    """Expired JWT should raise 401 Unauthorized."""
    get_current_user, _ = build_auth_dependency(mock_settings)

    mock_credentials = MagicMock()
    mock_credentials.credentials = "expired-token"

    with (
        patch.object(JWKSProvider, "get_jwks", return_value=mock_jwks),
        patch("jose.jwt.decode", side_effect=JWTError("Expired")),
        pytest.raises(HTTPException) as exc_info,
    ):
        await get_current_user(mock_credentials)

    assert exc_info.value.status_code == 401
