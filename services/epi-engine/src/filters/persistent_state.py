"""Postgres-backed filter state persistence with Redis cache.

Replaces Redis-only storage with:
- Postgres as source-of-truth
- Redis as write-through cache (7-day TTL)
- Observation history retained in Postgres
"""
import contextlib
import json
from datetime import UTC, datetime
from typing import Any

import numpy as np
import redis.asyncio as redis
from sqlalchemy import select

from ..db.models import FilterState


def _json_safe(obj: Any) -> Any:
    """Recursively map NaN/±inf floats to None.

    Postgres JSON columns reject bare `NaN`/`Infinity` literals, and the
    observation vector legitimately carries NaN on channels with no data
    for a given week.
    """
    if isinstance(obj, np.ndarray):
        obj = obj.tolist()
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, float) and not np.isfinite(obj):
        return None
    return obj


class PersistentFilterState:
    """Filter state manager: Postgres + Redis cache."""

    def __init__(
        self,
        redis_client: redis.Redis,
        session_maker,
        cache_ttl: int = 604800  # 7 days
    ):
        self.redis = redis_client
        self.session_maker = session_maker
        self.cache_ttl = cache_ttl

    def _cache_key(self, region_id: str) -> str:
        return f"filter_state:{region_id}"

    async def load(self, region_id: str) -> tuple[np.ndarray | None, np.ndarray | None, dict[str, Any]]:
        """
        Load filter state. Cache hit → Redis; miss → Postgres → cache.
        Returns (x_est, P, meta) or (None, None, {})
        """
        # Try Redis cache first (best-effort: Postgres is source-of-truth,
        # so a Redis outage must degrade to the DB path, not fail)
        cache_key = self._cache_key(region_id)
        try:
            cached = await self.redis.get(cache_key)
        except redis.RedisError:
            cached = None

        if cached is not None:
            data = json.loads(cached)
            return (
                np.array(data['x']),
                np.array(data['P']),
                data.get('meta', {})
            )

        # Cache miss — fetch from Postgres
        async with self.session_maker() as session:
            result = await session.execute(
                select(FilterState).where(FilterState.region_id == region_id)
            )
            state = result.scalars().first()

            if state is None:
                return None, None, {}

            # Reconstruct state (None sanitization markers -> NaN)
            def _arr(vals):
                return np.array(
                    [float('nan') if v is None else v for v in vals],
                    dtype=float,
                )
            x = _arr(state.state_vector)
            # Covariance stored as flattened 144-element array or compressed
            P_flat = _arr(state.covariance_matrix)
            P = P_flat.reshape(12, 12) if len(P_flat) == 144 else np.diag(P_flat)

            meta = {
                'cusum': state.cusum_score,
                'fail_count': state.fail_count,
                'mode': state.filter_type,
                'last_observation': state.last_observation,
                'last_innovation': state.last_innovation,
                'last_chi2': state.last_chi2,
            }

            # Populate cache
            cache_data = {
                'x': x.tolist(),
                'P': P.tolist(),
                'meta': meta,
                'updated_at': state.updated_at.isoformat()
            }
            with contextlib.suppress(redis.RedisError):
                await self.redis.setex(cache_key, self.cache_ttl, json.dumps(cache_data))

            return x, P, meta

    async def save(
        self,
        region_id: str,
        x: np.ndarray,
        P: np.ndarray,
        meta: dict[str, Any],
        y_obs: np.ndarray | None = None,
        innovation: np.ndarray | None = None,
        chi2: float | None = None
    ):
        """
        Save filter state to Postgres and update Redis cache.
        Appends observation to history.
        """
        async with self.session_maker() as session, session.begin():
            result = await session.execute(
                select(FilterState).where(FilterState.region_id == region_id)
            )
            state = result.scalars().first()

            # Prepare observation history entry
            obs_entry = None
            if y_obs is not None:
                obs_entry = {
                    'timestamp': datetime.now(UTC).isoformat(),
                    'y_obs': _json_safe(y_obs),
                    'innovation': _json_safe(innovation),
                    'chi2': float(chi2) if chi2 is not None else None
                }

            if state is None:
                # Create new state
                obs_history = [obs_entry] if obs_entry else []
                state = FilterState(
                    region_id=region_id,
                    filter_type=meta.get('mode', 'ekf'),
                    state_vector=_json_safe(x),
                    covariance_matrix=_json_safe(P.flatten()),
                    cusum_score=meta.get('cusum', 0.0),
                    fail_count=meta.get('fail_count', 0),
                    last_observation=_json_safe(y_obs),
                    last_innovation=_json_safe(innovation),
                    last_chi2=chi2,
                    observation_history=obs_history
                )
                session.add(state)
            else:
                # Update existing state
                state.state_vector = _json_safe(x)
                state.covariance_matrix = _json_safe(P.flatten())
                state.filter_type = meta.get('mode', state.filter_type)
                state.cusum_score = meta.get('cusum', state.cusum_score)
                state.fail_count = meta.get('fail_count', state.fail_count)
                state.updated_at = datetime.now(UTC)

                if y_obs is not None:
                    state.last_observation = _json_safe(y_obs)
                    state.last_innovation = _json_safe(innovation)
                    state.last_chi2 = chi2

                    # Append to history (keep last 100)
                    history = state.observation_history or []
                    history.append(obs_entry)
                    state.observation_history = history[-100:]

        # Update Redis cache
        cache_data = {
            'x': x.tolist(),
            'P': P.tolist(),
            'meta': meta,
            'updated_at': datetime.now(UTC).isoformat()
        }
        cache_key = self._cache_key(region_id)
        with contextlib.suppress(redis.RedisError):
            await self.redis.setex(cache_key, self.cache_ttl, json.dumps(cache_data))
