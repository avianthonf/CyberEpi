"""JWT authentication middleware – validates tokens against Keycloak JWKS."""

from __future__ import annotations

from typing import Any

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from jose import jwt, JWTError
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


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict[str, Any]:
    """Extract and validate the current user from the JWT bearer token."""
    token = credentials.credentials
    try:
        jwks = await _get_jwks()
        payload = jwt.decode(
            token,
            jwks,
            algorithms=["RS256"],
            audience=settings.keycloak_client_id,
            options={"verify_aud": False},
        )
    except JWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Could not validate credentials: {str(exc)}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Error validating token",
        ) from exc
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
