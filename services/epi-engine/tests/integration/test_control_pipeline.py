import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import get_current_user
from src.db.connection import get_db
from src.db.models import ControlRecommendation, ControlWeights, EpiParams
from src.main import app


@pytest.fixture
def db():
    mock = AsyncMock(spec=AsyncSession)
    mock.add = MagicMock()
    return mock

@pytest.fixture
def client(db):
    app.dependency_overrides[get_db] = lambda: db

    async def override_auth():
        return {"sub": str(uuid.uuid4()), "realm_access": {"roles": ["admin"]}}

    app.dependency_overrides[get_current_user] = override_auth
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()

def test_get_recommendation_not_found(client, db):
    db.execute.return_value = MagicMock(scalar_one_or_none=lambda: None)
    response = client.get("/api/v1/control/recommendations?region_id=test-region")
    assert response.status_code == 404

def test_update_weights_triggers_task(client, db, mocker):
    mock_task = mocker.patch("src.api.routers.control.solve_optimal_control.delay")
    # Exercise the Celery dispatch path (inline mode is covered elsewhere).
    mocker.patch("src.config.settings.run_forecast_inline", False)

    # Mock existing weights not found
    class MockResult:
        def scalar_one_or_none(self):
            return None
    db.execute.return_value = MockResult()

    payload = {
        "C1": 2.0,
        "C2": 10.0,
        "C3": 1.0,
        "C4": 20.0,
        "W_u1": 1.0,
        "W_u2": 1.0,
        "W_u3": 1.0,
        "ethical_framework": "egalitarian"
    }

    # Set ID and dates since the mock DB won't auto-generate them
    import uuid
    from datetime import UTC, datetime

    async def mock_refresh(obj):
        obj.id = uuid.uuid4()
        obj.updated_at = datetime.now(UTC)

    db.refresh.side_effect = mock_refresh

    response = client.put("/api/v1/control/weights/test-region", json=payload)
    assert response.status_code == 200
    assert mock_task.called
    assert mock_task.call_args[0][0] == "test-region"

@pytest.mark.asyncio
async def test_solve_optimal_control_task(mocker):
    # Mock DB calls inside the task
    mock_db_cm = MagicMock()
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db_cm.return_value.__aenter__.return_value = mock_db
    mocker.patch("src.db.connection.AsyncSessionLocal", mock_db_cm)

    # Mock EpiParams
    mock_params = MagicMock(spec=EpiParams)
    mock_params.region_id = "test-region"
    mock_params.N_pop = 1000000
    mock_params.beta = 0.5
    mock_params.gamma = 0.1
    mock_params.id = uuid.uuid4()
    # Mock table columns for dict conversion
    class MockCol:
        def __init__(self, name):
            self.name = name

    col_names = [
        'beta', 'sigma', 'gamma', 'rho', 'fM', 'fS', 'gamma_M', 'gamma_S',
        'h_rate', 'gamma_H', 'delta', 'gamma_ICU', 'mu', 'mu_icu', 'N_pop',
    ]
    mock_params.__table__.columns = [MockCol(n) for n in col_names]

    for n in col_names:
        setattr(mock_params, n, 0.1) # Default
    mock_params.N_pop = 1000000
    mock_params.beta = 0.5
    mock_params.gamma = 0.1

    # Mock ControlWeights
    mock_weights = MagicMock(spec=ControlWeights)
    mock_weights.C1, mock_weights.C2, mock_weights.C3, mock_weights.C4 = 1, 5, 2, 10
    mock_weights.W_u1, mock_weights.W_u2, mock_weights.W_u3 = 1, 0.5, 0.8
    mock_weights.id = uuid.uuid4()
    mock_weights.ethical_framework = "utilitarian"

    class MockResultParams:
        def scalar_one_or_none(self): return mock_params
    class MockResultWeights:
        def scalar_one_or_none(self):
            return mock_weights

    async def fake_execute(*args, **kwargs):
        if not hasattr(fake_execute, "calls"):
            fake_execute.calls = 0
        fake_execute.calls += 1
        if fake_execute.calls == 1:
            return MockResultParams()
        return MockResultWeights()

    mock_db.execute.side_effect = fake_execute

    from src.tasks.control_tasks import async_solve_optimal_control
    result = await async_solve_optimal_control("test-region")

    assert result["status"] == "success"
    assert mock_db.add.called
    # Check that it added a ControlRecommendation
    added_obj = mock_db.add.call_args[0][0]
    assert isinstance(added_obj, ControlRecommendation)
    assert added_obj.region_id == "test-region"
    assert added_obj.converged in [0, 1]
