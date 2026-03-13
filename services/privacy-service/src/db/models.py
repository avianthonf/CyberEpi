from sqlalchemy import Column, UUID, Float, Integer, DateTime, func
from sqlalchemy.ext.declarative import declarative_base
import uuid

Base = declarative_base()

class PrivacyBudget(Base):
    __tablename__ = "privacy_budget"
    
    user_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    total_consumed = Column(Float, nullable=False, default=0.0)
    last_reset = Column(DateTime(timezone=True))
    n_rounds = Column(Integer, default=0)

class FLRound(Base):
    __tablename__ = "fl_rounds"
    
    round_id = Column(Integer, primary_key=True)
    started_at = Column(DateTime(timezone=True), server_default=func.now())
    completed_at = Column(DateTime(timezone=True))
    n_clients = Column(Integer, default=0)
    epsilon_round = Column(Float, default=0.5)
    model_version = Column(Float)

class FLModelVersion(Base):
    __tablename__ = "fl_model_versions"
    
    version = Column(Float, primary_key=True)
    round_id = Column(Integer)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    params = Column(UUID) # Placeholder for storage path or blob
    metrics = Column(UUID)
