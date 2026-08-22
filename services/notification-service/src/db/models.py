"""SQLAlchemy models for notification-service."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import Column, DateTime, ForeignKey, MetaData, String, Table, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

if TYPE_CHECKING:
    pass

metadata = MetaData()

# Define the 'patients' table in this service's metadata so Alembic can resolve the FK
patients_table = Table(
    "patients",
    metadata,
    Column("id", UUID(as_uuid=True), primary_key=True),
)

class Base(DeclarativeBase):
    metadata = metadata

class PushToken(Base):
    __tablename__ = "push_tokens"

    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('patients.id'), nullable=False)
    platform: Mapped[str] = mapped_column(String(10), primary_key=True)
    token: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('patients.id'), nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    body: Mapped[str] = mapped_column(String(500), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False)  # risk_alert, reminder, general
    priority: Mapped[str] = mapped_column(String(10), nullable=False)  # low, medium, high
    read: Mapped[bool] = mapped_column(sa.Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
