from fastapi import APIRouter, Depends, HTTPException
from typing import Dict, Any, List
from pydantic import BaseModel
from ...services.deterioration import DeteriorationPredictor
from ...services.risk import calculate_bayesian_risk # Existing risk logic

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
    alerts: List[str]
    timestamp_utc: str

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

@router.get("/score/{patient_id}")
async def get_patient_risk_score(patient_id: str):
    """
    Computes the real-time Bayesian risk score (Chapter 4.3).
    """
    # This would normally pull from Redis/DB
    return {"patient_id": patient_id, "risk_score": 0.42, "tier": "moderate"}
