"""CyberEpi User Service - Configuration."""

from __future__ import annotations

from shared.config import Settings as BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    service_name: str = "user-service"
    service_port: int = 8001
    keycloak_admin_realm: str = "master"
    keycloak_admin_client_id: str = "admin-cli"
    keycloak_admin_username: str = "admin"
    keycloak_admin_password: str = "admin"


settings = Settings()
