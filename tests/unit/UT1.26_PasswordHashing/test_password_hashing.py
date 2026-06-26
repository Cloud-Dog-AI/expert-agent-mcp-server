import pytest
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
Unit Test: UT1.26 - Password Hashing and Verification

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for password hashing and verification

Related Requirements: CS1.1
Related Tasks: T005
Related Architecture: SE1.1
Related Tests: UT1.26

Recent Changes:
- Initial implementation
"""

from src.core.auth.password import hash_password, verify_password
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_hash_password():
    """Test password hashing."""
    password = "test_password_123"
    hashed = hash_password(password)

    assert hashed is not None
    assert isinstance(hashed, str)
    assert len(hashed) > 0
    assert hashed != password  # Should be different from original
    assert hashed.startswith("$argon2id$")  # cloud_dog_idam local-password format
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_verify_password_correct():
    """Test password verification with correct password."""
    password = "test_password_123"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_verify_password_incorrect():
    """Test password verification with incorrect password."""
    password = "test_password_123"
    wrong_password = "wrong_password"
    hashed = hash_password(password)

    assert verify_password(wrong_password, hashed) is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_hash_password_different_salts():
    """Test that same password produces different hashes (due to salt)."""
    password = "test_password_123"
    hashed1 = hash_password(password)
    hashed2 = hash_password(password)

    # Should be different due to random salt
    assert hashed1 != hashed2
    # But both should verify correctly
    assert verify_password(password, hashed1) is True
    assert verify_password(password, hashed2) is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_verify_password_empty():
    """Test password verification with empty password."""
    password = ""
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True
    assert verify_password("wrong", hashed) is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_verify_password_special_characters():
    """Test password hashing with special characters."""
    password = "P@ssw0rd!@#$%^&*()"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True
    assert verify_password("P@ssw0rd!@#$%^&*()", hashed) is True
    assert verify_password("P@ssw0rd!@#$%^&*()x", hashed) is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_verify_password_unicode():
    """Test password hashing with unicode characters."""
    password = "测试密码123"
    hashed = hash_password(password)

    assert verify_password(password, hashed) is True
    assert verify_password("测试密码1234", hashed) is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_verify_password_invalid_hash():
    """Test password verification with invalid hash."""
    password = "test_password"
    invalid_hash = "invalid_hash_string"

    # Should return False for invalid hash
    assert verify_password(password, invalid_hash) is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_verify_password_none_values():
    """Test password verification with None values."""
    # Should handle None gracefully
    assert verify_password("", None) is False
    assert verify_password(None, "") is False

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.pure, pytest.mark.fast]
