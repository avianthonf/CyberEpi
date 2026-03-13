from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from uuid import UUID
from datetime import datetime

from src.db.connection import get_db
from src.db.models import ControlWeights, ControlRecommendation
from src.tasks.control_tasks import solve_optimal_control

router = APIRouter(prefix="/api/v1/control", tags=["control"])

class ControlWeightsIn(BaseModel):
    C1: float = 1.0
    C2: float = 5.0
    C3: float = 2.0
    C4: float = 10.0
    W_u1: float = 1.0
    W_u2: float = 0.5
    W_u3: float = 0.8
    ethical_framework: str = "utilitarian"
    notes: Optional[str] = None

class ControlWeightsOut(ControlWeightsIn):
    id: UUID
    region_id: str
    updated_at: datetime
    
    model_config = ConfigDict(from_attributes=True)

class RecommendationOut(BaseModel):
    id: UUID
    region_id: str
    generated_at: datetime
    u1_recommended: float
    u2_recommended: float
    u3_recommended: float
    Rt_current: float
    Rt_predicted_30d: float
    cost_J: float
    converged: bool
    rationale: str
    interpretation: dict
    
    model_config = ConfigDict(from_attributes=True)

@router.get("/recommendations", response_model=RecommendationOut)
async def get_latest_recommendation(region_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ControlRecommendation)
        .where(ControlRecommendation.region_id == region_id)
        .order_by(desc(ControlRecommendation.generated_at))
        .limit(1)
    )
    rec = result.scalar_one_or_none()
    if not rec:
        raise HTTPException(status_code=404, detail="No recommendations found for this region")
    
    # Add interpretation text
    interpretation = {
        "u1_desc": f"{rec.u1_recommended*100:.1f}% physical distancing compliance recommended",
        "u2_desc": f"{rec.u2_recommended*100:.1f}% daily vaccination rate of susceptibles recommended",
        "u3_desc": f"{rec.u3_recommended*100:.1f}% mask mandate adherence recommended"
    }
    
    # Map rec to pydantic
    return RecommendationOut(
        id=rec.id,
        region_id=rec.region_id,
        generated_at=rec.generated_at,
        u1_recommended=rec.u1_recommended,
        u2_recommended=rec.u2_recommended,
        u3_recommended=rec.u3_recommended,
        Rt_current=rec.Rt_current,
        Rt_predicted_30d=rec.Rt_predicted_30d,
        cost_J=rec.cost_J,
        converged=bool(rec.converged),
        rationale=rec.rationale,
        interpretation=interpretation
    )

@router.get("/weights/{region_id}", response_model=ControlWeightsOut)
async def get_control_weights(region_id: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ControlWeights).where(ControlWeights.region_id == region_id))
    weights = result.scalar_one_or_none()
    if not weights:
        raise HTTPException(status_code=404, detail="Control weights not set for this region")
    return weights

@router.put("/weights/{region_id}", response_model=ControlWeightsOut)
async def update_control_weights(region_id: str, weights_in: ControlWeightsIn, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(ControlWeights).where(ControlWeights.region_id == region_id))
    weights = result.scalar_one_or_none()
    
    if not weights:
        weights = ControlWeights(region_id=region_id, updated_by=UUID("00000000-0000-0000-0000-000000000000"), **weights_in.model_dump())
        db.add(weights)
    else:
        for field, value in weights_in.model_dump().items():
            setattr(weights, field, value)
            
    await db.commit()
    await db.refresh(weights)
    
    # Trigger re-solve immediately
    solve_optimal_control.delay(region_id)
    
    return weights
