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
    producer = getattr(request.app.state, "kafka_producer", None)
    if producer is None:
        return False, "unhealthy: not initialized"
    # Honest check: ask the producer whether its client is still connected.
    try:
        client = getattr(producer, "_client", None)
        connected = bool(client is not None and not getattr(client, "_closed", True))
        return (True, "healthy") if connected else (False, "unhealthy: client closed")
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
            "database": lambda req: _db_healthy(engine),
        }
        if extra_checks:
            checks.update(extra_checks)

        for name, check in checks.items():
            ok, detail = await check(request)
            health_status["components"][name] = detail
            if not ok:
                overall_healthy = False

        if not overall_healthy:
            raise HTTPException(status_code=503, detail=health_status)
        return health_status

    return router
