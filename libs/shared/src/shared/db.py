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

    Installs a do_connect listener to intercept raw asyncpg connection failures
    at the driver boundary and convert them to OperationalError.
    """
    import socket

    from sqlalchemy import event
    from sqlalchemy.exc import OperationalError

    engine_kwargs: dict = {"echo": settings.debug, "pool_pre_ping": True}
    if not settings.database_url.startswith("sqlite"):
        engine_kwargs.update(pool_size=pool_size, max_overflow=max_overflow)
    engine = create_async_engine(settings.database_url, **engine_kwargs)

    def _wrap_db_connection_errors(dialect, conn_rec, cargs, cparams):
        """Intercept raw connection errors at driver boundary and convert to OperationalError.

        asyncpg raises socket.gaierror, ConnectionRefusedError, TimeoutError during
        connection attempts. These are raw Python OSError subclasses that escape
        SQLAlchemy's normal exception wrapping.

        This listener wraps dialect.connect() and catches ONLY database connection
        errors, converting them to OperationalError so the global handler maps to 503.

        Non-database network errors (Kafka, Redis, HTTP clients) are unaffected
        since they never touch this code path.
        """
        try:
            return dialect.connect(*cargs, **cparams)
        except (socket.gaierror, ConnectionRefusedError, TimeoutError) as exc:
            raise OperationalError(
                statement=None,
                params=None,
                orig=exc,
            ) from exc

    event.listen(engine.sync_engine, "do_connect", _wrap_db_connection_errors)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory


async def get_db(
    session_factory: async_sessionmaker[AsyncSession],
    *,
    auto_commit: bool = False,
) -> AsyncIterator[AsyncSession]:
    """Yield a session, rolling back and re-raising on failure.

    Meant for use as a FastAPI dependency, so commit/rollback on success/error
    stay explicit. Set `auto_commit=True` if the dependency should commit before
    returning.
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


async def create_all_on_startup(engine: AsyncEngine, base) -> None:
    """Create every table owned by ``base.metadata`` if it doesn't exist.

    This is a dev-time convenience so the API doesn't 500 on first boot. In
    production each service should run `alembic upgrade head` instead and
    skip this helper.
    """
    async with engine.begin() as conn:
        await conn.run_sync(base.metadata.create_all)


async def _db_outage_handler(request, exc):
    """Database connectivity failure -> 503 (dependency outage), not 500 (bug).

    Only ``OperationalError`` is handled here. Raw connection exceptions
    (socket.gaierror, ConnectionRefusedError, TimeoutError) are converted to
    OperationalError at the driver boundary in create_session_factory().

    Application errors remain unhandled:
    - ``IntegrityError``, ``DataError``, ``ProgrammingError``: SQL/data issues -> 500
    - All other exceptions: application bugs -> 500

    Response contains no connection details for security.
    """
    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=503, content={"detail": "Database temporarily unavailable"})


def install_db_outage_handler(app) -> None:
    """Map database OperationalError to clean 503.

    Raw asyncpg connection errors (socket.gaierror, ConnectionRefusedError, TimeoutError)
    are converted to OperationalError at the driver boundary via do_connect listener in
    create_session_factory(), ensuring only database connection failures map to 503.

    Non-database network errors (Kafka, Redis, HTTP clients) remain unaffected.
    """
    from sqlalchemy.exc import OperationalError

    app.add_exception_handler(OperationalError, _db_outage_handler)
