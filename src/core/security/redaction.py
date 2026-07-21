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

"""Write-only credential handling for API and MCP response payloads."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, Iterable


REDACTED_SECRET = "[REDACTED]"

_SENSITIVE_KEYS = frozenset(
    {
        "access_key",
        "access_key_id",
        "access_token",
        "api_key",
        "apikey",
        "auth_token",
        "client_secret",
        "credential",
        "credentials",
        "jwt_secret",
        "password",
        "passwd",
        "private_key",
        "refresh_token",
        "secret",
        "secret_access_key",
        "secret_key",
        "token",
    }
)


def _normalise_key(key: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")


def _sensitive_keys(extra_sensitive_keys: Iterable[str]) -> frozenset[str]:
    return _SENSITIVE_KEYS | frozenset(_normalise_key(key) for key in extra_sensitive_keys)


def redact_sensitive_values(
    value: Any,
    *,
    extra_sensitive_keys: Iterable[str] = (),
) -> Any:
    """Return a JSON-compatible copy with non-empty credential values redacted."""
    sensitive_keys = _sensitive_keys(extra_sensitive_keys)

    def _redact(item: Any) -> Any:
        if isinstance(item, Mapping):
            redacted: dict[Any, Any] = {}
            for key, child in item.items():
                if _normalise_key(key) in sensitive_keys and child not in (None, ""):
                    redacted[key] = REDACTED_SECRET
                else:
                    redacted[key] = _redact(child)
            return redacted
        if isinstance(item, (list, tuple)):
            return [_redact(child) for child in item]
        return item

    return _redact(value)


def merge_write_only_values(
    existing: Mapping[str, Any] | None,
    incoming: Mapping[str, Any] | None,
    *,
    extra_sensitive_keys: Iterable[str] = (),
) -> dict[str, Any]:
    """Merge config while treating response redaction markers as unchanged secrets."""
    sensitive_keys = _sensitive_keys(extra_sensitive_keys)
    merged: dict[str, Any] = dict(existing or {})

    for key, value in (incoming or {}).items():
        normalised = _normalise_key(key)
        if normalised in sensitive_keys and value == REDACTED_SECRET:
            continue
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = merge_write_only_values(
                current,
                value,
                extra_sensitive_keys=extra_sensitive_keys,
            )
        else:
            merged[key] = value
    return merged
