"""CyberEpi Load Test – Locust scenarios.

Simulate concurrent users for:
- SymptomReporter: POST /api/v1/symptoms every 5-10s
- RiskPoller: GET /api/v1/patients/{id}/risk every 30s
- PhysicianDashboard: GET /api/v1/physicians/{id}/panel every 60s

Target: 1000 concurrent users; p99 < 500ms symptom submit; p99 < 200ms risk poll.

Usage:
    locust -f tests/load/locustfile.py --host http://localhost:8000
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from locust import HttpUser, between, task
from locust.contrib.fasthttp import FastHttpUser


# Fake JWT for load testing (bypasses auth in test mode)
LOAD_TEST_TOKEN = (
    "eyJhbGciOiJSUzI1NiJ9."
    "eyJzdWIiOiJsb2FkLXRlc3QiLCJleHAiOjk5OTk5OTk5OTksInJlYWxtX2FjY2VzcyI6"
    "eyJyb2xlcyI6WyJwYXRpZW50IiwicGh5c2ljaWFuIl19fQ."
    "fakesig"
)

HEADERS = {"Authorization": f"Bearer {LOAD_TEST_TOKEN}"}


class SymptomReporter(FastHttpUser):
    """Simulates patients reporting symptoms every 5-10 seconds."""

    weight = 60  # 60% of users
    wait_time = between(5, 10)

    def on_start(self) -> None:
        self.patient_id = str(uuid.uuid4())

    @task
    def report_symptoms(self) -> None:
        payload = {
            "patient_id": self.patient_id,
            "symptoms": ["fever", "cough", "fatigue"],
            "heart_rate": 88,
            "spo2": 96.5,
            "temperature": 38.2,
            "region_id": "US-CA",
            "patch_id": "LA-001",
        }
        self.client.post(
            "/api/v1/symptoms",
            json=payload,
            headers=HEADERS,
            name="/api/v1/symptoms [POST]",
        )


class RiskPoller(FastHttpUser):
    """Simulates apps polling risk score every 30 seconds."""

    weight = 30  # 30% of users
    wait_time = between(25, 35)

    def on_start(self) -> None:
        self.patient_id = str(uuid.uuid4())

    @task
    def poll_risk(self) -> None:
        self.client.get(
            f"/api/v1/patients/{self.patient_id}/risk",
            headers=HEADERS,
            name="/api/v1/patients/{id}/risk [GET]",
        )


class PhysicianDashboard(FastHttpUser):
    """Simulates physicians refreshing their dashboard every 60 seconds."""

    weight = 10  # 10% of users
    wait_time = between(50, 70)

    def on_start(self) -> None:
        self.physician_id = str(uuid.uuid4())

    @task(3)
    def poll_alerts(self) -> None:
        self.client.get(
            f"/api/v1/physicians/{self.physician_id}/alerts/stream",
            headers=HEADERS,
            name="/api/v1/physicians/{id}/alerts/stream [GET]",
            timeout=5,
        )

    @task(1)
    def list_patients(self) -> None:
        self.client.get(
            f"/api/v1/patients/{uuid.uuid4()}/prescriptions",
            headers=HEADERS,
            name="/api/v1/patients/{id}/prescriptions [GET]",
        )
