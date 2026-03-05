"""CyberEpi Symptom Service – FastAPI application entry point."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import structlog
from aiokafka import AIOKafkaProducer
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from src.config import settings
from src.db.session import engine

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting symptom-service", port=settings.service_port)

    # DB
    async with engine.begin() as conn:
        await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    logger.info("Database connected")

    # Redis
    r = aioredis.from_url(settings.redis_url)
    await r.ping()
    app.state.redis = r
    logger.info("Redis connected")

    # Kafka producer
    producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
    await producer.start()
    app.state.kafka_producer = producer
    logger.info("Kafka producer started")

    yield

    await producer.stop()
    await r.aclose()
    await engine.dispose()
    logger.info("Symptom-service shutdown complete")


app = FastAPI(
    title="CyberEpi Symptom Service",
    version="0.1.0",
    docs_url="/docs",
    lifespan=lifespan,
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

from src.api.routers.symptoms import router as symptoms_router  # noqa: E402

app.include_router(symptoms_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": settings.service_name}
