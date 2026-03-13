from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import List, Dict, Any
import numpy as np
import uuid
from src.federated.aggregator import FedAvgAggregator

router = APIRouter()

# Global aggregator instance for now (in-memory)
# In production, this would be backed by Redis and persistent storage
aggregator = FedAvgAggregator(model_dim=10, min_clients=3)

class GradientUploadRequest(BaseModel):
    round_id: int
    gradient: List[float]
    n_samples: int
    user_id: str

from src.auth import get_current_user

@router.post("/upload_gradient")
async def upload_gradient(
    req: GradientUploadRequest, 
    request: Request,
    user: dict[str, Any] = Depends(get_current_user)
):
    # 1. Validate round (hardcoded active round for now)
    if req.round_id != 1:
        raise HTTPException(status_code=400, detail="Round not active")

    # 2. Check and consume budget 
    budget_tracker = request.app.state.budget_tracker
    user_id = user.get("sub")
    
    # Each gradient upload consumes a fixed amount of epsilon (e.g., 0.1)
    epsilon_per_upload = 0.1 
    success = await budget_tracker.consume(user_id, epsilon_per_upload)
    if not success:
        raise HTTPException(status_code=403, detail="Privacy budget exceeded for this round")
    
    # 3. Receive gradient
    try:
        aggregator.receive_gradient(np.array(req.gradient))
    except ValueError as e:
        # Rollback budget? In a production system, we'd use a transaction or more complex state.
        raise HTTPException(status_code=422, detail=str(e))

    return {
        "accepted": True,
        "round_id": req.round_id,
        "gradients_received": len(aggregator.current_round_gradients),
        "budget_remaining": await budget_tracker.get_remaining(user_id)
    }

@router.get("/model/{round_id}")
async def get_model(round_id: int):
    # Mock global model params
    return {
        "round_id": round_id,
        "params": [0.0] * 10,
        "version": "1.0"
    }

@router.post("/trigger_aggregation")
async def trigger_aggregation():
    """
    Manually trigger the FedAvg aggregation for the current round.
    """
    if not aggregator.current_round_gradients:
        raise HTTPException(status_code=400, detail="No gradients received yet")
        
    result = aggregator.aggregate(C=1.0, epsilon=0.5)
    aggregator.start_new_round() # Reset for next
    
    return {
        "status": "aggregated",
        "new_update": result.tolist()
    }
