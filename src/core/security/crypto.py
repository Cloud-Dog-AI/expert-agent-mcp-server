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
**************************************************
License: Apache 2.0
Ownership: Cloud Dog
Description: Minimal cryptographic helpers for at-rest encryption.

Implements symmetric encryption/decryption using Fernet with a key derived from
`auth.jwt_secret` (config-driven). This supports `privacy.data_encryption_at_rest`
without hardcoding secrets.

Related Requirements: CS1.3, NF1.5
Related Tasks: T041
Related Architecture: SE1.3
Related Tests: AT1.31, UT1.32
**************************************************
"""

from __future__ import annotations

import base64
import hashlib
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken

from src.config.loader import get_config


def _derive_fernet_key(secret: str) -> bytes:
    """
    Derive a Fernet key from an arbitrary secret string.

    Fernet expects 32 urlsafe-base64-encoded bytes.
    """
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _get_fernet() -> Fernet:
    secret = get_config("auth.jwt_secret")
    if not secret:
        raise RuntimeError("auth.jwt_secret not configured; cannot encrypt/decrypt at rest")
    return Fernet(_derive_fernet_key(str(secret)))


def encrypt_if_enabled(plaintext: Optional[str]) -> Optional[str]:
    """Encrypt plaintext if privacy.data_encryption_at_rest is enabled."""
    if plaintext is None:
        return None
    enabled = bool(get_config("privacy.data_encryption_at_rest", False))
    if not enabled:
        return plaintext
    token = _get_fernet().encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_if_enabled(ciphertext: Optional[str]) -> Optional[str]:
    """Decrypt ciphertext if privacy.data_encryption_at_rest is enabled."""
    if ciphertext is None:
        return None
    enabled = bool(get_config("privacy.data_encryption_at_rest", False))
    if not enabled:
        return ciphertext
    try:
        out = _get_fernet().decrypt(ciphertext.encode("utf-8"))
        return out.decode("utf-8")
    except (InvalidToken, ValueError):
        # Backward compatibility: if data was stored plaintext, return as-is.
        return ciphertext
