"""CyberEpi User Service – Configuration via pydantic-settings."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    # Service
    service_name: str = "user-service"
    service_port: int = 8001
    debug: bool = False

    # Database (Value required in environment, no default for security)
    database_url: str

    # Redis
    redis_url: str = "redis://localhost:6379/0"

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


settings = Settings()
