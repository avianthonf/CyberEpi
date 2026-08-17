"""Celery task definitions for epi-engine.

`run_forecast_async` and `solve_optimal_control` are real Celery tasks. When
`settings.run_forecast_inline` is true (no worker configured), `run_forecast_async`
executes the forecast logic synchronously in the API process instead of
dispatching to a broker — this keeps the forecast feature working out of the box.
"""

import asyncio
import hashlib
import json
from datetime import datetime

import numpy as np
from celery import Celery
from seir_core import SEIRParams, compute_Rt, run_seir
from sqlalchemy import select

from ..config import settings
from ..db.connection import AsyncSessionLocal
from ..db.models import EpiParams, ForecastCache

celery_app = Celery(
    "tasks",
    broker="redis://localhost:6379/1",
    backend="redis://localhost:6379/1",
)


def _params_hash(db_params) -> str:
    """Deterministic hash of model parameters — matches the API cache key."""
    param_dict = {
        k: v for k, v in db_params.__dict__.items()
        if not k.startswith("_") and k not in ["id", "updated_at", "source"]
    }
    return hashlib.sha256(json.dumps(param_dict, sort_keys=True).encode()).hexdigest()


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
            gamma_ICU=db_params.gamma_ICU, papp=db_params.papp, N_pop=db_params.N_pop,
        )

        params_hash = _params_hash(db_params)

        # 2. Run solver
        y0 = np.array([params.N_pop - 10, 10, 0, 0, 0, 0, 0, 0, 0])
        t_span = (0, horizon_days)
        t_eval = np.linspace(0, horizon_days, int(horizon_days) + 1)

        sol = run_seir(y0, t_span, t_eval, params)

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
            "Load": (sol.y[5] + sol.y[6]).tolist(),
        }

        cache_entry = ForecastCache(
            region_id=region_id,
            horizon_days=horizon_days,
            trajectory=trajectory,
            params_hash=params_hash,
            generated_at=datetime.utcnow(),
        )
        db.add(cache_entry)
        await db.commit()

        # 4. Update Redis cache (shared with API)
        import redis.asyncio as aioredis

        redis_client = aioredis.from_url(settings.redis_url)
        cache_key = f"forecast:{region_id}:{horizon_days}:{params_hash}"
        from ..models.parameters import ForecastResponse

        resp_data = ForecastResponse(
            region_id=region_id,
            generated_at=cache_entry.generated_at,
            horizon_days=horizon_days,
            trajectory=trajectory,
            params_hash=params_hash,
        ).model_dump_json()
        await redis_client.setex(cache_key, 3600, resp_data)
        await redis_client.aclose()

        # 5. Kafka emission
        from aiokafka import AIOKafkaProducer

        producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
        await producer.start()
        try:
            rt = compute_Rt(params, sol.y[0, -1], params.N_pop)
            update = {
                "region_id": region_id,
                "timestamp": datetime.utcnow().isoformat(),
                "beta": params.beta,
                "Rt": rt,
                "forecast_hash": params_hash,
            }
            await producer.send_and_wait(settings.kafka_topic_updates, json.dumps(update).encode())
        finally:
            await producer.stop()


def run_forecast_async(region_id: str, horizon_days: int):
    """Run a forecast. Inline when no Celery worker is configured, else dispatch."""
    if settings.run_forecast_inline:
        asyncio.run(_run_forecast_logic(region_id, horizon_days))
    else:
        # Celery dispatch — this function is wrapped as a task below.
        _forecast_task.delay(region_id, horizon_days)


@celery_app.task
def _forecast_task(region_id: str, horizon_days: int):
    asyncio.run(_run_forecast_logic(region_id, horizon_days))
