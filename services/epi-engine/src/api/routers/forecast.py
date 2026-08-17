import hashlib
import json

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.connection import get_db
from src.db.models import EpiParams, ForecastCache
from src.models.parameters import ForecastResponse
from src.tasks.celery_app import run_forecast_async

router = APIRouter()


@router.get("/{id}/forecast", response_model=ForecastResponse)
async def get_region_forecast(id: str, horizon_days: int = 14, db: AsyncSession = Depends(get_db), request: Request = None):
    # 1. Get current params to compute hash
    result = await db.execute(select(EpiParams).where(EpiParams.region_id == id))
    epi_params = result.scalar_one_or_none()
    if not epi_params:
        raise HTTPException(status_code=404, detail="Region parameters not found")

    # Deterministic hash of parameters
    param_dict = {
        k: v for k, v in epi_params.__dict__.items()
        if not k.startswith('_') and k not in ['id', 'updated_at', 'source']
    }
    params_hash = hashlib.sha256(json.dumps(param_dict, sort_keys=True).encode()).hexdigest()

    # 2. Check Redis cache
    redis = request.app.state.redis
    cache_key = f"forecast:{id}:{horizon_days}:{params_hash}"

    cached = await redis.get(cache_key)
    if cached:
        return json.loads(cached)

    # 3. Check DB cache
    db_cache_result = await db.execute(
        select(ForecastCache).where(
            ForecastCache.region_id == id,
            ForecastCache.horizon_days == horizon_days,
            ForecastCache.params_hash == params_hash
        )
    )
    db_cache = db_cache_result.scalar_one_or_none()
    if db_cache:
        # Populate Redis for next time
        resp_data = ForecastResponse(
            region_id=id,
            generated_at=db_cache.generated_at,
            horizon_days=horizon_days,
            trajectory=db_cache.trajectory,
            params_hash=params_hash
        ).model_dump_json()
        await redis.setex(cache_key, 3600, resp_data)
        return json.loads(resp_data)

    # 4. Trigger forecast (inline by default; Celery dispatch when configured)
    run_forecast_async(id, horizon_days)

    # Re-check the DB cache — the inline task writes it synchronously.
    db_cache_result = await db.execute(
        select(ForecastCache).where(
            ForecastCache.region_id == id,
            ForecastCache.horizon_days == horizon_days,
            ForecastCache.params_hash == params_hash
        )
    )
    db_cache = db_cache_result.scalar_one_or_none()
    if db_cache:
        resp_data = ForecastResponse(
            region_id=id,
            generated_at=db_cache.generated_at,
            horizon_days=horizon_days,
            trajectory=db_cache.trajectory,
            params_hash=params_hash
        ).model_dump_json()
        await redis.setex(cache_key, 3600, resp_data)
        return json.loads(resp_data)

    # Celery dispatch path: forecast is being generated asynchronously.
    raise HTTPException(
        status_code=202,
        detail={
            "message": "Forecast generation triggered",
            "region_id": id,
            "horizon_days": horizon_days,
        },
    )
