"""Shared Keycloak JWT authentication.

`get_current_user` validates RS256 bearer tokens against the Keycloak JWKS
endpoint with TTL-based caching, bounded retries, and stale-cache fallback so
auth survives short Keycloak outages. `require_role` enforces realm roles.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from shared.config import Settings

logger = structlog.get_logger()
_bearer = HTTPBearer()


class JWKSProvider:
    """Fetch and cache Keycloak JWKS with TTL, retries, and stale fallback."""

    def __init__(self, settings: Settings, ttl: int = 3600, max_retries: int = 3):
        self._settings = settings
        self._ttl = ttl
        self._max_retries = max_retries
        self._cache: dict[str, Any] = {}
        self._last_fetch = 0.0

    async def get_jwks(self) -> dict[str, Any]:
        now = time.time()
        if self._cache and (now - self._last_fetch) < self._ttl:
            return self._cache

        url = self._settings.keycloak_jwks_url
        logger.info("Fetching Keycloak JWKS", url=url)
        for attempt in range(self._max_retries):
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    resp = await client.get(url)
                    resp.raise_for_status()
                self._cache.clear()
                self._cache.update(resp.json())
                self._last_fetch = now
                logger.info("JWKS updated successfully")
                return self._cache
            except Exception as e:
                last_error = e
                if self._cache:
                    logger.warning("JWKS fetch failed, using stale cache", error=str(e))
                    return self._cache
                if attempt == self._max_retries - 1:
                    logger.error("JWKS fetch failed persistently, no cache available", error=str(e))
                    raise
                wait = 2**attempt
                logger.warning("JWKS fetch failed, retrying", error=str(e), attempt=attempt + 1, wait=wait)
                await asyncio.sleep(wait)
        raise last_error  # pragma: no cover - unreachable, satisfies type checkers


def build_auth_dependency(settings: Settings):
    """Return (get_current_user, require_role) bound to a service's settings."""
    jwks_provider = JWKSProvider(settings)

    async def get_current_user(
        credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    ) -> dict[str, Any]:
        # Dev mode: bypass JWT validation for local testing
        if settings.dev_auth_mode:
            return {"sub": "dev-user-id", "realm_access": {"roles": ["patient", "admin"]}}

        token = credentials.credentials
        try:
            jwks = await jwks_provider.get_jwks()
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
                detail=f"Could not validate credentials: {exc}",
            ) from exc
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Error validating token",
            ) from exc
        return payload

    def require_role(role: str):
        """Dependency factory verifying the user has the required realm role."""

        async def _require_role(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
            roles = user.get("realm_access", {}).get("roles", [])
            if role not in roles:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Role '{role}' required",
                )
            return user

        return _require_role

    return get_current_user, require_role
