"""CyberEpi Notification Service - Configuration."""

from __future__ import annotations

from shared.config import Settings as BaseSettings


class Settings(BaseSettings):
    service_name: str = "notification-service"
    service_port: int = 8004

    firebase_credentials_path: str = ""
    apns_key_path: str = ""
    apns_key_id: str = ""
    apns_team_id: str = ""
    apns_bundle_id: str = "com.cyberepi.patient"


settings = Settings()
