"""Contract tests for epi-engine.

Covers:
- EpiParams / ForecastCache DB model contracts
- Params API (GET/PUT)
- Forecast API (inline mode, horizon validation)
- Region state API (Redis-backed)
- Control weights API (GET/PUT, role enforcement)
- ControlWeightsIn schema validation

Run with:
  cd /home/avinash/Projects/CyberEpi
  .venv/bin/python -m pytest services/epi-engine/tests/test_contracts.py -v
"""

from __future__ import annotations

import os
import sys

# ── Path setup + env: must happen before any src.* import ────────────────────
# src.db.connection creates an engine from settings.database_url at module
# level.  Set a valid (but unused) URL so the import does not crash.
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")

_SVC_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SVC_SRC not in sys.path:
    sys.path.insert(0, _SVC_SRC)
# ── SQLite compat: replace PG UUID/JSONB/JSON on all mapped tables ────────────
#
# Must run at module-import time — before SQLAlchemy compiles and caches any
# statement with the old PG type processors.

import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import String, TypeDecorator

from src.db.models import Base


class _UUIDStr(TypeDecorator):
    """TEXT-backed UUID for SQLite: coerces uuid.UUID on bind."""

    impl = String
    cache_ok = True

    def __init__(self):
        super().__init__(36)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        return value


def _sqlite_compat():
    for tbl in Base.metadata.tables.values():
        for col in tbl.columns:
            if isinstance(col.type, PG_UUID):
                col.type = _UUIDStr()


_sqlite_compat()

# ── Remaining imports ─────────────────────────────────────────────────────────

import asyncio
import hashlib
import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.db.models import (
    ControlWeights,
    EpiParams,
    ForecastCache,
)
from src.models.parameters import RegionParams

DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _make_db():
    engine = create_async_engine(DATABASE_URL, echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _pragmas(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return engine


def _factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── Canonical valid EpiParams for tests ───────────────────────────────────────

_VALID_PARAMS = dict(
    region_id="region-test",
    source="manual_override",
    beta=0.3,
    sigma=0.2,
    gamma=0.1,
    rho=1.0,
    fA=0.4,
    fM=0.4,
    fS=0.2,
    alpha=0.05,
    h_rate=0.03,
    delta=0.01,
    mu=0.005,
    mu_icu=0.02,
    gamma_A=0.15,
    gamma_M=0.1,
    gamma_S=0.07,
    gamma_H=0.05,
    gamma_ICU=0.04,
    papp=0.12,
    N_pop=500_000,
)


def _make_epi_params(**overrides) -> EpiParams:
    """Build an EpiParams ORM object from _VALID_PARAMS with optional overrides."""
    kw = dict(_VALID_PARAMS)  # includes region_id and source
    kw.update(overrides)  # caller may override any field, including region_id
    return EpiParams(**kw)


# ── Auth / dependency helpers ─────────────────────────────────────────────────

ADMIN_USER = {"sub": str(uuid.uuid4()), "realm_access": {"roles": ["physician", "admin"]}}
PATIENT_USER = {"sub": str(uuid.uuid4()), "realm_access": {"roles": ["patient"]}}


def _build_params_app(fac, mock_redis=None):
    from src.api.routers.params import router as params_router
    from src.db.connection import get_db

    if mock_redis is None:
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)

    app = FastAPI()
    app.include_router(params_router)
    app.state.redis = mock_redis

    async def _db():
        async with fac() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    return app


def _build_forecast_app(fac, mock_redis=None):
    from src.api.routers.forecast import router as forecast_router
    from src.db.connection import get_db

    if mock_redis is None:
        mock_redis = AsyncMock()
        mock_redis.get = AsyncMock(return_value=None)
        mock_redis.setex = AsyncMock()

    app = FastAPI()
    app.include_router(forecast_router)
    app.state.redis = mock_redis

    async def _db():
        async with fac() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    return app


def _build_state_app(mock_redis):
    from src.api.routers.state import router as state_router

    app = FastAPI()
    app.include_router(state_router)
    app.state.redis = mock_redis
    return app


def _build_control_app(fac):
    from src.api.routers.control import router as control_router
    from src.db.connection import get_db

    app = FastAPI()
    app.include_router(control_router)

    async def _db():
        async with fac() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    return app


def _set_user(app, user):
    from src.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: user


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1 – EpiParams DB model contracts (tests 1–3)
# ═══════════════════════════════════════════════════════════════════════════


class TestEpiParamsModel:
    """A parameter record without a region must fail at the database boundary."""

    def test_region_id_required(self):
        # SQLAlchemy ORM won't raise on missing nullable=False at init time,
        # but it will fail at flush.  We test it at the DB level.
        async def _go():
            engine = await _make_db()
            fac = _factory(engine)
            try:
                async with fac() as s:
                    bad = EpiParams(**{k: v for k, v in _VALID_PARAMS.items() if k not in ("region_id", "source")})
                    # region_id left as None → should fail INSERT
                    bad.source = "manual_override"
                    s.add(bad)
                    with pytest.raises(sa.exc.IntegrityError):
                        await s.flush()
            finally:
                await engine.dispose()

        _run(_go())


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2 – Params API contracts (tests 4–7)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def params_db():
    async def _setup():
        engine = await _make_db()
        fac = _factory(engine)
        async with fac() as s:
            s.add(_make_epi_params())
            await s.commit()
        return engine, fac

    engine, fac = _run(_setup())
    yield engine, fac
    _run(engine.dispose())


# Test 4 – GET /{id}/params → 200 with RegionParams fields
def test_get_params_returns_200_with_all_fields(params_db):
    _, fac = params_db
    app = _build_params_app(fac)
    _set_user(app, ADMIN_USER)

    # Patch out the forecast side-effects triggered by PUT (not used here)
    resp = TestClient(app).get("/region-test/params")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    region_params_fields = RegionParams.model_fields.keys()
    for field in region_params_fields:
        if field == "updated_at":
            continue  # optional
        assert field in data, f"RegionParams field '{field}' missing from GET response"


# Test 5 – GET /{id}/params for non-existent region → 404
def test_get_params_nonexistent_region_returns_404(params_db):
    _, fac = params_db
    app = _build_params_app(fac)
    _set_user(app, ADMIN_USER)
    resp = TestClient(app).get("/does-not-exist/params")
    assert resp.status_code == 404


# Test 6 – PUT /{id}/params as patient → 403
def test_put_params_as_patient_returns_403(params_db):
    _, fac = params_db
    app = _build_params_app(fac)
    _set_user(app, PATIENT_USER)
    body = {k: v for k, v in _VALID_PARAMS.items()}
    with patch("src.tasks.celery_app._run_forecast_logic", new_callable=AsyncMock), patch("src.tasks.celery_app._forecast_task"):
        resp = TestClient(app).put("/region-test/params", json=body)
    assert resp.status_code == 403


# Test 7 – PUT /{id}/params as admin → 200; DB row updated
def test_put_params_as_admin_returns_200_and_updates_db(params_db):
    _, fac = params_db
    app = _build_params_app(fac)
    _set_user(app, ADMIN_USER)
    body = dict(_VALID_PARAMS)
    body["beta"] = 0.42  # change a rate

    # Patch names in the router module (they were imported at module load time)
    # and force run_forecast_inline=False so the Celery path is taken instead.
    mock_task = MagicMock()
    mock_task.delay = MagicMock()
    with (
        patch("src.api.routers.params._run_forecast_logic", new_callable=AsyncMock),
        patch("src.api.routers.params._forecast_task", mock_task),
        patch("src.config.settings") as ms,
    ):
        ms.run_forecast_inline = False
        resp = TestClient(app).put("/region-test/params", json=body)

    assert resp.status_code == 200, resp.text

    async def _check():
        async with fac() as s:
            from sqlalchemy import select

            result = await s.execute(select(EpiParams).where(EpiParams.region_id == "region-test"))
            return result.scalar_one_or_none()

    row = _run(_check())
    assert row is not None
    assert abs(row.beta - 0.42) < 1e-9


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3 – Forecast API contracts (tests 8–11)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def forecast_db():
    async def _setup():
        engine = await _make_db()
        fac = _factory(engine)
        async with fac() as s:
            s.add(_make_epi_params(region_id="forecast-region"))
            await s.commit()
        return engine, fac

    engine, fac = _run(_setup())
    yield engine, fac
    _run(engine.dispose())


async def _params_hash_async(region_id: str, fac) -> str:
    """Async version: compute the same params hash the API uses."""
    from sqlalchemy import select

    async with fac() as s:
        result = await s.execute(select(EpiParams).where(EpiParams.region_id == region_id))
        p = result.scalar_one()
        param_dict = {k: v for k, v in p.__dict__.items() if not k.startswith("_") and k not in ("id", "updated_at", "source")}
        return hashlib.sha256(json.dumps(param_dict, sort_keys=True).encode()).hexdigest()


def _params_hash(region_id: str, fac) -> str:
    """Sync version: used outside a running event loop."""
    return _run(_params_hash_async(region_id, fac))


# Test 8 – non-existent region → 404
def test_forecast_nonexistent_region_returns_404(forecast_db):
    _, fac = forecast_db
    app = _build_forecast_app(fac)
    _set_user(app, ADMIN_USER)
    resp = TestClient(app).get("/no-such-region/forecast")
    assert resp.status_code == 404


# Test 9 – seeded params + inline mode ON + mock _run_forecast_logic → ForecastResponse shape
def test_forecast_inline_mode_returns_forecast_response_shape(forecast_db):
    _, fac = forecast_db
    region_id = "forecast-region"

    async def _seed_cache(fac_ref, rid, horizon_days, ph):
        traj = {k: [0.0] * (horizon_days + 1) for k in ("t", "S", "E", "IA", "IM", "IS", "H", "ICU", "R", "D", "Load")}
        async with fac_ref() as s:
            s.add(
                ForecastCache(
                    region_id=rid,
                    horizon_days=horizon_days,
                    trajectory=traj,
                    params_hash=ph,
                    generated_at=datetime.now(UTC),
                )
            )
            await s.commit()

    async def _mock_run(rid, horizon_days):
        # Compute hash fully async — no nested _run() call
        ph = await _params_hash_async(region_id, fac)
        await _seed_cache(fac, rid, horizon_days, ph)

    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    mock_redis.setex = AsyncMock()

    app = _build_forecast_app(fac, mock_redis=mock_redis)
    _set_user(app, ADMIN_USER)

    # Patch the name in the router module (imported at load time)
    with (
        patch("src.api.routers.forecast._run_forecast_logic", side_effect=_mock_run),
        patch("src.api.routers.forecast._forecast_task"),
        patch("src.config.settings") as ms,
    ):
        ms.run_forecast_inline = True
        resp = TestClient(app).get(f"/{region_id}/forecast?horizon_days=7")

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["region_id"] == region_id
    assert data["horizon_days"] == 7
    assert "trajectory" in data


# Test 10 – horizon_days=0 → 422
def test_forecast_horizon_below_1_returns_422(forecast_db):
    _, fac = forecast_db
    app = _build_forecast_app(fac)
    _set_user(app, ADMIN_USER)
    resp = TestClient(app).get("/forecast-region/forecast?horizon_days=0")
    assert resp.status_code == 422


# Test 11 – horizon_days=43 → 422
def test_forecast_horizon_above_42_returns_422(forecast_db):
    _, fac = forecast_db
    app = _build_forecast_app(fac)
    _set_user(app, ADMIN_USER)
    resp = TestClient(app).get("/forecast-region/forecast?horizon_days=43")
    assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4 – Region state API contracts (tests 12–14)
# ═══════════════════════════════════════════════════════════════════════════


def _make_state_payload(cusum: float = 3.0) -> str:
    """Build a valid filter_state Redis payload."""
    x = [0.9, 0.01, 0.005, 0.005, 0.003, 0.002, 0.001, 0.06, 0.001, 0.12, 0.08, 1.0]
    P = [[0.001 if i == j else 0.0 for j in range(12)] for i in range(12)]
    return json.dumps(
        {
            "x": x,
            "P": P,
            "updated_at": datetime.now(UTC).isoformat(),
            "meta": {"mode": "ekf", "cusum": cusum},
        }
    )


def _state_client(redis_mock):
    app = _build_state_app(redis_mock)
    # state router uses get_current_user from src.auth
    from src.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: ADMIN_USER
    return TestClient(app)


# Test 12 – missing Redis key → 404
def test_state_missing_redis_key_returns_404():
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=None)
    resp = _state_client(mock_redis).get("/api/v1/regions/nonexistent/state")
    assert resp.status_code == 404


