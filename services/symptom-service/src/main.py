from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import sqlalchemy as sa
import structlog
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from shared.db import create_all_on_startup, install_db_outage_handler
from shared.health import build_health_router, kafka_health_check
from shared.kafka import (
    connect_kafka,
    connect_redis,
    disconnect_kafka,
    disconnect_redis,
)
from shared.security import SecurityHeadersMiddleware
from shared.validation import install_validation_handler

from src.config import settings
from src.db.models import Base
from src.db.session import engine

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting symptom-service", port=settings.service_port)

    # This service owns the vitals schema and its TimescaleDB conversion.
    await create_all_on_startup(engine, Base)

    # Convert vitals_ts to TimescaleDB hypertable if not already
    async with engine.begin() as conn:
        await conn.execute(
            sa.text("""
            SELECT create_hypertable('vitals_ts', 'time',
                chunk_time_interval => INTERVAL '1 day',
                if_not_exists => TRUE
            )
        """)
        )
    logger.info("vitals_ts hypertable ready")
    app.state.redis = await connect_redis(settings)
    app.state.kafka_producer = await connect_kafka(settings)
    yield

    logger.info("Shutting down dependencies")
    await disconnect_kafka(app.state.kafka_producer)
    await disconnect_redis(app.state.redis)
    await engine.dispose()
    logger.info("Symptom-service shutdown complete")


app = FastAPI(
    title="CyberEpi Symptom Service",
    version="0.1.0",
    docs_url="/docs",
    lifespan=lifespan,
)
install_validation_handler(app)
install_db_outage_handler(app)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")
app.add_middleware(SecurityHeadersMiddleware)

from src.api.routers.risk import router as risk_router  # noqa: E402
from src.api.routers.symptoms import router as symptoms_router  # noqa: E402

app.include_router(symptoms_router)
app.include_router(risk_router)

app.include_router(build_health_router(settings, engine=engine, extra_checks={"kafka": kafka_health_check}))
