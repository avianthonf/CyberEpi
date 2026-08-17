"""CyberEpi Disease Dynamics Engine – Configuration."""

from __future__ import annotations

from shared.config import Settings as BaseSettings


class Settings(BaseSettings):
    service_name: str = "epi-engine"
    service_port: int = 8005

    kafka_topic_updates: str = "epi.updates"
    kafka_topic_events: str = "patient.events"

    # When true, forecasts run inline in the API process instead of via Celery.
    # Set CELERY_BROKER_URL to enable async task dispatch instead.
    run_forecast_inline: bool = True


settings = Settings()
