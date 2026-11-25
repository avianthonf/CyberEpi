"""Postgres-backed DP budget tracker with Redis write-through cache."""

import contextlib
import json
from datetime import UTC, datetime

import redis.asyncio as redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db.models import DPBudget, DPQuery


class PersistentBudgetTracker:
    """DP budget tracker: Postgres source-of-truth, Redis write-through cache."""

    def __init__(self, redis_client: redis.Redis, session_maker, max_budget: float = 10.0, cache_ttl: int = 3600):
        self.redis = redis_client
        self.session_maker = session_maker
        self.max_budget = max_budget
        self.cache_ttl = cache_ttl

    def _cache_key(self, user_id) -> str:
        return f"dp_budget:{user_id!s}"

    async def _get_from_db(self, session: AsyncSession, user_id):
        """Fetch budget from Postgres."""
        result = await session.execute(select(DPBudget).where(DPBudget.user_id == str(user_id)))
        return result.scalars().first()

    async def _sync_to_cache(self, user_id, consumed: float) -> None:
        """Write budget to Redis cache. Best-effort: Postgres is source-of-truth,
        so a Redis outage must not fail budget operations."""
        key = self._cache_key(user_id)
        with contextlib.suppress(redis.RedisError):
            await self.redis.setex(key, self.cache_ttl, str(consumed))

    async def get_remaining(self, user_id) -> float:
        """Get remaining budget. Cache hit → Redis; miss → Postgres → cache."""
        user_id_str = str(user_id)
        key = self._cache_key(user_id_str)
        try:
            cached = await self.redis.get(key)
        except redis.RedisError:
            cached = None
        if cached is not None:
            return max(0.0, self.max_budget - float(cached))

        # Cache miss — fetch from Postgres
        async with self.session_maker() as session:
            budget = await self._get_from_db(session, user_id_str)
            consumed = 0.0 if budget is None else budget.consumed

            # Populate cache
            await self._sync_to_cache(user_id_str, consumed)
            return max(0.0, self.max_budget - consumed)

    async def consume(
        self,
        user_id,
        epsilon: float,
        mechanism: str = "gaussian",
        sensitivity: float = 1.0,
        query_type: str | None = None,
        noised_value: float | None = None,
        metadata: dict | None = None,
    ) -> bool:
        """
        Atomically consume budget. Returns True if successful.
        Writes to Postgres first (source-of-truth), then updates cache.
        Logs query to audit table.
        """
        user_id_str = str(user_id)
        async with self.session_maker() as session, session.begin():
            # Race-safe bootstrap: idempotent insert first, then lock the row.
            # `SELECT ... FOR UPDATE` against a missing row does NOT serialize
            # concurrent inserters, so N parallel calls for a brand-new user
            # each saw "no row", each tried INSERT, and the loser blew up
            # with UniqueViolation → 500. ON CONFLICT DO NOTHING guarantees
            # exactly one row regardless of arrival order; the FOR UPDATE
            # then serializes the budget update.
            from sqlalchemy.dialects.postgresql import insert as pg_insert

            await session.execute(
                pg_insert(DPBudget)
                .values(
                    user_id=user_id_str,
                    consumed=0.0,
                    max_budget=self.max_budget,
                    reset_count=0,
                    updated_at=datetime.now(UTC),
                )
                .on_conflict_do_nothing(index_elements=["user_id"])
            )
            result = await session.execute(select(DPBudget).where(DPBudget.user_id == user_id_str).with_for_update())
            budget = result.scalars().first()
            if budget is None:
                # Defensive: should be unreachable because of the upsert above.
                raise RuntimeError(f"DP budget row missing after upsert for user {user_id_str}")

            # Check if consumption would exceed budget
            new_consumed = budget.consumed + epsilon
            if new_consumed > budget.max_budget:
                return False

            # Update budget
            budget.consumed = new_consumed
            budget.updated_at = datetime.now(UTC)

            # Log query to audit table
            query_log = DPQuery(
                user_id=user_id_str,
                mechanism=mechanism,
                epsilon=epsilon,
                sensitivity=sensitivity,
                query_type=query_type,
                noised_value=noised_value,
                query_metadata=json.dumps(metadata) if metadata else None,
            )
            session.add(query_log)

        # Update successful — invalidate cache or write new value
        await self._sync_to_cache(user_id_str, new_consumed)
        return True

    async def batch_consume(
        self, user_ids: list[str], epsilon: float, mechanism: str = "gaussian", sensitivity: float = 1.0
    ) -> dict[str, bool]:
        """Batch consume (sequential for simplicity; can be parallelized)."""
        results = {}
        for uid in user_ids:
            results[uid] = await self.consume(uid, epsilon, mechanism, sensitivity)
        return results

    async def reset(self, user_id) -> None:
        """Reset budget to zero consumed."""
        user_id_str = str(user_id)
        async with self.session_maker() as session, session.begin():
            result = await session.execute(select(DPBudget).where(DPBudget.user_id == user_id_str).with_for_update())
            budget = result.scalars().first()

            if budget is None:
                # No record to reset
                return

            budget.consumed = 0.0
            budget.reset_count += 1
            budget.updated_at = datetime.now(UTC)

        # Clear cache (best-effort; stale cache expires by TTL)
        key = self._cache_key(user_id_str)
        with contextlib.suppress(redis.RedisError):
            await self.redis.delete(key)

    async def get_audit_log(self, user_id, limit: int = 100) -> list[DPQuery]:
        """Retrieve recent DP query audit log for a user."""
        user_id_str = str(user_id)
        async with self.session_maker() as session:
            result = await session.execute(
                select(DPQuery).where(DPQuery.user_id == user_id_str).order_by(DPQuery.timestamp.desc()).limit(limit)
            )
            return list(result.scalars().all())
