
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from shared.security import SecurityHeadersMiddleware


@pytest.mark.asyncio
async def test_security_headers():
    app = FastAPI()
    app.add_middleware(SecurityHeadersMiddleware)

    @app.get("/")
    async def index():
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        response = await ac.get("/")
        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["X-XSS-Protection"] == "1; mode=block"
        assert response.headers["Strict-Transport-Security"] == "max-age=31536000; includeSubDomains"
        assert response.headers["Content-Security-Policy"] == "default-src 'none'; frame-ancestors 'none'"
