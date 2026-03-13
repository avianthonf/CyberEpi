
import sys
import os
sys.path.append("services/epi-engine")

print("Checking imports...")
try:
    import pytest
    print("pytest: OK")
    import pytest_asyncio
    print("pytest_asyncio: OK")
    import httpx
    print("httpx: OK")
    from testcontainers.postgres import PostgresContainer
    print("testcontainers.postgres: OK")
    from testcontainers.redis import RedisContainer
    print("testcontainers.redis: OK")
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    print("sqlalchemy.ext.asyncio: OK")
    from sqlalchemy.orm import sessionmaker
    print("sqlalchemy.orm: OK")
    from src.config import settings
    print("src.config: OK")
    from src.main import app
    print("src.main: OK")
    import redis.asyncio as aioredis
    print("redis.asyncio: OK")
    print("ALL IMPORTS SUCCESSFUL")
except ImportError as e:
    print(f"IMPORT ERROR: {e}")
    import traceback
    traceback.print_exc()
except Exception as e:
    print(f"OTHER ERROR: {e}")
    import traceback
    traceback.print_exc()
