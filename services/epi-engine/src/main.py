from fastapi import FastAPI, Depends, HTTPException
from contextlib import asynccontextmanager
from redis import asyncio as aioredis
import os
import logging
import structlog
import asyncio
from typing import AsyncGenerator
from aiokafka import AIOKafkaProducer

if os.getenv("TESTING") == "1":
    class MockProducer:
        def __init__(self, *args, **kwargs): pass
        async def start(self): pass
        async def stop(self): pass
        async def send_and_wait(self, topic, value): pass
    AIOKafkaProducer = MockProducer
from .config import settings
from .api.routers import forecast, params, simulate, state, population, control
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

# Structured logging setup
structlog.configure(
    processors=[
        structlog.processors.JSONRenderer(),
    ],
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
)
logger = structlog.get_logger()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: Initialize Redis and Kafka with bounded retries
    logger.info("Initializing dependencies", redis_url=settings.redis_url, kafka=settings.kafka_bootstrap_servers)
    
    # Redis with retry
    for i in range(5):
        try:
            app.state.redis = aioredis.from_url(settings.redis_url, decode_responses=True)
            await asyncio.wait_for(app.state.redis.ping(), timeout=5.0)
            logger.info("Redis connected")
            break
        except Exception as e:
            if i == 4: raise
            logger.warning("Redis connection failed, retrying...", error=str(e), attempt=i+1)
            await asyncio.sleep(min(2 ** i, 10))

    # Kafka with retry
    for i in range(5):
        try:
            app.state.kafka_producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
            await asyncio.wait_for(app.state.kafka_producer.start(), timeout=10.0)
            logger.info("Kafka producer started")
            break
        except Exception as e:
            if i == 4: raise
            logger.warning("Kafka connection failed, retrying...", error=str(e), attempt=i+1)
            await asyncio.sleep(min(2 ** i, 10))
    
    yield
    
    # Shutdown with strict timeouts
    logger.info("Shutting down dependencies")
    try:
        await asyncio.wait_for(app.state.kafka_producer.stop(), timeout=10.0)
    except asyncio.TimeoutError:
        logger.error("Kafka shutdown timed out")
    
    try:
        await asyncio.wait_for(app.state.redis.close(), timeout=5.0)
    except asyncio.TimeoutError:
        logger.error("Redis shutdown timed out")

app = FastAPI(title="CyberEpi Disease Dynamics Engine", lifespan=lifespan)
app.add_middleware(SecurityHeadersMiddleware)

# Routers
app.include_router(params.router, prefix="/api/v1/regions", tags=["params"])
app.include_router(forecast.router, prefix="/api/v1/regions", tags=["forecast"])
app.include_router(simulate.router, prefix="/api/v1", tags=["simulate"])
app.include_router(state.router, tags=["state"])
app.include_router(population.router)
app.include_router(control.router)

@app.get("/health")
async def health_check():
    """Deep health check verifying Redis, Kafka, and Database."""
    health_status = {"status": "ok", "components": {}}
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
        # Simple check: is it still running?
        health_status["components"]["kafka"] = "healthy"

    # Check Database
    try:
        from .db.connection import engine
        from sqlalchemy import text
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=2.0)
        health_status["components"]["database"] = "healthy"
    except Exception as e:
        health_status["components"]["database"] = f"unhealthy: {str(e)}"
        overall_healthy = False

    if not overall_healthy:
        raise HTTPException(status_code=503, detail=health_status)
    
    return health_status

@app.get("/metrics")
async def metrics():
    # Placeholder for Prometheus metrics
    return {"message": "Prometheus metrics would go here"}
