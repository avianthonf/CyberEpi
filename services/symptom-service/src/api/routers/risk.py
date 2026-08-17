
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ...db.models import VitalsTS
from ...db.session import get_db
from ...services.deterioration import DeteriorationPredictor

router = APIRouter(prefix="/v1/risk", tags=["risk"])


class PatientFeatures(BaseModel):
    age: int
    n_comorbidities: int
    days_since_onset: float
    spo2_current: float
    spo2_slope_48h: float
    spo2_min_24h: float
    heart_rate_current: float
    hr_slope_48h: float
    fever_max_24h: float
    fever_duration_h: float
    risk_score_current: float
    risk_score_acceleration: float
    local_hosp_rate: float
    regional_Rt: float


class DeteriorationResponse(BaseModel):
    p_hospitalization_72h: float
    p_icu_7d: float
    alerts: list[str]
    source: str
    timestamp_utc: str


class RiskScoreResponse(BaseModel):
    patient_id: str
    risk_score: float | None
    tier: str | None


predictor = DeteriorationPredictor()


@router.post("/deterioration", response_model=DeteriorationResponse)
async def get_deterioration_prediction(features: PatientFeatures):
    """
    Computes clinical deterioration probability (Chapter 5.2).
    """
    try:
        result = predictor.predict(features.model_dump())
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/score/{patient_id}", response_model=RiskScoreResponse)
async def get_patient_risk_score(patient_id: str, db: AsyncSession = Depends(get_db)):
    """
    Computes the real-time Bayesian risk score from the patient's latest vitals.
    """
    result = await db.execute(
        select(VitalsTS.risk_score, VitalsTS.risk_tier)
        .where(VitalsTS.patient_id == patient_id)
        .order_by(VitalsTS.time.desc())
        .limit(1)
    )
    latest = result.first()
    if latest is None:
        raise HTTPException(status_code=404, detail="No symptom reports found for patient")
    return RiskScoreResponse(patient_id=patient_id, risk_score=latest.risk_score, tier=latest.risk_tier)
