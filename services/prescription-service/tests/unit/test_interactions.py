import pytest
import uuid
from unittest.mock import AsyncMock, patch
from src.services.interactions import check_interactions
from src.db.models import Prescription

@pytest.mark.asyncio
async def test_interaction_detection_success():
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None # Cache miss
    
    mock_db = AsyncMock()
    # Mock active prescriptions
    mock_rx = Prescription(
        id=uuid.uuid4(),
        patient_id=uuid.uuid4(),
        drug_name="Warfarin",
        rxnorm_id="11289", # Warfarin
        status="active"
    )
    
    class MockResult:
        def __init__(self, val): self.val = val
        def scalars(self): 
            class Scalars:
                def __init__(self, val): self.val = val
                def all(self): return self.val
            return Scalars(self.val)
            
    mock_db.execute.return_value = MockResult([mock_rx])
    
    patient_id = mock_rx.patient_id
    new_rxnorm_id = "1191" # Aspirin
    
    # Mock RxNorm interaction API
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "fullInteractionTypeGroup": [{
            "fullInteractionType": [{
                "interactionPair": [{
                    "severity": "high",
                    "description": "Increased risk of bleeding."
                }]
            }]
        }]
    }
    
    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        interactions = await check_interactions(mock_redis, new_rxnorm_id, patient_id, mock_db)
        
    assert len(interactions) == 1
    assert interactions[0]["severity"] == "high"
    assert "bleeding" in interactions[0]["description"]
    assert interactions[0]["drug_b"] == "11289"

@pytest.mark.asyncio
async def test_interaction_caching():
    mock_redis = AsyncMock()
    # Mock cached interaction
    import json
    mock_redis.get.return_value = json.dumps([{
        "severity": "high",
        "description": "Cached interaction",
        "drug_a": "1191",
        "drug_b": "11289"
    }]).encode()
    
    mock_db = AsyncMock()
    mock_rx = Prescription(rxnorm_id="11289", status="active", patient_id=uuid.uuid4(), drug_name="Warfarin")
    
    class MockResult:
        def __init__(self, val): self.val = val
        def scalars(self):
            class Scalars:
                def __init__(self, val): self.val = val
                def all(self): return self.val
            return Scalars(self.val)

    mock_db.execute.return_value = MockResult([mock_rx])
    
    interactions = await check_interactions(mock_redis, "1191", mock_rx.patient_id, mock_db)
    
    assert len(interactions) == 1
    assert interactions[0]["description"] == "Cached interaction"
    # Verify we didn't call the API
    with patch("httpx.AsyncClient.get") as mock_get:
        await check_interactions(mock_redis, "1191", mock_rx.patient_id, mock_db)
        mock_get.assert_not_called()
