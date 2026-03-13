import pytest
import numpy as np
from src.population.hotspot import process_hotspot_states

class MockState:
    def __init__(self, patch_id, I, hotspot_prob):
        self.patch_id = patch_id
        self.I = I
        self.hotspot_prob = hotspot_prob

@pytest.mark.asyncio
async def test_process_hotspot_states():
    states = [
        MockState("p1", 110, 0.95),  # Latest comes first
        MockState("p2", 50, 0.2),
        MockState("p1", 100, 0.9),   # Older comes later
    ]
    
    results = await process_hotspot_states(states)
    
    assert len(results) == 2
    
    p1_res = next(r for r in results if r["patch_id"] == "p1")
    p2_res = next(r for r in results if r["patch_id"] == "p2")
    
    # DP adds noise, so we just check structural types
    assert "I_estimate" in p1_res
    assert isinstance(p1_res["I_estimate"], float)
    assert p1_res["hotspot_prob"] == 0.95
    assert p1_res["is_hotspot"] is True
    
    assert "I_estimate" in p2_res
    assert p2_res["hotspot_prob"] == 0.2
    assert p2_res["is_hotspot"] is False
