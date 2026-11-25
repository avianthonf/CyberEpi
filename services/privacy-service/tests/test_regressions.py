"""Regression tests for ISS-02 FL round persistence.

Real async SQLAlchemy with aiosqlite for isolated DB testing.
"""

import numpy as np
import pytest
import pytest_asyncio
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import Base, FLRound
from src.federated.aggregator import FedAvgAggregator


@pytest_asyncio.fixture
async def async_db_session():
    """In-memory async SQLite session for isolated FL persistence tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    # Create tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    yield session_maker

    await engine.dispose()


class TestIss02FLRoundPersistence:
    """ISS-02: FL workflow must persist completed rounds and restore state after restart."""

    @pytest.mark.asyncio
    async def test_completed_round_persists_to_db(self, async_db_session):
        """Aggregated round must persist to fl_rounds table and survive 'restart'."""
        aggregator = FedAvgAggregator(
            model_dim=5,
            min_clients=2,
            session_maker=async_db_session,
        )
        await aggregator.initialize_from_db()

        # Upload 2 gradients
        g1 = np.array([0.1, 0.2, 0.3, 0.4, 0.5])
        g2 = np.array([0.2, 0.3, 0.4, 0.5, 0.6])
        aggregator.receive_gradient(g1, client_id="client1")
        aggregator.receive_gradient(g2, client_id="client2")

        # Trigger aggregation with persistence
        completed_round_id = aggregator.current_round_id
        result = await aggregator.aggregate(C=1.0, epsilon=0.5)

        assert completed_round_id == 1
        assert result.shape == (5,)

        # Verify DB persistence
        async with async_db_session() as session:
            from sqlalchemy import select

            db_result = await session.execute(select(FLRound).where(FLRound.round_id == 1))
            fl_round = db_result.scalar_one()
            assert fl_round.round_id == 1
            assert fl_round.num_clients == 2
            assert isinstance(fl_round.model_params, list)
            assert len(fl_round.model_params) == 5
            assert isinstance(fl_round.aggregation_config, dict)
            assert fl_round.aggregation_config["C"] == 1.0
            assert fl_round.aggregation_config["epsilon"] == 0.5

        # Simulate restart: create new aggregator with same session_maker
        aggregator2 = FedAvgAggregator(
            model_dim=5,
            min_clients=2,
            session_maker=async_db_session,
        )
        await aggregator2.initialize_from_db()

        # Should restore current_round_id from DB
        assert aggregator2.current_round_id == 2, "Should advance to next round after round 1 completed"

        # Should be able to fetch completed round 1 from DB
        cached = await aggregator2.get_completed_model(1)
        assert cached is not None
        assert cached.shape == (5,)
        # Verify actual values match persisted model
        np.testing.assert_array_almost_equal(cached, np.asarray(fl_round.model_params), decimal=10)

    @pytest.mark.asyncio
    async def test_multiple_rounds_increment_correctly(self, async_db_session):
        """Rounds must increment monotonically: 1 → 2 → 3."""
        aggregator = FedAvgAggregator(
            model_dim=3,
            min_clients=2,
            session_maker=async_db_session,
        )
        await aggregator.initialize_from_db()

        assert aggregator.current_round_id == 1

        # Complete round 1
        aggregator.receive_gradient(np.array([1.0, 2.0, 3.0]), "c1")
        aggregator.receive_gradient(np.array([1.0, 2.0, 3.0]), "c2")
        r1_id = aggregator.current_round_id
        await aggregator.aggregate(C=1.0, epsilon=0.5)
        assert r1_id == 1

        aggregator.start_new_round()
        assert aggregator.current_round_id == 2

        # Complete round 2
        aggregator.receive_gradient(np.array([2.0, 3.0, 4.0]), "c1")
        aggregator.receive_gradient(np.array([2.0, 3.0, 4.0]), "c2")
        r2_id = aggregator.current_round_id
        await aggregator.aggregate(C=1.0, epsilon=0.5)
        assert r2_id == 2

        aggregator.start_new_round()
        assert aggregator.current_round_id == 3

    @pytest.mark.asyncio
    async def test_db_failure_does_not_create_phantom_completed_round(self, async_db_session):
        """If DB persistence fails, completed_models must not be updated (no phantom cache)."""
        aggregator = FedAvgAggregator(
            model_dim=3,
            min_clients=2,
            session_maker=async_db_session,
        )
        await aggregator.initialize_from_db()

        # Upload gradients
        aggregator.receive_gradient(np.array([1.0, 2.0, 3.0]), "c1")
        aggregator.receive_gradient(np.array([1.0, 2.0, 3.0]), "c2")

        # Close the engine to simulate DB failure
        await async_db_session.kw["bind"].dispose()

        # Attempt aggregation should fail (DB commit fails)
        with pytest.raises(OperationalError):
            await aggregator.aggregate(C=1.0, epsilon=0.5)

        # completed_models must NOT contain round 1 (no phantom cache)
        assert 1 not in aggregator.completed_models