# Test 13 – valid Redis data → 200 with all required keys
def test_state_valid_redis_data_returns_200_with_keys():
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=_make_state_payload(cusum=3.0))

    resp = _state_client(mock_redis).get("/api/v1/regions/region-xyz/state")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["region_id"] == "region-xyz"
    assert "timestamp" in data
    assert "filter_type" in data
    assert "cusum_score" in data
    assert "model_alert" in data

    # state dict must have S/E/IA/IM/IS/H/ICU/R/D
    state_keys = {"S", "E", "IA", "IM", "IS", "H", "ICU", "R", "D"}
    assert state_keys.issubset(data["state"].keys()), f"state missing keys: {state_keys - data['state'].keys()}"
    assert state_keys.issubset(data["state_variance"].keys())

    obs_keys = {"papp", "ptest", "kappa"}
    assert obs_keys.issubset(data["observation_params"].keys())


# Test 14 – model_alert driven by cusum_score > 5.0
def test_state_model_alert_true_when_cusum_above_5():
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=_make_state_payload(cusum=5.1))
    data = _state_client(mock_redis).get("/api/v1/regions/r1/state").json()
    assert data["model_alert"] is True
    assert data["cusum_score"] == pytest.approx(5.1)


def test_state_model_alert_false_when_cusum_at_or_below_5():
    mock_redis = AsyncMock()
    mock_redis.get = AsyncMock(return_value=_make_state_payload(cusum=5.0))
    data = _state_client(mock_redis).get("/api/v1/regions/r1/state").json()
    assert data["model_alert"] is False

    mock_redis.get = AsyncMock(return_value=_make_state_payload(cusum=3.0))
    data2 = _state_client(mock_redis).get("/api/v1/regions/r1/state").json()
    assert data2["model_alert"] is False


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5 – Control weights API contracts (tests 15–17)
# ═══════════════════════════════════════════════════════════════════════════

