"""Privacy-service database models."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSON as PG_JSON
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class DPBudget(Base):
    """Differential privacy budget tracker — Postgres-backed with Redis cache."""

    __tablename__ = "dp_budgets"

    user_id = Column(PG_UUID(as_uuid=True), primary_key=True)
    consumed = Column(Float, nullable=False, default=0.0)
    max_budget = Column(Float, nullable=False, default=10.0)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    reset_count = Column(Integer, nullable=False, default=0)


class DPQuery(Base):
    """Audit log for DP queries."""

    __tablename__ = "dp_queries"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(PG_UUID(as_uuid=True), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))

    mechanism = Column(String(50), nullable=False)  # 'gaussian' | 'laplace' | 'exponential'
    epsilon = Column(Float, nullable=False)
    sensitivity = Column(Float, nullable=False)

    query_type = Column(String(100))  # e.g., 'count', 'sum', 'mean'
    noised_value = Column(Float)
    query_metadata = Column(Text)  # JSON string with additional context


class FLRound(Base):
    """Federated learning completed round storage."""

    __tablename__ = "fl_rounds"

    round_id = Column(Integer, primary_key=True)
    completed_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
    )
    num_clients = Column(Integer, nullable=False)
    model_params = Column(PG_JSON, nullable=False)  # List of floats
    aggregation_config = Column(PG_JSON)  # Dict with C, epsilon, delta
