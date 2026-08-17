"""CyberEpi Privacy Service – FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from shared.health import build_health_router
from shared.kafka import connect_redis, disconnect_redis
from shared.security import SecurityHeadersMiddleware
from src.config import settings
from src.dp.budget import BudgetTracker

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown lifecycle."""
    logger.info("Starting privacy-service", port=settings.service_port)

    app.state.redis = await connect_redis(settings)
    app.state.budget_tracker = BudgetTracker(app.state.redis, max_budget=settings.max_privacy_budget)

    yield

    logger.info("Shutting down dependencies")
    await disconnect_redis(app.state.redis)
    logger.info("Privacy-service shutdown complete")


app = FastAPI(title="CyberEpi Privacy Service", lifespan=lifespan)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")
app.add_middleware(SecurityHeadersMiddleware)

from src.api.routers import dp, fl

app.include_router(dp.router, prefix="/internal/dp", tags=["DP"])
app.include_router(fl.router, prefix="/api/v1/fl", tags=["FL"])

app.include_router(build_health_router(settings))
