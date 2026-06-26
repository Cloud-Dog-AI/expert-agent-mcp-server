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
Unit Test: UT1.90 - Security Crypto Helpers

License: Apache 2.0
Ownership: Cloud Dog
Description: Validates encryption/decryption helpers and API key validation behaviour.

Related Requirements: CS1.3, NF1.5
Related Tasks: T041, T055
Related Architecture: SE1.3
Related Tests: UT1.90
"""

from __future__ import annotations

import pytest

from src.core.security.crypto import encrypt_if_enabled, decrypt_if_enabled
from src.core.auth.api_key_manager import APIKeyManager
from src.core.auth.user_manager import UserManager
from src.config.loader import load_config, get_config
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-002")


def test_crypto_encrypt_decrypt_roundtrip(test_env_file):
    load_config.cache_clear()
    plain = "hello world"
    enc = encrypt_if_enabled(plain)
    assert isinstance(enc, str)
    dec = decrypt_if_enabled(enc)
    assert dec == plain
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-002")


def test_crypto_decrypt_plaintext_backward_compat(test_env_file):
    load_config.cache_clear()
    plain = '{"k":"v"}'
    dec = decrypt_if_enabled(plain)
    assert dec == plain
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-002")


def test_api_key_manager_validate_key_roundtrip(db_session, test_env_file):
    load_config.cache_clear()
    user_mgr = UserManager(db_session)
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in config")
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    domain = base_email.split("@", 1)[1]
    user = user_mgr.create_user(
        username=f"{base_username}_ut190",
        email=f"ut190@{domain}",
        password=password,
        role="user",
    )

    km = APIKeyManager(db_session)
    created = km.generate_key(user_id=user.id, name="ut190_key")
    key_plain = created["key"]

    validated = km.validate_key(key_plain)
    assert validated is not None
    assert validated.user_id == user.id

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.db, pytest.mark.smtp, pytest.mark.fast]

