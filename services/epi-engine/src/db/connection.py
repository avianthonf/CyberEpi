"""Async database connection for epi-engine — shared via libs/shared."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from shared.db import create_session_factory
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings

engine, AsyncSessionLocal = create_session_factory(settings)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding an async session."""
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
