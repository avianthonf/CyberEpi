"""JWT authentication middleware."""

from __future__ import annotations

import base64
import json
import time
from typing import Any

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_bearer = HTTPBearer()


def _decode_token_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Malformed token")
    payload_b64 = parts[1] + "=" * (4 - len(parts[1]) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload_b64))
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token encoding") from exc


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict[str, Any]:
    payload = _decode_token_payload(credentials.credentials)
    exp = payload.get("exp")
    if exp is not None and float(exp) < time.time():
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired")
    return payload


async def require_role(role: str, user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    roles = user.get("realm_access", {}).get("roles", [])
    if role not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Role '{role}' required")
    return user
