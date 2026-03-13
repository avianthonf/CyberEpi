"""SQLAlchemy models for prescription-service."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, validates



class Base(DeclarativeBase):
    pass


class Prescription(Base):
    __tablename__ = "prescriptions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    patient_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), sa.ForeignKey("patients.id", ondelete="CASCADE"), nullable=False)
    physician_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    drug_name: Mapped[str] = mapped_column(String(200), nullable=False)
    ndc_code: Mapped[str | None] = mapped_column(String(50))
    rxnorm_id: Mapped[str | None] = mapped_column(String(50))
    dosage: Mapped[str | None] = mapped_column(String(100))
    frequency: Mapped[str | None] = mapped_column(String(100))
    status: Mapped[str] = mapped_column(String(30), default="active")
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    @validates("end_date")
    def validate_end_date(self, key, value):
        if value and self.start_date and value < self.start_date:
            raise ValueError("End date must be after or equal to start date")
        return value

    @validates("status")
    def validate_status(self, key, value):
        valid_statuses = {"active", "paused", "completed", "cancelled"}
        if value not in valid_statuses:
            raise ValueError(f"Invalid status: {value}")
        return value

    def is_active(self) -> bool:
        return self.status == "active" and (self.end_date is None or self.end_date >= date.today())



class Patient(Base):
    __tablename__ = "patients"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))
