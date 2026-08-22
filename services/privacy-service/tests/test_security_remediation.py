from unittest.mock import AsyncMock

import pytest

# Test Privacy Budget Enforcement (privacy-service)
from src.dp.budget import BudgetTracker


@pytest.mark.asyncio
async def test_privacy_budget_exhaustion():
    """Verify that budget exhaustion blocks consumption."""
    mock_redis = AsyncMock()
    # Mock eval to return 1 then 0
    mock_redis.eval.side_effect = [1, 1, 0] # Success, Success, Fail

    tracker = BudgetTracker(mock_redis, max_budget=1.0)
    user_id = "test-user"

    assert await tracker.consume(user_id, 0.5) is True
    assert await tracker.consume(user_id, 0.5) is True
    assert await tracker.consume(user_id, 0.1) is False # Should fail

def test_simple_sync():
    assert True
