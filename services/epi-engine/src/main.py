"""CyberEpi Disease Dynamics Engine – FastAPI entry point."""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from alembic.config import Config
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from shared.db import install_db_outage_handler
from shared.health import build_health_router, kafka_health_check
from shared.kafka import (
    connect_kafka,
    connect_redis,
    disconnect_kafka,
    disconnect_redis,
)
from shared.security import SecurityHeadersMiddleware
from shared.validation import install_validation_handler

from alembic import command

from .api.routers import control, forecast, params, population, state
from .config import settings
from .db.connection import engine
from .tasks.observation_consumer import consume_observations
from .tasks.surveillance_ingest import ingest_loop

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: connect Redis and Kafka with bounded retries; shutdown with timeouts."""
    logger.info("Starting epi-engine", port=settings.service_port)

    # Run database migrations on startup. The epi-engine env.py uses
    # `asyncio.run()` internally, which raises RuntimeError when called from
    # inside an already-running event loop (our async lifespan). Run the
    # synchronous `command.upgrade` in a separate thread to avoid that.
    # Resolve the ini relative to the repo layout, not the process cwd, so
    # the service (and tests using TestClient) work from any directory.
    # main.py lives at <service>/src/main.py, so parents[1] is <service>/.
    service_dir = Path(__file__).resolve().parents[1]
    alembic_cfg = Config(str(service_dir / "alembic.ini"))
    # The ini's script_location is relative to cwd; pin it absolutely.
    alembic_cfg.set_main_option("script_location", str(service_dir / "alembic"))
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
    logger.info("Alembic migrations applied")
    app.state.redis = await connect_redis(settings)
    app.state.kafka_producer = await connect_kafka(settings)

    # Background task: drive filter orchestrator + Rt writer from Kafka.
    consumer_task = asyncio.create_task(consume_observations(app))
    # Background task: continuous CDC surveillance ingestion (NHSN + NSSP).
    ingest_task = (
        asyncio.create_task(ingest_loop(app))
        if settings.surveillance_enabled else None
    )

    yield

    consumer_task.cancel()
    if ingest_task is not None:
        ingest_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await ingest_task
    with contextlib.suppress(asyncio.CancelledError):
        await consumer_task
    logger.info("Shutting down dependencies")
    await disconnect_kafka(app.state.kafka_producer)
    await disconnect_redis(app.state.redis)
    logger.info("Epi-engine shutdown complete")


app = FastAPI(title="CyberEpi Disease Dynamics Engine", lifespan=lifespan)
install_validation_handler(app)
install_db_outage_handler(app)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
app.add_middleware(SecurityHeadersMiddleware)

# Routers
app.include_router(params.router, prefix="/api/v1/regions", tags=["params"])
app.include_router(forecast.router, prefix="/api/v1/regions", tags=["forecast"])
app.include_router(state.router, tags=["state"])
app.include_router(population.router)
app.include_router(control.router)

app.include_router(build_health_router(settings, engine=engine, extra_checks={"kafka": kafka_health_check}))
