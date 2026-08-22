"""CyberEpi Notification Service - FastAPI entry point with Kafka consumer."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis.asyncio as aioredis
import structlog
from aiokafka import AIOKafkaConsumer
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


async def _consume_alerts(app: FastAPI) -> None:
    """Background task: consume alerts.push topic and forward to Redis pub/sub.

    Bounded retries: when the broker is unreachable we sleep with
    exponential backoff instead of letting aiokafka's internal retry loop
    spam the log. The /health endpoint will still report Kafka as
    unhealthy while this is retrying, which is the truthful signal.
    """

    from aiokafka.errors import KafkaError

    backoff = 1.0
    while True:
        consumer = AIOKafkaConsumer(
            "symptom-reports",
            bootstrap_servers=settings.kafka_bootstrap_servers,
            group_id="notification-service",
            auto_offset_reset="latest",
        )
        try:
            await consumer.start()
            logger.info("Kafka consumer started for symptom-reports")
            backoff = 1.0  # reset after a successful connect
            try:
                async for msg in consumer:
                    try:
                        event = json.loads(msg.value.decode("utf-8"))
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
                with contextlib.suppress(Exception):
                    await consumer.stop()
        except KafkaError as exc:
            logger.warning(
                "Kafka consumer connect failed; backing off",
                error=str(exc),
                backoff_seconds=backoff,
            )
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
            continue
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Kafka consumer crashed; restarting")
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, 30.0)
            continue

@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting notification-service", port=settings.service_port)

    # Dev-time schema bootstrap. Production should run migrations instead.
    await create_all_on_startup(engine, Base)

    app.state.redis = await connect_redis(settings)

    # Firebase init (if credentials available)
    try:
        import firebase_admin
        from firebase_admin import credentials

        if settings.firebase_credentials_path:
            cred = credentials.Certificate(settings.firebase_credentials_path)
            firebase_admin.initialize_app(cred)
            logger.info("Firebase Admin initialized")
    except Exception:  # noqa: BLE001 — push is optional infrastructure; any init failure degrades to no-FCM
        logger.warning("Firebase Admin not initialized (no credentials)")

    # Start Kafka consumer in background
    consumer_task = asyncio.create_task(_consume_alerts(app))

    yield

    # Shutdown
    consumer_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await consumer_task
    await disconnect_redis(app.state.redis)
    await engine.dispose()
    logger.info("Notification-service shutdown complete")


app = FastAPI(
    title="CyberEpi Notification Service",
    version="0.1.0",
    docs_url="/docs",
    lifespan=lifespan,
)
install_validation_handler(app)
install_db_outage_handler(app)

Instrumentator().instrument(app).expose(app, endpoint="/metrics")
app.add_middleware(SecurityHeadersMiddleware)

from src.api.routers.notifications import router as notifications_router  # noqa: E402

app.include_router(notifications_router)

app.include_router(build_health_router(settings, engine=engine))
