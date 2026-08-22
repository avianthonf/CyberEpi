import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import redis.asyncio as aioredis
import structlog
from aiokafka import AIOKafkaProducer
from seir_core import SEIRParams

from ..config import settings
from .ekf import SEIR_EKF
from .particle_filter import ParticleFilter
from .persistent_state import PersistentFilterState

logger = structlog.get_logger()

@dataclass
class FilterResult:
    region_id: str
    timestamp: str
    filter_type: str  # 'ekf' | 'particle'
    state: dict[str, float]
    variance: dict[str, float]
    obs_params: dict[str, float]
    cusum_score: float
    model_alert: bool
    innovation: list | None = None

class FilterService:
    @staticmethod
    def initialize_state(params: SEIRParams) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
        x_est = np.zeros(12)
        x_est[:9] = [params.N_pop - 10, 10, 0, 0, 0, 0, 0, 0, 0]
        x_est[9:] = [0.12, 0.30, 0.001]  # papp, ptest, kappa
        P = np.eye(12) * (0.1 * params.N_pop)**2
        P[9:, 9:] = np.diag([0.01**2, 0.05**2, 0.0001**2])
        meta = {'cusum': 0.0, 'fail_count': 0, 'mode': 'ekf'}
        return x_est, P, meta

    @staticmethod
    def get_obs_matrices(x: np.ndarray, params: SEIRParams):
        papp, ptest, kappa = x[9], x[10], x[11]
        # H matrix: 5 observations, 12 states
        H = np.zeros((5, 12))
        H[0, 3:5] = papp  # app_reports (IM, IS)
        H[1, 3:5] = ptest # confirmed_cases (IM, IS)
        H[2, 5] = 1.0     # hospital_admissions (H)
        H[3, 3] = kappa   # pharmacy_proxy (IM)
        H[4, 2:5] = 0.0001 # wastewater (IA, IM, IS) - scaling factor
        return H

    @staticmethod
    def get_noise_matrices(x: np.ndarray, params: SEIRParams, y_obs: np.ndarray, meta: dict[str, Any]):
        Q = np.zeros((12, 12))
        sigmas = [0.01*params.N_pop, 0.01*params.N_pop, 0.005*params.N_pop, 0.005*params.N_pop,
                  0.002*params.N_pop, 0.001*params.N_pop, 0.001*params.N_pop, 0.01*params.N_pop,
                  0.0001*params.N_pop, 0.001, 0.001, 0.00001]
        np.fill_diagonal(Q, np.array(sigmas)**2)

        cusum = meta.get('cusum', 0.0)
        if cusum > 1.0:
            Q *= np.exp(cusum / 10.0)

        # R: 5x5 observation noise
        R = np.zeros((5, 5))
        R_vals = [
            (0.3*max(1, y_obs[0]))**2,
            (0.2*max(1, y_obs[1]))**2,
            (0.1*max(1, y_obs[2]))**2,
            (0.5*max(1, y_obs[3]))**2,
            (0.4*max(1, y_obs[4]))**2  # wastewater noise
        ]

        # Replace NaN with a default high variance
        R_vals = [v if not np.isnan(v) else 1e9 for v in R_vals]
        np.fill_diagonal(R, R_vals)
        return Q, R

