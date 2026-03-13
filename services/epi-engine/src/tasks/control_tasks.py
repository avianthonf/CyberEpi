import asyncio
import json
import numpy as np
import structlog
from datetime import datetime
from sqlalchemy import select
from .celery_app import celery_app
from ..db.connection import AsyncSessionLocal
from ..db.models import EpiParams, ControlWeights, ControlRecommendation
from ..control.fb_sweep import forward_backward_sweep
from ..config import settings

logger = structlog.get_logger()

@celery_app.task(name="tasks.solve_optimal_control")
def solve_optimal_control(region_id: str):
    """Celery task to solve optimal control for a region."""
    # Since Celery is synchronous, we use a wrapper for async DB calls
    return asyncio.run(async_solve_optimal_control(region_id))

async def async_solve_optimal_control(region_id: str):
    logger.info("solving_optimal_control_start", region_id=region_id)
    
    async with AsyncSessionLocal() as db:
        # 1. Load current params
        result = await db.execute(select(EpiParams).where(EpiParams.region_id == region_id))
        params_row = result.scalar_one_or_none()
        if not params_row:
            logger.error("region_params_not_found", region_id=region_id)
            return
        
        # Convert row to dict
        params_dict = {c.name: getattr(params_row, c.name) for c in params_row.__table__.columns}
        params_dict['eta'] = 0.3 # Mask efficacy
        
        # 2. Load control weights
        result = await db.execute(select(ControlWeights).where(ControlWeights.region_id == region_id))
        weights_row = result.scalar_one_or_none()
        if not weights_row:
            # Create default weights if missing
            weights_row = ControlWeights(region_id=region_id, updated_by=params_row.id) # Placeholder ID
            db.add(weights_row)
            await db.commit()
            await db.refresh(weights_row)
            
        C1, C2, C3, C4 = weights_row.C1, weights_row.C2, weights_row.C3, weights_row.C4
        W = np.diag([weights_row.W_u1, weights_row.W_u2, weights_row.W_u3])
        
        # 3. Get latest state (x0)
        # For simplicity, we'll assume x0 is the last state from the EKF/SMC
        # In a real app, this would be fetched from Redis filter_state:{region_id}
        # Placeholder x0:
        x0 = np.array([params_dict['N_pop'] * 0.9, params_dict['N_pop'] * 0.05, 100, 50, 10, 5, 0, 0])
        
        # 4. Run FB Sweep
        T = 30.0 # 30 day horizon
        result_sweep = forward_backward_sweep(x0, T, params_dict, C1, C2, C3, W)
        
        # 5. Store Recommendation
        # Calculate Rt_current (placeholder or from actual data)
        Rt_current = 1.2 # Placeholder
        
        # Rt_predicted_30d: from x trajectory
        # Rt ~= (beta * S / N) / gamma
        S_end = result_sweep.x[0, -1]
        Rt_predicted = (params_dict['beta'] * S_end / params_dict['N_pop']) / params_dict['gamma']
        
        recommendation = ControlRecommendation(
            region_id=region_id,
            weights_id=weights_row.id,
            generated_at=datetime.utcnow(),
            u1_recommended=float(np.mean(result_sweep.u[0, :])),
            u2_recommended=float(np.mean(result_sweep.u[1, :])),
            u3_recommended=float(np.mean(result_sweep.u[2, :])),
            Rt_current=Rt_current,
            Rt_predicted_30d=float(Rt_predicted),
            cost_J=result_sweep.final_cost,
            converged=1 if result_sweep.converged else 0,
            trajectory={
                "t": result_sweep.t.tolist(),
                "x": result_sweep.x.tolist(),
                "u": result_sweep.u.tolist()
            },
            rationale=f"Optimal control recommendation for {region_id} based on {weights_row.ethical_framework} framework."
        )
        db.add(recommendation)
        await db.commit()
        
        # 6. Publish to Kafka (Placeholder for actual Kafka producer call)
        logger.info("recommendation_published", region_id=region_id, cost=result_sweep.final_cost)
        
    return {"status": "success", "region_id": region_id}
