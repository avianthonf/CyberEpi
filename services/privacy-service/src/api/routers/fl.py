from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from src.auth import get_current_user
from src.config import settings
from src.federated.aggregator import FedAvgAggregator

router = APIRouter()

# Global aggregator instance for now (in-memory)
# In production, this would be backed by Redis and persistent storage
aggregator = FedAvgAggregator(model_dim=10, min_clients=settings.fl_min_clients)


class GradientUploadRequest(BaseModel):
    round_id: int
    gradient: list[float]
    n_samples: int
    user_id: str


@router.post("/upload_gradient")
async def upload_gradient(
    req: GradientUploadRequest,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user)
):
    # 1. Validate round (single active round for now)
    if req.round_id != 1:
        raise HTTPException(status_code=400, detail="Round not active")

    # 2. Validate the gradient BEFORE charging budget so rejected
    #    uploads do not consume the user's privacy budget.
    #    (pure check — no aggregation state is mutated here)
    try:
        aggregator.validate_gradient(np.array(req.gradient))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # 3. Reject duplicate submissions: one gradient per client per round.
    #    Keyed on the declared FL client id (an account may operate several
    #    clients). Checked BEFORE consuming budget so a rejected retry is free.
    if aggregator.has_submitted(req.user_id):
        raise HTTPException(
            status_code=409,
            detail="Gradient already submitted for this round",
        )

    # 4. Check and consume budget
    budget_tracker = request.app.state.budget_tracker
    user_id = user.get("sub")
    epsilon_per_upload = 0.1
    success = await budget_tracker.consume(user_id, epsilon_per_upload)
    if not success:
        raise HTTPException(status_code=403, detail="Privacy budget exceeded for this round")

    # 5. Append only after budget success. Appending late avoids a
    #    concurrency hazard where a budget-rejected uploader would have to
    #    pop() its gradient out from under concurrent accepted uploads.
    aggregator.receive_gradient(np.array(req.gradient), client_id=req.user_id)

    return {
        "accepted": True,
        "round_id": req.round_id,
        "gradients_received": len(aggregator.current_round_gradients),
        "budget_remaining": await budget_tracker.get_remaining(user_id),
    }


@router.get("/model/{round_id}")
async def get_model(round_id: int, user: dict[str, Any] = Depends(get_current_user)):
    """Return the current global model for a round, if one exists."""
    if round_id != 1 or aggregator.global_model is None:
        raise HTTPException(status_code=404, detail="No model available for this round")
    return {
        "round_id": round_id,
        "params": aggregator.global_model.tolist(),
        "version": "1.0",
    }


@router.post("/trigger_aggregation")
async def trigger_aggregation(user: dict[str, Any] = Depends(get_current_user)):
    """
    Manually trigger the FedAvg aggregation for the current round.
    Staff-only: uncontrolled triggering would starve rounds of updates.
    """
    roles = user.get("realm_access", {}).get("roles", [])
    if "physician" not in roles and "admin" not in roles:
        raise HTTPException(
            status_code=403,
            detail="Access denied: only physicians or admins can trigger aggregation.",
        )

    if not aggregator.current_round_gradients:
        raise HTTPException(status_code=400, detail="No gradients received yet")

    try:
        result = aggregator.aggregate(C=1.0, epsilon=0.5)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    aggregator.start_new_round()  # Reset for next

    return {
        "status": "aggregated",
        "new_update": result.tolist(),
    }
