import os
import uuid

import pytest

os.environ["DATABASE_URL"] = "postgresql+asyncpg://user:pass@localhost/db"
os.environ["KAFKA_BOOTSTRAP_SERVERS"] = "localhost:9092"
os.environ["REDIS_URL"] = "redis://localhost:6379"
os.environ["KEYCLOAK_URL"] = "http://localhost:8080"
os.environ["KEYCLOAK_REALM"] = "cyberepi"
os.environ["KEYCLOAK_CLIENT_ID"] = "test"
os.environ["KEYCLOAK_CLIENT_SECRET"] = "test"

from src.services.risk import calculate_and_update_risk


class MockDB:
    def __init__(self, count_val=3):
        self.count_val = count_val
        self.executed_queries = []

    async def execute(self, query, params=None):
        self.executed_queries.append((query, params))
        class MockResult:
            def __init__(self, val): self.val = val
            def scalar(self): return self.val
        return MockResult(self.count_val)

class MockRedis:
    async def get(self, key):
        return b'{"prevalence": 0.05}'

class MockApp:
    def __init__(self):
        self.state = type('State', (), {'redis': MockRedis()})()

class MockRequest:
    def __init__(self):
        self.app = MockApp()

class MockBody:
    def __init__(self, symptoms, spo2):
        self.patient_id = uuid.uuid4()
        self.symptoms = symptoms
        self.spo2 = spo2

@pytest.mark.asyncio
async def test_calculate_and_update_risk():
    db = MockDB()
    request = MockRequest()
    body = MockBody(symptoms=["fever", "cough"], spo2=92)
    region_id = "reg1"

    # Needs to mock compute_bayesian_risk from routers if not already, but since they exist in the router file
    # calculate_and_update_risk imports them. Wait, calculate_and_update_risk imports from src.api.routers.symptoms
    # Let's see if we can just test the integration or mock them out.
    # risk.py imports them so it should run.
    report_count, risk_score, risk_tier = await calculate_and_update_risk(db, request, body, region_id)

    assert report_count == 4 # 3 + 1
    assert 0.0 <= risk_score <= 1.0
    assert risk_score > 0.5 # symptomatic inputs should yield high risk
    assert risk_tier in ["consult", "urgent"] # should not be low for fever/cough+low spo2
    assert len(db.executed_queries) == 2 # count, and update
