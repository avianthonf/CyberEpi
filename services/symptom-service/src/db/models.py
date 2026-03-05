"""SQLAlchemy models for symptom-service."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class VitalsTS(Base):
    """Vitals time-series (hypertable in TimescaleDB)."""

    __tablename__ = "vitals_ts"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    heart_rate: Mapped[int | None] = mapped_column(Integer)
    spo2: Mapped[float | None] = mapped_column(Float)
    temperature: Mapped[float | None] = mapped_column(Float)
    systolic_bp: Mapped[int | None] = mapped_column(Integer)
    diastolic_bp: Mapped[int | None] = mapped_column(Integer)
    symptoms: Mapped[dict | None] = mapped_column(JSONB)
    risk_score: Mapped[float | None] = mapped_column(Float)
    risk_tier: Mapped[str | None] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(30), default="app")


class Patient(Base):
    """Read-only reference to patients table."""

    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    region_id: Mapped[str | None] = mapped_column(String(50))
    patch_id: Mapped[str | None] = mapped_column(String(20))
    risk_tier: Mapped[str] = mapped_column(String(20), default="low")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
