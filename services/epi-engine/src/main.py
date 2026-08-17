from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator
from shared.health import build_health_router, kafka_health_check
from shared.kafka import (
    connect_kafka,
    connect_redis,
    disconnect_kafka,
    disconnect_redis,
)
from shared.security import SecurityHeadersMiddleware

from .api.routers import control, forecast, params, population, state
from .config import settings
from .db.connection import engine

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: connect Redis and Kafka with bounded retries; shutdown with timeouts."""
    logger.info("Starting epi-engine", port=settings.service_port)

    app.state.redis = await connect_redis(settings)
    app.state.kafka_producer = await connect_kafka(settings)

    yield

    logger.info("Shutting down dependencies")
    await disconnect_kafka(app.state.kafka_producer)
    await disconnect_redis(app.state.redis)
    logger.info("Epi-engine shutdown complete")


app = FastAPI(title="CyberEpi Disease Dynamics Engine", lifespan=lifespan)
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
app.add_middleware(SecurityHeadersMiddleware)

# Routers
app.include_router(params.router, prefix="/api/v1/regions", tags=["params"])
app.include_router(forecast.router, prefix="/api/v1/regions", tags=["forecast"])
app.include_router(state.router, tags=["state"])
app.include_router(population.router)
app.include_router(control.router)

app.include_router(build_health_router(settings, engine=engine, extra_checks={"kafka": kafka_health_check}))
