from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import get_current_user
from src.db.connection import get_db
from src.db.models import ControlRecommendation, ControlWeights
from src.tasks.control_tasks import async_solve_optimal_control, solve_optimal_control

router = APIRouter(prefix="/api/v1/control", tags=["control"])

class ControlWeightsIn(BaseModel):
    C1: float = Field(1.0, gt=0, le=1_000_000)
    C2: float = Field(5.0, gt=0, le=1_000_000)
    C3: float = Field(2.0, gt=0, le=1_000_000)
    C4: float = Field(10.0, gt=0, le=1_000_000)
    W_u1: float = Field(1.0, gt=0, le=1_000_000)
    W_u2: float = Field(0.5, gt=0, le=1_000_000)
    W_u3: float = Field(0.8, gt=0, le=1_000_000)
    ethical_framework: str = Field("utilitarian", min_length=1, max_length=100)
    notes: str | None = Field(None, max_length=1000)

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
async def get_latest_recommendation(
    region_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
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
async def get_control_weights(
    region_id: str,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    result = await db.execute(select(ControlWeights).where(ControlWeights.region_id == region_id))
    weights = result.scalar_one_or_none()
    if not weights:
        raise HTTPException(status_code=404, detail="Control weights not set for this region")
    return weights

@router.put("/weights/{region_id}", response_model=ControlWeightsOut)
@router.post("/weights/{region_id}", response_model=ControlWeightsOut)
async def update_control_weights(
    region_id: str,
    weights_in: ControlWeightsIn,
    db: AsyncSession = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    # Control weights shape the public-health cost function: staff only.
    roles = user.get("realm_access", {}).get("roles", [])
    if "physician" not in roles and "admin" not in roles:
        raise HTTPException(
            status_code=403,
            detail="Role 'physician' or 'admin' required to update control weights",
        )
    result = await db.execute(select(ControlWeights).where(ControlWeights.region_id == region_id))
    weights = result.scalar_one_or_none()
    updated_by = UUID(user.get("sub", "00000000-0000-0000-0000-000000000000"))

    if not weights:
        weights = ControlWeights(region_id=region_id, updated_by=updated_by, **weights_in.model_dump())
        db.add(weights)
    else:
        weights.updated_by = updated_by
        for field, value in weights_in.model_dump().items():
            setattr(weights, field, value)

    await db.commit()
    await db.refresh(weights)
    # Trigger re-solve. Inline mode awaits directly in the request loop;
    # Celery mode dispatches asynchronously.
    from src.config import settings
    if settings.run_forecast_inline:
        await async_solve_optimal_control(region_id, updated_by=str(updated_by))
    else:
        solve_optimal_control.delay(region_id, str(updated_by))

    return weights
