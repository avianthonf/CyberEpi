import socket

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from shared.config import Settings
from shared.db import create_session_factory, get_db


@pytest.mark.asyncio
async def test_db_session_factory():
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
    engine, session_factory = create_session_factory(settings)

    try:
        async with session_factory() as session:
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_get_db_yields_session():
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
    engine, session_factory = create_session_factory(settings)

    try:
        async for session in get_db(session_factory):
            result = await session.execute(text("SELECT 1"))
            assert result.scalar() == 1
    finally:
        await engine.dispose()


def test_db_outage_handler_maps_operational_error_to_503():
    """OperationalError (SQLAlchemy-wrapped DB errors) -> 503."""
    from sqlalchemy.exc import IntegrityError, OperationalError
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from shared.db import install_db_outage_handler

    async def boom(request):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    async def dup(request):
        raise IntegrityError("INSERT", {}, Exception("duplicate key"))

    app = Starlette(routes=[Route("/down", boom), Route("/dup", dup)])
    install_db_outage_handler(app)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/down")
    assert resp.status_code == 503
    assert resp.json() == {"detail": "Database temporarily unavailable"}

    # IntegrityError (data bug / duplicate input) must NOT be masked as an outage.
    resp = client.get("/dup")
    assert resp.status_code == 500


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw_exception",
    [
        socket.gaierror(-3, "Temporary failure in name resolution"),
        ConnectionRefusedError("Connection refused"),
        TimeoutError("Connection timed out"),
    ],
    ids=["socket.gaierror", "ConnectionRefusedError", "TimeoutError"],
)
async def test_raw_connection_failure_converts_to_operational_error(raw_exception):
    """do_connect listener converts raw driver exceptions to OperationalError at boundary.

    Monkeypatches dialect.connect() to raise raw connection exceptions, verifying
    the do_connect listener catches them and converts to OperationalError without
    external network calls.
    """
    from unittest.mock import MagicMock

    settings = Settings(database_url="postgresql+asyncpg://fake:fake@localhost:5432/fake")
    engine, session_factory = create_session_factory(settings)

    # Monkeypatch dialect.connect to raise the raw exception
    original_connect = engine.sync_engine.dialect.connect
    engine.sync_engine.dialect.connect = MagicMock(side_effect=raw_exception)

    try:
        # Attempt connection - should raise OperationalError, not raw exception
        try:
            async with session_factory() as session:
                await session.execute(text("SELECT 1"))
            raise AssertionError("Should have raised OperationalError")
        except OperationalError as e:
            # Verify the original exception is preserved
            assert e.orig is raw_exception, f"Expected {raw_exception}, got {e.orig}"
        except type(raw_exception):
            raise AssertionError(f"{type(raw_exception).__name__} should have been wrapped") from None
    finally:
        engine.sync_engine.dialect.connect = original_connect
        await engine.dispose()


def test_non_db_socket_gaierror_remains_500():
    """socket.gaierror from non-DB sources (Kafka, Redis, HTTP) -> 500, not 503.

    Regression test ensuring only DB connection errors map to 503.
    """
    from starlette.applications import Starlette
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from shared.db import install_db_outage_handler

    async def kafka_dns_failure(request):
        """Simulates Kafka broker DNS failure - NOT a database error."""
        raise socket.gaierror(-3, "kafka-broker.invalid")

    app = Starlette(routes=[Route("/kafka", kafka_dns_failure)])
    install_db_outage_handler(app)
    client = TestClient(app, raise_server_exceptions=False)

    resp = client.get("/kafka")
    assert resp.status_code == 500, "Non-DB socket.gaierror must remain 500, not 503"
