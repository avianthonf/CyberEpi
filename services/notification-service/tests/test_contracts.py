"""Contract tests for notification-service.

Covers:
  - Pydantic schema validation contracts
  - Notification HTTP endpoint contracts (auth, CRUD, send)
  - PushToken DB model contracts
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

# ── sys.path setup ────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

import pytest
import sqlalchemy.dialects.postgresql as _pg_dialect
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import String
from sqlalchemy import event as sa_event
from sqlalchemy.exc import IntegrityError
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

from src.api.routers.notifications import (
    CreateNotificationRequest,
    NotificationResponse,
    SendNotificationRequest,
)
from src.db.models import Base, Notification, PushToken, patients_table

# ═══════════════════════════════════════════════════════════════════════════════
# Constants
# ═══════════════════════════════════════════════════════════════════════════════

_PATIENT_UUID = uuid.UUID("11111111-1111-1111-1111-111111111111")
_PATIENT_KC_ID = "kc-notif-patient"
_OTHER_UUID = uuid.UUID("22222222-2222-2222-2222-222222222222")
_OTHER_KC_ID = "kc-notif-other"
_NOTIF_UUID = uuid.UUID("33333333-3333-3333-3333-333333333333")


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _physician_user(**extra: Any) -> dict[str, Any]:
    return {"sub": "physician-sub", "realm_access": {"roles": ["physician"]}, **extra}


def _patient_user(sub: str = _PATIENT_KC_ID, **extra: Any) -> dict[str, Any]:
    return {"sub": sub, "realm_access": {"roles": ["patient"]}, **extra}


class _FakeRedis:
    """Minimal async-compatible dict-backed Redis fake for tests."""

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
        ps = MagicMock()
        ps.subscribe = AsyncMock()
        ps.unsubscribe = AsyncMock()
        ps.aclose = AsyncMock()
        ps.get_message = AsyncMock(return_value=None)
        return ps


def _make_client(
    db_override: Any,
    user_override: Any,
) -> TestClient:
    """Build a TestClient with dependency overrides and mocked lifespan."""
    import src.main  # noqa: F401 — ensure module importable

    redis = _FakeRedis()

    with (
        patch("src.main.engine") as mock_engine,
        patch("src.main.connect_redis", return_value=redis),
        patch("src.main.disconnect_redis", new=AsyncMock()),
        patch("src.main.create_all_on_startup", new=AsyncMock()),
        patch("src.main.AIOKafkaConsumer"),
        patch("src.main._consume_alerts", new_callable=AsyncMock),
    ):
        mock_engine.dispose = AsyncMock()

        from src.auth import get_current_user
        from src.db.session import get_db
        from src.main import app

        app.dependency_overrides[get_db] = db_override
        app.dependency_overrides[get_current_user] = lambda: user_override
        app.state.redis = redis

        with TestClient(app, raise_server_exceptions=False) as c:
            yield c

        app.dependency_overrides.clear()


def _build_sqlite_db():
    """Return (engine, async_session_factory) with schema created."""
    import asyncio

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @sa_event.listens_for(engine.sync_engine, "connect")
    def _fk_pragma(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

    asyncio.run(_init())

    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


# ═══════════════════════════════════════════════════════════════════════════════
# Section 1: Pydantic schema contracts
# ═══════════════════════════════════════════════════════════════════════════════


class TestSendNotificationRequestSchema:
    def test_valid_minimal(self):
        obj = SendNotificationRequest(
            patient_id=_PATIENT_UUID,
            title="Alert",
            body="You have a new alert.",
        )
        assert obj.patient_id == _PATIENT_UUID
        assert obj.data is None

    def test_data_optional(self):
        obj = SendNotificationRequest(
            patient_id=_PATIENT_UUID,
            title="T",
            body="B",
            data={"key": "value"},
        )
        assert obj.data == {"key": "value"}

    def test_patient_id_required(self):
        with pytest.raises(ValidationError):
            SendNotificationRequest(title="T", body="B")

    def test_title_required(self):
        with pytest.raises(ValidationError):
            SendNotificationRequest(patient_id=_PATIENT_UUID, body="B")

    def test_body_required(self):
        with pytest.raises(ValidationError):
            SendNotificationRequest(patient_id=_PATIENT_UUID, title="T")


class TestCreateNotificationRequestSchema:
    def test_valid(self):
        obj = CreateNotificationRequest(
            patient_id=_PATIENT_UUID,
            title="Reminder",
            body="Take your medication.",
            type="reminder",
            priority="medium",
        )
        assert obj.type == "reminder"
        assert obj.priority == "medium"

    def test_all_fields_required(self):
        # Missing type
        with pytest.raises(ValidationError):
            CreateNotificationRequest(
                patient_id=_PATIENT_UUID,
                title="T",
                body="B",
                priority="low",
            )
        # Missing priority
        with pytest.raises(ValidationError):
            CreateNotificationRequest(
                patient_id=_PATIENT_UUID,
                title="T",
                body="B",
                type="reminder",
            )


class TestNotificationResponseSchema:
    def test_shape(self):
        now = datetime.now(UTC)
        obj = NotificationResponse(
            id=_NOTIF_UUID,
            patient_id=_PATIENT_UUID,
            title="Test",
            body="Body text",
            type="risk_alert",
            priority="high",
            read=False,
            created_at=now,
        )
        assert obj.id == _NOTIF_UUID
        assert obj.read is False
        assert obj.created_at == now

    def test_read_defaults_to_bool(self):
        now = datetime.now(UTC)
        obj = NotificationResponse(
            id=_NOTIF_UUID,
            patient_id=_PATIENT_UUID,
            title="T",
            body="B",
            type="general",
            priority="low",
            read=False,
            created_at=now,
        )
        assert isinstance(obj.read, bool)


# ═══════════════════════════════════════════════════════════════════════════════
# Section 2: HTTP endpoint contracts
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def _db_engine_factory():
    return _build_sqlite_db()


@pytest.fixture(scope="module")
def db_session(_db_engine_factory):
    """Seed DB and return an async generator for dependency injection."""
    import asyncio

    _, factory = _db_engine_factory

    async def _seed():
        async with factory() as session:
            # patients_table is a core Table, insert directly
            await session.execute(patients_table.insert().values(id=_PATIENT_UUID, keycloak_id=_PATIENT_KC_ID))
            await session.execute(patients_table.insert().values(id=_OTHER_UUID, keycloak_id=_OTHER_KC_ID))
            notif = Notification(
                id=_NOTIF_UUID,
                patient_id=_PATIENT_UUID,
                title="Seed notification",
                body="Seeded for tests",
                type="general",
                priority="low",
                read=False,
            )
            session.add(notif)
            await session.commit()

    asyncio.run(_seed())

    async def _get_session():
        async with factory() as s:
            yield s

    return _get_session


@pytest.fixture()
def physician_client(db_session):
    yield from _make_client(db_override=db_session, user_override=_physician_user())


@pytest.fixture()
def patient_client(db_session):
    yield from _make_client(db_override=db_session, user_override=_patient_user(sub=_PATIENT_KC_ID))


@pytest.fixture()
def other_patient_client(db_session):
    yield from _make_client(db_override=db_session, user_override=_patient_user(sub=_OTHER_KC_ID))


# ── POST /api/v1/notifications ────────────────────────────────────────────────


class TestCreateNotification:
    def test_patient_cannot_create_notification_403(self, patient_client):
        resp = patient_client.post(
            "/api/v1/notifications",
            json={
                "patient_id": str(_PATIENT_UUID),
                "title": "Alert",
                "body": "Body",
                "type": "risk_alert",
                "priority": "high",
            },
        )
        assert resp.status_code == 403

    def test_physician_creates_notification_200(self, physician_client):
        resp = physician_client.post(
            "/api/v1/notifications",
            json={
                "patient_id": str(_PATIENT_UUID),
                "title": "Medication Reminder",
                "body": "Take your pills.",
                "type": "reminder",
                "priority": "medium",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["patient_id"] == str(_PATIENT_UUID)
        assert data["title"] == "Medication Reminder"
        assert data["body"] == "Take your pills."
        assert data["type"] == "reminder"
        assert data["priority"] == "medium"
        assert data["read"] is False
        assert "id" in data


# ── GET /api/v1/notifications ─────────────────────────────────────────────────


class TestGetNotifications:
    def test_patient_sees_only_own_notifications(self, patient_client):
        resp = patient_client.get("/api/v1/notifications")
        assert resp.status_code == 200
        items = resp.json()
        assert all(item["patient_id"] == str(_PATIENT_UUID) for item in items)

    def test_patient_cannot_filter_for_other_patient_403(self, patient_client):
        resp = patient_client.get("/api/v1/notifications", params={"patient_id": str(_OTHER_UUID)})
        assert resp.status_code == 403

    def test_physician_can_filter_by_patient_id(self, physician_client):
        resp = physician_client.get("/api/v1/notifications", params={"patient_id": str(_PATIENT_UUID)})
        assert resp.status_code == 200
        items = resp.json()
        assert all(item["patient_id"] == str(_PATIENT_UUID) for item in items)


# ── PATCH /api/v1/notifications/{id} ─────────────────────────────────────────


class TestMarkNotificationRead:
    def test_mark_read_200(self, patient_client):
        resp = patient_client.patch(f"/api/v1/notifications/{_NOTIF_UUID}", json={"read": True})
        assert resp.status_code == 200
        assert resp.json()["read"] is True

    def test_mark_unread_200(self, patient_client):
        """Regression: false must be respected, not ignored."""
        # First mark as read
        resp = patient_client.patch(f"/api/v1/notifications/{_NOTIF_UUID}", json={"read": True})
        assert resp.status_code == 200
        assert resp.json()["read"] is True
        # Then mark as unread
        resp = patient_client.patch(f"/api/v1/notifications/{_NOTIF_UUID}", json={"read": False})
        assert resp.status_code == 200
        assert resp.json()["read"] is False
        # Verify it persists
        resp = patient_client.get("/api/v1/notifications")
        assert resp.status_code == 200
        notifs = [n for n in resp.json() if n["id"] == str(_NOTIF_UUID)]
        assert len(notifs) == 1
        assert notifs[0]["read"] is False

    def test_nonexistent_notification_404(self, patient_client):
        missing = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
        resp = patient_client.patch(f"/api/v1/notifications/{missing}", json={"read": True})
        assert resp.status_code == 404

    def test_wrong_patient_cannot_mark_read_403(self, other_patient_client):
        # _NOTIF_UUID belongs to _PATIENT_UUID; other patient must not patch it
        resp = other_patient_client.patch(f"/api/v1/notifications/{_NOTIF_UUID}", json={"read": True})
        assert resp.status_code == 403


# ═══════════════════════════════════════════════════════════════════════════════
# Section 3: Send notification contracts
# ═══════════════════════════════════════════════════════════════════════════════


@pytest.fixture(scope="module")
def _token_db_engine_factory():
    """Separate in-memory DB that includes a PushToken row for android."""
    import asyncio

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @sa_event.listens_for(engine.sync_engine, "connect")
    def _fk_pragma(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            await s.execute(patients_table.insert().values(id=_PATIENT_UUID, keycloak_id=_PATIENT_KC_ID))
            s.add(
                PushToken(
                    patient_id=_PATIENT_UUID,
                    platform="android",
                    token="fake-fcm-token-abc",
                )
            )
            await s.commit()

    asyncio.run(_init())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


@pytest.fixture()
def token_db_session(_token_db_engine_factory):
    _, factory = _token_db_engine_factory

    async def _get_session():
        async with factory() as s:
            yield s

    return _get_session


@pytest.fixture()
def send_physician_client(token_db_session):
    yield from _make_client(
        db_override=token_db_session,
        user_override=_physician_user(),
    )


@pytest.fixture()
def send_patient_client(token_db_session):
    yield from _make_client(
        db_override=token_db_session,
        user_override=_patient_user(sub=_PATIENT_KC_ID),
    )


@pytest.fixture(scope="module")
def _no_token_db_engine_factory():
    """Separate in-memory DB with NO push tokens."""
    import asyncio

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
    )

    @sa_event.listens_for(engine.sync_engine, "connect")
    def _fk_pragma(conn, _):
        conn.execute("PRAGMA foreign_keys=ON")

    async def _init():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with async_sessionmaker(engine, expire_on_commit=False)() as s:
            await s.execute(patients_table.insert().values(id=_PATIENT_UUID, keycloak_id=_PATIENT_KC_ID))
            await s.commit()

    asyncio.run(_init())
    factory = async_sessionmaker(engine, expire_on_commit=False)
    return engine, factory


@pytest.fixture()
def no_token_db_session(_no_token_db_engine_factory):
    _, factory = _no_token_db_engine_factory

    async def _get_session():
        async with factory() as s:
            yield s

    return _get_session


@pytest.fixture()
def no_token_physician_client(no_token_db_session):
    yield from _make_client(
        db_override=no_token_db_session,
        user_override=_physician_user(),
    )


class TestSendNotification:
    def test_patient_cannot_send_notification_403(self, send_patient_client):
        resp = send_patient_client.post(
            "/api/v1/notifications/send",
            json={
                "patient_id": str(_PATIENT_UUID),
                "title": "T",
                "body": "B",
            },
        )
        assert resp.status_code == 403

    def test_no_push_tokens_returns_404(self, no_token_physician_client):
        resp = no_token_physician_client.post(
            "/api/v1/notifications/send",
            json={
                "patient_id": str(_PATIENT_UUID),
                "title": "T",
                "body": "B",
            },
        )
        assert resp.status_code == 404

    @patch(
        "src.api.routers.notifications._send_fcm",
        new=AsyncMock(return_value=True),
    )
    def test_fcm_token_delivers_android_200(self, send_physician_client):
        resp = send_physician_client.post(
            "/api/v1/notifications/send",
            json={
                "patient_id": str(_PATIENT_UUID),
                "title": "Alert",
                "body": "You have a new alert.",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "android" in data["platforms_sent"]

    @patch(
        "src.api.routers.notifications._send_fcm",
        new=AsyncMock(return_value=False),
    )
    @patch(
        "src.api.routers.notifications._send_apns",
        new=AsyncMock(return_value=False),
    )
    def test_all_delivery_fails_502(self, send_physician_client):
        resp = send_physician_client.post(
            "/api/v1/notifications/send",
            json={
                "patient_id": str(_PATIENT_UUID),
                "title": "Alert",
                "body": "You have a new alert.",
            },
        )
        assert resp.status_code == 502


# ═══════════════════════════════════════════════════════════════════════════════
# Section 4: PushToken DB model contracts
# ═══════════════════════════════════════════════════════════════════════════════


class TestPushTokenUpsertSemantics:
    def test_duplicate_patient_platform_raises_integrity_error(self):
        """Composite PK (patient_id, platform) must reject duplicate inserts."""
        import asyncio

        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )

        @sa_event.listens_for(engine.sync_engine, "connect")
        def _fk(conn, _):
            conn.execute("PRAGMA foreign_keys=ON")

        async def _run():
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)

            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                # Seed a patient row first (FK constraint)
                await session.execute(patients_table.insert().values(id=_PATIENT_UUID, keycloak_id="kc-pk-test"))
                await session.commit()

            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                session.add(
                    PushToken(
                        patient_id=_PATIENT_UUID,
                        platform="ios",
                        token="first-token",
                    )
                )
                await session.commit()

            # Second insert with same (patient_id, platform) must raise
            async with async_sessionmaker(engine, expire_on_commit=False)() as session:
                session.add(
                    PushToken(
                        patient_id=_PATIENT_UUID,
                        platform="ios",
                        token="second-token",
                    )
                )
                with pytest.raises(IntegrityError):
                    await session.commit()

        asyncio.run(_run())
