"""JWT authentication middleware – validates tokens against Keycloak JWKS."""

from __future__ import annotations

from typing import Any

import httpx
import asyncio
import time
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.config import settings

from jose import jwt, JWTError

logger = structlog.get_logger()
_bearer = HTTPBearer()

_jwks_cache: dict[str, Any] = {}
_jwks_last_fetch = 0
_JWKS_TTL = 3600  # 1 hour


async def _get_jwks() -> dict[str, Any]:
    """Fetch and cache the Keycloak JWKS with TTL and retries."""
    global _jwks_last_fetch
    now = time.time()
    
    if not _jwks_cache or (now - _jwks_last_fetch) > _JWKS_TTL:
        logger.info("Fetching Keycloak JWKS", url=settings.keycloak_jwks_url)
        for i in range(3):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(settings.keycloak_jwks_url)
                    resp.raise_for_status()
                    _jwks_cache.clear()
                    _jwks_cache.update(resp.json())
                    _jwks_last_fetch = now
                    logger.info("JWKS updated successfully")
                    return _jwks_cache
            except Exception as e:
                if i == 2:
                    if _jwks_cache:
                        logger.warning("JWKS fetch failed, using stale cache", error=str(e))
                        return _jwks_cache
                    logger.error("JWKS fetch failed persistently, no cache available", error=str(e))
                    raise
                wait = 2 ** i
                logger.warning("JWKS fetch failed, retrying...", error=str(e), attempt=i+1, wait=wait)
                await asyncio.sleep(wait)
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
            options={"verify_aud": False}, # Often client_id != aud in Keycloak defaults without config
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
