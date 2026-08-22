"""CyberEpi Symptom Service - Configuration."""

from __future__ import annotations

from shared.config import Settings as BaseSettings


class Settings(BaseSettings):
    service_name: str = "symptom-service"
    service_port: int = 8002


settings = Settings()
