from fastapi import FastAPI, Depends
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
        return response
from src.api.routers import dp, fl
import redis.asyncio as redis
import os

from src.dp.budget import BudgetTracker
from src.config import settings

app = FastAPI(title="CyberEpi Privacy Service")
app.add_middleware(SecurityHeadersMiddleware)

@app.on_event("startup")
async def startup():
    app.state.redis = redis.from_url(settings.redis_url)
    app.state.budget_tracker = BudgetTracker(app.state.redis, max_budget=settings.max_privacy_budget)

app.include_router(dp.router, prefix="/internal/dp", tags=["DP"])
app.include_router(fl.router, prefix="/api/v1/fl", tags=["FL"])

@app.get("/health")
async def health():
    return {"status": "healthy"}
