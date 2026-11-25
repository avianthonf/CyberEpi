"""Celery task definitions for epi-engine.

`run_forecast_async` and `solve_optimal_control` are real Celery tasks. When
`settings.run_forecast_inline` is true (no worker configured), `run_forecast_async`
executes the forecast logic synchronously in the API process instead of
dispatching to a broker — this keeps the forecast feature working out of the box.
"""

import asyncio
import hashlib
import json
import logging
from datetime import UTC, datetime

import numpy as np
from celery import Celery
from seir_core import SEIRParams, compute_Rt, run_seir
from sqlalchemy import select

from ..config import settings
from ..db.models import EpiParams, ForecastCache

celery_app = Celery(
    "tasks",
    broker=settings.celery_url,
    backend=settings.celery_url,
)

_logger = logging.getLogger(__name__)

# Strong references to fire-and-forget loop tasks, so the GC cannot cancel
# an in-flight forecast; the done callback both releases the reference and
# logs failures instead of silently swallowing them.
_background_tasks: set = set()


def _task_done(task: "asyncio.Task") -> None:
    _background_tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        _logger.exception("Background forecast task failed", exc_info=exc)


def _params_hash(db_params) -> str:
    """Deterministic hash of model parameters — matches the API cache key."""
    param_dict = {
        k: v for k, v in db_params.__dict__.items() if not k.startswith("_") and k not in ["id", "updated_at", "source"]
    }
    return hashlib.sha256(json.dumps(param_dict, sort_keys=True).encode()).hexdigest()


async def _run_forecast_logic(region_id: str, horizon_days: int):
    # Resolve the session factory at call time: tests replace
    # src.db.connection.AsyncSessionLocal per test (per event loop).
    from ..db.connection import AsyncSessionLocal
    from ..filters.state_loader import load_state_snapshot
    import redis.asyncio as aioredis

    redis_client = None
    try:
        redis_client = aioredis.from_url(settings.redis_url)

        async with AsyncSessionLocal() as db:
            # 1. Load params
            result = await db.execute(select(EpiParams).where(EpiParams.region_id == region_id))
            db_params = result.scalar_one_or_none()
            if not db_params:
                return

            params = SEIRParams(
                beta=db_params.beta,
                sigma=db_params.sigma,
                gamma=db_params.gamma,
                rho=db_params.rho,
                fA=db_params.fA,
                fM=db_params.fM,
                fS=db_params.fS,
                alpha=db_params.alpha,
                h_rate=db_params.h_rate,
                delta=db_params.delta,
                mu=db_params.mu,
                mu_icu=db_params.mu_icu,
                gamma_A=db_params.gamma_A,
                gamma_M=db_params.gamma_M,
                gamma_S=db_params.gamma_S,
                gamma_H=db_params.gamma_H,
                gamma_ICU=db_params.gamma_ICU,
                papp=db_params.papp,
                N_pop=db_params.N_pop,
            )

            params_hash = _params_hash(db_params)

            # 2. Load state snapshot (DB-backed with Redis cache fallback)
            state_snapshot = await load_state_snapshot(region_id, redis_client, AsyncSessionLocal)

            _logger.info(
                "forecast_state_loaded",
                region_id=region_id,
                has_state=state_snapshot.has_state,
                version=state_snapshot.version,
            )

            # 3. Run solver with snapshot's initial condition
            y0 = state_snapshot.get_ode_initial_condition(params.N_pop)
            t_span = (0, horizon_days)
            t_eval = np.linspace(0, horizon_days, int(horizon_days) + 1)

            sol = run_seir(y0, t_span, t_eval, params)

            # 4. Store in DB with state version for cache invalidation
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
                state_version=state_snapshot.version,
                generated_at=datetime.now(UTC),
            )
            db.add(cache_entry)
            await db.commit()

            # 5. Update Redis cache with state version for invalidation
            from ..models.parameters import ForecastResponse

            cache_key = f"forecast:{region_id}:{horizon_days}:{params_hash}:{state_snapshot.version}"

            resp_data = ForecastResponse(
                region_id=region_id,
                generated_at=cache_entry.generated_at,
                horizon_days=horizon_days,
                trajectory=trajectory,
                params_hash=params_hash,
            ).model_dump_json()
            await redis_client.setex(cache_key, 3600, resp_data)

            # 6. Kafka emission
            from aiokafka import AIOKafkaProducer

            producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
            await producer.start()
            try:
                rt = compute_Rt(params, sol.y[0, -1], params.N_pop)
                update = {
                    "region_id": region_id,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "beta": params.beta,
                    "Rt": rt,
                    "forecast_hash": params_hash,
                    "state_version": state_snapshot.version,
                }
                await producer.send_and_wait(settings.kafka_topic_updates, json.dumps(update).encode())
            finally:
                await producer.stop()
    finally:
        if redis_client:
            await redis_client.aclose()


def run_forecast_async(region_id: str, horizon_days: int) -> None:
    """Run a forecast synchronously when no Celery worker is configured.

    The inline path is meant to run inside a Celery worker (its own thread /
    process — no running event loop). When invoked from a FastAPI request
    handler (already in a loop), the caller MUST `await` `_run_forecast_logic`
    directly. We expose `_run_forecast_logic` so routers can do that.
    """
    if settings.run_forecast_inline:
        # Schedule on the running loop. asyncio.run() would crash here
        # because the request handler is already inside an event loop.
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(_run_forecast_logic(region_id, horizon_days))
        else:
            task = loop.create_task(_run_forecast_logic(region_id, horizon_days))
            # Retain a reference so the task isn't garbage-collected early,
            # and log failures instead of silently dropping them.
            _background_tasks.add(task)
            task.add_done_callback(_task_done)
    else:
        _forecast_task.delay(region_id, horizon_days)


@celery_app.task
def _forecast_task(region_id: str, horizon_days: int):
    asyncio.run(_run_forecast_logic(region_id, horizon_days))
