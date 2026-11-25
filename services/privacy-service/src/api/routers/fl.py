from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from src.auth import get_current_user
from src.config import settings
from src.federated.aggregator import FedAvgAggregator

router = APIRouter()

# Global aggregator instance; session_maker injected during app startup
# and initialize_from_db() restores current_round_id from DB.
aggregator = FedAvgAggregator(model_dim=10, min_clients=settings.fl_min_clients)


class GradientUploadRequest(BaseModel):
    round_id: int
    gradient: list[float]
    n_samples: int
    user_id: str


@router.post("/upload_gradient")
async def upload_gradient(req: GradientUploadRequest, request: Request, user: dict[str, Any] = Depends(get_current_user)):
    # Round lifecycle lock prevents concurrent same-client duplicate uploads
    # and concurrent trigger/upload races that would cause phantom state.
    async with aggregator._round_lock:
        # 1. Validate round is the currently-active one (single in-flight round)
        if req.round_id != aggregator.current_round_id:
            raise HTTPException(
                status_code=400,
                detail=(f"Round not active: requested {req.round_id}, current active round is {aggregator.current_round_id}"),
            )

        # 2. Validate the gradient BEFORE charging budget so rejected
        # uploads do not consume the user's privacy budget.
        try:
            gradient = np.array(req.gradient)
            aggregator.validate_gradient(gradient)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=f"Invalid gradient: {e!s}") from e

        # 3. Use keycloak user_id from JWT, not request body
        user_id = user.get("sub")

        # 4. Reject duplicate uploads from the same client
        if aggregator.has_submitted(user_id):
            raise HTTPException(
                status_code=409,
                detail="Gradient already submitted for this round",
            )

        # 5. Check and consume budget
        budget_tracker = request.app.state.budget_tracker
        epsilon_per_upload = 0.1
        success = await budget_tracker.consume(user_id, epsilon_per_upload)
        if not success:
            raise HTTPException(status_code=403, detail="Privacy budget exceeded for this round")

        # 6. Append only after budget success. Appending late avoids a
        # concurrency hazard where a budget-rejected uploader would have to
        # pop() its gradient out from under concurrent accepted uploads.
        aggregator.receive_gradient(gradient, client_id=user_id)

        return {
            "accepted": True,
            "round_id": req.round_id,
            "gradients_received": len(aggregator.current_round_gradients),
            "budget_remaining": await budget_tracker.get_remaining(user_id),
        }


@router.get("/model/{round_id}")
async def get_model(round_id: int, user: dict[str, Any] = Depends(get_current_user)):
    """Return the aggregated update for a completed round, if one exists."""
    cached = await aggregator.get_completed_model(round_id)
    if cached is None:
        raise HTTPException(
            status_code=404,
            detail=f"No model available for round {round_id}",
        )
    return {
        "round_id": round_id,
        "params": cached.tolist(),
        "version": f"round-{round_id}",
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

    # Lock prevents concurrent triggers from committing same round twice
    async with aggregator._round_lock:
        num_clients = len(aggregator.current_round_gradients)
        if num_clients == 0:
            raise HTTPException(status_code=400, detail="No gradients received yet")
        if aggregator.min_clients > num_clients:
            raise HTTPException(
                status_code=400,
                detail=(f"Not enough gradients to aggregate: {num_clients} < min_clients {aggregator.min_clients}"),
            )

        try:
            result = await aggregator.aggregate(C=1.0, epsilon=0.5)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        # Round is now complete and persisted to DB. Advance to next round.
        completed_round_id = aggregator.current_round_id
        aggregator.start_new_round()

        return {
            "status": "aggregated",
            "round_id": completed_round_id,
            "num_clients": num_clients,
            "new_update": result.tolist(),
        }


@router.get("/status")
async def fl_status(_user: dict[str, Any] = Depends(get_current_user)):
    """Inspect current aggregator state (handy for clients/tests)."""
    # Query DB for all completed rounds to survive restarts
    completed_rounds = []
    if aggregator.session_maker is not None:
        from sqlalchemy import select

        from src.db.models import FLRound

        async with aggregator.session_maker() as session:
            result = await session.execute(select(FLRound.round_id).order_by(FLRound.round_id))
            completed_rounds = [r for r in result.scalars().all()]

    return {
        "current_round_id": aggregator.current_round_id,
        "gradients_received": len(aggregator.current_round_gradients),
        "min_clients": aggregator.min_clients,
        "completed_rounds": completed_rounds,
    }
