import json

import redis.asyncio as aioredis
from fastapi import APIRouter, HTTPException, Request
from src.db.models import EpiParams  # noqa: F401  (kept for parity)

router = APIRouter()


@router.get("/api/v1/regions/{id}/state")
async def get_region_state(id: str, request: Request):
    """Retrieves the last filtered state from Redis"""
    key = f"filter_state:{id}"
    redis_client: aioredis.Redis = request.app.state.redis
    data = await redis_client.get(key)
    if not data:
        raise HTTPException(status_code=404, detail="Filter state not found for region")

    state_data = json.loads(data)
    # Map vector back to named fields
    x = state_data['x']
    P = state_data['P']
    keys = ['S', 'E', 'IA', 'IM', 'IS', 'H', 'ICU', 'R', 'D']

    return {
        "region_id": id,
        "timestamp": state_data.get('updated_at'),
        "filter_type": state_data.get('meta', {}).get('mode', 'unknown'),
        "state": {k: x[i] for i, k in enumerate(keys)},
        "state_variance": {k: P[i][i] for i, k in enumerate(keys)},
        "observation_params": {"papp": x[9], "ptest": x[10], "kappa": x[11]},
        "cusum_score": state_data.get('meta', {}).get('cusum', 0.0),
        "model_alert": state_data.get('meta', {}).get('cusum', 0.0) > 5.0,
    }
