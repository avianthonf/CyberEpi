"""Symptom-service API – ingest symptoms, compute Bayesian risk, publish to Kafka."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import get_current_user
from src.db.models import Patient, VitalsTS
from src.db.session import get_db

router = APIRouter()

# ─── Load symptom likelihoods ─────────────────────────────────────
_LIKELIHOODS_PATH = Path(__file__).resolve().parent.parent.parent / "symptom_likelihoods.json"
with open(_LIKELIHOODS_PATH) as f:
    SYMPTOM_LIKELIHOODS: dict[str, dict[str, dict[str, float]]] = json.load(f)

# ─── Risk tier thresholds ─────────────────────────────────────────
RISK_THRESHOLDS = [
    (0.8, "urgent"),
    (0.6, "consult"),
    (0.3, "moderate"),
    (0.0, "low"),
]


def compute_risk_tier(score: float) -> str:
    """Map risk score to tier label."""
    for threshold, tier in RISK_THRESHOLDS:
        if score >= threshold:
            return tier
    return "low"


def compute_bayesian_risk(
    symptoms: list[str],
    prior: float = 0.01,
    disease: str = "influenza",
) -> float:
    """Compute P(Infected | symptoms) using Bayes' rule.

    P(I|S) = P(I) * prod(P(s_i|I)) / [P(I)*prod(P(s_i|I)) + P(~I)*prod(P(s_i|~I))]
    """
    likelihoods = SYMPTOM_LIKELIHOODS.get(disease, {})

    numerator = prior
    denominator_not = 1.0 - prior

    for symptom in symptoms:
        if symptom in likelihoods:
            p_s_given_i = likelihoods[symptom]["p_given_infected"]
            p_s_given_not_i = likelihoods[symptom]["p_given_not_infected"]
            numerator *= p_s_given_i
            denominator_not *= p_s_given_not_i

    total = numerator + denominator_not
    if total == 0:
        return 0.0
    return numerator / total


# ─── Pydantic Schemas ─────────────────────────────────────────────
class SymptomReport(BaseModel):
    patient_id: uuid.UUID
    symptoms: list[str] = Field(..., min_length=1)
    heart_rate: int | None = None
    spo2: float | None = None
    temperature: float | None = None
    systolic_bp: int | None = None
    diastolic_bp: int | None = None
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
    body: SymptomReport,
    request: Request,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> SymptomResponse:
    """Ingest a symptom report, compute risk score, store, and publish to Kafka."""
    now = datetime.now(timezone.utc)

    # Verify patient exists and get region info
    result = await db.execute(select(Patient).where(Patient.id == body.patient_id))
    patient = result.scalar_one_or_none()
    if not patient:
        raise HTTPException(status_code=404, detail="Patient not found")

    region_id = body.region_id or patient.region_id or "unknown"
    patch_id = body.patch_id or patient.patch_id or "unknown"

    # Count existing reports for this patient
    count_result = await db.execute(
        select(func.count()).select_from(VitalsTS).where(VitalsTS.patient_id == body.patient_id)
    )
    report_count = (count_result.scalar() or 0) + 1  # +1 for current report

    # Compute risk score (null if < 3 total reports)
    risk_score: float | None = None
    risk_tier: str | None = None

    if report_count >= 3:
        # Get regional prevalence from Redis as Bayesian prior
        prior = 0.01
        try:
            redis_client: aioredis.Redis = request.app.state.redis
            cached_state = await redis_client.get(f"filter_state:{region_id}")
            if cached_state:
                state_data = json.loads(cached_state)
                prior = float(state_data.get("prevalence", 0.01))
        except Exception:
            pass  # Use default prior

        # Add spo2_low as virtual symptom if SpO2 < 95
        symptoms = list(body.symptoms)
        if body.spo2 is not None and body.spo2 < 95:
            symptoms.append("spo2_low")

        risk_score = compute_bayesian_risk(symptoms, prior=prior)
        risk_tier = compute_risk_tier(risk_score)

        # Update patient risk tier
        await db.execute(
            text("UPDATE patients SET risk_tier = :tier, updated_at = now() WHERE id = :pid"),
            {"tier": risk_tier, "pid": str(body.patient_id)},
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
        source="app",
    )
    db.add(vitals)
    await db.flush()

    # Publish to Kafka
    try:
        kafka_producer = request.app.state.kafka_producer
        event = {
            "event_id": str(uuid.uuid4()),
            "patient_id": str(body.patient_id),
            "event_type": "SYMPTOM_REPORT",
            "timestamp_ms": int(now.timestamp() * 1000),
            "region_id": region_id,
            "patch_id": patch_id,
            "payload": json.dumps({
                "symptoms": body.symptoms,
                "risk_score": risk_score,
                "risk_tier": risk_tier,
                "vitals": {
                    "heart_rate": body.heart_rate,
                    "spo2": body.spo2,
                    "temperature": body.temperature,
                },
            }),
            "schema_ver": "1.0",
        }
        await kafka_producer.send_and_wait(
            "patient.events",
            json.dumps(event).encode("utf-8"),
        )
    except Exception:
        # Log but don't fail the request if Kafka is unavailable
        import structlog
        structlog.get_logger().warning("Failed to publish to Kafka", patient_id=str(body.patient_id))

    return SymptomResponse(
        patient_id=body.patient_id,
        risk_score=risk_score,
        risk_tier=risk_tier,
        report_count=report_count,
    )


@router.get("/api/v1/patients/{patient_id}/history", response_model=list[HistoryItem])
async def get_symptom_history(
    patient_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
) -> list[HistoryItem]:
    """Get last 30 symptom reports for a patient."""
    result = await db.execute(
        select(VitalsTS)
        .where(VitalsTS.patient_id == patient_id)
        .order_by(VitalsTS.time.desc())
        .limit(30)
    )
    rows = result.scalars().all()
    return [HistoryItem.model_validate(r) for r in rows]
