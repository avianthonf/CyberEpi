"""SQLAlchemy models for user-service."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared.models import Base
from sqlalchemy import DateTime, Index, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class PushToken(Base):
    __tablename__ = "push_tokens"

    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    platform: Mapped[str] = mapped_column(String(10), primary_key=True)
    token: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    """Append-only audit trail of privileged patient-data access.

    Institutional compliance (HIPAA-style reviews) requires answering
    "who accessed whose record, when, and what did they do".
    """

    __tablename__ = "audit_log"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_sub: Mapped[str] = mapped_column(String(120), nullable=False)  # JWT subject
    action: Mapped[str] = mapped_column(String(40), nullable=False)      # register|read|update|risk.read|push.register
    patient_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    outcome: Mapped[str] = mapped_column(String(10), nullable=False, default="success")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_audit_log_patient", "patient_id"),
        Index("ix_audit_log_actor_time", "actor_sub", "created_at"),
    )
