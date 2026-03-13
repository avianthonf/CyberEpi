from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    service_name: str = "privacy-service"
    service_port: int = 8006
    
    redis_url: str = "redis://localhost:6379/0"
    
    keycloak_url: str = "http://localhost:8080"
    keycloak_realm: str = "cyberepi"
    keycloak_client_id: str = "cyberepi-api"
    
    max_privacy_budget: float = 10.0
    
    @property
    def keycloak_jwks_url(self) -> str:
        return f"{self.keycloak_url}/realms/{self.keycloak_realm}/protocol/openid-connect/certs"

settings = Settings()
