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

    # Broker URL for Celery. Defaults to a Redis-backed broker on the same
    # host as the main Redis, but can be overridden (e.g. RabbitMQ, separate
    # Redis cluster, in-memory test broker).
    celery_broker_url: str = ""

    @property
    def celery_url(self) -> str:
        """Resolved Celery broker URL.

        Falls back to the configured Redis URL when no Celery-specific
        override is provided. Empty string disables dispatch (callers must
        use the inline path).
        """
        return self.celery_broker_url or self.redis_url

    # --- Continuous surveillance ingestion (FluSight targets: NHSN + NSSP) ---
    surveillance_enabled: bool = True
    # Poll cadence for the remote feeds; both CDC files refresh weekly
    # (hospitalizations Fri, ED-visits Mon), so every 12h keeps us current
    # without hammering the source.
    surveillance_refresh_seconds: int = 43200
    # On startup, ingest this many most-recent weeks immediately.
    surveillance_backfill_weeks: int = 520
    surveillance_admissions_url: str = (
        "https://raw.githubusercontent.com/cdcepi/FluSight-forecast-hub/"
        "main/target-data/target-hospital-admissions.csv"
    )
    surveillance_ili_url: str = (
        "https://raw.githubusercontent.com/cdcepi/FluSight-forecast-hub/"
        "main/target-data/target-ed-visits-prop.csv"
    )


settings = Settings()
