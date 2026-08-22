
import pytest
from sqlalchemy import text

from shared.config import Settings
from shared.db import create_session_factory, get_db


@pytest.mark.asyncio
async def test_db_session_factory():
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
    _engine, session_factory = create_session_factory(settings)

    async with session_factory() as session:
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1

@pytest.mark.asyncio
async def test_get_db_yields_session():
    settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
    _engine, session_factory = create_session_factory(settings)

    async for session in get_db(session_factory):
        result = await session.execute(text("SELECT 1"))
        assert result.scalar() == 1


def test_db_outage_handler_maps_operational_error_to_503():
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
