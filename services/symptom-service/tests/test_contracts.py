"""Contract tests for symptom-service.

Covers:
- Pydantic schema validation contracts (SymptomReport, SymptomResponse)
- VitalsTS SQLAlchemy @validates contracts
- VitalsTS CHECK constraint at the DB level
- HTTP contracts for symptom ingest, history, risk score, and deterioration endpoints

Run with:
  cd /home/avinash/Projects/CyberEpi
  .venv/bin/python -m pytest services/symptom-service/tests/test_contracts.py -v
"""

from __future__ import annotations

import os
import sys

# ── Path setup: must precede all src.* imports ───────────────────────────────
_SVC_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if _SVC_SRC not in sys.path:
    sys.path.insert(0, _SVC_SRC)

# ── SQLite compat: swap PG-dialect UUID/JSONB types before any mapper uses them ─
#
# PostgreSQL UUID(as_uuid=True) ships a bind processor that calls value.hex,
# which crashes on plain strings — and SQLite stores UUIDs as TEXT.
# We replace every PG UUID column with a custom String subtype that coerces
# uuid.UUID objects to their canonical string form on the way in, leaving
# everything else untouched.  Same swap for JSONB → JSON.
#
# Must happen at module import time: any deferred patch arrives after
# SQLAlchemy has already compiled and cached statements with the old type.

import uuid

import sqlalchemy as sa
from shared.models import Base as SharedBase  # registers patients table
from shared.models import Patient
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.types import String, TypeDecorator

from src.db.models import Base, VitalsTS  # registers vitals_ts table


class _UUIDStr(TypeDecorator):
    """Stores UUIDs as TEXT in SQLite; coerces uuid.UUID objects on bind."""

    impl = String
    cache_ok = True

    def __init__(self):
        super().__init__(36)

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return str(value)

    def process_result_value(self, value, dialect):
        return value  # return raw string; callers that need uuid.UUID can coerce


def _sqlite_compat():
    for meta in (SharedBase.metadata, Base.metadata):
        for tbl in meta.tables.values():
            for col in tbl.columns:
                if isinstance(col.type, PG_UUID):
                    col.type = _UUIDStr()
                elif isinstance(col.type, JSONB):
                    col.type = sa.JSON()


_sqlite_compat()

# ── Everything else ───────────────────────────────────────────────────────────

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = "sqlite+aiosqlite:///:memory:"


