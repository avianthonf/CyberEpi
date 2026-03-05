"""CyberEpi Symptom Service – Configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    service_name: str = "symptom-service"
    service_port: int = 8002
    debug: bool = False

    database_url: str = "postgresql+asyncpg://cyberepi:devpassword@localhost:5432/cyberepi"
    redis_url: str = "redis://localhost:6379/0"
    kafka_bootstrap_servers: str = "localhost:9092"

    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "cyberepi"

    @property
    def keycloak_jwks_url(self) -> str:
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}/protocol/openid-connect/certs"


settings = Settings()
