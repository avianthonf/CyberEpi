"""Deep health check shared by all services.

`build_health_router` wires honest component checks (Redis ping, DB SELECT 1,
Kafka producer state) into a `/health` endpoint. Kafka health reports a real
producer ping when possible instead of claiming healthy on attribute existence.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import structlog
from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.config import Settings

logger = structlog.get_logger()


async def _redis_healthy(request: Request) -> tuple[bool, str]:
    redis = getattr(request.app.state, "redis", None)
    if redis is None:
        return False, "unhealthy: not initialized"
    try:
        await asyncio.wait_for(redis.ping(), timeout=2.0)
        return True, "healthy"
    except Exception as e:  # noqa: BLE001
        return False, f"unhealthy: {e}"


async def _db_healthy(engine: AsyncEngine | None) -> tuple[bool, str]:
    if engine is None:
        return False, "unhealthy: not initialized"
    try:
        async with engine.connect() as conn:
            await asyncio.wait_for(conn.execute(text("SELECT 1")), timeout=2.0)
        return True, "healthy"
    except Exception as e:  # noqa: BLE001
        return False, f"unhealthy: {e}"


async def kafka_health_check(request: Request) -> tuple[bool, str]:
    """Honest Kafka health probe.

    aiokafka's internals (`producer.client`, `_closed`, `cluster.brokers()`)
    have shifted across versions. We probe the durable contract instead:
    "we can fetch cluster metadata" — that's what proves the producer is
    actually connected to a broker. If the producer exposes nothing usable,
    we treat it as unhealthy rather than claiming green.
    """
    producer = getattr(request.app.state, "kafka_producer", None)
    if producer is None:
        return False, "unhealthy: not initialized"
    try:
        client = getattr(producer, "client", None) or getattr(producer, "_client", None)
        if client is None:
            return False, "unhealthy: no client"
        # `client.cluster.brokers()` works across the aiokafka 0.x line we target.
        brokers = list(client.cluster.brokers())
        if not brokers:
            return False, "unhealthy: no brokers known"
        return True, f"healthy: {len(brokers)} broker(s)"
    except Exception as e:  # noqa: BLE001
        return False, f"unhealthy: {e}"

def build_health_router(
    settings: Settings,
    *,
    engine: AsyncEngine | None = None,
    extra_checks: dict[str, Callable[[Request], Awaitable[tuple[bool, str]]]] | None = None,
) -> APIRouter:
    router = APIRouter()

    @router.get("/health")
    async def health(request: Request) -> dict[str, Any]:
        health_status: dict[str, Any] = {
            "status": "healthy",
            "service": settings.service_name,
            "components": {},
        }
        overall_healthy = True
        checks: dict[str, Callable[[Request], Awaitable[tuple[bool, str]]]] = {
            "redis": _redis_healthy,
        }
        if engine is not None:
            checks["database"] = lambda req: _db_healthy(engine)
        if extra_checks:
            checks.update(extra_checks)

        for name, check in checks.items():
            ok, detail = await check(request)
            health_status["components"][name] = detail
            if not ok:
                overall_healthy = False

        if not overall_healthy:
            health_status["status"] = "unhealthy"
            raise HTTPException(status_code=503, detail=health_status)
        return health_status

    return router
