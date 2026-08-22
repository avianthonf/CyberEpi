from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import get_current_user
from src.db.connection import get_db
from src.db.models import EpiParams
from src.models.parameters import RegionParams
from src.tasks.celery_app import _forecast_task, _run_forecast_logic

router = APIRouter()


@router.get("/{id}/params", response_model=RegionParams)
async def get_region_params(
    id: str,
    db: AsyncSession = Depends(get_db),
):
    """Public read of region parameters — used by the patient app to display
    the SEIR model used for its region. There is no sensitive data here."""
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
    user: dict[str, Any] = Depends(get_current_user),
):
    """Update region parameters. Only physicians or admins may do this."""
    roles = user.get("realm_access", {}).get("roles", [])
    if not any(r in roles for r in ("physician", "admin")):
        raise HTTPException(
            status_code=403,
            detail="Role 'physician' or 'admin' required to update region parameters",
        )
    result = await db.execute(select(EpiParams).where(EpiParams.region_id == id))
    params = result.scalar_one_or_none()
    payload = params_in.model_dump(exclude={"region_id", "updated_at"}, exclude_none=True)
    if params is None:
        params = EpiParams(region_id=id, **payload)
        db.add(params)
    else:
        for field, value in payload.items():
            setattr(params, field, value)

    await db.commit()

    # Trigger re-forecast for 7, 14, and 21 days. Inline mode awaits
    # directly in the request loop; Celery mode dispatches asynchronously.
    from src.config import settings

    for horizon in [7, 14, 21]:
        if settings.run_forecast_inline:
            await _run_forecast_logic(id, horizon)
        else:
            _forecast_task.delay(id, horizon)

    return {"status": "updated", "region_id": id}
