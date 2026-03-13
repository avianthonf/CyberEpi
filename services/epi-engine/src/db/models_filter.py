from sqlalchemy import Column, String, JSON, DateTime, Float
from .models import Base
import datetime

class FilterHistory(Base):
    __tablename__ = "filter_history"
    
    time = Column(DateTime(timezone=True), primary_key=True, default=datetime.datetime.utcnow)
    region_id = Column(String(50), primary_key=True)
    filter_type = Column(String(20), nullable=False)
    state_vec = Column(JSON, nullable=False)
    variance_vec = Column(JSON, nullable=False)
    obs_params = Column(JSON, nullable=False)
    cusum_score = Column(Float)
    innovation = Column(JSON)
