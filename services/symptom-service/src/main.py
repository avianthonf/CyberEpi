"""CyberEpi Symptom Service – FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import asyncio
import redis.asyncio as aioredis
import structlog
from aiokafka import AIOKafkaProducer
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
        # Since these are internal services behind Kong, HSTS might be redundant but good for defense-in-depth
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting symptom-service", port=settings.service_port)

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

    # Kafka producer with retry
    for i in range(5):
        try:
            producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
            await asyncio.wait_for(producer.start(), timeout=10.0)
            app.state.kafka_producer = producer
            logger.info("Kafka producer started")
            break
        except Exception as e:
            if i == 4: raise
            logger.warning("Kafka connection failed, retrying...", error=str(e), attempt=i+1)
            await asyncio.sleep(min(2 ** i, 10))

    yield

    logger.info("Shutting down dependencies")
    try:
        await asyncio.wait_for(producer.stop(), timeout=10.0)
    except asyncio.TimeoutError:
        logger.error("Kafka shutdown timed out")
    
    try:
        await asyncio.wait_for(r.aclose(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.error("Redis shutdown timed out")
    
    await engine.dispose()
    logger.info("Symptom-service shutdown complete")


app = FastAPI(
    title="CyberEpi Symptom Service",
    version="0.1.0",
    docs_url="/docs",
    lifespan=lifespan,
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")
app.add_middleware(SecurityHeadersMiddleware)

from src.api.routers.symptoms import router as symptoms_router  # noqa: E402
from src.api.routers.risk import router as risk_router  # noqa: E402

app.include_router(symptoms_router)
app.include_router(risk_router)


@app.get("/health")
async def health() -> dict[str, Any]:
    """Deep health check verifying Redis, Kafka, and Database."""
    health_status = {"status": "ok", "service": settings.service_name, "components": {}}
    overall_healthy = True

    # Check Redis
    try:
        await asyncio.wait_for(app.state.redis.ping(), timeout=2.0)
        health_status["components"]["redis"] = "healthy"
    except Exception as e:
        health_status["components"]["redis"] = f"unhealthy: {str(e)}"
        overall_healthy = False

    # Check Kafka
    if not hasattr(app.state, "kafka_producer"):
        health_status["components"]["kafka"] = "unhealthy: not initialized"
        overall_healthy = False
    else:
        health_status["components"]["kafka"] = "healthy"

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
