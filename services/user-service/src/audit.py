"""Audit logging helper for privileged data access."""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.db.models import AuditLog

logger = structlog.get_logger()


async def record_audit(
    db: AsyncSession,
    *,
    actor_sub: str,
    action: str,
    patient_id: uuid.UUID | None = None,
    outcome: str = "success",
) -> None:
    """Append one audit row. Failures are logged, never raised into the
    request path (audit must not break patient-facing operations)."""
    try:
        db.add(AuditLog(actor_sub=actor_sub, action=action,
                        patient_id=patient_id, outcome=outcome))
        await db.commit()
    except Exception as exc:  # noqa: BLE001
        await db.rollback()
        logger.error("audit_write_failed", action=action, error=str(exc))
