"""Unit tests for symptom-service – including Bayesian risk scoring."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import src.main  # noqa: F401  (ensure module exists before patching)


@pytest.fixture
def client(mock_db, mock_redis, mock_kafka_producer):
    with (
        patch("src.main.engine") as mock_main_engine,
        patch("src.main.connect_redis", return_value=mock_redis),
        patch("src.main.connect_kafka", return_value=mock_kafka_producer),
        patch("src.main.disconnect_redis", new=AsyncMock()),
        patch("src.main.disconnect_kafka", new=AsyncMock()),
    ):
        mock_main_engine.dispose = AsyncMock()

        from src.main import app

        app.state.redis = mock_redis
        app.state.kafka_producer = mock_kafka_producer
        with TestClient(app, raise_server_exceptions=False) as c:
            yield c


class TestHealthEndpoint:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "healthy"


class TestAuthRequired:
    def test_symptom_post_without_auth_returns_401(self, client):
        resp = client.post("/api/v1/symptoms", json={"patient_id": str(uuid.uuid4()), "symptoms": ["fever"]})
        assert resp.status_code in (401, 403)

    def test_history_without_auth_returns_401(self, client):
        resp = client.get(f"/api/v1/patients/{uuid.uuid4()}/history")
        assert resp.status_code in (401, 403)


class TestInvalidToken:
    def test_expired_token_returns_401(self, client, expired_token):
        resp = client.post(
            "/api/v1/symptoms",
            headers={"Authorization": f"Bearer {expired_token}"},
            json={"patient_id": str(uuid.uuid4()), "symptoms": ["fever"]},
        )
        assert resp.status_code == 401


class TestBayesianRiskScore:
    """Test the Bayesian risk score computation."""

    def test_risk_score_computation_known_symptoms(self):
        """Verify Bayes formula with known symptom set."""
        from src.services.risk import compute_bayesian_risk

        # With fever + cough + fatigue at default prior (0.01)
        score = compute_bayesian_risk(["fever", "cough", "fatigue"], prior=0.01)
        assert isinstance(score, float)
        assert 0.0 <= score <= 1.0
        # With strong symptoms (fever=0.89, cough=0.82, fatigue=0.77),
        # even lo prior should produce moderate-to-high score
        assert score > 0.05

    def test_risk_score_high_with_multiple_strong_symptoms(self):
        """Multiple strong symptoms should give high score."""
        from src.services.risk import compute_bayesian_risk

        score = compute_bayesian_risk(
            ["fever", "cough", "dyspnoea", "anosmia", "fatigue"],
            prior=0.05,
        )
        assert score > 0.5

    def test_risk_score_low_with_weak_symptoms(self):
        """Weak/non-specific symptoms should give low score."""
        from src.services.risk import compute_bayesian_risk

        score = compute_bayesian_risk(["nausea"], prior=0.01)
        assert score < 0.3

    def test_risk_score_empty_symptoms(self):
        """No matching symptoms: falls back to prior."""
        from src.services.risk import compute_bayesian_risk

        score = compute_bayesian_risk(["unknown_symptom"], prior=0.01)
        # Unknown symptoms don't change the prior
        assert abs(score - 0.01) < 0.001

    def test_risk_score_with_high_prior(self):
        """High regional prevalence should increase posterior."""
        from src.services.risk import compute_bayesian_risk

        low_prior = compute_bayesian_risk(["fever"], prior=0.01)
        high_prior = compute_bayesian_risk(["fever"], prior=0.20)
        assert high_prior > low_prior


class TestRiskTierThresholds:
    def test_tier_low(self):
        from src.services.risk import compute_risk_tier

        assert compute_risk_tier(0.1) == "low"

    def test_tier_moderate(self):
        from src.services.risk import compute_risk_tier

        assert compute_risk_tier(0.3) == "moderate"

    def test_tier_consult(self):
        from src.services.risk import compute_risk_tier

        assert compute_risk_tier(0.6) == "consult"

    def test_tier_urgent(self):
        from src.services.risk import compute_risk_tier

        assert compute_risk_tier(0.8) == "urgent"

    def test_tier_boundary_low(self):
        from src.services.risk import compute_risk_tier

        assert compute_risk_tier(0.29) == "low"

    def test_tier_boundary_urgent(self):
        from src.services.risk import compute_risk_tier

        assert compute_risk_tier(0.99) == "urgent"
