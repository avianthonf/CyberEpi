"""Contract tests for prescription-service.

Covers:
  - Pydantic schema validation contracts
  - Prescription DB model method contracts
  - HTTP endpoint contracts (auth, CRUD, scan)
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# ── sys.path setup ────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# Provide a valid DATABASE_URL before any service module is imported.
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest
import sqlalchemy.dialects.postgresql as _pg_dialect
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import String
from sqlalchemy import event as sa_event
from sqlalchemy.exc import StatementError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.types import TypeDecorator


# Patch postgresql.UUID → CHAR(36) TypeDecorator so SQLite stores/retrieves
# UUID values as strings instead of 128-bit integers (which come back as floats).
class _GUID(TypeDecorator):  # type: ignore[misc]
    impl = String(36)
    cache_ok = True

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        return None if value is None else str(value)

    def process_result_value(self, value, dialect):  # type: ignore[override]
        return None if value is None else __import__("uuid").UUID(str(value))


_pg_dialect.UUID = _GUID  # type: ignore[assignment]

# ── Import service schemas / models ──────────────────────────────────────────

from src.api.routers.prescriptions import (
    MedicationScanRequest,
    PrescriptionCreate,
    StatusUpdate,
)
from src.db.models import Base, Patient, Prescription

# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════

_PATIENT_UUID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_PATIENT_KC_ID = "kc-patient-sub"
_PHYSICIAN_UUID = uuid.UUID("22222222-2222-2222-2222-222222222222")
_RX_UUID = uuid.UUID("33333333-3333-3333-3333-333333333333")
_OTHER_PATIENT_UUID = uuid.UUID("44444444-4444-4444-4444-444444444444")
_OTHER_KC_ID = "kc-other-sub"


def _physician_user(**extra: Any) -> dict[str, Any]:
    return {"sub": "physician-sub", "realm_access": {"roles": ["physician"]}, **extra}


def _patient_user(sub: str = _PATIENT_KC_ID, **extra: Any) -> dict[str, Any]:
    return {"sub": sub, "realm_access": {"roles": ["patient"]}, **extra}


def _make_client(
    db_override: Any,
    user_override: Any,
    redis_override: Any | None = None,
) -> TestClient:
    """Build a TestClient with dep overrides and no lifespan side-effects."""
    os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

    import src.main  # noqa: F401 — ensure module is importable

    with (
        patch("src.main.engine") as mock_engine,
        patch("src.main.connect_redis", return_value=redis_override or _fake_redis()),
        patch("src.main.disconnect_redis", new=AsyncMock()),
        patch("src.main.create_all_on_startup", new=AsyncMock()),
    ):
        mock_engine.dispose = AsyncMock()

        from src.auth import get_current_user
        from src.db.session import get_db
        from src.main import app

        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[get_current_user] = lambda: user_override

        redis = redis_override or _fake_redis()
        app.state.redis = redis

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

        app.dependency_overrides.clear()


class _FakeRedis:
    """Minimal async-compatible dict-backed Redis fake."""

    def __init__(self) -> None:
        self._store: dict[str, Any] = {}

    async def get(self, key: str) -> bytes | None:
        v = self._store.get(key)
        return v.encode() if isinstance(v, str) else v

    async def setex(self, key: str, ttl: int, value: Any) -> None:
        self._store[key] = value

    async def set(self, key: str, value: Any, **_: Any) -> None:
        self._store[key] = value

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        pass

    async def publish(self, *_: Any) -> None:
        pass

    def pubsub(self) -> MagicMock:
        return MagicMock()


def _fake_redis() -> _FakeRedis:
    return _FakeRedis()


# ── In-process async SQLite DB for HTTP tests ─────────────────────────────────


def _build_sqlite_db():
    """Return (engine, async_session_factory) on an in-memory SQLite database
    with the prescription-service schema already created."""
    import asyncio

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    # Enable FK support for every new connection
    @sa_event.listens_for(engine.sync_engine, "connect")
    def _fk_pragma(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    async def _init():
        async with engine.begin() as conn:
            # SQLite doesn't have pg UUID type; patch dialect before create_all
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init())

    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1: Pydantic schema contracts (no HTTP)
# ═══════════════════════════════════════════════════════════════════════════════


class TestPrescriptionCreateSchema:
    def test_valid_minimal(self):
        obj = PrescriptionCreate(
            patient_id=_PATIENT_UUID,
            drug_name="Amoxicillin",
            start_date=datetime.now(UTC).date(),
        )
        assert obj.drug_name == "Amoxicillin"
        assert obj.patient_id == _PATIENT_UUID

    def test_optional_fields_accepted(self):
        obj = PrescriptionCreate(
            patient_id=_PATIENT_UUID,
            drug_name="Metformin",
            start_date=datetime.now(UTC).date(),
            dosage="500mg",
            frequency="twice daily",
            notes="Take with food",
            ndc_code="12345-678-90",
            rxnorm_id="860975",
        )
        assert obj.dosage == "500mg"
        assert obj.notes == "Take with food"

    def test_drug_name_required(self):
        with pytest.raises(ValidationError):
            PrescriptionCreate(patient_id=_PATIENT_UUID, start_date=datetime.now(UTC).date())

    def test_drug_name_empty_string_rejected(self):
        with pytest.raises(ValidationError):
            PrescriptionCreate(
                patient_id=_PATIENT_UUID,
                drug_name="",
                start_date=datetime.now(UTC).date(),
            )

    def test_drug_name_max_200_chars(self):
        # Exactly 200 chars → valid
        PrescriptionCreate(
            patient_id=_PATIENT_UUID,
            drug_name="A" * 200,
            start_date=datetime.now(UTC).date(),
        )

    def test_drug_name_over_200_chars_rejected(self):
        with pytest.raises(ValidationError):
            PrescriptionCreate(
                patient_id=_PATIENT_UUID,
                drug_name="A" * 201,
                start_date=datetime.now(UTC).date(),
            )

    def test_notes_max_10000_chars(self):
        PrescriptionCreate(
            patient_id=_PATIENT_UUID,
            drug_name="Drug",
            start_date=datetime.now(UTC).date(),
            notes="x" * 10000,
        )

    def test_notes_over_10000_chars_rejected(self):
        with pytest.raises(ValidationError):
            PrescriptionCreate(
                patient_id=_PATIENT_UUID,
                drug_name="Drug",
                start_date=datetime.now(UTC).date(),
                notes="x" * 10001,
            )

    def test_patient_id_must_be_uuid(self):
        with pytest.raises(ValidationError):
            PrescriptionCreate(
                patient_id="not-a-uuid",
                drug_name="Drug",
                start_date=datetime.now(UTC).date(),
            )

    def test_start_date_required(self):
        with pytest.raises(ValidationError):
            PrescriptionCreate(patient_id=_PATIENT_UUID, drug_name="Drug")


class TestStatusUpdateSchema:
    @pytest.mark.parametrize("status", ["active", "paused", "completed", "cancelled"])
    def test_valid_statuses(self, status):
        obj = StatusUpdate(status=status)
        assert obj.status == status

    @pytest.mark.parametrize("bad", ["ACTIVE", "unknown", "deleted", "", "draft"])
    def test_invalid_status_rejected(self, bad):
        with pytest.raises(ValidationError):
            StatusUpdate(status=bad)


class TestMedicationScanRequestSchema:
    def test_valid(self):
        obj = MedicationScanRequest(
            ocr_text="Aspirin 500mg",
            patient_id=_PATIENT_UUID,
        )
        assert obj.ocr_text == "Aspirin 500mg"

    def test_empty_ocr_text_rejected(self):
        with pytest.raises(ValidationError):
            MedicationScanRequest(ocr_text="", patient_id=_PATIENT_UUID)

    def test_ocr_text_max_4096_chars(self):
        MedicationScanRequest(ocr_text="x" * 4096, patient_id=_PATIENT_UUID)

    def test_ocr_text_over_4096_chars_rejected(self):
        with pytest.raises(ValidationError):
            MedicationScanRequest(ocr_text="x" * 4097, patient_id=_PATIENT_UUID)


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2: Prescription DB model contracts
# ═══════════════════════════════════════════════════════════════════════════════


class TestPrescriptionModel:
    def _rx(self, **kwargs: Any) -> Prescription:
        defaults: dict[str, Any] = dict(
            id=uuid.uuid4(),
            patient_id=_PATIENT_UUID,
            drug_name="Lisinopril",
            status="active",
            start_date=datetime.now(UTC).date(),
            end_date=None,
        )
        defaults.update(kwargs)
        return Prescription(**defaults)

    def test_is_active_when_status_active_no_end_date(self):
        rx = self._rx(status="active", end_date=None)
        assert rx.is_active() is True

    def test_is_active_false_when_cancelled(self):
        rx = self._rx(status="cancelled")
        assert rx.is_active() is False

    def test_is_active_false_when_status_paused(self):
        rx = self._rx(status="paused")
        assert rx.is_active() is False

    def test_is_active_false_when_end_date_yesterday(self):
        # start_date must be before end_date to satisfy the model validator;
        # use a fixed past start so yesterday is a valid (but expired) end date.
        start = date(2024, 1, 1)
        yesterday = datetime.now(UTC).date() - timedelta(days=1)
        rx = Prescription(
            id=uuid.uuid4(),
            patient_id=_PATIENT_UUID,
            drug_name="Lisinopril",
            status="active",
            start_date=start,
            end_date=yesterday,
        )
        assert rx.is_active() is False

    def test_is_active_true_when_end_date_today(self):
        rx = self._rx(status="active", end_date=datetime.now(UTC).date())
        assert rx.is_active() is True

    def test_validate_status_rejects_unknown(self):
        with pytest.raises((ValueError, StatementError)):
            self._rx(status="unknown_xyz")

    def test_validate_status_rejects_empty(self):
        with pytest.raises((ValueError, StatementError)):
            self._rx(status="")


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3: HTTP endpoint contracts
# ═══════════════════════════════════════════════════════════════════════════════

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def _db_engine_factory():
    return _build_sqlite_db()


@pytest.fixture(scope="module")
def db_session(_db_engine_factory):
    """Seed the module-scoped DB once; return the async-generator dependency."""
    import asyncio

    _, factory = _db_engine_factory

    async def _seed():
        async with factory() as session:
            patient = Patient(
                id=_PATIENT_UUID,
                keycloak_id=_PATIENT_KC_ID,
                first_name="Alice",
                last_name="Liddell",
            )
            other_patient = Patient(
                id=_OTHER_PATIENT_UUID,
                keycloak_id=_OTHER_KC_ID,
                first_name="Bob",
                last_name="Other",
            )
            rx = Prescription(
                id=_RX_UUID,
                patient_id=_PATIENT_UUID,
                drug_name="Warfarin",
                status="active",
                start_date=date(2024, 1, 1),
            )
            paused_rx = Prescription(
                id=uuid.UUID("55555555-5555-5555-5555-555555555555"),
                patient_id=_PATIENT_UUID,
                drug_name="Metformin",
                status="paused",
                start_date=date(2024, 1, 1),
            )
            session.add_all([patient, other_patient, rx, paused_rx])
            await session.commit()

    asyncio.run(_seed())

    # Return the async-generator function directly — FastAPI calls it per request.
    async def _get_session():
        async with factory() as s:
            yield s

    return _get_session


@pytest.fixture()
def physician_client(db_session):
    """TestClient authenticated as a physician."""
    user = _physician_user()
    client_cm = _make_client(
        db_override=db_session,
        user_override=user,
    )
    yield from client_cm


@pytest.fixture()
def patient_client(db_session):
    """TestClient authenticated as the seeded patient."""
    user = _patient_user(sub=_PATIENT_KC_ID)
    client_cm = _make_client(
        db_override=db_session,
        user_override=user,
    )
    yield from client_cm


@pytest.fixture()
def other_patient_client(db_session):
    """TestClient authenticated as a different patient."""
    user = _patient_user(sub=_OTHER_KC_ID)
    client_cm = _make_client(
        db_override=db_session,
        user_override=user,
    )
    yield from client_cm


# ── POST /api/v1/prescriptions ────────────────────────────────────────────────


class TestCreatePrescription:
    @patch("src.api.routers.prescriptions.rxnorm_lookup", new=AsyncMock(return_value="860975"))
    @patch("src.api.routers.prescriptions.check_interactions", new=AsyncMock(return_value=[]))
    @patch("src.api.routers.prescriptions.cached_fda_lookup", new=AsyncMock(return_value=None))
    def test_patient_creates_own_prescription_201(self, patient_client):
        resp = patient_client.post(
            "/api/v1/prescriptions",
            json={
                "patient_id": str(_PATIENT_UUID),
                "drug_name": "Aspirin",
                "start_date": "2024-06-01",
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["patient_id"] == str(_PATIENT_UUID)
        assert data["drug_name"] == "Aspirin"
        assert data["status"] == "active"
        assert "id" in data

    @patch("src.api.routers.prescriptions.rxnorm_lookup", new=AsyncMock(return_value=None))
    @patch("src.api.routers.prescriptions.check_interactions", new=AsyncMock(return_value=[]))
    @patch("src.api.routers.prescriptions.cached_fda_lookup", new=AsyncMock(return_value=None))
    def test_patient_creates_for_different_patient_403(self, patient_client):
        resp = patient_client.post(
            "/api/v1/prescriptions",
            json={
                "patient_id": str(_OTHER_PATIENT_UUID),
                "drug_name": "Ibuprofen",
                "start_date": "2024-06-01",
            },
        )
        assert resp.status_code == 403

    @patch("src.api.routers.prescriptions.rxnorm_lookup", new=AsyncMock(return_value=None))
    @patch("src.api.routers.prescriptions.check_interactions", new=AsyncMock(return_value=[]))
    @patch("src.api.routers.prescriptions.cached_fda_lookup", new=AsyncMock(return_value=None))
    def test_nonexistent_patient_id_returns_404(self, physician_client):
        nonexistent = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
        resp = physician_client.post(
            "/api/v1/prescriptions",
            json={
                "patient_id": str(nonexistent),
                "drug_name": "Digoxin",
                "start_date": "2024-06-01",
            },
        )
        assert resp.status_code == 404


# ── GET /api/v1/prescriptions/{rx_id} ─────────────────────────────────────────


class TestGetPrescription:
    def test_get_own_prescription_200(self, patient_client):
        resp = patient_client.get(f"/api/v1/prescriptions/{_RX_UUID}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == str(_RX_UUID)
        assert data["patient_id"] == str(_PATIENT_UUID)
        assert data["drug_name"] == "Warfarin"
        # Verify all PrescriptionResponse fields are present
        for field in (
            "id",
            "patient_id",
            "drug_name",
            "ndc_code",
            "rxnorm_id",
            "dosage",
            "frequency",
            "status",
            "start_date",
            "end_date",
            "notes",
        ):
            assert field in data

    def test_get_nonexistent_prescription_404(self, patient_client):
        missing = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
        resp = patient_client.get(f"/api/v1/prescriptions/{missing}")
        assert resp.status_code == 404

    def test_get_other_patients_prescription_403(self, other_patient_client):
        # _RX_UUID belongs to _PATIENT_UUID; other patient must not see it
        resp = other_patient_client.get(f"/api/v1/prescriptions/{_RX_UUID}")
        assert resp.status_code == 403

    def test_physician_can_get_any_prescription(self, physician_client):
        resp = physician_client.get(f"/api/v1/prescriptions/{_RX_UUID}")
        assert resp.status_code == 200


# ── GET /api/v1/patients/{patient_id}/prescriptions ──────────────────────────


class TestListPrescriptions:
    def test_list_returns_active_only(self, physician_client):
        """Only status=active rows must be returned; paused row must be excluded."""
        resp = physician_client.get(f"/api/v1/patients/{_PATIENT_UUID}/prescriptions")
        assert resp.status_code == 200
        items = resp.json()
        assert all(item["status"] == "active" for item in items), (
            f"Non-active item in response: {[i for i in items if i['status'] != 'active']}"
        )

    def test_list_excludes_paused_prescription(self, physician_client):
        resp = physician_client.get(f"/api/v1/patients/{_PATIENT_UUID}/prescriptions")
        drug_names = [i["drug_name"] for i in resp.json()]
        assert "Metformin" not in drug_names  # Metformin is seeded as paused


# ── PUT /api/v1/prescriptions/{rx_id}/status ─────────────────────────────────


class TestUpdatePrescriptionStatus:
    def test_patient_cannot_update_status_403(self, patient_client):
        resp = patient_client.put(
            f"/api/v1/prescriptions/{_RX_UUID}/status",
            json={"status": "paused"},
        )
        assert resp.status_code == 403

    def test_physician_updates_status_200(self, physician_client):
        resp = physician_client.put(
            f"/api/v1/prescriptions/{_RX_UUID}/status",
            json={"status": "paused"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "paused"

        # Restore for downstream tests
        physician_client.put(
            f"/api/v1/prescriptions/{_RX_UUID}/status",
            json={"status": "active"},
        )


# ── POST /api/v1/medications/scan ────────────────────────────────────────────


class TestMedicationScan:
    @patch("src.api.routers.prescriptions.rxnorm_lookup", new=AsyncMock(return_value="1049502"))
    @patch(
        "src.api.routers.prescriptions.check_interactions",
        new=AsyncMock(return_value=[{"drugs": ["Warfarin", "Aspirin"], "severity": "major", "description": "Bleeding risk"}]),
    )
    @patch(
        "src.api.routers.prescriptions.cached_fda_lookup",
        new=AsyncMock(return_value={"brand_name": "Aspirin"}),
    )
    def test_scan_returns_medication_scan_response(self, physician_client):
        resp = physician_client.post(
            "/api/v1/medications/scan",
            json={
                "ocr_text": "Aspirin 500mg\n00536-3273-01",
                "patient_id": str(_PATIENT_UUID),
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        # All four required fields must be present
        assert "drug_name" in data
        assert "ndc_code" in data
        assert "rxnorm_id" in data
        assert "interactions" in data
        assert isinstance(data["interactions"], list)

    def test_scan_cross_patient_403(self, patient_client, other_patient_client):
        """P1 regression: medication scan must authorize patient_id before interaction lookup."""
        resp = patient_client.post(
            "/api/v1/medications/scan",
            json={
                "ocr_text": "LIPITOR 10mg",
                "patient_id": str(_OTHER_PATIENT_UUID),  # Trying to scan for different patient
            },
        )
        assert resp.status_code == 403, f"Expected 403, got {resp.status_code}"
