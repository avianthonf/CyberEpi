"""Integration tests for Population Intelligence Layer."""

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth import get_current_user
from src.db.connection import get_db
from src.db.models import RtEstimate, SpatialState
from src.main import app


@pytest.fixture
def db():
    mock_session = AsyncMock(spec=AsyncSession)
    mock_session.add = MagicMock()

    # Setup mock chain for query results
    mock_result = MagicMock()
    mock_scalars = MagicMock()
    mock_result.scalars.return_value = mock_scalars
    mock_session.execute.return_value = mock_result

    # Store seeded data to return it later
    mock_session._seeded_data = []

    def mock_all():
        return mock_session._seeded_data

    mock_scalars.all.side_effect = mock_all
    return mock_session


@pytest.fixture
def client(db):
    async def override_get_db():
        yield db

    async def override_auth():
        return {"sub": str(uuid.uuid4()), "realm_access": {"roles": ["physician"]}}

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_auth

    with TestClient(app) as c:
        yield c

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_rt_pipeline_integration(client, db):
    # Seed data into our mock's internal storage
    res = RtEstimate(time=datetime.now(UTC), region_id="reg_1", Rt_mean=1.2, Rt_lower=0.8, Rt_upper=1.6)
    db._seeded_data = [res]

    response = client.get("/api/v1/regions/reg_1/Rt")
    assert response.status_code == 200
    data = response.json()
    assert data["latest_Rt"] == 1.2
    assert data["alert"] is True


@pytest.mark.asyncio
async def test_hotspot_api_integration(client, db):
    # Seed spatial_states
    s1 = SpatialState(time=datetime.now(UTC), region_id="reg_1", patch_id="patch_1", I=100, hotspot_prob=0.9)
    db._seeded_data = [s1]

    response = client.get("/api/v1/map/hotspots?region_id=reg_1")
    assert response.status_code == 200
    data = response.json()
    assert data[0]["patch_id"] == "patch_1"
    # Check DP noise (value should be float and not exactly 100 with probability)
    assert isinstance(data[0]["I_estimate"], float)


@pytest.mark.asyncio
async def test_mobility_upload_integration(client, db: AsyncSession):
    csv_content = "from_patch_id,to_patch_id,fraction\np1,p2,0.1\np2,p1,0.2"
    files = {"file": ("mobility.csv", csv_content, "text/csv")}

    response = client.post("/api/v1/mobility/upload?region_id=reg_1", files=files)
    assert response.status_code == 200
    assert response.json()["count"] == 2
