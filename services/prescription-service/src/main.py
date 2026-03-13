"""CyberEpi Prescription Service – FastAPI entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncio
import redis.asyncio as aioredis
import structlog
from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator

from src.config import settings
from src.db.session import engine
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting prescription-service", port=settings.service_port)

    # DB with retry
    for i in range(5):
        try:
            async with engine.begin() as conn:
                await asyncio.wait_for(conn.execute(__import__("sqlalchemy").text("SELECT 1")), timeout=5.0)
            logger.info("Database connected")
            break
        except Exception as e:
            if i == 4: raise
            logger.warning("Database connection failed, retrying...", error=str(e), attempt=i+1)
            await asyncio.sleep(min(2 ** i, 10))

    # Redis with retry
    for i in range(5):
        try:
            r = aioredis.from_url(settings.redis_url)
            await asyncio.wait_for(r.ping(), timeout=5.0)
            app.state.redis = r
            logger.info("Redis connected")
            break
        except Exception as e:
            if i == 4: raise
            logger.warning("Redis connection failed, retrying...", error=str(e), attempt=i+1)
            await asyncio.sleep(min(2 ** i, 10))

    yield

    logger.info("Shutting down dependencies")
    try:
        await asyncio.wait_for(r.aclose(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.error("Redis shutdown timed out")
    
    await engine.dispose()
    logger.info("Prescription-service shutdown complete")


app = FastAPI(
    title="CyberEpi Prescription Service",
    version="0.1.0",
    docs_url="/docs",
    lifespan=lifespan,
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")
app.add_middleware(SecurityHeadersMiddleware)

from src.api.routers.prescriptions import router as prescriptions_router  # noqa: E402

app.include_router(prescriptions_router)


@app.get("/health")
async def health() -> dict[str, Any]:
    """Deep health check verifying Redis and Database."""
    health_status = {"status": "ok", "service": settings.service_name, "components": {}}
    overall_healthy = True

    # Check Redis
    try:
        if not hasattr(app.state, "redis"):
             health_status["components"]["redis"] = "unhealthy: not initialized"
             overall_healthy = False
        else:
            await asyncio.wait_for(app.state.redis.ping(), timeout=2.0)
            health_status["components"]["redis"] = "healthy"
    except Exception as e:
        health_status["components"]["redis"] = f"unhealthy: {str(e)}"
        overall_healthy = False

    # Check Database
    try:
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(__import__("sqlalchemy").text("SELECT 1")), timeout=2.0)
        health_status["components"]["database"] = "healthy"
    except Exception as e:
        health_status["components"]["database"] = f"unhealthy: {str(e)}"
        overall_healthy = False

    if not overall_healthy:
        raise HTTPException(status_code=503, detail=health_status)
    
    return health_status
