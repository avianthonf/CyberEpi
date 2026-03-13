import json
import hashlib
from datetime import datetime
from sqlalchemy import select
from .celery_app import celery_app
from ..db.connection import AsyncSessionLocal
from ..db.models import EpiParams, ForecastCache
from ..config import settings
from seir_core import run_seir, SEIRParams, compute_Rt
import numpy as np
import asyncio
from aiokafka import AIOKafkaProducer

async def _run_forecast_logic(region_id: str, horizon_days: int):
    async with AsyncSessionLocal() as db:
        # 1. Load params
        result = await db.execute(select(EpiParams).where(EpiParams.region_id == region_id))
        db_params = result.scalar_one_or_none()
        if not db_params:
            return

        params = SEIRParams(
            beta=db_params.beta, sigma=db_params.sigma, gamma=db_params.gamma,
            rho=db_params.rho, fA=db_params.fA, fM=db_params.fM, fS=db_params.fS,
            alpha=db_params.alpha, h_rate=db_params.h_rate, delta=db_params.delta,
            mu=db_params.mu, mu_icu=db_params.mu_icu, gamma_A=db_params.gamma_A,
            gamma_M=db_params.gamma_M, gamma_S=db_params.gamma_S, gamma_H=db_params.gamma_H,
            gamma_ICU=db_params.gamma_ICU, papp=db_params.papp, N_pop=db_params.N_pop
        )

        # Determinstic Hash (matching API)
        param_dict = {
            k: v for k, v in db_params.__dict__.items() 
            if not k.startswith('_') and k not in ['id', 'updated_at', 'source']
        }
        params_hash = hashlib.sha256(json.dumps(param_dict, sort_keys=True).encode()).hexdigest()

        # 2. Run solver
        y0 = np.array([params.N_pop - 10, 10, 0, 0, 0, 0, 0, 0, 0])
        t_span = (0, horizon_days)
        t_eval = np.linspace(0, horizon_days, int(horizon_days) + 1)
        
        sol = run_seir(y0, t_span, t_eval, params)
        
        # BRUTAL AUDIT: Mass Conservation
        # Expected N = params.N_pop. Actual N = sum(y[:, -1])
        final_state = sol.y[:, -1]
        total_pop = np.sum(final_state)
        mass_error = abs(total_pop - params.N_pop)
        if mass_error > 1e-3: # Tolerance for numerical drift
            print(f"CRITICAL: Mass conservation failed for {region_id}. Error: {mass_error}")
            # In a strict environment, we might raise or log heavily
        
        # 3. Store in DB
        trajectory = {
            "t": sol.t.tolist(),
            "S": sol.y[0].tolist(),
            "E": sol.y[1].tolist(),
            "IA": sol.y[2].tolist(),
            "IM": sol.y[3].tolist(),
            "IS": sol.y[4].tolist(),
            "H": sol.y[5].tolist(),
            "ICU": sol.y[6].tolist(),
            "R": sol.y[7].tolist(),
            "D": sol.y[8].tolist(),
            "Load": (sol.y[5] + sol.y[6]).tolist()
        }
        
        cache_entry = ForecastCache(
            region_id=region_id,
            horizon_days=horizon_days,
            trajectory=trajectory,
            params_hash=params_hash,
            generated_at=datetime.utcnow()
        )
        db.add(cache_entry)
        await db.commit()

        # 4. Update Redis Cache (shared with API)
        from ..main import app # Simplified for demo, in real app use a shared redis client
        # In a background task, we reach out to redis directly
        import redis.asyncio as aioredis
        redis_client = aioredis.from_url(settings.redis_url)
        cache_key = f"forecast:{region_id}:{horizon_days}:{params_hash}"
        from ..models.parameters import ForecastResponse
        resp_data = ForecastResponse(
            region_id=region_id,
            generated_at=cache_entry.generated_at,
            horizon_days=horizon_days,
            trajectory=trajectory,
            params_hash=params_hash
        ).model_dump_json()
        await redis_client.setex(cache_key, 3600, resp_data)
        await redis_client.close()

        # 5. Kafka emission
        producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
        await producer.start()
        try:
            rt = compute_Rt(params, sol.y[0, -1], params.N_pop)
            update = {
                "region_id": region_id,
                "timestamp": datetime.utcnow().isoformat(),
                "beta": params.beta,
                "Rt": rt,
                "forecast_hash": params_hash
            }
            await producer.send_and_wait(settings.kafka_topic_updates, json.dumps(update).encode())
        finally:
            await producer.stop()

@celery_app.task
def run_forecast_async(region_id: str, horizon_days: int):
    asyncio.run(_run_forecast_logic(region_id, horizon_days))

@celery_app.task
def recompute_all_regions():
    # Implementation for periodic sweep
    pass
