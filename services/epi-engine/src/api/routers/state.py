from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from src.db.connection import get_db
from src.db.models import EpiParams # Assuming we can load params from here
from src.filters.orchestrator import FilterOrchestrator
from src.config import settings
import redis
import json

router = APIRouter()

# Global redis client for simplicity, ideally from app state
redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)

@router.get("/api/v1/regions/{id}/state")
async def get_region_state(id: str):
    """Retrieves the last filtered state from Redis"""
    key = f"filter_state:{id}"
    data = redis_client.get(key)
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
        "model_alert": state_data.get('meta', {}).get('cusum', 0.0) > 5.0
    }
