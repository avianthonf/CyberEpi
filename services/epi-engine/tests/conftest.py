import os
import sys
from unittest.mock import AsyncMock, MagicMock

# Force TESTING environment for all tests
os.environ["TESTING"] = "1"

# Create a robust mock for aiokafka to be used via sys.modules
mock_producer_class = MagicMock()
mock_instance = mock_producer_class.return_value
mock_instance.start = AsyncMock()
mock_instance.stop = AsyncMock()
mock_instance.send_and_wait = AsyncMock()

# Mock the entire aiokafka module before anything else imports it
aiokafka_mock = MagicMock()
aiokafka_mock.AIOKafkaProducer = mock_producer_class
# `from aiokafka.errors import KafkaError` needs a real submodule whose
# names are usable in `except` clauses.
aiokafka_errors_mock = MagicMock()
aiokafka_errors_mock.KafkaError = type("KafkaError", (Exception,), {})
sys.modules["aiokafka"] = aiokafka_mock
sys.modules["aiokafka.errors"] = aiokafka_errors_mock

import pytest


@pytest.fixture(autouse=True)
def mock_kafka_fixture():
    """Ensure the mock is available to tests if needed."""
    return mock_instance

@pytest.fixture(autouse=True)
def mock_redis(mocker):
    """Globally mock aioredis/redis.asyncio for all tests."""
    mock_redis_client = AsyncMock()
    # Explicitly set get() to return None for cache miss by default
    mock_redis_client.get = AsyncMock(return_value=None)
    # from_url is a sync function that returns the client
    mocker.patch("redis.from_url", return_value=mock_redis_client)
    mocker.patch("redis.asyncio.from_url", return_value=mock_redis_client)
    return mock_redis_client
