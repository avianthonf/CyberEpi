"""Unit tests for shared config module."""
from shared.config import Settings


def test_settings_defaults():
    """Settings should have sensible defaults."""
    settings = Settings()
    assert settings.service_name == "service"
    assert settings.service_port == 8000
    assert not settings.debug
    assert not settings.dev_auth_mode
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.kafka_bootstrap_servers == "localhost:9092"


def test_settings_from_env(monkeypatch):
    """Settings should load from environment variables."""
    monkeypatch.setenv("SERVICE_NAME", "test-service")
    monkeypatch.setenv("SERVICE_PORT", "9000")
    monkeypatch.setenv("DEBUG", "true")
    monkeypatch.setenv("DEV_AUTH_MODE", "true")
    monkeypatch.setenv("DATABASE_URL", "postgresql://test")

    settings = Settings()
    assert settings.service_name == "test-service"
    assert settings.service_port == 9000
    assert settings.debug
    assert settings.dev_auth_mode
    assert settings.database_url == "postgresql://test"


def test_keycloak_jwks_url():
    """keycloak_jwks_url property should construct correct URL."""
    settings = Settings(
        keycloak_url="http://localhost:8080",
        keycloak_realm="test-realm"
    )
    expected = "http://localhost:8080/realms/test-realm/protocol/openid-connect/certs"
    assert settings.keycloak_jwks_url == expected


def test_keycloak_token_url():
    """keycloak_token_url property should construct correct URL."""
    settings = Settings(
        keycloak_url="http://keycloak:8080",
        keycloak_realm="cyberepi"
    )
    expected = "http://keycloak:8080/realms/cyberepi/protocol/openid-connect/token"
    assert settings.keycloak_token_url == expected


def test_keycloak_admin_url():
    """keycloak_admin_url property should construct correct URL."""
    settings = Settings(
        keycloak_url="https://auth.example.com",
        keycloak_realm="production"
    )
    expected = "https://auth.example.com/admin/realms/production"
    assert settings.keycloak_admin_url == expected


def test_case_insensitive_env_vars(monkeypatch):
    """Settings should accept case-insensitive environment variables."""
    monkeypatch.setenv("service_name", "lowercase-service")
    monkeypatch.setenv("SERVICE_PORT", "8080")

    settings = Settings()
    assert settings.service_name == "lowercase-service"
    assert settings.service_port == 8080
