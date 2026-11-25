"""Shared state loader with DB-backed persistence fallback.

Provides consistent snapshot access for forecast and control computations.
Uses PersistentFilterState when available (DB authoritative, Redis cache),
falls back to Redis-only for regions without persisted state.
"""

from typing import Any

import numpy as np
import redis.asyncio as aioredis
import structlog
from sqlalchemy.ext.asyncio import async_sessionmaker

from ..filters.persistent_state import PersistentFilterState

logger = structlog.get_logger()


class StateSnapshot:
    """Immutable snapshot of filter state at a point in time."""

    def __init__(
        self,
        region_id: str,
        x: np.ndarray | None,
        P: np.ndarray | None,
        meta: dict[str, Any],
        timestamp: str | None,
    ):
        self.region_id = region_id
        self.x = x
        self.P = P
        self.meta = meta
        self.timestamp = timestamp  # ISO8601 or None for bootstrap
        self.version = timestamp or "bootstrap"

    @property
    def has_state(self) -> bool:
        """True if filtered state exists (not bootstrap)."""
        return self.x is not None

    def get_ode_initial_condition(self, N_pop: int) -> np.ndarray:
        """Get 9-dim initial condition for SEIR ODE solver."""
        if self.has_state and len(self.x) >= 9:
            return np.array(self.x[0:9])
        # Bootstrap: no observations yet
        return np.array([N_pop - 10, 10, 0, 0, 0, 0, 0, 0, 0])

    def get_control_initial_condition(self, N_pop: int) -> np.ndarray:
        """Get 8-dim initial condition for control optimizer."""
        if self.has_state and len(self.x) >= 8:
            return np.array(self.x[0:8])
        # Bootstrap: no observations yet
        return np.array([N_pop * 0.9, N_pop * 0.05, 100, 50, 10, 5, 0, 0])


async def load_state_snapshot(
    region_id: str,
    redis_client: aioredis.Redis,
    session_maker: async_sessionmaker | None = None,
) -> StateSnapshot:
    """Load filter state snapshot with DB fallback.

    Order of precedence:
    1. PersistentFilterState (DB-backed + Redis cache) if session_maker provided
    2. Redis-only fallback
    3. Bootstrap (no state exists)

    Args:
        region_id: Region identifier
        redis_client: Redis connection (must be closed by caller)
        session_maker: Optional DB session factory for persistent state

    Returns:
        Immutable StateSnapshot with version/timestamp for cache keying
    """
    timestamp = None

    # Try persistent state (DB-backed) first
    if session_maker is not None:
        try:
            persistent = PersistentFilterState(redis_client, session_maker)
            x, P, meta = await persistent.load(region_id)
            if x is not None:
                # Get timestamp from DB state (PersistentFilterState sets updated_at in meta)
                async with session_maker() as session:
                    from sqlalchemy import select
                    from ..db.models import FilterState

                    result = await session.execute(select(FilterState.updated_at).where(FilterState.region_id == region_id))
                    row = result.first()
                    if row:
                        timestamp = row[0].isoformat()

                logger.info("state_loaded_from_db", region_id=region_id, timestamp=timestamp)
                return StateSnapshot(region_id, x, P, meta, timestamp)
        except Exception:
            logger.warning("persistent_state_load_failed", region_id=region_id, exc_info=True)

    # Fallback: Redis-only (observation_consumer may write here without DB persistence)
    try:
        cache_key = f"filter_state:{region_id}"
        data_raw = await redis_client.get(cache_key)
        if data_raw:
            import json

            data = json.loads(data_raw)
            x = data.get("x")
            P = data.get("P")
            meta = data.get("meta", {})
            timestamp = data.get("updated_at")

            if x is not None:
                x = np.array(x)
                if P is not None:
                    P = np.array(P)
                logger.info("state_loaded_from_redis", region_id=region_id, timestamp=timestamp)
                return StateSnapshot(region_id, x, P, meta, timestamp)
    except (aioredis.RedisError, Exception):
        logger.warning("redis_state_load_failed", region_id=region_id, exc_info=True)

    # Bootstrap: no state exists (region never had observations)
    logger.info("state_bootstrap", region_id=region_id)
    return StateSnapshot(region_id, None, None, {}, None)
