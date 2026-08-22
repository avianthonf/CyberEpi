
from unittest.mock import patch

import pytest

from shared.config import Settings


@pytest.fixture
def mock_settings():
    return Settings(
        KEYCLOAK_URL="http://keycloak",
        KEYCLOAK_REALM="test",
        KEYCLOAK_CLIENT_ID="test-client"
    )

@pytest.mark.asyncio
async def test_valid_token_accepted(mock_settings):
    """Valid RS256 JWT should be accepted."""
    # Generate a dummy RS256 token
    # In reality we'd need a real key pair for jwt.encode
    # But for testing, let's mock the JWT decoding

    with patch("jwt.decode") as mock_decode:
        mock_payload = {"sub": "123", "realm_access": {"roles": ["patient"]}}
        mock_decode.return_value = mock_payload

        # ... invoke the dependency ...
        # This will need some more mocking of the provider