def _run(coro):
    """Execute a coroutine in a fresh event loop (safe from any sync context)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _make_db():
    """Fresh in-memory SQLite engine with all tables created."""
    engine = create_async_engine(DATABASE_URL, echo=False)

    @event.listens_for(engine.sync_engine, "connect")
    def _pragmas(dbapi_conn, _rec):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON")
        cur.close()

    async with engine.begin() as conn:
        await conn.run_sync(SharedBase.metadata.create_all)
        await conn.run_sync(Base.metadata.create_all)

    return engine


def _factory(engine):
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


# ── Auth helpers ──────────────────────────────────────────────────────────────

ADMIN_USER = {"sub": "admin-001", "realm_access": {"roles": ["admin"]}}
PATIENT_SUB = "patient-kc-sub-001"
PATIENT_USER = {"sub": PATIENT_SUB, "realm_access": {"roles": ["patient"]}}
OTHER_USER = {"sub": "other-sub-999", "realm_access": {"roles": ["patient"]}}


# ── App factory ───────────────────────────────────────────────────────────────


def _build_app(factory):
    from src.api.routers.risk import router as risk_router
    from src.api.routers.symptoms import router as symptoms_router
    from src.db.session import get_db

    app = FastAPI()
    app.include_router(symptoms_router)
    app.include_router(risk_router)
    app.state.kafka_producer = AsyncMock()
    app.state.redis = AsyncMock()
    app.state.redis.get = AsyncMock(return_value=None)

    async def _db():
        async with factory() as s:
            yield s

    app.dependency_overrides[get_db] = _db
    return app


def _set_user(app, user):
    from src.auth import get_current_user

    app.dependency_overrides[get_current_user] = lambda: user


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 1 - Pydantic schema contracts
# ═══════════════════════════════════════════════════════════════════════════


class TestSymptomReportSchema:
    def _ok(self, **kw):
        return {"patient_id": str(uuid.uuid4()), "symptoms": ["fever"], **kw}

    # Test 1 - symptoms ≥ 1 entry
    def test_empty_symptoms_rejected(self):
        from pydantic import ValidationError

        from src.api.routers.symptoms import SymptomReport

        with pytest.raises(ValidationError):
            SymptomReport(**self._ok(symptoms=[]))

    def test_non_empty_symptoms_accepted(self):
        from src.api.routers.symptoms import SymptomReport

        r = SymptomReport(**self._ok(symptoms=["fever"]))
        assert r.symptoms == ["fever"]

    # Test 2 - heart_rate [20, 300]
    def test_heart_rate_below_20_rejected(self):
        from pydantic import ValidationError

        from src.api.routers.symptoms import SymptomReport

        with pytest.raises(ValidationError):
            SymptomReport(**self._ok(heart_rate=19))

    def test_heart_rate_above_300_rejected(self):
        from pydantic import ValidationError

        from src.api.routers.symptoms import SymptomReport

        with pytest.raises(ValidationError):
            SymptomReport(**self._ok(heart_rate=301))

    def test_heart_rate_boundaries_accepted(self):
        from src.api.routers.symptoms import SymptomReport

        assert SymptomReport(**self._ok(heart_rate=20)).heart_rate == 20
        assert SymptomReport(**self._ok(heart_rate=300)).heart_rate == 300

    # spo2 [0, 100]
    def test_spo2_below_0_rejected(self):
        from pydantic import ValidationError

        from src.api.routers.symptoms import SymptomReport

        with pytest.raises(ValidationError):
            SymptomReport(**self._ok(spo2=-0.1))

    def test_spo2_above_100_rejected(self):
        from pydantic import ValidationError

        from src.api.routers.symptoms import SymptomReport

        with pytest.raises(ValidationError):
            SymptomReport(**self._ok(spo2=100.1))

    def test_spo2_boundaries_accepted(self):
        from src.api.routers.symptoms import SymptomReport

        assert SymptomReport(**self._ok(spo2=0.0)).spo2 == pytest.approx(0.0)
        assert SymptomReport(**self._ok(spo2=100.0)).spo2 == pytest.approx(100.0)

    # temperature [25, 45]
    def test_temperature_below_25_rejected(self):
        from pydantic import ValidationError

        from src.api.routers.symptoms import SymptomReport

        with pytest.raises(ValidationError):
            SymptomReport(**self._ok(temperature=24.9))

    def test_temperature_above_45_rejected(self):
        from pydantic import ValidationError

        from src.api.routers.symptoms import SymptomReport

        with pytest.raises(ValidationError):
            SymptomReport(**self._ok(temperature=45.1))

    def test_temperature_boundaries_accepted(self):
        from src.api.routers.symptoms import SymptomReport

        assert SymptomReport(**self._ok(temperature=25.0)).temperature == pytest.approx(25.0)
        assert SymptomReport(**self._ok(temperature=45.0)).temperature == pytest.approx(45.0)


class TestSymptomResponseSchema:
    """Test 3 - SymptomResponse has the required fields."""

    def test_required_fields_present(self):
        from src.api.routers.symptoms import SymptomResponse

        pid = uuid.uuid4()
        r = SymptomResponse(patient_id=pid, risk_score=0.42, risk_tier="moderate", report_count=3)
        assert r.patient_id == pid
        assert r.risk_score == pytest.approx(0.42)
        assert r.risk_tier == "moderate"
        assert r.report_count == 3
        assert r.message == "Symptom report recorded"

    def test_risk_fields_may_be_none(self):
        from src.api.routers.symptoms import SymptomResponse

        r = SymptomResponse(patient_id=uuid.uuid4(), risk_score=None, risk_tier=None, report_count=1)
        assert r.risk_score is None
        assert r.risk_tier is None


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 2 - VitalsTS model @validates contracts (tests 4-6)
# ═══════════════════════════════════════════════════════════════════════════


class TestVitalsTSValidates:
    def _v(self, **kw):
        defaults = dict(time=datetime.now(UTC), patient_id=str(uuid.uuid4()))
        defaults.update(kw)
        return VitalsTS(**defaults)

    # Test 4 - heart_rate [0, 300]
    def test_heart_rate_below_0_raises(self):
        with pytest.raises(ValueError, match=r"(?i)heart"):
            self._v(heart_rate=-1)

    def test_heart_rate_above_300_raises(self):
        with pytest.raises(ValueError, match=r"(?i)heart"):
            self._v(heart_rate=301)

    def test_heart_rate_boundaries_ok(self):
        assert self._v(heart_rate=0).heart_rate == 0
        assert self._v(heart_rate=300).heart_rate == 300

    # Test 5 - spo2 [0, 100]
    def test_spo2_below_0_raises(self):
        with pytest.raises(ValueError, match=r"(?i)spo2"):
            self._v(spo2=-0.1)

    def test_spo2_above_100_raises(self):
        with pytest.raises(ValueError, match=r"(?i)spo2"):
            self._v(spo2=100.1)

    def test_spo2_boundary_ok(self):
        assert self._v(spo2=0.0).spo2 == pytest.approx(0.0)

    # Test 6 - temperature [20, 50]
    def test_temperature_below_20_raises(self):
        with pytest.raises(ValueError, match=r"(?i)temperature"):
            self._v(temperature=19.9)

    def test_temperature_above_50_raises(self):
        with pytest.raises(ValueError, match=r"(?i)temperature"):
            self._v(temperature=50.1)

    def test_temperature_boundaries_ok(self):
        assert self._v(temperature=20.0).temperature == pytest.approx(20.0)
        assert self._v(temperature=50.0).temperature == pytest.approx(50.0)


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 3 - VitalsTS CHECK constraint at DB level (test 7)
# ═══════════════════════════════════════════════════════════════════════════


def test_vitals_risk_score_check_constraint_db():
    """Test 7: risk_score=1.5 must be rejected at the DB level."""

    async def _go():
        engine = await _make_db()
        fac = _factory(engine)
        pid = str(uuid.uuid4())

        async with fac() as session:
            session.add(Patient(id=pid, keycloak_id="chk-test", risk_tier="low"))
            await session.commit()

        inserted = False
        try:
            async with fac() as session:
                await session.execute(
                    text("INSERT INTO vitals_ts (time, patient_id, risk_score) VALUES (:t, :pid, :rs)"),
                    {"t": datetime.now(UTC).isoformat(), "pid": pid, "rs": 1.5},
                )
                await session.commit()
                inserted = True
        except IntegrityError:
            pass  # expected

        await engine.dispose()

        if inserted:
            pytest.fail("Expected CHECK constraint to reject risk_score=1.5, but the row was inserted")

    _run(_go())


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 4 - Symptom ingest HTTP contracts (tests 8-12)
# ═══════════════════════════════════════════════════════════════════════════
#
# calculate_and_update_risk is deferred-imported inside ingest_symptom:
#   from src.services.risk import calculate_and_update_risk
# so we patch the canonical module, not the router's namespace.

_RISK_PATCH = "src.services.risk.calculate_and_update_risk"
_KAFKA_PATCH = "shared.kafka.publish_kafka"


@pytest.fixture(scope="module")
def ingest_db():
    async def _setup():
        engine = await _make_db()
        fac = _factory(engine)
        pid = str(uuid.uuid4())
        async with fac() as s:
            s.add(
                Patient(
                    id=pid,
                    keycloak_id=PATIENT_SUB,
                    region_id="region-1",
                    patch_id="patch-A",
                    risk_tier="low",
                )
            )
            await s.commit()
        return engine, fac, pid

    engine, fac, pid = _run(_setup())
    yield engine, fac, pid
    _run(engine.dispose())


def _ingest_client(fac, user):
    app = _build_app(fac)
    _set_user(app, user)
    return TestClient(app, raise_server_exceptions=True)


# Test 8 - valid POST → 201 with required fields
def test_ingest_valid_body_returns_201(ingest_db):
    _, fac, pid = ingest_db
    client = _ingest_client(fac, ADMIN_USER)
    body = {"patient_id": pid, "symptoms": ["fever", "cough"]}
    with (
        patch(_RISK_PATCH, new_callable=AsyncMock, return_value=(1, 0.3, "moderate")),
        patch(_KAFKA_PATCH, new_callable=AsyncMock),
    ):
        resp = client.post("/api/v1/symptoms", json=body)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    for key in ("patient_id", "risk_score", "risk_tier", "report_count"):
        assert key in data, f"missing key '{key}' in response"
    assert data["risk_score"] == pytest.approx(0.3)
    assert data["risk_tier"] == "moderate"


# Test 9 - wrong patient (sub has no Patient row) → 403
def test_ingest_wrong_patient_returns_403(ingest_db):
    _, fac, pid = ingest_db
    client = _ingest_client(fac, OTHER_USER)
    body = {"patient_id": pid, "symptoms": ["fever"]}
    with patch(_RISK_PATCH, new_callable=AsyncMock, return_value=(1, 0.3, "moderate")):
        resp = client.post("/api/v1/symptoms", json=body)
    assert resp.status_code == 403


# Test 10 - non-existent patient_id → 404
def test_ingest_nonexistent_patient_returns_404(ingest_db):
    _, fac, _ = ingest_db
    client = _ingest_client(fac, ADMIN_USER)
    body = {"patient_id": str(uuid.uuid4()), "symptoms": ["fever"]}
    with patch(_RISK_PATCH, new_callable=AsyncMock, return_value=(1, 0.3, "moderate")):
        resp = client.post("/api/v1/symptoms", json=body)
    assert resp.status_code == 404


# Test 11 - empty symptoms → 422
def test_ingest_empty_symptoms_returns_422(ingest_db):
    _, fac, pid = ingest_db
    client = _ingest_client(fac, ADMIN_USER)
    resp = client.post("/api/v1/symptoms", json={"patient_id": pid, "symptoms": []})
    assert resp.status_code == 422


# Test 12 - VitalsTS row persisted after successful POST
def test_ingest_writes_vitals_row(ingest_db):
    from sqlalchemy import select

    _, fac, pid = ingest_db
    client = _ingest_client(fac, ADMIN_USER)
    body = {"patient_id": pid, "symptoms": ["headache"], "heart_rate": 80, "spo2": 98.0}

    with patch(_RISK_PATCH, new_callable=AsyncMock, return_value=(1, 0.25, "low")), patch(_KAFKA_PATCH, new_callable=AsyncMock):
        resp = client.post("/api/v1/symptoms", json=body)

    assert resp.status_code == 201, resp.text

    async def _check():
        async with fac() as s:
            result = await s.execute(select(VitalsTS).where(VitalsTS.patient_id == pid))
            return result.scalars().all()

    rows = _run(_check())
    assert len(rows) >= 1, "Expected at least one VitalsTS row after ingest POST"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 5 - History endpoint contracts (tests 13-14)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def history_db():
    async def _setup():
        engine = await _make_db()
        fac = _factory(engine)
        pid = str(uuid.uuid4())

        async with fac() as s:
            s.add(Patient(id=pid, keycloak_id=PATIENT_SUB, region_id="r1", risk_tier="low"))
            await s.commit()

        async with fac() as s:
            for i in range(2):
                s.add(
                    VitalsTS(
                        time=datetime(2026, 1, i + 1, 12, 0, 0, tzinfo=UTC),
                        patient_id=pid,
                        heart_rate=70 + i,
                        spo2=98.0,
                        temperature=37.0,
                        symptoms={"reported": ["fever"]},
                        risk_score=0.1 * (i + 1),
                        risk_tier="low",
                    )
                )
            await s.commit()

        return engine, fac, pid

    engine, fac, pid = _run(_setup())
    yield engine, fac, pid
    _run(engine.dispose())


# Test 13 - no rows → empty list []
def test_history_empty_returns_empty_list(history_db):
    _, fac, _ = history_db
    empty_pid = str(uuid.uuid4())

    async def _seed():
        async with fac() as s:
            s.add(Patient(id=empty_pid, keycloak_id="empty-hist-kc", risk_tier="low"))
            await s.commit()

    _run(_seed())

    app = _build_app(fac)
    _set_user(app, ADMIN_USER)
    resp = TestClient(app).get(f"/api/v1/patients/{empty_pid}/history")
    assert resp.status_code == 200
    assert resp.json() == []


# Test 14 - seeded rows → list with HistoryItem keys
def test_history_returns_items_with_correct_keys(history_db):
    _, fac, pid = history_db
    app = _build_app(fac)
    _set_user(app, ADMIN_USER)

    resp = TestClient(app).get(f"/api/v1/patients/{pid}/history")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    required = {"time", "risk_score", "risk_tier", "heart_rate", "spo2", "temperature"}
    for item in items:
        missing = required - item.keys()
        assert not missing, f"HistoryItem missing keys: {missing}"


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 6 - Risk score HTTP contracts (tests 15-17)
# ═══════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def risk_db():
    async def _setup():
        engine = await _make_db()
        fac = _factory(engine)
        pid = str(uuid.uuid4())

        async with fac() as s:
            s.add(Patient(id=pid, keycloak_id=PATIENT_SUB, risk_tier="moderate"))
            await s.commit()

        async with fac() as s:
            s.add(
                VitalsTS(
                    time=datetime.now(UTC),
                    patient_id=pid,
                    heart_rate=88,
                    spo2=96.0,
                    temperature=38.1,
                    symptoms={"reported": ["fever"]},
                    risk_score=0.45,
                    risk_tier="moderate",
                )
            )
            await s.commit()

        return engine, fac, pid

    engine, fac, pid = _run(_setup())
    yield engine, fac, pid
    _run(engine.dispose())


# Test 15 - no vitals for patient → 404
def test_risk_score_no_vitals_returns_404(risk_db):
    _, fac, _ = risk_db
    app = _build_app(fac)
    _set_user(app, ADMIN_USER)
    resp = TestClient(app).get(f"/v1/risk/score/{uuid.uuid4()}")
    assert resp.status_code == 404


# Test 16 - vitals present → 200 with expected fields
def test_risk_score_returns_200_with_fields(risk_db):
    _, fac, pid = risk_db
    app = _build_app(fac)
    _set_user(app, ADMIN_USER)
    resp = TestClient(app).get(f"/v1/risk/score/{pid}")
    assert resp.status_code == 200
    data = resp.json()
    assert "patient_id" in data
    assert "risk_score" in data
    assert "tier" in data
    assert data["risk_score"] == pytest.approx(0.45)
    assert data["tier"] == "moderate"


# Test 17 - wrong patient (sub has no Patient row) → 403
def test_risk_score_wrong_patient_returns_403(risk_db):
    _, fac, pid = risk_db
    app = _build_app(fac)
    _set_user(app, OTHER_USER)
    resp = TestClient(app).get(f"/v1/risk/score/{pid}")
    assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════
# SECTION 7 - Deterioration endpoint contracts (tests 18-19)
# ═══════════════════════════════════════════════════════════════════════════

_VALID_FEATURES = {
    "age": 55,
    "n_comorbidities": 2,
    "days_since_onset": 3.0,
    "spo2_current": 96.0,
    "spo2_slope_48h": -0.5,
    "spo2_min_24h": 94.0,
    "heart_rate_current": 90.0,
    "hr_slope_48h": 2.0,
    "fever_max_24h": 38.5,
    "fever_duration_h": 12.0,
    "risk_score_current": 0.35,
    "risk_score_acceleration": 0.1,
    "local_hosp_rate": 0.05,
    "regional_Rt": 1.2,
}


@pytest.fixture(scope="module")
def detn_client():
    engine = _run(_make_db())
    fac = _factory(engine)
    app = _build_app(fac)
    _set_user(app, ADMIN_USER)
    yield TestClient(app)
    _run(engine.dispose())


# Test 18 - valid body → 200 with all required keys
def test_deterioration_returns_200_with_required_keys(detn_client):
    resp = detn_client.post("/v1/risk/deterioration", json=_VALID_FEATURES)
    assert resp.status_code == 200
    data = resp.json()
    required = {"p_hospitalization_72h", "p_icu_7d", "alerts", "source", "timestamp_utc"}
    missing = required - data.keys()
    assert not missing, f"Deterioration response missing keys: {missing}"


# Test 19 - probabilities are in [0, 1]
def test_deterioration_probabilities_in_unit_interval(detn_client):
    resp = detn_client.post("/v1/risk/deterioration", json=_VALID_FEATURES)
    assert resp.status_code == 200
    data = resp.json()
    assert 0.0 <= data["p_hospitalization_72h"] <= 1.0, f"p_hospitalization_72h={data['p_hospitalization_72h']} outside [0,1]"
    assert 0.0 <= data["p_icu_7d"] <= 1.0, f"p_icu_7d={data['p_icu_7d']} outside [0,1]"
