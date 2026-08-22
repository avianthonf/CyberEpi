
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from shared.config import Settings
from shared.kafka import connect_kafka


@pytest.mark.asyncio
async def test_kafka_connection():
    with patch("shared.kafka.AIOKafkaProducer") as mock_producer_class:
        mock_producer = MagicMock()
        mock_producer.start = AsyncMock()
        mock_producer_class.return_value = mock_producer

        producer = await connect_kafka(Settings(kafka_bootstrap_servers="localhost:9092"))
        assert producer == mock_producer
        mock_producer.start.assert_called_once()

@pytest.mark.asyncio
async def test_redis_connection():
    from shared.kafka import connect_redis
    with patch("shared.kafka.aioredis.from_url") as mock_redis_from_url:
        mock_redis = MagicMock()
        mock_redis.ping = AsyncMock()
        mock_redis_from_url.return_value = mock_redis

        redis = await connect_redis(Settings(redis_url="redis://localhost:6379"))
        assert redis == mock_redis
        mock_redis.ping.assert_called_once()
