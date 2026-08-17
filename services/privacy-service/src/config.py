"""CyberEpi Privacy Service – Configuration."""

from __future__ import annotations

from shared.config import Settings as BaseSettings


class Settings(BaseSettings):
    service_name: str = "privacy-service"
    service_port: int = 8006

    max_privacy_budget: float = 10.0


settings = Settings()
