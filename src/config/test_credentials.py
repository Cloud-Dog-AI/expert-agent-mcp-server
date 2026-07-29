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

"""Test-profile credential derivation without persisting or logging secrets."""

from __future__ import annotations


def derive_test_user_password(configured_value: str) -> str:
    """Return a deterministic policy-compliant test-user password.

    Test profiles currently derive their user password from a service credential.
    That credential is not guaranteed to satisfy the local-user password policy.
    Derive the effective test password from the configured secret so every normal
    configuration path can seed and authenticate the same principal without
    storing a separate literal password.
    """
    value = str(configured_value or "")
    if not value:
        raise ValueError("test.user.password must be configured")

    suffix = ""
    if not any(character.islower() for character in value):
        suffix += "a"
    if not any(character.isupper() for character in value):
        suffix += "A"
    if not any(character.isdigit() for character in value):
        suffix += "1"
    if not any(not character.isalnum() for character in value):
        suffix += "!"
    if len(value) + len(suffix) < 8:
        suffix += "aA1!"
    return f"{value}{suffix}"
