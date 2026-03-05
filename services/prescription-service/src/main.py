"""CyberEpi Prescription Service – FastAPI entry point."""

from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from src.config import settings
from src.db.session import engine

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting prescription-service", port=settings.service_port)

    async with engine.begin() as conn:
        await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    logger.info("Database connected")

    r = aioredis.from_url(settings.redis_url)
    await r.ping()
    app.state.redis = r
    logger.info("Redis connected")

    yield

    await r.aclose()
    await engine.dispose()
    logger.info("Prescription-service shutdown complete")


app = FastAPI(
    title="CyberEpi Prescription Service",
    version="0.1.0",
    docs_url="/docs",
    lifespan=lifespan,
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

from src.api.routers.prescriptions import router as prescriptions_router  # noqa: E402

app.include_router(prescriptions_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": settings.service_name}
