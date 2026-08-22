"""Shared infrastructure connection helpers.

`connect_redis` / `connect_kafka` retry with exponential backoff (bounded at 5
attempts) so services tolerate slow infra startup. `disconnect_*` shut down
with strict timeouts so the app never hangs on shutdown.
"""

from __future__ import annotations

import asyncio

import redis.asyncio as aioredis
import structlog
from aiokafka import AIOKafkaProducer

from shared.config import Settings

logger = structlog.get_logger()

MAX_ATTEMPTS = 5


async def connect_redis(settings: Settings, timeout: float = 5.0) -> aioredis.Redis:
    """Connect to Redis with bounded retries. Raises after MAX_ATTEMPTS."""
    for i in range(MAX_ATTEMPTS):
        try:
            client = aioredis.from_url(settings.redis_url, decode_responses=True)
            await asyncio.wait_for(client.ping(), timeout=timeout)
            logger.info("Redis connected")
            return client
        except Exception as e:
            if i == MAX_ATTEMPTS - 1:
                raise
            logger.warning("Redis connection failed, retrying", error=str(e), attempt=i + 1)
            await asyncio.sleep(min(2**i, 10))
    raise RuntimeError("Redis connection failed")  # pragma: no cover


async def connect_kafka(settings: Settings, timeout: float = 10.0) -> AIOKafkaProducer:
    """Start a Kafka producer with bounded retries. Raises after MAX_ATTEMPTS."""
    for i in range(MAX_ATTEMPTS):
        try:
            producer = AIOKafkaProducer(bootstrap_servers=settings.kafka_bootstrap_servers)
            await asyncio.wait_for(producer.start(), timeout=timeout)
            logger.info("Kafka producer started")
            return producer
        except Exception as e:
            if i == MAX_ATTEMPTS - 1:
                raise
            logger.warning("Kafka connection failed, retrying", error=str(e), attempt=i + 1)
            await asyncio.sleep(min(2**i, 10))
    raise RuntimeError("Kafka connection failed")  # pragma: no cover


async def disconnect_redis(client: aioredis.Redis | None, timeout: float = 5.0) -> None:
    if client is None:
        return
    try:
        await asyncio.wait_for(client.aclose(), timeout=timeout)
    except TimeoutError:
        logger.error("Redis shutdown timed out")


async def publish_kafka(
    producer: AIOKafkaProducer,
    topic: str,
    value: bytes,
    timeout: float = 5.0,
) -> None:
    """Send-and-wait with a hard timeout so a dead broker can never wedge a
    request handler. Raises TimeoutError or the underlying producer error;
    callers decide whether to tolerate it."""
    await asyncio.wait_for(producer.send_and_wait(topic, value), timeout=timeout)


async def disconnect_kafka(producer: AIOKafkaProducer | None, timeout: float = 10.0) -> None:
    if producer is None:
        return
    try:
        await asyncio.wait_for(producer.stop(), timeout=timeout)
    except TimeoutError:
        logger.error("Kafka shutdown timed out")
