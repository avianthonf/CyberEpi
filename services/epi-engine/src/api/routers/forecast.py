import contextlib
import hashlib
import json
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import get_current_user
from src.db.connection import get_db
from src.db.models import EpiParams, ForecastCache
from src.models.parameters import ForecastResponse
from src.tasks.celery_app import _forecast_task, _run_forecast_logic

router = APIRouter()


async def _cache_get(redis: aioredis.Redis, key: str) -> Any:
    """Best-effort cache read: Redis outage must not fail the request."""
    try:
        return await redis.get(key)
    except aioredis.RedisError:
        return None


async def _cache_set(redis: aioredis.Redis, key: str, ttl: int, value: str) -> None:
    with contextlib.suppress(aioredis.RedisError):
        await redis.setex(key, ttl, value)


@router.get("/{id}/forecast", response_model=ForecastResponse)
async def get_region_forecast(
    id: str,
    # Unbounded horizons are a compute-DoS vector: integration cost scales
    # linearly with horizon. Public-health uses need at most ~6 weeks.
    horizon_days: int = Query(default=14, ge=1, le=42),
    db: AsyncSession = Depends(get_db),
    request: Request = None,
    user: dict[str, Any] = Depends(get_current_user),
):
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

    cached = await _cache_get(redis, cache_key)
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
        await _cache_set(redis, cache_key, 3600, resp_data)
        return json.loads(resp_data)

    # 4. Run the forecast. Inline mode awaits directly in the request loop
    # (no Celery worker required). Celery mode dispatches and returns 202.
    from src.config import settings
    if settings.run_forecast_inline:
        await _run_forecast_logic(id, horizon_days)
    else:
        _forecast_task.delay(id, horizon_days)

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
        await _cache_set(redis, cache_key, 3600, resp_data)
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
