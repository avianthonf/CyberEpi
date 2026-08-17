import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from src.services.interactions import check_interactions
from src.db.models import Prescription

@pytest.mark.asyncio
async def test_interaction_detection_success():
    mock_redis = AsyncMock()
    mock_redis.mget.return_value = [None]  # Cache miss for the single pair

    mock_db = AsyncMock()
    # Mock active prescriptions
    mock_rx = Prescription(
        id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        drug_name="Warfarin",
        rxnorm_id="11289",  # Warfarin
        status="active"
    )

    class MockResult:
        def __init__(self, val):
            self.val = val

        def scalars(self):
            class Scalars:
                def __init__(self, val):
                    self.val = val

                def all(self):
                    return self.val

            return Scalars(self.val)

    mock_db.execute.return_value = MockResult([mock_rx])

    patient_id = mock_rx.patient_id
    new_rxnorm_id = "1191"  # Aspirin

    # Mock RxNorm interaction API — patch the whole AsyncClient so the
    # `async with httpx.AsyncClient(...)` in the service gets a mock whose
    # `.get()` returns a real-ish Response-like object.
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "fullInteractionTypeGroup": [{
            "fullInteractionType": [{
                "interactionPair": [{
                    "severity": "high",
                    "description": "Increased risk of bleeding.",
                }]
            }]
        }]
    }

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    async def _mock_context(*args, **kwargs):
        return mock_client

    mock_client.__aenter__ = _mock_context
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("httpx.AsyncClient", return_value=mock_client):
        interactions = await check_interactions(mock_redis, new_rxnorm_id, patient_id, mock_db)

    assert len(interactions) == 1
    assert interactions[0]["severity"] == "high"
    assert "bleeding" in interactions[0]["description"]
    # The pair is sorted (min, max) by rxnorm ID — check both slots cover the pair
    assert {interactions[0]["drug_a"], interactions[0]["drug_b"]} == {"1191", "11289"}
    assert interactions[0]["drug_b_name"] == "Warfarin"

    # Result should have been cached via setex
    mock_redis.setex.assert_called_once()


@pytest.mark.asyncio
async def test_interaction_caching():
    mock_redis = AsyncMock()
    # Mock cached interaction — batch mget returns it
    import json

    cached = json.dumps([{
        "severity": "high",
        "description": "Cached interaction",
        "drug_a": "1191",
        "drug_b": "11289",
    }]).encode()
    mock_redis.mget.return_value = [cached]

    mock_db = AsyncMock()
    mock_rx = Prescription(rxnorm_id="11289", status="active", patient_id=uuid.uuid4(), drug_name="Warfarin")

    class MockResult:
        def __init__(self, val):
            self.val = val

        def scalars(self):
            class Scalars:
                def __init__(self, val):
                    self.val = val

                def all(self):
                    return self.val

            return Scalars(self.val)

    mock_db.execute.return_value = MockResult([mock_rx])

    interactions = await check_interactions(mock_redis, "1191", mock_rx.patient_id, mock_db)

    assert len(interactions) == 1
    assert interactions[0]["description"] == "Cached interaction"
    # Verify we didn't call the API
    with patch("httpx.AsyncClient.get") as mock_get:
        await check_interactions(mock_redis, "1191", mock_rx.patient_id, mock_db)
        mock_get.assert_not_called()
