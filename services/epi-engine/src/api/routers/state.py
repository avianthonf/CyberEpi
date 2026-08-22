import json
from typing import Any

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, HTTPException, Request

from src.auth import get_current_user
from src.db.models import EpiParams  # noqa: F401  (kept for parity)

router = APIRouter()


@router.get("/api/v1/regions/{id}/state")
async def get_region_state(id: str, request: Request, user: dict[str, Any] = Depends(get_current_user)):
    """Retrieves the last filtered state from Redis"""
    key = f"filter_state:{id}"
    redis_client: aioredis.Redis = request.app.state.redis
    try:
        data = await redis_client.get(key)
    except aioredis.RedisError as exc:
        raise HTTPException(status_code=503, detail="State store unavailable") from exc
    if not data:
        raise HTTPException(status_code=404, detail="Filter state not found for region")

    state_data = json.loads(data)
    # State vector is 12-dim: [S, E, IA, IM, IS, H, ICU, R, D, papp, ptest, kappa]
    x = state_data.get('x') or [0.0] * 12
    P = state_data.get('P') or [[0.0] * 12] * 12
    keys = ['S', 'E', 'IA', 'IM', 'IS', 'H', 'ICU', 'R', 'D']
    meta = state_data.get('meta') or {}

    cusum = float(meta.get('cusum', 0.0))
    return {
        "region_id": id,
        "timestamp": state_data.get('updated_at'),
        "filter_type": meta.get('mode', 'unknown'),
        "state": {k: (x[i] if i < len(x) else 0.0) for i, k in enumerate(keys)},
        "state_variance": {k: (P[i][i] if i < len(P) and i < len(P[i]) else 0.0) for i, k in enumerate(keys)},
        "observation_params": {
            "papp": x[9] if len(x) > 9 else 0.0,
            "ptest": x[10] if len(x) > 10 else 0.0,
            "kappa": x[11] if len(x) > 11 else 0.0,
        },
        "cusum_score": cusum,
        "model_alert": cusum > 5.0,
    }
