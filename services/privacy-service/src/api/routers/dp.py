import math
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator

from src.auth import get_current_user
from src.dp.mechanisms import (
    gaussian_mechanism,
    laplace_mechanism,
    laplace_mechanism_array,
)
from src.dp.sensitivity import (
    aggregate_count_sensitivity,
    hotspot_count_sensitivity,
    regional_rt_sensitivity,
)

router = APIRouter()

class DPPublishRequest(BaseModel):
    stat_type: str = Field(..., max_length=20)
    value: float | list[float]
    region_id: str = Field(..., max_length=50)
    epsilon: float = Field(default=1.0, gt=0, le=100)

    @field_validator("value")
    @classmethod
    def _value_finite(cls, v: float | list[float]) -> float | list[float]:
        vals = v if isinstance(v, list) else [v]
        if not all(math.isfinite(x) for x in vals):
            raise ValueError("value must be finite (no NaN or inf)")
        return v

    @field_validator("epsilon")
    @classmethod
    def _epsilon_finite_positive(cls, v: float) -> float:
        if not math.isfinite(v) or v <= 0:
            raise ValueError("epsilon must be a positive finite number")
        return v

class GaussianRequest(BaseModel):
    value: float
    sensitivity: float = Field(gt=0, le=1e6)
    epsilon: float = Field(gt=0, le=100)
    delta: float = Field(gt=0, lt=1, default=1e-5)

    @field_validator("value", "sensitivity", "epsilon", "delta")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("value must be finite (no NaN or inf)")
        return v


@router.post("/publish")
async def dp_publish(
    req: DPPublishRequest,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user)
):
    budget_tracker = request.app.state.budget_tracker
    user_id = user.get("sub")

    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")

    # Compute sensitivity based on stat type
    if req.stat_type == 'Rt':
        sensitivity = regional_rt_sensitivity()
    elif req.stat_type == 'hotspot_count':
        sensitivity = hotspot_count_sensitivity()
    else:
        sensitivity = aggregate_count_sensitivity()

    # Compute the noised value FIRST (so we can log it in audit trail)
    try:
        if isinstance(req.value, list):
            noised = laplace_mechanism_array(req.value, sensitivity, req.epsilon).tolist()
        else:
            noised = laplace_mechanism(req.value, sensitivity, req.epsilon)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    # Atomically consume budget (Postgres-backed with Redis cache)
    success = await budget_tracker.consume(
        user_id=user_id,
        epsilon=req.epsilon,
        mechanism='laplace',
        sensitivity=sensitivity,
        query_type=req.stat_type,
        noised_value=float(noised) if isinstance(noised, (int, float)) else None,
        metadata={'region_id': req.region_id}
    )
    if not success:
        remaining = await budget_tracker.get_remaining(user_id)
        raise HTTPException(
            status_code=403,
            detail=f"Privacy budget exceeded. Remaining: {remaining:.4f}"
        )

    return {
        "noised_value": noised,
        "epsilon_used": req.epsilon,
        "sensitivity": sensitivity,
        "budget_remaining": await budget_tracker.get_remaining(user_id)
    }
@router.post("/gaussian")
async def dp_gaussian(
    req: GaussianRequest,
    _user: dict[str, Any] = Depends(get_current_user),
):
    try:
        noised = gaussian_mechanism(req.value, req.sensitivity, req.epsilon, req.delta)
        return {"noised_value": noised}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
