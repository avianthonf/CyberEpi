"""Tests for the audit trail contract (who accessed whose record, when)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.audit import record_audit


@pytest.mark.asyncio
async def test_record_audit_persists_row():
    db = AsyncMock()
    pid = uuid.uuid4()
    await record_audit(db, actor_sub="physician-1", action="patient.read",
                       patient_id=pid)

    db.add.assert_called_once()
    row = db.add.call_args.args[0]
    assert row.actor_sub == "physician-1"
    assert row.action == "patient.read"
    assert row.patient_id == pid
    assert row.outcome == "success"
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_audit_never_raises_into_request_path():
    db = AsyncMock()
    db.commit.side_effect = RuntimeError("db down")
    # must log and swallow, not break the parent operation
    await record_audit(db, actor_sub="x", action="patient.read")
    db.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_patient_emits_audit_event():
    """GET /patients/{id} must record who read the record."""
    from src.api.routers.patients import get_patient

    pid = uuid.uuid4()
    patient = SimpleNamespace(
        id=pid, keycloak_id="owner-kc-id", first_name="A", last_name="B",
        date_of_birth=None, gender=None, region_id=None, patch_id=None,
        email="a@b.c", phone=None, risk_tier="low",
    )

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = patient
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)

    user = {"sub": "owner-kc-id", "realm_access": {"roles": ["patient"]}}

    with patch("src.api.routers.patients.record_audit",
               new=AsyncMock()) as mock_audit:
        resp = await get_patient(patient_id=pid, db=db, _user=user)

    assert resp is not None
    mock_audit.assert_awaited_once()
    _, kwargs = mock_audit.await_args
    assert kwargs["action"] == "patient.read"
    assert kwargs["actor_sub"] == "owner-kc-id"
    assert kwargs["patient_id"] == pid


@pytest.mark.asyncio
async def test_get_patient_forbidden_emits_no_audit():
    """Denied reads must not record 2 rows or leak; event is only logged
    for successful access (access attempts raise 403 before audit)."""
    from fastapi import HTTPException

    from src.api.routers.patients import get_patient

    pid = uuid.uuid4()
    patient = MagicMock()
    patient.keycloak_id = "someone-else"

    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = patient
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result_mock)
    user = {"sub": "attacker", "realm_access": {"roles": ["patient"]}}

    with patch("src.api.routers.patients.record_audit",
               new=AsyncMock()) as mock_audit, pytest.raises(HTTPException) as exc:
        await get_patient(patient_id=pid, db=db, _user=user)

    assert exc.value.status_code == 403
    mock_audit.assert_not_awaited()
