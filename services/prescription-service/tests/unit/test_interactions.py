"""Tests for the local drug-drug interaction check.

The NLM/RxNav Drug Interaction API was discontinued 2024-01-02.
`check_interactions` now evaluates the bundled ONC high-priority DDI rule
subset (`src/services/ddi_data.py`) against the patient's active
prescriptions — local, deterministic, no external network calls.
"""

import uuid
from unittest.mock import AsyncMock

import pytest

from src.services.interactions import check_interactions


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeDB:
    """Returns the given active drug names from execute()."""

    def __init__(self, active_drugs):
        self._rows = [(d,) for d in active_drugs]
        self.executed = 0

    async def execute(self, _query):
        self.executed += 1
        return _FakeResult(self._rows)


@pytest.mark.asyncio
async def test_check_interactions_flags_known_pair():
    db = _FakeDB(["Warfarin 5mg tablet"])
    hits = await check_interactions(
        db=db, patient_id=uuid.uuid4(), new_drug_name="Ibuprofen 200mg"
    )

    assert len(hits) == 1
    assert hits[0]["severity"] == "major"
    assert sorted(hits[0]["drugs"]) == ["Ibuprofen 200mg", "Warfarin 5mg tablet"]


@pytest.mark.asyncio
async def test_check_interactions_clean_for_unknown_pair():
    db = _FakeDB(["Metformin 500mg"])
    hits = await check_interactions(
        db=db, patient_id=uuid.uuid4(), new_drug_name="Atorvastatin"
    )

    assert hits == []


@pytest.mark.asyncio
async def test_check_interactions_ignores_pair_without_new_drug():
    """Interactions among existing meds alone are not reported here."""
    db = _FakeDB(["Warfarin", "Aspirin"])
    hits = await check_interactions(
        db=db, patient_id=uuid.uuid4(), new_drug_name="Atorvastatin"
    )

    assert hits == []


@pytest.mark.asyncio
async def test_check_interactions_contraindicated_pair():
    db = _FakeDB(["Nitroglycerin"])
    hits = await check_interactions(
        db=db, patient_id=uuid.uuid4(), new_drug_name="Sildenafil"
    )

    assert len(hits) == 1
    assert hits[0]["severity"] == "contraindicated"


@pytest.mark.asyncio
async def test_check_interactions_handles_empty_inputs():
    db = _FakeDB([])
    hits = await check_interactions(db=db, patient_id=uuid.uuid4(), new_drug_name="")

    assert hits == []


@pytest.mark.asyncio
async def test_check_interactions_never_raises_on_db_error():
    """DB failure must surface as an exception, not be swallowed (fail-fast
    in callers' hands), but a normal empty result set must not raise."""
    db = AsyncMock()
    db.execute.side_effect = RuntimeError("db down")
    with pytest.raises(RuntimeError):
        await check_interactions(db=db, patient_id=uuid.uuid4(), new_drug_name="X")
