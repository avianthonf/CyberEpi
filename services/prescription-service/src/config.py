"""CyberEpi Prescription Service – Configuration."""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False)

    service_name: str = "prescription-service"
    service_port: int = 8003
    debug: bool = False

    database_url: str
    redis_url: str = "redis://localhost:6379/0"

    openfda_api_url: str = "https://api.fda.gov"
    rxnorm_api_url: str = "https://rxnav.nlm.nih.gov/REST"
    fda_cache_ttl: int = 86400  # 24 hours

    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "cyberepi"
    keycloak_client_id: str = "cyberepi-api"

    @property
    def keycloak_jwks_url(self) -> str:
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}/protocol/openid-connect/certs"


settings = Settings()
