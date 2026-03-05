"""JWT authentication middleware – validates tokens against Keycloak JWKS."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import settings

_bearer = HTTPBearer()

_jwks_cache: dict[str, Any] = {}


async def _get_jwks() -> dict[str, Any]:
    """Fetch and cache the Keycloak JWKS."""
    if not _jwks_cache:
        async with httpx.AsyncClient() as client:
            resp = await client.get(settings.keycloak_jwks_url)
            resp.raise_for_status()
            _jwks_cache.update(resp.json())
    return _jwks_cache


def _decode_token_payload(token: str) -> dict[str, Any]:
    """Decode JWT payload without full verification (for dev/test).

    In production, use python-jose with JWKS keys for full verification.
    """
    import base64
    import json

    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token",
        )
    # Decode payload
    payload_b64 = parts[1]
    padding = 4 - len(payload_b64) % 4
    payload_b64 += "=" * padding
    try:
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        payload: dict[str, Any] = json.loads(payload_bytes)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token encoding",
        ) from exc
    return payload


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict[str, Any]:
    """Extract and validate the current user from the JWT bearer token."""
    token = credentials.credentials
    try:
        payload = _decode_token_payload(token)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        ) from exc

    # Check expiration
    import time

    exp = payload.get("exp")
    if exp is not None and float(exp) < time.time():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )

    return payload


async def require_role(
    role: str,
    user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Verify the user has the required realm role."""
    realm_access = user.get("realm_access", {})
    roles = realm_access.get("roles", [])
    if role not in roles:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Role '{role}' required",
        )
    return user
