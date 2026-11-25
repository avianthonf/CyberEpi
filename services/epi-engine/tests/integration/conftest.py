"""Keep API integration tests isolated from application infrastructure startup.

Container tests explicitly supply their own PostgreSQL and Redis connections.
Mock-backed API tests supply dependency overrides. Neither should run the
production lifespan, migrations, or background consumers during TestClient use.
The separately verified Compose workflow covers those startup paths.
"""

import os
from contextlib import asynccontextmanager

import pytest

# Engines are constructed while test modules are imported, before fixtures run.
# These syntactically valid placeholders are never contacted by this suite.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test")
os.environ.setdefault("REDIS_URL", "redis://localhost/0")


@pytest.fixture(autouse=True)
def isolated_api_lifespan(monkeypatch):
    """Patch the existing app, preserving imported references and real routes."""
    from src.main import app

    @asynccontextmanager
    async def integration_lifespan(application):
        yield

    monkeypatch.setattr(app.router, "lifespan_context", integration_lifespan)
