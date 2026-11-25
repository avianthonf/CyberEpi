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
        # Bound both connection acquisition AND query execution
        async with asyncio.timeout(2.0):
            async with engine.connect() as conn:
                await conn.execute(text("SELECT 1"))
        return True, "healthy"
    except TimeoutError:
        return False, "unhealthy: timeout"
    except Exception as e:  # noqa: BLE001
        return False, f"unhealthy: {e}"


async def kafka_health_check(request: Request) -> tuple[bool, str]:
    """Active Kafka health probe.

    Forces a real metadata fetch from the broker via network round-trip.
    Uses client.fetch_all_metadata() which performs _metadata_update with
    broker network I/O, not cached cluster state.
    """
    producer = getattr(request.app.state, "kafka_producer", None)
    if producer is None:
        return False, "unhealthy: not initialized"
    try:
        client = getattr(producer, "client", None) or getattr(producer, "_client", None)
        if client is None:
            return False, "unhealthy: no client"
        # fetch_all_metadata() returns new ClusterMetadata with broker network I/O
        metadata = await asyncio.wait_for(client.fetch_all_metadata(), timeout=2.0)
        # Use returned metadata, not client.cluster which may not be updated
        brokers = list(metadata.brokers())
        if not brokers:
            return False, "unhealthy: no brokers"
        return True, f"healthy: {len(brokers)} broker(s)"
    except TimeoutError:
        return False, "unhealthy: timeout"
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
