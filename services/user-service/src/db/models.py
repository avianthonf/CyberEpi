"""SQLAlchemy models for user-service."""

from __future__ import annotations

import uuid
from datetime import datetime

from shared.models import Base
from sqlalchemy import DateTime, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column


class PushToken(Base):
    __tablename__ = "push_tokens"

    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    platform: Mapped[str] = mapped_column(String(10), primary_key=True)
    token: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
