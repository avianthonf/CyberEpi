"""JWT authentication (shared via libs/shared) and patient-from-JWT helpers."""

from __future__ import annotations

import uuid
from typing import Any

from shared.auth import build_auth_dependency
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings
from src.db.models import Patient

get_current_user, require_role = build_auth_dependency(settings)


async def patient_id_from_jwt(
    db: AsyncSession,
    user: dict[str, Any],
) -> uuid.UUID | None:
    """Resolve `patients.id` from the JWT's `sub` (Keycloak user id).

    Returns None when no patient row has been linked to the JWT subject yet.
    """
    sub = user.get("sub") if user else None
    if not sub:
        return None
    result = await db.execute(select(Patient.id).where(Patient.keycloak_id == sub))
    row = result.first()
    return row[0] if row else None
