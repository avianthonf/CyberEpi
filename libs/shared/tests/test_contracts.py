"""Contract tests for shared public API.

These tests pin observable behavioral promises — not implementation details.
Each test must fail on any plausible regression of the documented contract.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from shared.config import Settings
from shared.health import _db_healthy, _redis_healthy

# ---------------------------------------------------------------------------
# Settings URLs compose from keycloak_url + keycloak_realm
# ---------------------------------------------------------------------------


class TestSettingsKeycloakUrls:
    @pytest.fixture
    def kc(self):
        return Settings(keycloak_url="http://kc.example.com:8080", keycloak_realm="testrealm")

    def test_jwks_url(self, kc):
        assert kc.keycloak_jwks_url == ("http://kc.example.com:8080/realms/testrealm/protocol/openid-connect/certs")

    def test_token_url(self, kc):
        assert kc.keycloak_token_url == ("http://kc.example.com:8080/realms/testrealm/protocol/openid-connect/token")

    def test_admin_url(self, kc):
        assert kc.keycloak_admin_url == ("http://kc.example.com:8080/admin/realms/testrealm")

    def test_urls_change_with_realm(self):
        s1 = Settings(keycloak_url="http://host", keycloak_realm="realm-a")
        s2 = Settings(keycloak_url="http://host", keycloak_realm="realm-b")
        assert "realm-a" in s1.keycloak_jwks_url
        assert "realm-b" in s2.keycloak_jwks_url
        assert s1.keycloak_jwks_url != s2.keycloak_jwks_url

    def test_urls_change_with_keycloak_url(self):
        s1 = Settings(keycloak_url="http://host-a", keycloak_realm="r")
        s2 = Settings(keycloak_url="http://host-b", keycloak_realm="r")
        assert s1.keycloak_token_url != s2.keycloak_token_url

    def test_settings_accept_env_override(self, monkeypatch):
        monkeypatch.setenv("KEYCLOAK_REALM", "overridden")
        s = Settings(keycloak_url="http://x")
        assert s.keycloak_realm == "overridden"
        assert "overridden" in s.keycloak_jwks_url


# ---------------------------------------------------------------------------
# publish_kafka propagates dependency failures
# ---------------------------------------------------------------------------


class TestPublishKafka:
    def test_raises_when_producer_send_raises(self):
        """A producer whose send_and_wait raises must propagate the error."""
        from shared.kafka import publish_kafka

        producer = MagicMock()
        producer.send_and_wait = AsyncMock(side_effect=RuntimeError("broker down"))

        with pytest.raises(RuntimeError, match="broker down"):
            asyncio.run(publish_kafka(producer, "test-topic", b"payload", timeout=5.0))

    def test_raises_timeout_error_when_send_hangs(self):
        """A producer that never completes send_and_wait must raise TimeoutError."""
        from shared.kafka import publish_kafka

        async def _hang(*_args, **_kwargs):
            await asyncio.sleep(9999)

        producer = MagicMock()
        producer.send_and_wait = _hang

        with pytest.raises((TimeoutError, asyncio.TimeoutError)):
            asyncio.run(publish_kafka(producer, "test-topic", b"payload", timeout=0.05))


# ---------------------------------------------------------------------------
# Redis readiness reflects actual dependency availability
# ---------------------------------------------------------------------------


class TestRedisHealthy:
    def _make_request(self, redis_value):
        """Build a minimal Request-like namespace with app.state.redis set."""
        state = SimpleNamespace(redis=redis_value)
        app = SimpleNamespace(state=state)
        return SimpleNamespace(app=app)

    def test_none_redis_returns_false(self):
        request = self._make_request(None)
        ok, _detail = asyncio.run(_redis_healthy(request))
        assert ok is False

    def test_none_redis_detail_starts_with_unhealthy(self):
        request = self._make_request(None)
        _, detail = asyncio.run(_redis_healthy(request))
        assert detail.startswith("unhealthy:")

    def test_working_redis_returns_true(self):
        redis_mock = MagicMock()
        redis_mock.ping = AsyncMock(return_value=True)
        request = self._make_request(redis_mock)
        ok, detail = asyncio.run(_redis_healthy(request))
        assert ok is True
        assert detail.startswith("healthy")

    def test_failing_redis_ping_returns_false(self):
        redis_mock = MagicMock()
        redis_mock.ping = AsyncMock(side_effect=ConnectionError("refused"))
        request = self._make_request(redis_mock)
        ok, detail = asyncio.run(_redis_healthy(request))
        assert ok is False
        assert detail.startswith("unhealthy:")

    def test_missing_state_attr_returns_false(self):
        # app.state has no 'redis' attribute at all — getattr must return None
        state = SimpleNamespace()  # no redis attribute
        app = SimpleNamespace(state=state)
        request = SimpleNamespace(app=app)
        ok, detail = asyncio.run(_redis_healthy(request))
        assert ok is False
        assert detail.startswith("unhealthy:")


# ---------------------------------------------------------------------------
# Database readiness reports unavailable engines
# ---------------------------------------------------------------------------


class TestDbHealthy:
    def test_none_engine_returns_false(self):
        ok, _detail = asyncio.run(_db_healthy(None))
        assert ok is False

    def test_none_engine_detail_starts_with_unhealthy(self):
        _, detail = asyncio.run(_db_healthy(None))
        assert detail.startswith("unhealthy:")
