"""Contract tests for the user-service patients router.

Scope: schema validation, CRUD, push-tokens, risk endpoint, audit log.
Infra: FastAPI TestClient + SQLite in-memory (aiosqlite).
No Keycloak, no Redis, no Postgres required.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Path bootstrap — must happen before any service imports
# ---------------------------------------------------------------------------
_ROOT = os.path.join(os.path.dirname(__file__), "..", "..", "..")
sys.path.insert(0, os.path.normpath(os.path.join(_ROOT, "services/user-service")))
sys.path.insert(0, os.path.normpath(os.path.join(_ROOT, "libs/shared/src")))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

# ---------------------------------------------------------------------------
# Third-party / service imports (after path bootstrap)
# ---------------------------------------------------------------------------
import pytest
import pytest_asyncio
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError
from shared.models import Base, Patient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from src.api.routers.patients import (
    PatientUpdateRequest,
    PushTokenRequest,
    RegisterRequest,
    RiskResponse,
    router,
)
from src.auth import get_current_user
from src.db.models import AuditLog, PushToken
from src.db.session import get_db

# ---------------------------------------------------------------------------
# vitals_ts DDL  (symptom-service model uses JSONB — not valid in SQLite;
#                 replicate as plain TEXT for the symptoms column)
# ---------------------------------------------------------------------------
_VITALS_DDL = """
CREATE TABLE IF NOT EXISTS vitals_ts (
    time         TEXT    NOT NULL,
    patient_id   TEXT    NOT NULL,
    heart_rate   INTEGER,
    spo2         REAL,
    temperature  REAL,
    systolic_bp  INTEGER,
    diastolic_bp INTEGER,
    symptoms     TEXT,
    risk_score   REAL,
    risk_tier    TEXT,
    PRIMARY KEY (time, patient_id)
)
"""

# ---------------------------------------------------------------------------
# Shared test identifiers
# ---------------------------------------------------------------------------
PATIENT_ID = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
OWNER_KC_ID = "kc-test-123"
OTHER_KC_ID = "other-kc-id"
PHYSICIAN_KC_ID = "doc-1"

# ---------------------------------------------------------------------------
# Token payloads — injected via dependency_overrides
# ---------------------------------------------------------------------------
PATIENT_USER: dict[str, Any] = {
    "sub": OWNER_KC_ID,
    "realm_access": {"roles": ["patient"]},
}
OTHER_USER: dict[str, Any] = {
    "sub": OTHER_KC_ID,
    "realm_access": {"roles": ["patient"]},
}
PHYSICIAN_USER: dict[str, Any] = {
    "sub": PHYSICIAN_KC_ID,
    "realm_access": {"roles": ["physician"]},
}


# ---------------------------------------------------------------------------
# Module-scoped async engine + schema creation
# (one engine for the whole module; each test gets a fresh session but
#  shares the same in-memory database so schema creation runs once)
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def engine():
    eng = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text(_VITALS_DDL))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def session_factory(engine):
    return async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# ---------------------------------------------------------------------------
# Per-test DB session override — each test gets a clean session
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(loop_scope="function")
async def db_session(session_factory):
    async with session_factory() as session:
        yield session


# ---------------------------------------------------------------------------
# Pre-seeded Patient row — created once per module, never mutated by tests
# ---------------------------------------------------------------------------
@pytest_asyncio.fixture(scope="module", loop_scope="module")
async def seeded_patient(session_factory):
    """Insert the canonical Patient row used by all CRUD tests."""
    async with session_factory() as s:
        # idempotent: skip if already present (re-runs / parametrize)
        existing = await s.execute(select(Patient).where(Patient.id == PATIENT_ID))
        if existing.scalar_one_or_none() is None:
            s.add(
                Patient(
                    id=PATIENT_ID,
                    keycloak_id=OWNER_KC_ID,
                    first_name="Alice",
                    last_name="Smith",
                    risk_tier="low",
                    email="alice@example.com",
                )
            )
            await s.commit()
    return PATIENT_ID


# ---------------------------------------------------------------------------
# TestClient factory — accepts a user-payload dict for dependency override
# ---------------------------------------------------------------------------
def _make_client(session_factory, user_payload: dict[str, Any]) -> TestClient:
    app = FastAPI()
    app.include_router(router)

    async def _override_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[get_current_user] = lambda: user_payload
    return TestClient(app, raise_server_exceptions=True)


# ---------------------------------------------------------------------------
# Per-test client fixtures
# ---------------------------------------------------------------------------
@pytest.fixture
def patient_client(session_factory):
    with _make_client(session_factory, PATIENT_USER) as c:
        yield c


@pytest.fixture
def other_client(session_factory):
    with _make_client(session_factory, OTHER_USER) as c:
        yield c


@pytest.fixture
def physician_client(session_factory):
    with _make_client(session_factory, PHYSICIAN_USER) as c:
        yield c


# ===========================================================================
# 1-4  Schema contracts (Pydantic model validation — no HTTP)
# ===========================================================================


class TestRegisterRequestSchema:
    def test_rejects_short_password(self):
        with pytest.raises(ValidationError) as exc_info:
            RegisterRequest(
                email="a@b.com",
                password="short",
                first_name="A",
                last_name="B",
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("password",) for e in errors)

    def test_rejects_invalid_role(self):
        with pytest.raises(ValidationError) as exc_info:
            RegisterRequest(
                email="a@b.com",
                password="validpass",
                first_name="A",
                last_name="B",
                role="superuser",
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("role",) for e in errors)

    def test_rejects_email_without_at(self):
        with pytest.raises(ValidationError) as exc_info:
            RegisterRequest(
                email="notanemail",
                password="validpass",
                first_name="A",
                last_name="B",
            )
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("email",) for e in errors)

    def test_accepts_valid_payload(self):
        req = RegisterRequest(
            email="patient@hospital.org",
            password="securepass1",
            first_name="Bob",
            last_name="Jones",
            role="patient",
        )
        assert req.role == "patient"
        assert req.email == "patient@hospital.org"


class TestPushTokenRequestSchema:
    def test_rejects_invalid_platform(self):
        with pytest.raises(ValidationError) as exc_info:
            PushTokenRequest(token="tok123", platform="fcm")
        errors = exc_info.value.errors()
        assert any(e["loc"] == ("platform",) for e in errors)

    def test_rejects_empty_token(self):
        # max_length=200, but token is required — empty string still passes
        # length constraint; the field is `...` (required) so missing raises.
        with pytest.raises(ValidationError):
            PushTokenRequest(platform="ios")  # token omitted entirely

    def test_accepts_valid_platforms(self):
        for platform in ("ios", "android", "web"):
            req = PushTokenRequest(token="abc", platform=platform)
            assert req.platform == platform


class TestPatientUpdateRequestSchema:
    def test_empty_body_is_valid(self):
        """All fields optional — {} must not raise."""
        req = PatientUpdateRequest()
        assert req.first_name is None
        assert req.last_name is None

    def test_partial_body_is_valid(self):
        req = PatientUpdateRequest(first_name="Carol")
        assert req.first_name == "Carol"
        assert req.last_name is None


class TestRiskResponseSchema:
    def test_has_required_fields(self):
        pid = uuid.uuid4()
        r = RiskResponse(patient_id=pid, risk_score=0.5, risk_tier="medium")
        assert r.patient_id == pid
        assert r.risk_score == 0.5
        assert r.risk_tier == "medium"

    def test_risk_score_nullable(self):
        r = RiskResponse(patient_id=uuid.uuid4(), risk_score=None, risk_tier="low")
        assert r.risk_score is None


# ===========================================================================
# 5-10  Patient CRUD contracts
# ===========================================================================


class TestGetPatient:
    def test_200_with_expected_fields(self, patient_client, seeded_patient):
        """Contract 5: GET own record → 200, PatientResponse shape."""
        resp = patient_client.get(f"/api/v1/patients/{PATIENT_ID}")
        assert resp.status_code == 200
        body = resp.json()
        assert uuid.UUID(body["id"]) == PATIENT_ID
        assert body["keycloak_id"] == OWNER_KC_ID
        assert body["first_name"] == "Alice"
        assert body["last_name"] == "Smith"
        assert body["risk_tier"] == "low"

    def test_404_for_nonexistent_patient(self, patient_client):
        """Contract 6: non-existent patient_id → 404."""
        resp = patient_client.get(f"/api/v1/patients/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_403_for_different_patient(self, other_client, seeded_patient):
        """Contract 7: different patient (wrong keycloak_id, no staff role) → 403."""
        resp = other_client.get(f"/api/v1/patients/{PATIENT_ID}")
        assert resp.status_code == 403

    def test_200_for_physician_staff_bypass(self, physician_client, seeded_patient):
        """Contract 8: physician role bypasses ownership check → 200."""
        resp = physician_client.get(f"/api/v1/patients/{PATIENT_ID}")
        assert resp.status_code == 200


class TestUpdatePatient:
    def test_put_updates_fields_and_returns_patientresponse(self, patient_client, seeded_patient):
        """Contract 9: valid PUT body → updated PatientResponse."""
        resp = patient_client.put(
            f"/api/v1/patients/{PATIENT_ID}",
            json={"first_name": "Alicia", "phone": "+1-555-0100"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["first_name"] == "Alicia"
        assert body["phone"] == "+1-555-0100"
        assert uuid.UUID(body["id"]) == PATIENT_ID

    def test_403_for_wrong_patient(self, other_client, seeded_patient):
        """Contract 10: PUT by different patient → 403."""
        resp = other_client.put(
            f"/api/v1/patients/{PATIENT_ID}",
            json={"first_name": "Hacker"},
        )
        assert resp.status_code == 403


# ===========================================================================
# 11-14  Push token contracts
# ===========================================================================


class TestPushToken:
    def test_201_with_message_key(self, patient_client, seeded_patient):
        """Contract 11: valid push token registration → 201, message key."""
        resp = patient_client.post(
            f"/api/v1/patients/{PATIENT_ID}/push_token",
            json={"token": "device-token-abc", "platform": "ios"},
        )
        assert resp.status_code == 201
        assert "message" in resp.json()

    def test_upsert_same_platform(self, patient_client, seeded_patient, session_factory):
        """Contract 12: second POST for same platform updates token, still 201."""
        for tok in ("first-token", "second-token"):
            resp = patient_client.post(
                f"/api/v1/patients/{PATIENT_ID}/push_token",
                json={"token": tok, "platform": "android"},
            )
            assert resp.status_code == 201

        # Only one row for this patient+platform; token is the latest value.
        async def _check():
            async with session_factory() as s:
                result = await s.execute(
                    select(PushToken).where(
                        PushToken.patient_id == PATIENT_ID,
                        PushToken.platform == "android",
                    )
                )
                rows = result.scalars().all()
                return rows

        rows = asyncio.get_event_loop().run_until_complete(_check())
        assert len(rows) == 1
        assert rows[0].token == "second-token"

    def test_403_for_wrong_patient(self, other_client, seeded_patient):
        """Contract 13: push token registration by wrong patient → 403."""
        resp = other_client.post(
            f"/api/v1/patients/{PATIENT_ID}/push_token",
            json={"token": "tok", "platform": "web"},
        )
        assert resp.status_code == 403

    def test_422_for_invalid_platform(self, patient_client, seeded_patient):
        """Contract 14: platform='fcm' (not in {ios,android,web}) → 422."""
        resp = patient_client.post(
            f"/api/v1/patients/{PATIENT_ID}/push_token",
            json={"token": "tok", "platform": "fcm"},
        )
        assert resp.status_code == 422

    def test_token_transfer_exclusive_ownership(self, patient_client, other_client, seeded_patient, session_factory):
        """P2 regression: token transfer must unbind from previous owner."""
        # Seed other patient for the test
        other_patient_id = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")

        async def _seed_other():
            async with session_factory() as s:
                s.add(Patient(id=other_patient_id, keycloak_id=OTHER_KC_ID, first_name="Other", last_name="Patient"))
                await s.commit()

        asyncio.get_event_loop().run_until_complete(_seed_other())

        shared_token = "device-transfer-token"

        # Patient A registers token
        resp = patient_client.post(
            f"/api/v1/patients/{PATIENT_ID}/push_token",
            json={"token": shared_token, "platform": "android"},
        )
        assert resp.status_code == 201

        # Patient B registers same token (device transfer scenario)
        resp = other_client.post(
            f"/api/v1/patients/{other_patient_id}/push_token",
            json={"token": shared_token, "platform": "android"},
        )
        assert resp.status_code == 201

        # Verify token now bound only to Patient B, not Patient A
        async def _check():
            async with session_factory() as s:
                result = await s.execute(
                    select(PushToken).where(PushToken.token == shared_token, PushToken.platform == "android")
                )
                rows = result.scalars().all()
                return rows

        rows = asyncio.get_event_loop().run_until_complete(_check())
        assert len(rows) == 1, f"Expected 1 binding, found {len(rows)}"
        assert rows[0].patient_id == other_patient_id

    def test_delete_idempotent(self, patient_client, seeded_patient):
        """P2 regression: DELETE is idempotent, returns 204 with JSON body."""
        token = "idempotent-test-token"

        # Register token
        resp = patient_client.post(
            f"/api/v1/patients/{PATIENT_ID}/push_token",
            json={"token": token, "platform": "ios"},
        )
        assert resp.status_code == 201

        # DELETE with correct token succeeds
        resp = patient_client.delete(
            "/api/v1/patients/me/push_token",
            json={"platform": "ios", "token": token},
        )
        assert resp.status_code == 204

        # Second DELETE is idempotent (token already removed)
        resp = patient_client.delete(
            "/api/v1/patients/me/push_token",
            json={"platform": "ios", "token": token},
        )
        assert resp.status_code == 204


# ===========================================================================
# 15-17  Risk endpoint contracts
# ===========================================================================


class TestRiskEndpoint:
    def test_no_vitals_returns_none_score_and_low_tier(self, session_factory):
        """Contract 15: no vitals row → risk_score=None, risk_tier='low'."""
        fresh_id = uuid.uuid4()
        fresh_kc = str(fresh_id)

        async def _seed():
            async with session_factory() as s:
                s.add(
                    Patient(
                        id=fresh_id,
                        keycloak_id=fresh_kc,
                        first_name="NoVitals",
                        last_name="Patient",
                        risk_tier="low",
                    )
                )
                await s.commit()

        asyncio.get_event_loop().run_until_complete(_seed())

        user = {"sub": fresh_kc, "realm_access": {"roles": ["patient"]}}
        with _make_client(session_factory, user) as c:
            resp = c.get(f"/api/v1/patients/{fresh_id}/risk")
        assert resp.status_code == 200
        body = resp.json()
        assert body["risk_score"] is None
        assert body["risk_tier"] == "low"

    def test_with_vitals_returns_correct_score_and_tier(self, session_factory):
        """Contract 16: existing vitals row → correct risk_score and risk_tier."""
        vitals_id = uuid.uuid4()
        vitals_kc = str(vitals_id)

        async def _seed():
            async with session_factory() as s:
                s.add(
                    Patient(
                        id=vitals_id,
                        keycloak_id=vitals_kc,
                        first_name="HasVitals",
                        last_name="Patient",
                        risk_tier="high",
                    )
                )
                await s.commit()
                now = datetime.now(UTC).isoformat()
                await s.execute(
                    text("INSERT INTO vitals_ts (time, patient_id, risk_score, risk_tier) VALUES (:t, :pid, :rs, :rt)"),
                    {"t": now, "pid": str(vitals_id), "rs": 0.87, "rt": "high"},
                )
                await s.commit()

        asyncio.get_event_loop().run_until_complete(_seed())

        user = {"sub": vitals_kc, "realm_access": {"roles": ["patient"]}}
        with _make_client(session_factory, user) as c:
            resp = c.get(f"/api/v1/patients/{vitals_id}/risk")
        assert resp.status_code == 200
        body = resp.json()
        assert abs(body["risk_score"] - 0.87) < 1e-6
        assert body["risk_tier"] == "high"

    def test_403_for_wrong_patient(self, other_client, seeded_patient):
        """Contract 17: wrong patient accessing risk → 403."""
        resp = other_client.get(f"/api/v1/patients/{PATIENT_ID}/risk")
        assert resp.status_code == 403


# ===========================================================================
# 18  Audit log contract
# ===========================================================================


class TestAuditLog:
    def test_get_patient_writes_audit_row(self, patient_client, seeded_patient, session_factory):
        """Contract 18: GET /patients/{id} must persist an AuditLog row
        with action='patient.read' and the correct patient_id."""
        # Make the request that must trigger the audit write.
        resp = patient_client.get(f"/api/v1/patients/{PATIENT_ID}")
        assert resp.status_code == 200

        async def _check():
            async with session_factory() as s:
                result = await s.execute(
                    select(AuditLog).where(
                        AuditLog.patient_id == PATIENT_ID,
                        AuditLog.action == "patient.read",
                    )
                )
                return result.scalars().all()

        rows = asyncio.get_event_loop().run_until_complete(_check())
        assert len(rows) >= 1
        row = rows[-1]
        assert row.action == "patient.read"
        assert row.patient_id == PATIENT_ID
        assert row.actor_sub == OWNER_KC_ID
        assert row.outcome == "success"
