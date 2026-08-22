"""Base configuration for all CyberEpi microservices.

Subclass `Settings` in each service to add service-specific fields.
Environment variables are read case-insensitively via pydantic-settings.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Common settings shared by every service."""

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    # Service
    service_name: str = "service"
    service_port: int = 8000
    debug: bool = False
    dev_auth_mode: bool = False  # Skip JWT validation for local development

    # Database (no default: services that need a DB must provide one)
    database_url: str = ""

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Kafka
    kafka_bootstrap_servers: str = "localhost:9092"

    # Keycloak
    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "cyberepi"
    keycloak_client_id: str = "cyberepi-api"
    keycloak_client_secret: str = ""

    @property
    def keycloak_jwks_url(self) -> str:
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}/protocol/openid-connect/certs"

    @property
    def keycloak_token_url(self) -> str:
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}/protocol/openid-connect/token"

    @property
    def keycloak_admin_url(self) -> str:
        return f"{self.keycloak_url}/admin/realms/{self.keycloak_realm}"
