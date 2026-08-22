"""Shared patient lookup helpers.

The system has two IDs for a patient:
- `patient.id` — DB-side UUID, used in REST URLs.
- `user["sub"]` — Keycloak-side UUID, present in JWTs.

Authorization checks need to compare these without breaking. The standard
helper `resolve_patient_id` looks up the DB UUID by `keycloak_id` so a
patient can only act on their own record without the client having to
remember two IDs.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def resolve_patient_id(
    db: AsyncSession,
    user: dict[str, Any],
    *,
    not_found_detail: str = "Patient record not found for current user",
) -> uuid.UUID | None:
    """Look up the DB `patients.id` by `keycloak_id == user["sub"]`.

    Returns None if the JWT has no `sub` or no matching row.
    Raises `LookupError` if `raise_on_missing=True`.
    """
    sub = user.get("sub") if user else None
    if not sub:
        if not_found_detail:
            raise LookupError(not_found_detail)
        return None
    from shared.db import patient_table  # local import to avoid circulars

    table = patient_table()
    stmt = select(table.c.id).where(table.c.keycloak_id == sub)
    row = (await db.execute(stmt)).first()
    if row is None:
        return None
    return row[0]
