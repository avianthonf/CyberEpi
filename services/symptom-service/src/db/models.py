"""SQLAlchemy models for symptom-service."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, validates
import sqlalchemy as sa



class Base(DeclarativeBase):
    pass


class VitalsTS(Base):
    """Vitals time-series (hypertable in TimescaleDB)."""

    __tablename__ = "vitals_ts"

    time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="CASCADE"), primary_key=True)
    heart_rate: Mapped[int | None] = mapped_column(Integer)
    spo2: Mapped[float | None] = mapped_column(Float)
    temperature: Mapped[float | None] = mapped_column(Float)
    systolic_bp: Mapped[int | None] = mapped_column(Integer)
    diastolic_bp: Mapped[int | None] = mapped_column(Integer)
    symptoms: Mapped[dict | None] = mapped_column(JSONB)
    risk_score: Mapped[float | None] = mapped_column(Float)
    risk_tier: Mapped[str | None] = mapped_column(String(20))
    
    __table_args__ = (
        sa.CheckConstraint('risk_score >= 0 AND risk_score <= 1', name='chk_vitals_risk_score'),
    )

    @validates("heart_rate")
    def validate_heart_rate(self, key, value):
        if value is not None and (value < 0 or value > 300):
            raise ValueError("Heart rate must be between 0 and 300")
        return value

    @validates("spo2")
    def validate_spo2(self, key, value):
        if value is not None and (value < 0 or value > 100):
            raise ValueError("SpO2 must be between 0 and 100")
        return value

    @validates("temperature")
    def validate_temperature(self, key, value):
        if value is not None and (value < 20 or value > 50):
            raise ValueError("Temperature must be between 20 and 50 Celsius")
        return value



class Patient(Base):
    """Read-only reference to patients table."""

    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    region_id: Mapped[str | None] = mapped_column(String(50))
    patch_id: Mapped[str | None] = mapped_column(String(20))
    risk_tier: Mapped[str] = mapped_column(String(20), default="low")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
