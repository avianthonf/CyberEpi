from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from typing import List, Union, Any
from src.dp.mechanisms import laplace_mechanism, laplace_mechanism_array
from src.dp.sensitivity import regional_rt_sensitivity, hotspot_count_sensitivity, aggregate_count_sensitivity

router = APIRouter()

class DPPublishRequest(BaseModel):
    stat_type: str # 'Rt', 'hotspot_count', 'aggregate'
    value: Union[float, List[float]]
    region_id: str
    epsilon: float = 1.0

from src.auth import get_current_user
from typing import Any

@router.post("/publish")
async def dp_publish(
    req: DPPublishRequest,
    request: Request,
    user: dict[str, Any] = Depends(get_current_user)
):
    budget_tracker = request.app.state.budget_tracker
    user_id = user.get("sub")
    
    if not user_id:
        raise HTTPException(status_code=401, detail="User ID not found in token")

    # Check and consume budget
    success = await budget_tracker.consume(user_id, req.epsilon)
    if not success:
        remaining = await budget_tracker.get_remaining(user_id)
        raise HTTPException(
            status_code=403, 
            detail=f"Privacy budget exceeded. Remaining: {remaining:.4f}"
        )

    if req.stat_type == 'Rt':
        sensitivity = regional_rt_sensitivity()
    elif req.stat_type == 'hotspot_count':
        sensitivity = hotspot_count_sensitivity()
    else:
        sensitivity = aggregate_count_sensitivity()

    if isinstance(req.value, list):
        noised = laplace_mechanism_array(req.value, sensitivity, req.epsilon).tolist()
    else:
        noised = laplace_mechanism(req.value, sensitivity, req.epsilon)

    return {
        "noised_value": noised,
        "epsilon_used": req.epsilon,
        "sensitivity": sensitivity,
        "budget_remaining": await budget_tracker.get_remaining(user_id)
    }
