"""CyberEpi User Service – Configuration."""

from __future__ import annotations

from shared.config import Settings as BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    service_name: str = "user-service"
    service_port: int = 8001

    keycloak_client_secret: str = ""


settings = Settings()
