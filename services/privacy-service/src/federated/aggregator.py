"""FedAvg aggregator with database-backed round persistence."""

import asyncio

import numpy as np
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from src.dp.mechanisms import vector_gaussian_mechanism


class FedAvgAggregator:
    """FedAvg aggregator with explicit round lifecycle and DB persistence.

    - `current_round_id`: monotonically increasing integer tracking which
      round is currently accepting uploads. Defaults to 1 on first init;
      `start_new_round()` increments and clears in-memory gradients.
    - `completed_models`: dict[round_id, np.ndarray] of aggregated
      update vectors keyed by round id, so late GETs against any past
      round still work in-memory until process restart.
    - DB persistence: completed rounds stored in fl_rounds; restored on startup.
    - `_round_lock`: asyncio.Lock protecting round lifecycle (upload, aggregate, advance).
    """

    def __init__(
        self,
        model_dim: int,
        min_clients: int = 10,
        session_maker: sessionmaker | None = None,
    ):
        self.model_dim = model_dim
        self.min_clients = min_clients
        self.session_maker = session_maker
        self.current_round_id: int = 1
        self.current_round_gradients: list[np.ndarray] = []
        self.current_round_clients: set[str] = set()
        self.global_model: np.ndarray | None = np.zeros(model_dim)
        self.completed_models: dict[int, np.ndarray] = {}
        self._round_lock = asyncio.Lock()

    async def initialize_from_db(self):
        """Restore current_round_id from the highest stored round in DB.
        Called once during app startup after session_maker is available."""
        if self.session_maker is None:
            return

        from src.db.models import FLRound

        async with self.session_maker() as session:
            result = await session.execute(select(FLRound.round_id).order_by(FLRound.round_id.desc()).limit(1))
            max_round = result.scalar()
            if max_round is not None:
                self.current_round_id = max_round + 1

    async def _load_round_from_db(self, round_id: int) -> np.ndarray | None:
        """Load a completed round's model from DB. Returns None if not found."""
        if self.session_maker is None:
            return None

        from src.db.models import FLRound

        async with self.session_maker() as session:
            result = await session.execute(select(FLRound).where(FLRound.round_id == round_id))
            fl_round = result.scalar_one_or_none()
            if fl_round is None:
                return None
            # model_params is JSONB column storing list directly
            return np.asarray(fl_round.model_params)

    async def _persist_round(
        self,
        round_id: int,
        model: np.ndarray,
        num_clients: int,
        aggregation_config: dict,
    ):
        """Persist a completed round to the database."""
        if self.session_maker is None:
            return

        from datetime import UTC, datetime

        from src.db.models import FLRound

        async with self.session_maker() as session, session.begin():
            fl_round = FLRound(
                round_id=round_id,
                completed_at=datetime.now(UTC),
                num_clients=num_clients,
                model_params=model.tolist(),  # JSONB column stores list directly
                aggregation_config=aggregation_config,  # JSONB column stores dict directly
            )
            session.add(fl_round)

    async def get_completed_model(self, round_id: int) -> np.ndarray | None:
        """Retrieve a completed round's model (in-memory cache or DB)."""
        if round_id in self.completed_models:
            return self.completed_models[round_id]

        # Cache miss: try loading from DB
        model = await self._load_round_from_db(round_id)
        if model is not None:
            self.completed_models[round_id] = model
        return model

    def start_new_round(self):
        """Close current round (caller must aggregate first), open next one."""
        self.current_round_id += 1
        self.current_round_gradients = []
        self.current_round_clients = set()

    def reset_to_round(self, round_id: int):
        """Hard reset to a specific round id (test / recovery path)."""
        self.current_round_id = round_id
        self.current_round_gradients = []
        self.current_round_clients = set()

    def has_submitted(self, client_id: str) -> bool:
        """True if this client already uploaded in the current round."""
        return client_id in self.current_round_clients

    def validate_gradient(self, gradient: np.ndarray):
        """Pure validation. Raises ValueError on malformed input. No mutation."""
        if gradient.shape[0] != self.model_dim:
            raise ValueError(f"Gradient dimension mismatch. Expected {self.model_dim}, got {gradient.shape[0]}")
        if not np.all(np.isfinite(gradient)):
            raise ValueError("Gradient contains non-finite values (NaN/Inf)")
        if np.linalg.norm(gradient) > 1e6:
            raise ValueError("Gradient norm exceeds safety threshold")

    def receive_gradient(self, gradient: np.ndarray, client_id: str):
        """Validate and append gradient. Caller must have already
        checked `has_submitted` and budget."""
        self.validate_gradient(gradient)
        if client_id in self.current_round_clients:
            raise ValueError(f"Client {client_id} already submitted to round {self.current_round_id}")
        self.current_round_gradients.append(gradient)
        self.current_round_clients.add(client_id)

    async def aggregate(
        self,
        C: float,
        epsilon: float,
        delta: float = 1e-5,
    ) -> np.ndarray:
        """Run FedAvg on the current round's gradients with DB persistence.

        Per the algorithm:
            theta_new = theta_old + (1/K) * sum(DP(clipped(delta_theta_i)))

        Raises ValueError if fewer than min_clients gradients were received —
        aggregating on too few clients leaks information and is not honest.

        Persists to DB first, then updates in-memory state atomically.
        """
        K = len(self.current_round_gradients)
        if K == 0:
            return np.zeros(self.model_dim)
        if self.min_clients > K:
            raise ValueError(f"Not enough gradients to aggregate: {K} < min_clients {self.min_clients}")

        # 1. Clip and noise each gradient
        noised_gradients = []
        for g in self.current_round_gradients:
            g_dp = vector_gaussian_mechanism(g, C, epsilon, delta)
            noised_gradients.append(g_dp)

        # 2. Average
        aggregated_update = np.mean(noised_gradients, axis=0)

        num_clients = K
        completed_round_id = self.current_round_id

        # 3. Persist to database FIRST before updating in-memory state
        await self._persist_round(
            round_id=completed_round_id,
            model=aggregated_update,
            num_clients=num_clients,
            aggregation_config={"C": C, "epsilon": epsilon, "delta": delta},
        )

        # 4. Only after successful DB commit: cache result and update global model
        self.completed_models[self.current_round_id] = aggregated_update
        self.global_model = self.global_model + aggregated_update

        return aggregated_update
