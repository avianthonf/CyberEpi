"""Symptom-service API - ingest symptoms, compute Bayesian risk, publish to Kafka."""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import get_current_user
from src.db.models import Patient, VitalsTS
from src.db.session import get_db

logger = structlog.get_logger()

router = APIRouter()




# ─── Pydantic Schemas ─────────────────────────────────────────────
class SymptomReport(BaseModel):
    patient_id: uuid.UUID
    symptoms: list[str] = Field(..., min_length=1)
    heart_rate: int | None = Field(None, ge=20, le=300)
    spo2: float | None = Field(None, ge=0, le=100)
    temperature: float | None = Field(None, ge=25, le=45)
    systolic_bp: int | None = Field(None, ge=20, le=400)
    diastolic_bp: int | None = Field(None, ge=20, le=400)
    region_id: str | None = None
    patch_id: str | None = None


class SymptomResponse(BaseModel):
    patient_id: uuid.UUID
    risk_score: float | None
    risk_tier: str | None
    report_count: int
    message: str = "Symptom report recorded"


class HistoryItem(BaseModel):
    time: datetime
    symptoms: dict | list | None
    risk_score: float | None
    risk_tier: str | None
    heart_rate: int | None
    spo2: float | None
    temperature: float | None

    model_config = {"from_attributes": True}


# ─── Endpoints ────────────────────────────────────────────────────
@router.post("/api/v1/symptoms", response_model=SymptomResponse, status_code=201)
async def ingest_symptom(
    request: Request,
    body: SymptomReport,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> SymptomResponse:
    from pydantic import ValidationError
    try:
        # Authorization: Patient can only report for themselves. Physician/Admin can report for anyone.
        roles = user.get("realm_access", {}).get("roles", [])

        if "physician" not in roles and "admin" not in roles:
            from src.auth import patient_id_from_jwt

            own_patient_id = await patient_id_from_jwt(db, user)
            if own_patient_id is None or body.patient_id != own_patient_id:
                raise HTTPException(
                    status_code=403,
                    detail="Access denied: Patients can only report symptoms for themselves.",
                )
        now = datetime.now(UTC)

        # Verify patient exists and get region info
        result = await db.execute(select(Patient).where(Patient.id == body.patient_id))
        patient = result.scalar_one_or_none()
        if not patient:
            raise HTTPException(status_code=404, detail="Patient not found")

        region_id = body.region_id or patient.region_id or "unknown"
        patch_id = body.patch_id or patient.patch_id or "unknown"

        from src.services.risk import calculate_and_update_risk
        report_count, risk_score, risk_tier = await calculate_and_update_risk(
            db, request, body, region_id
        )

        # Store vitals record
        vitals = VitalsTS(
            time=now,
            patient_id=body.patient_id,
            heart_rate=body.heart_rate,
            spo2=body.spo2,
            temperature=body.temperature,
            systolic_bp=body.systolic_bp,
            diastolic_bp=body.diastolic_bp,
            symptoms={"reported": body.symptoms},
            risk_score=risk_score,
            risk_tier=risk_tier,
        )
        db.add(vitals)
        await db.flush()
        await db.commit()

        # Publish to Kafka
        try:
            from shared.kafka import publish_kafka

            kafka_producer = request.app.state.kafka_producer
            event = {
                "event_id": str(uuid.uuid4()),
                "patient_id": str(body.patient_id),
                "event_type": "SYMPTOM_REPORT",
                "timestamp_ms": int(now.timestamp() * 1000),
                "region_id": region_id,
                "patch_id": patch_id,
                "payload": json.dumps(
                    {
                        "symptoms": body.symptoms,
                        "risk_score": risk_score,
                        "risk_tier": risk_tier,
                        "vitals": {
                            "heart_rate": body.heart_rate,
                            "spo2": body.spo2,
                            "temperature": body.temperature,
                        },
                    }
                ),
                "schema_ver": "1.0",
            }
            await publish_kafka(
                kafka_producer,
                "symptom-reports",
                json.dumps(event).encode("utf-8"),
                timeout=5.0,
            )
        except Exception as exc:  # noqa: BLE001 — Log but don't fail the request if Kafka is unavailable
            logger.warning("Failed to publish to Kafka", patient_id=str(body.patient_id), error=str(exc))

        return SymptomResponse(
            patient_id=body.patient_id,
            risk_score=risk_score,
            risk_tier=risk_tier,
            report_count=report_count,
        )

    except (ValueError, ValidationError) as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

@router.get("/api/v1/patients/{patient_id}/history", response_model=list[HistoryItem])
async def get_symptom_history(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: dict[str, Any] = Depends(get_current_user),
) -> list[HistoryItem]:
    """Get last 30 symptom reports for a patient."""
    # Authorization: Patient can only view their own history. Physician/Admin can view any history.
    roles = user.get("realm_access", {}).get("roles", [])

    # Check if patient exists
    res = await db.execute(select(Patient).where(Patient.id == patient_id))
    if not res.scalar_one_or_none():
        raise HTTPException(status_code=404, detail="Patient not found")

    if "physician" not in roles and "admin" not in roles:
        from src.auth import patient_id_from_jwt

        own_patient_id = await patient_id_from_jwt(db, user)
        if own_patient_id is None or patient_id != own_patient_id:
            raise HTTPException(
                status_code=403,
                detail="Access denied: Patients can only view their own symptom history.",
            )

    result = await db.execute(select(VitalsTS).where(VitalsTS.patient_id == patient_id).order_by(VitalsTS.time.desc()).limit(30))
    rows = result.scalars().all()
    return [HistoryItem.model_validate(r) for r in rows]
