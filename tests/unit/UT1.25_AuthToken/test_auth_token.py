# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
Unit Test: UT1.25 - Authentication Token Generation and Validation

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for authentication token generation, validation, and expiration

Related Requirements: CS1.1
Related Tasks: T006
Related Architecture: SE1.1
Related Tests: UT1.25

Recent Changes:
- Initial implementation
"""

import pytest
import time
from src.core.auth.token import TokenManager


@pytest.fixture
def token_manager():
    """Create token manager instance."""
    return TokenManager()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_token_generation(token_manager):
    """Test token generation."""
    user_id = 1
    token = token_manager.generate_token(user_id)

    assert token is not None
    assert isinstance(token, str)
    assert len(token) > 0
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_token_validation_valid(token_manager):
    """Test validation of valid token."""
    user_id = 1
    token = token_manager.generate_token(user_id)

    # Validate token
    is_valid, decoded_user_id = token_manager.validate_token(token)

    assert is_valid is True
    assert decoded_user_id == user_id
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_token_validation_invalid(token_manager):
    """Test validation of invalid token."""
    invalid_token = "invalid_token_string"

    is_valid, user_id = token_manager.validate_token(invalid_token)

    assert is_valid is False
    assert user_id is None
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_token_validation_invalid_emits_structured_audit(token_manager, monkeypatch):
    """Invalid token validation emits a structured audit event."""
    captured = []
    monkeypatch.setattr(
        "src.core.auth.token.log_token_event",
        lambda *args, **kwargs: captured.append((args, kwargs)),
    )

    is_valid, user_id = token_manager.validate_token("invalid_token_string")

    assert is_valid is False
    assert user_id is None
    assert captured == [(("token_validate", "failure"), {"reason": "invalid_or_expired"})]
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_token_validation_expired(token_manager):
    """Test validation of expired token."""
    user_id = 1
    # Generate token with short expiration (1 second)
    token = token_manager.generate_token(user_id, expires_in=1)

    # Wait for expiration
    time.sleep(2)

    # Validate expired token
    is_valid, decoded_user_id = token_manager.validate_token(token)

    assert is_valid is False
    assert decoded_user_id is None
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_token_validation_not_expired(token_manager):
    """Test validation of non-expired token."""
    user_id = 1
    # Generate token with long expiration (1 hour)
    token = token_manager.generate_token(user_id, expires_in=3600)

    # Validate immediately
    is_valid, decoded_user_id = token_manager.validate_token(token)

    assert is_valid is True
    assert decoded_user_id == user_id
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_token_generation_different_users(token_manager):
    """Test token generation for different users."""
    user1_token = token_manager.generate_token(1)
    user2_token = token_manager.generate_token(2)

    assert user1_token != user2_token

    # Validate both tokens
    is_valid1, user_id1 = token_manager.validate_token(user1_token)
    is_valid2, user_id2 = token_manager.validate_token(user2_token)

    assert is_valid1 is True
    assert user_id1 == 1
    assert is_valid2 is True
    assert user_id2 == 2
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_token_generation_unique(token_manager):
    """Test that generated tokens are unique."""
    # Test uniqueness by generating tokens for different users (guaranteed unique)
    # and also test that tokens generated in different seconds are unique
    import time

    # Test 1: Different users produce different tokens
    tokens_different_users = [token_manager.generate_token(user_id) for user_id in range(1, 6)]
    assert len(set(tokens_different_users)) == len(tokens_different_users), (
        "Tokens for different users should be unique"
    )

    # Test 2: Same user, but wait for timestamp to change
    user_id = 1
    tokens = [token_manager.generate_token(user_id)]
    # Wait at least 1 second to ensure different 'iat' timestamp
    time.sleep(1.1)
    tokens.append(token_manager.generate_token(user_id))

    # These should be different due to different 'iat' timestamps
    assert tokens[0] != tokens[1], "Tokens generated in different seconds should be unique"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_token_contains_user_info(token_manager):
    """Test that token contains user information."""
    user_id = 123
    token = token_manager.generate_token(user_id)

    # Validate and extract user info
    is_valid, decoded_user_id = token_manager.validate_token(token)

    assert is_valid is True
    assert decoded_user_id == user_id
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_token_refresh(token_manager):
    """Test token refresh functionality."""
    user_id = 1
    original_token = token_manager.generate_token(user_id, expires_in=60)

    # Refresh token
    new_token = token_manager.refresh_token(original_token)

    assert new_token is not None
    assert new_token != original_token

    # New token should be valid
    is_valid, decoded_user_id = token_manager.validate_token(new_token)
    assert is_valid is True
    assert decoded_user_id == user_id
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_token_revocation(token_manager):
    """Test token revocation."""
    user_id = 1
    token = token_manager.generate_token(user_id)

    # Revoke token
    token_manager.revoke_token(token)

    # Token should no longer be valid
    is_valid, decoded_user_id = token_manager.validate_token(token)
    assert is_valid is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_token_bad_claim_emits_structured_audit(token_manager, monkeypatch):
    """Non-numeric token subjects emit a structured audit event."""
    captured = []

    class _BadTokenService:
        def verify(self, _token):
            return {"user_id": "not-a-number"}

    monkeypatch.setattr(token_manager, "_token_service", _BadTokenService())
    monkeypatch.setattr(
        "src.core.auth.token.log_token_event",
        lambda *args, **kwargs: captured.append((args, kwargs)),
    )

    is_valid, user_id = token_manager.validate_token("bad-claim-token")

    assert is_valid is False
    assert user_id is None
    assert captured
    assert captured[-1][0] == ("token_validate", "failure")
    assert captured[-1][1]["reason"] == "invalid_user_claim"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.pure, pytest.mark.fast]
