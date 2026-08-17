"""Async database session management — shared via libs/shared."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from shared.db import create_session_factory
from sqlalchemy.ext.asyncio import AsyncSession

from src.config import settings

engine, async_session_factory = create_session_factory(settings)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session."""
    async with async_session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
