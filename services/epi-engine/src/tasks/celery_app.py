from celery import Celery
import os
from ..config import settings

celery_app = Celery(
    "tasks",
    broker=os.getenv("CELERY_BROKER_URL", "redis://localhost:6379/1"),
    backend=os.getenv("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")
)

@celery_app.task
def run_forecast_async(region_id: str, horizon_days: int):
    # This is implemented in celery_app_impl.py
    pass

from .celery_app_impl import run_forecast_async, recompute_all_regions
from .control_tasks import solve_optimal_control

@celery_app.task
def recompute_all_regions():
    # Trigger run_forecast_async for all regions
    pass
