"""CyberEpi Notification Service – FastAPI entry point with Kafka consumer."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import structlog
from aiokafka import AIOKafkaConsumer
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

from src.config import settings
from src.db.session import engine

logger = structlog.get_logger()


async def _consume_alerts(app: FastAPI) -> None:
    """Background task: consume alerts.push topic and forward to Redis pub/sub."""
    consumer = AIOKafkaConsumer(
        "alerts.push",
        bootstrap_servers=settings.kafka_bootstrap_servers,
        group_id="notification-service",
        auto_offset_reset="latest",
    )
    await consumer.start()
    logger.info("Kafka consumer started for alerts.push")

    try:
        async for msg in consumer:
            try:
                event = json.loads(msg.value.decode("utf-8"))
                # Determine physician to notify (from event payload)
                payload = json.loads(event.get("payload", "{}"))
                physician_id = payload.get("physician_id")
                if physician_id:
                    redis_client: aioredis.Redis = app.state.redis
                    await redis_client.publish(
                        f"alerts:{physician_id}",
                        json.dumps(event),
                    )
                    logger.info(
                        "Alert forwarded to physician",
                        physician_id=physician_id,
                    )
            except Exception:
                logger.exception("Error processing alert message")
    finally:
        await consumer.stop()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting notification-service", port=settings.service_port)

    # DB
    async with engine.begin() as conn:
        await conn.execute(__import__("sqlalchemy").text("SELECT 1"))
    logger.info("Database connected")

    # Redis
    r = aioredis.from_url(settings.redis_url)
    await r.ping()
    app.state.redis = r
    logger.info("Redis connected")

    # Firebase init (if credentials available)
    try:
        import firebase_admin
        from firebase_admin import credentials

        if settings.firebase_credentials_path:
            cred = credentials.Certificate(settings.firebase_credentials_path)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin initialized")
    except Exception:
        logger.warning("Firebase Admin not initialized (no credentials)")

    # Start Kafka consumer in background
    consumer_task = asyncio.create_task(_consume_alerts(app))

    yield

    # Shutdown
    consumer_task.cancel()
    import contextlib

    with contextlib.suppress(asyncio.CancelledError):
        await consumer_task
    await r.aclose()
    await engine.dispose()
    logger.info("Notification-service shutdown complete")


app = FastAPI(
    title="CyberEpi Notification Service",
    version="0.1.0",
    docs_url="/docs",
    lifespan=lifespan,
)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")

from src.api.routers.notifications import router as notifications_router  # noqa: E402

app.include_router(notifications_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy", "service": settings.service_name}
