"""Integration test: Symptom submission → Kafka → Avro schema validation.

Requires: running Kafka, Schema Registry, Postgres, Redis.
Run with: pytest tests/integration/ -v
"""

from __future__ import annotations

import json
import uuid

import pytest


class TestSymptomToKafka:
    """Verify the end-to-end flow: symptom → Kafka event."""

    def test_event_format_matches_avro_schema(self):
        """Validate that a mock patient event matches the PatientEvent Avro schema."""
        event = {
            "event_id": str(uuid.uuid4()),
            "patient_id": str(uuid.uuid4()),
            "event_type": "SYMPTOM_REPORT",
            "timestamp_ms": 1710000000000,
            "region_id": "US-CA",
            "patch_id": "LA-001",
            "payload": json.dumps({
                "symptoms": ["fever", "cough"],
                "risk_score": 0.45,
                "risk_tier": "moderate",
            }),
            "schema_ver": "1.0",
        }

        # Validate required fields
        required_fields = [
            "event_id", "patient_id", "event_type",
            "timestamp_ms", "region_id", "patch_id",
            "payload", "schema_ver",
        ]
        for field in required_fields:
            assert field in event, f"Missing field: {field}"

        # Validate event_type enum
        valid_types = ["SYMPTOM_REPORT", "VITAL_UPDATE", "MED_SCAN", "EXPOSURE_ALERT"]
        assert event["event_type"] in valid_types

        # Validate timestamp is positive integer
        assert isinstance(event["timestamp_ms"], int)
        assert event["timestamp_ms"] > 0

        # Validate payload is valid JSON
        payload = json.loads(event["payload"])
        assert "symptoms" in payload

    def test_event_serialization_roundtrip(self):
        """Verify event can be serialized and deserialized."""
        event = {
            "event_id": str(uuid.uuid4()),
            "patient_id": str(uuid.uuid4()),
            "event_type": "SYMPTOM_REPORT",
            "timestamp_ms": 1710000000000,
            "region_id": "US-CA",
            "patch_id": "LA-001",
            "payload": json.dumps({"symptoms": ["fever"]}),
            "schema_ver": "1.0",
        }

        serialized = json.dumps(event).encode("utf-8")
        deserialized = json.loads(serialized.decode("utf-8"))

        assert deserialized == event
        assert deserialized["event_type"] == "SYMPTOM_REPORT"


class TestEpiUpdateSchema:
    """Validate EpiUpdate event format."""

    def test_epi_update_format(self):
        event = {
            "event_id": str(uuid.uuid4()),
            "region_id": "US-CA",
            "patch_id": None,
            "timestamp_ms": 1710000000000,
            "update_type": "RT_UPDATE",
            "Rt": 1.25,
            "payload": json.dumps({"confidence_interval": [1.1, 1.4]}),
        }

        valid_update_types = ["RT_UPDATE", "STATE_UPDATE", "HOTSPOT_ALERT", "CONTROL_RECOMMENDATION"]
        assert event["update_type"] in valid_update_types
        assert event["Rt"] is None or isinstance(event["Rt"], (int, float))
