"""CyberEpi Prescription Service - FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from shared.db import create_all_on_startup, install_db_outage_handler
from shared.health import build_health_router
from shared.kafka import connect_redis, disconnect_redis
from shared.security import SecurityHeadersMiddleware
from shared.validation import install_validation_handler

from src.config import settings
from src.db.models import Base
from src.db.session import engine

logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown lifecycle with bounded retries and timeouts."""
    logger.info("Starting prescription-service", port=settings.service_port)

    # Dev-time schema bootstrap. Production should run migrations instead.
    await create_all_on_startup(engine, Base)

    app.state.redis = await connect_redis(settings)

    yield
    logger.info("Shutting down dependencies")
    await disconnect_redis(app.state.redis)
    await engine.dispose()
    logger.info("Prescription-service shutdown complete")


app = FastAPI(
    title="CyberEpi Prescription Service",
    version="0.1.0",
    docs_url="/docs",
    lifespan=lifespan,
)
install_validation_handler(app)
install_db_outage_handler(app)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")
app.add_middleware(SecurityHeadersMiddleware)

from src.api.routers.prescriptions import router as prescriptions_router  # noqa: E402

app.include_router(prescriptions_router)

app.include_router(build_health_router(settings, engine=engine))
