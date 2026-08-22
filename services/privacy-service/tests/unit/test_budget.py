from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
import redis.asyncio as redis

from src.dp.budget import BudgetTracker


@pytest_asyncio.fixture
async def mock_redis():
    mock = AsyncMock(spec=redis.Redis)
    return mock

@pytest.mark.asyncio
async def test_budget_consume_success(mock_redis):
    tracker = BudgetTracker(mock_redis, max_budget=10.0)

    # Use an async side_effect to ensure it's awaitable
    async def mock_eval(*args, **kwargs):
        return 1
    mock_redis.eval.side_effect = mock_eval

    success = await tracker.consume("user1", 0.5)
    assert success is True
    assert mock_redis.eval.called

@pytest.mark.asyncio
async def test_budget_exhausted_returns_false(mock_redis):
    tracker = BudgetTracker(mock_redis, max_budget=1.0)

    async def mock_eval_fail(*args, **kwargs):
        return 0
    mock_redis.eval.side_effect = mock_eval_fail

    success = await tracker.consume("user1", 1.5)
    assert success is False

@pytest.mark.asyncio
async def test_get_remaining(mock_redis):
    tracker = BudgetTracker(mock_redis, max_budget=10.0)

    async def mock_get(*args, **kwargs):
        return b"4.5"
    mock_redis.get.side_effect = mock_get

    remaining = await tracker.get_remaining("user1")
    assert remaining == 5.5
