"""Tests for the interaction-check stub.

The RxNorm DDI API was deprecated upstream (NIH sunset), so
`check_interactions` intentionally returns a single informational notice
instead of querying an external API. These tests pin that contract:
callers (prescription creation) must keep receiving a well-formed,
non-blocking result.
"""

import uuid
from unittest.mock import AsyncMock

import pytest

from src.services.interactions import check_interactions


@pytest.mark.asyncio
async def test_check_interactions_returns_deprecation_notice():
    interactions = await check_interactions(
        db=AsyncMock(), patient_id=uuid.uuid4(), new_drug_name="Aspirin"
    )

    assert len(interactions) == 1
    assert interactions[0]["severity"] == "info"
    assert "unavailable" in interactions[0]["description"]
    assert interactions[0]["drugs"] == ["Aspirin"]


@pytest.mark.asyncio
async def test_check_interactions_never_blocks_on_db():
    """The stub must not hit the DB or raise on any input."""
    db = AsyncMock()
    result = await check_interactions(db=db, patient_id=uuid.uuid4(), new_drug_name="")

    db.execute.assert_not_called()
    assert result and isinstance(result, list)
