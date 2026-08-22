"""CyberEpi Privacy Service - FastAPI application entry point."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import structlog
from alembic.config import Config
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from shared.db import install_db_outage_handler
from shared.health import build_health_router
from shared.kafka import connect_redis, disconnect_redis
from shared.security import SecurityHeadersMiddleware
from shared.validation import install_validation_handler
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker as async_sessionmaker

from alembic import command
from src.api.routers import dp, fl
from src.config import settings
from src.dp.persistent_budget import PersistentBudgetTracker

logger = structlog.get_logger()

# Lazy: no connections are opened until first use. Module scope so the
# health router can check DB liveness.
db_engine = create_async_engine(settings.database_url)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup: run Alembic migrations, init Redis + Postgres, wire budget tracker.
    Shutdown: close Redis."""
    # Run database migrations on startup. Run in a separate thread because
    # alembic's env.py uses asyncio.run() which can't run inside a running
    # event loop.
    alembic_cfg = Config("alembic.ini")
    await asyncio.to_thread(command.upgrade, alembic_cfg, "head")
    logger.info("Alembic migrations applied")

    app.state.redis = await connect_redis(settings)

    # Initialize Postgres session maker for DP budget tracker
    session_maker = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    app.state.db_engine = db_engine

    app.state.budget_tracker = PersistentBudgetTracker(
        redis_client=app.state.redis,
        session_maker=session_maker,
        max_budget=settings.max_privacy_budget,
    )

    yield

    logger.info("Shutting down dependencies")
    await disconnect_redis(app.state.redis)
    logger.info("Privacy-service shutdown complete")


app = FastAPI(title="CyberEpi Privacy Service", lifespan=lifespan)
install_validation_handler(app)
install_db_outage_handler(app)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")
app.add_middleware(SecurityHeadersMiddleware)

app.include_router(dp.router, prefix="/internal/dp", tags=["DP"])
app.include_router(fl.router, prefix="/api/v1/fl", tags=["FL"])

app.include_router(build_health_router(settings, engine=db_engine))
