"""Shared test fixtures for privacy-service."""

from __future__ import annotations

import os

# Deterministic unit-test env: parse-only URLs (engine creation is lazy).
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost:5432/test")
