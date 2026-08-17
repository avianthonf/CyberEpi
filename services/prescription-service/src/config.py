"""CyberEpi Prescription Service – Configuration."""

from __future__ import annotations

from shared.config import Settings as BaseSettings


class Settings(BaseSettings):
    service_name: str = "prescription-service"
    service_port: int = 8003

    openfda_api_url: str = "https://api.fda.gov"
    rxnorm_api_url: str = "https://rxnav.nlm.nih.gov/REST"
    fda_cache_ttl: int = 86400  # 24 hours


settings = Settings()