class FilterOrchestrator:
    def __init__(
        self,
        region_id: str,
        redis_client: aioredis.Redis,
        kafka_producer: AIOKafkaProducer,
        session_maker=None,
    ):
        self.region_id = region_id
        self.redis = redis_client
        self.producer = kafka_producer
        self.session_maker = session_maker
        # Persistent state (Postgres source-of-truth, Redis cache)
        self.persistent_state = (
            PersistentFilterState(redis_client, session_maker)
            if session_maker is not None
            else None
        )
        self.ekf_threshold = 13.28
        self.cusum_threshold = 5.0
        self.failure_limit = 3
        self.service = FilterService()

    def _get_redis_key(self):
        return f"filter_state:{self.region_id}"

    async def load_state(self) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
        """Load filter state. Uses PersistentFilterState (Postgres+Redis) if available,
        else falls back to Redis-only."""
        if self.persistent_state is not None:
            return await self.persistent_state.load(self.region_id)
        # Fallback: Redis-only
        data = await self.redis.get(self._get_redis_key())
        if not data:
            return None, None, {}
        state_data = json.loads(data)
        return (
            np.array(state_data['x']),
            np.array(state_data['P']),
            state_data.get('meta', {}),
        )

    async def save_state(
        self,
        x: np.ndarray,
        P: np.ndarray,
        meta: dict[str, Any],
        y_obs: np.ndarray | None = None,
        innovation: np.ndarray | None = None,
        chi2: float | None = None,
    ):
        """Save filter state. Uses PersistentFilterState (Postgres+Redis) if available,
        else falls back to Redis-only."""
        if self.persistent_state is not None:
            await self.persistent_state.save(
                self.region_id, x, P, meta, y_obs, innovation, chi2
            )
            return
        # Fallback: Redis-only
        state_data = {
            'x': x.tolist(),
            'P': P.tolist(),
            'meta': meta,
            'updated_at': datetime.now(UTC).isoformat(),
        }
        await self.redis.setex(self._get_redis_key(), 604800, json.dumps(state_data))

    def _construct_obs_vector(self, observations: dict[str, Any], meta: dict[str, Any]) -> np.ndarray:
        y = np.full(5, np.nan)
        y[0] = observations.get('app_reports', np.nan)
        y[1] = observations.get('confirmed_cases', np.nan)
        y[2] = observations.get('hospital_admissions', np.nan)
        y[3] = observations.get('pharmacy_proxy', np.nan)
        y[4] = observations.get('wastewater', np.nan)
        return y

    async def process_observation(self, params: SEIRParams, observations: dict[str, Any]):
        x_est, P, meta = await self.load_state()

        if x_est is None:
            x_est, P, meta = self.service.initialize_state(params)

        y_obs = self._construct_obs_vector(observations, meta)
        H = self.service.get_obs_matrices(x_est, params)
        Q, R = self.service.get_noise_matrices(x_est, params, y_obs, meta)

        filter_type = meta.get('mode', 'ekf')
        cusum = meta.get('cusum', 0.0)
        innovation: np.ndarray | None = None
        chi2: float | None = None
        if filter_type == 'ekf':
            ekf = SEIR_EKF(params, Q, R, H)
            x_upd, P_upd, innovation, chi2 = ekf.step(x_est, P, y_obs)
            nu = chi2 / len(innovation) if len(innovation) > 0 else 0
            new_cusum = max(0, cusum + nu - 0.5)
            fail_count = meta.get('fail_count', 0)
            if chi2 > self.ekf_threshold:
                fail_count += 1
            else:
                fail_count = 0
            if fail_count >= self.failure_limit:
                filter_type = 'particle'
                logger.warning("EKF failed, switching to PF", region_id=self.region_id, chi2=chi2)

        if filter_type == 'particle':
            pf = ParticleFilter(10000, params, Q, R, H)
            pf.initialize(x_est, P)
            x_upd, var_upd = pf.step(y_obs)
            P_upd = np.diag(var_upd)
            new_cusum = 0.0
            fail_count = 0

        # Save state (Postgres-backed when session_maker provided; else Redis-only)
        meta.update({'cusum': new_cusum, 'fail_count': fail_count, 'mode': filter_type})
        last_innovation = innovation if filter_type == 'ekf' else None
        last_chi2 = chi2 if filter_type == 'ekf' else None
        await self.save_state(
            x_upd, P_upd, meta,
            y_obs=y_obs,
            innovation=last_innovation,
            chi2=last_chi2,
        )
        keys = ['S', 'E', 'IA', 'IM', 'IS', 'H', 'ICU', 'R', 'D']
        result = FilterResult(
            region_id=self.region_id,
            timestamp=datetime.now(UTC).isoformat(),
            filter_type=filter_type,
            state={k: float(x_upd[i]) for i, k in enumerate(keys)},
            variance={k: float(P_upd[i, i]) for i, k in enumerate(keys)},
            obs_params={'papp': float(x_upd[9]), 'ptest': float(x_upd[10]), 'kappa': float(x_upd[11])},
            cusum_score=float(new_cusum),
            model_alert=bool(new_cusum > self.cusum_threshold)
        )

        if self.producer is not None:
            from shared.kafka import publish_kafka

            await publish_kafka(self.producer, settings.kafka_topic_updates,
                                json.dumps(asdict(result)).encode(), timeout=5.0)
        return result
