"""Shared async database session management.

`create_session_factory` builds an engine + sessionmaker from a settings object;
`get_db` yields a session with configurable auto-commit behavior. All services
use the same factory so engine/session semantics stay consistent.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from shared.config import Settings


def create_session_factory(
    settings: Settings,
    *,
    auto_commit: bool = False,
    pool_size: int = 10,
    max_overflow: int = 20,
) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """Build an engine and sessionmaker bound to a service's settings.

    Pool args are only passed for non-sqlite URLs (sqlite uses a StaticPool
    and rejects pool_size/max_overflow).
    """
    engine_kwargs: dict = {"echo": settings.debug, "pool_pre_ping": True}
    if not settings.database_url.startswith("sqlite"):
        engine_kwargs.update(pool_size=pool_size, max_overflow=max_overflow)
    engine = create_async_engine(settings.database_url, **engine_kwargs)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory


async def get_db(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    auto_commit: bool = False,
) -> AsyncIterator[AsyncSession]:
    """Yield a session, rolling back and re-raising on failure.

    With `auto_commit=True` the session commits on successful exit (used by
    services whose endpoints do not explicitly commit). Otherwise callers own
    the transaction lifecycle.
    """
    async with session_factory() as session:
        try:
            yield session
            if auto_commit:
                await session.commit()
        except Exception:
            await session.rollback()
            raise


# Module-level dependency generator used by FastAPI routers. Services create one
# instance per app and bind it via `app.dependency_overrides` in tests.
class SessionProvider:
    def __init__(self, settings: Settings, *, auto_commit: bool = False):
        self.engine, self.session_factory = create_session_factory(settings, auto_commit=auto_commit)

    async def dependency(self) -> AsyncGenerator[AsyncSession, None]:
        async with self.session_factory() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise
