import os
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    service_name: str = "epi-engine"
    port: int = 8005
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost/cyberepi_engine"
    redis_url: str = "redis://localhost:6379/0"
    kafka_bootstrap_servers: str = "localhost:9092"
    kafka_topic_updates: str = "epi.updates"
    kafka_topic_events: str = "patient.events"
    
    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "cyberepi"
    keycloak_client_id: str = "cyberepi-api"

    @property
    def keycloak_jwks_url(self) -> str:
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}/protocol/openid-connect/certs"
    
    model_config = {
        "env_file": ".env",
        "env_prefix": "",
        "case_sensitive": False
    }

settings = Settings()
