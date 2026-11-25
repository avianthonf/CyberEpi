import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import declarative_base, validates

Base = declarative_base()


class EpiParams(Base):
    __tablename__ = "epi_params"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id = Column(String(50), nullable=False, unique=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    source = Column(String(20), nullable=False)  # 'ekf_estimate' | 'manual_override'

    beta = Column(Float, nullable=False)
    sigma = Column(Float, nullable=False)
    gamma = Column(Float, nullable=False)
    rho = Column(Float, nullable=False, default=1.0)
    fA = Column(Float, nullable=False)
    fM = Column(Float, nullable=False)
    fS = Column(Float, nullable=False)
    alpha = Column(Float, nullable=False)
    h_rate = Column(Float, nullable=False)
    delta = Column(Float, nullable=False)
    mu = Column(Float, nullable=False)
    mu_icu = Column(Float, nullable=False)
    gamma_A = Column(Float, nullable=False)
    gamma_M = Column(Float, nullable=False)
    gamma_S = Column(Float, nullable=False)
    gamma_H = Column(Float, nullable=False)
    gamma_ICU = Column(Float, nullable=False)
    papp = Column(Float, nullable=False, default=0.12)
    N_pop = Column(BigInteger, nullable=False)


class ForecastCache(Base):
    __tablename__ = "forecast_cache"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id = Column(String(50), nullable=False)
    generated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
    horizon_days = Column(Integer, nullable=False)
    trajectory = Column(JSON, nullable=False)  # {t:[], S:[], E:[], IA:[], ...}
    params_hash = Column(String(64), nullable=False)
    state_version = Column(String(64), nullable=False, default="bootstrap")

    __mapper_args__ = {"primary_key": [id]}  # noqa: RUF012 - SQLAlchemy mapping directive


class MobilityMatrix(Base):
    __tablename__ = "mobility_matrix"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id = Column(String(50), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    from_patch = Column(String(20), nullable=False)
    to_patch = Column(String(20), nullable=False)
    fraction = Column(Float, nullable=False)


class SpatialState(Base):
    __tablename__ = "spatial_states"
    time = Column(DateTime(timezone=True), primary_key=True)
    region_id = Column(String(50), nullable=False)
    patch_id = Column(String(20), primary_key=True)
    S = Column(Float, nullable=False, default=0.0)
    E = Column(Float, nullable=True, default=0.0)
    I = Column(Float, nullable=False, default=0.0)
    R = Column(Float, nullable=False, default=0.0)
    H = Column(Float, nullable=True)
    D = Column(Float, nullable=True)
    N = Column(Float, nullable=False)
    Rt = Column(Float, nullable=True)
    I_variance = Column(Float)
    hotspot_prob = Column(Float)


class RtEstimate(Base):
    @validates("Rt_mean", "Rt_lower", "Rt_upper")
    def validate_rt(self, key, value):
        if value < 0:
            raise ValueError(f"{key} must be >= 0")
        return value

    __tablename__ = "rt_estimates"
    time = Column(DateTime(timezone=True), primary_key=True)
    region_id = Column(String(50), primary_key=True)
    patch_id = Column(String(20))
    Rt_mean = Column(Float, nullable=False)
    Rt_lower = Column(Float, nullable=False)
    Rt_upper = Column(Float, nullable=False)
    window_days = Column(Integer, default=7)


class ControlWeights(Base):
    __tablename__ = "control_weights"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id = Column(String(50), nullable=False, unique=True)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_by = Column(PG_UUID(as_uuid=True), nullable=False)

    C1 = Column(Float, nullable=False, default=1.0)
    C2 = Column(Float, nullable=False, default=5.0)
    C3 = Column(Float, nullable=False, default=2.0)
    C4 = Column(Float, nullable=False, default=10.0)

    W_u1 = Column(Float, nullable=False, default=1.0)
    W_u2 = Column(Float, nullable=False, default=0.5)
    W_u3 = Column(Float, nullable=False, default=0.8)

    ethical_framework = Column(String(50))  # 'utilitarian'|'libertarian'|'egalitarian'|'custom'
    notes = Column(Text)


class ControlRecommendation(Base):
    @validates("u1_recommended", "u2_recommended", "u3_recommended")
    def validate_controls(self, key, value):
        if not (0 <= value <= 1):
            raise ValueError(f"{key} must be between 0 and 1")
        return value

    __tablename__ = "control_recommendations"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    region_id = Column(String(50), nullable=False)
    generated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    weights_id = Column(PG_UUID(as_uuid=True), sa.ForeignKey("control_weights.id", ondelete="CASCADE"), nullable=False)

    u1_recommended = Column(Float, nullable=False)
    u2_recommended = Column(Float, nullable=False)
    u3_recommended = Column(Float, nullable=False)

    Rt_current = Column(Float, nullable=False)
    Rt_predicted_30d = Column(Float, nullable=False)
    cost_J = Column(Float, nullable=False)
    converged = Column(Integer, nullable=False)  # Boolean as int for safety

    trajectory = Column(JSON)  # full x(t) and u(t) arrays
    rationale = Column(Text)


class FilterState(Base):
    """Persistent storage for EKF/Particle Filter state with Redis cache."""

    __tablename__ = "filter_states"

    region_id = Column(String(50), primary_key=True)
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
    )
    filter_type = Column(String(20), nullable=False)  # 'ekf' | 'particle'

    # State vector [S, E, IA, IM, IS, H, ICU, R, D, papp, ptest, kappa]
    state_vector = Column(JSON, nullable=False)  # 12-element array
    covariance_matrix = Column(JSON, nullable=False)  # 12x12 flattened or compressed

    # Metadata
    cusum_score = Column(Float, nullable=False, default=0.0)
    fail_count = Column(Integer, nullable=False, default=0)
    last_observation = Column(JSON)  # 5-element observation vector
    last_innovation = Column(JSON)  # innovation from last update
    last_chi2 = Column(Float)

    # History depth for Postgres — last N observations
    observation_history = Column(JSON)  # Array of {timestamp, y_obs, innovation}


class SurveillanceObservation(Base):
    """Per-region weekly surveillance observations from official feeds.

    Sources: FluSight target-hospital-admissions (NHSN influ hospitalizations)
    and FluSight target-ed-visits-prop (NSSP ED influenza visit fraction).
    """

    __tablename__ = "surveillance_observations"

    region_id = Column(String(50), primary_key=True)  # FIPS or 'US'
    week_end = Column(DateTime(timezone=True), primary_key=True, index=True)
    admissions = Column(Float)  # weekly incident influenza admissions
    ili_fraction = Column(Float)  # fraction of ED visits with influenza
    source = Column(String(40), nullable=False)
    fetched_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC))
