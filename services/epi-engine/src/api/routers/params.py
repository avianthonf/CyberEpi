from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.auth import get_current_user, require_role
from src.db.connection import get_db
from src.db.models import EpiParams
from src.models.parameters import RegionParams
from src.tasks.celery_app import run_forecast_async

router = APIRouter()

@router.get("/{id}/params", response_model=RegionParams)
async def get_region_params(
    id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any] = Depends(get_current_user),
):
    result = await db.execute(select(EpiParams).where(EpiParams.region_id == id))
    params = result.scalar_one_or_none()
    if not params:
        raise HTTPException(status_code=404, detail="Region not found")
    return params

@router.put("/{id}/params")
async def update_region_params(
    id: str,
    params_in: RegionParams,
    db: AsyncSession = Depends(get_db),
    _user: dict[str, Any] = Depends(require_role("admin")),
):
    # JWT Auth check (Authority role) is now enforced by require_role("admin")
    # For now, just update the DB
    result = await db.execute(select(EpiParams).where(EpiParams.region_id == id))
    params = result.scalar_one_or_none()
    if not params:
        params = EpiParams(region_id=id, **params_in.model_dump())
        db.add(params)
    else:
        for field, value in params_in.model_dump().items():
            setattr(params, field, value)
    
    await db.commit()
    
    # Trigger re-forecast for 7, 14, and 21 days
    for horizon in [7, 14, 21]:
        run_forecast_async.delay(id, horizon)
        
    return {"status": "updated", "region_id": id}