_VALID_WEIGHTS = dict(
    C1=1.0,
    C2=5.0,
    C3=2.0,
    C4=10.0,
    W_u1=1.0,
    W_u2=0.5,
    W_u3=0.8,
    ethical_framework="utilitarian",
)


@pytest.fixture(scope="module")
def control_db():
    async def _setup():
        engine = await _make_db()
        fac = _factory(engine)
        async with fac() as s:
            s.add(
                ControlWeights(
                    region_id="ctrl-region",
                    updated_by=str(uuid.uuid4()),
                    **_VALID_WEIGHTS,
                )
            )
            await s.commit()
        return engine, fac

    engine, fac = _run(_setup())
    yield engine, fac
    _run(engine.dispose())


def _ctrl_client(fac, user):
    app = _build_control_app(fac)
    _set_user(app, user)
    return TestClient(app)


# Test 15 – GET /weights/{region_id} → 200 with ControlWeightsOut fields
def test_get_control_weights_returns_200_with_fields(control_db):
    _, fac = control_db
    resp = _ctrl_client(fac, ADMIN_USER).get("/api/v1/control/weights/ctrl-region")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for field in ("C1", "C2", "C3", "C4", "W_u1", "W_u2", "W_u3", "ethical_framework"):
        assert field in data, f"ControlWeightsOut missing field '{field}'"


# Test 16 – PUT /weights as patient → 403
def test_put_control_weights_as_patient_returns_403(control_db):
    _, fac = control_db
    with (
        patch("src.tasks.control_tasks.async_solve_optimal_control", new_callable=AsyncMock),
        patch("src.tasks.control_tasks.solve_optimal_control") as mock_solve,
    ):
        mock_solve.delay = MagicMock()
        resp = _ctrl_client(fac, PATIENT_USER).put("/api/v1/control/weights/ctrl-region", json=_VALID_WEIGHTS)
    assert resp.status_code == 403


# Test 17 – PUT /weights as admin → 200 with expected fields
def test_put_control_weights_as_admin_returns_200_with_fields(control_db):
    _, fac = control_db
    updated = dict(_VALID_WEIGHTS, C1=2.5)
    # Patch the names the control router imported at module load time.
    # Use run_forecast_inline=False so .delay() is called, not the async path.
    mock_solve = MagicMock()
    mock_solve.delay = MagicMock()
    with (
        patch("src.api.routers.control.async_solve_optimal_control", new_callable=AsyncMock),
        patch("src.api.routers.control.solve_optimal_control", mock_solve),
        patch("src.config.settings") as ms,
    ):
        ms.run_forecast_inline = False
        resp = _ctrl_client(fac, ADMIN_USER).put("/api/v1/control/weights/ctrl-region", json=updated)
    assert resp.status_code == 200, resp.text
    data = resp.json()
    for field in ("C1", "C2", "C3", "C4", "W_u1", "W_u2", "W_u3", "ethical_framework"):
        assert field in data, f"Response missing field '{field}'"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6 – ControlWeightsIn schema contracts (tests 18–19)
# ═══════════════════════════════════════════════════════════════════════════


class TestControlWeightsInSchema:
    """ControlWeightsIn Pydantic field validators."""

    def _ok(self, **overrides):
        return {**_VALID_WEIGHTS, **overrides}

    # Test 18 – C1 <= 0 rejected (gt=0)
    def test_c1_zero_rejected(self):
        from pydantic import ValidationError

        from src.api.routers.control import ControlWeightsIn

        with pytest.raises(ValidationError):
            ControlWeightsIn(**self._ok(C1=0.0))

    def test_c1_negative_rejected(self):
        from pydantic import ValidationError

        from src.api.routers.control import ControlWeightsIn

        with pytest.raises(ValidationError):
            ControlWeightsIn(**self._ok(C1=-1.0))

    # Test 19 – C1 > 1_000_000 rejected (le=1_000_000)
    def test_c1_above_max_rejected(self):
        from pydantic import ValidationError

        from src.api.routers.control import ControlWeightsIn

        with pytest.raises(ValidationError):
            ControlWeightsIn(**self._ok(C1=1_000_001.0))

    def test_c1_at_max_accepted(self):
        from src.api.routers.control import ControlWeightsIn

        w = ControlWeightsIn(**self._ok(C1=1_000_000.0))
        assert w.C1 == 1_000_000.0

    def test_c1_small_positive_accepted(self):
        from src.api.routers.control import ControlWeightsIn

        w = ControlWeightsIn(**self._ok(C1=0.001))
        assert pytest.approx(0.001) == w.C1
