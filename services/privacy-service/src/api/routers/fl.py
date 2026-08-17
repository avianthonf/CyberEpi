from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from src.federated.aggregator import FedAvgAggregator

router = APIRouter()

# Global aggregator instance for now (in-memory)
# In production, this would be backed by Redis and persistent storage
aggregator = FedAvgAggregator(model_dim=10, min_clients=3)


class GradientUploadRequest(BaseModel):
    round_id: int
    gradient: list[float]
    n_samples: int
    user_id: str


from src.auth import get_current_user


@router.post("/upload_gradient")
async def upload_gradient(
    req: GradientUploadRequest,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user),
):
    # 1. Validate round (single active round for now)
    if req.round_id != 1:
        raise HTTPException(status_code=400, detail="Round not active")

    # 2. Validate the gradient BEFORE charging budget so rejected
    #    uploads do not consume the user's privacy budget.
    try:
        aggregator.receive_gradient(np.array(req.gradient))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    # 3. Check and consume budget
    budget_tracker = request.app.state.budget_tracker
    user_id = user.get("sub")

    epsilon_per_upload = 0.1
    success = await budget_tracker.consume(user_id, epsilon_per_upload)
    if not success:
        # Gradient was accepted but the user has no budget left — drop it.
        aggregator.current_round_gradients.pop()
        raise HTTPException(status_code=403, detail="Privacy budget exceeded for this round")

    return {
        "accepted": True,
        "round_id": req.round_id,
        "gradients_received": len(aggregator.current_round_gradients),
        "budget_remaining": await budget_tracker.get_remaining(user_id),
    }


@router.get("/model/{round_id}")
async def get_model(round_id: int):
    """Return the current global model for a round, if one exists."""
    if round_id != 1 or aggregator.global_model is None:
        raise HTTPException(status_code=404, detail="No model available for this round")
    return {
        "round_id": round_id,
        "params": aggregator.global_model.tolist(),
        "version": "1.0",
    }


@router.post("/trigger_aggregation")
async def trigger_aggregation():
    """
    Manually trigger the FedAvg aggregation for the current round.
    """
    if not aggregator.current_round_gradients:
        raise HTTPException(status_code=400, detail="No gradients received yet")

    try:
        result = aggregator.aggregate(C=1.0, epsilon=0.5)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    aggregator.start_new_round()  # Reset for next

    return {
        "status": "aggregated",
        "new_update": result.tolist(),
    }
