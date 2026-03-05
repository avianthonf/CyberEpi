"""CyberEpi User Service – FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from src.config import settings
from src.db.session import engine

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown lifecycle."""
    logger.info("Starting user-service", port=settings.service_port)

    # Verify DB connection
    async with engine.begin() as conn:
        await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    logger.info("Database connected")

    # Verify Redis connection
    r = aioredis.from_url(settings.redis_url)
    await r.ping()
    app.state.redis = r
    logger.info("Redis connected")

    yield

    # Shutdown
    await r.aclose()
    await engine.dispose()
    logger.info("User-service shutdown complete")


app = FastAPI(
    title="CyberEpi User Service",
    version="0.1.0",
    docs_url="/docs",
    lifespan=lifespan,
)

# Prometheus metrics
Instrumentator().instrument(app).expose(app, endpoint="/metrics")

# Import and include routers
from src.api.routers.patients import router as patients_router  # noqa: E402

app.include_router(patients_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": settings.service_name}
