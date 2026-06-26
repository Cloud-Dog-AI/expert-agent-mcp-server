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
A2A Client Helpers

License: Apache 2.0
Ownership: Cloud Dog
Description: Single entry point for cross-process A2A event publishing

Related Requirements: FR1.2, FR1.7
Related Tasks: T044, T045, T046, T047
Related Architecture: CC1.1.4, AI1.3
Related Tests: IT2.5

Recent Changes:
- Added config CRUD event publishing helper for expert-agent
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import requests

from src.config.loader import get_config
from src.utils.logger import get_logger


logger = get_logger(__name__)


def _a2a_base_url() -> str:
    """Resolve the A2A base URL from the standard config hierarchy."""
    base_url = get_config("a2a_server.base_url")
    if base_url:
        return str(base_url).rstrip("/")

    host = get_config("a2a_server.host")
    port = get_config("a2a_server.port")
    scheme = str(get_config("a2a_server.scheme") or "http").strip().lower()
    if not host or port is None:
        raise RuntimeError("a2a_server.host/a2a_server.port not configured")
    return f"{scheme}://{host}:{int(port)}"


def _a2a_broadcast_url(topic: str) -> str:
    """Build the broadcast endpoint without duplicating the /a2a prefix."""
    base_url = _a2a_base_url()
    if base_url.endswith("/a2a"):
        return f"{base_url}/broadcast/{topic}"
    return f"{base_url}/a2a/broadcast/{topic}"


def _event_timeout_seconds() -> float:
    """Use the shared HTTP timeout budget for cross-service event delivery."""
    raw_timeout = get_config("test.http_timeout_seconds")
    if raw_timeout is None:
        raise RuntimeError("test.http_timeout_seconds not configured")
    return float(raw_timeout)


def _resource_topic(resource_type: str) -> str:
    """Map config resource types to A2A topics."""
    normalized = str(resource_type).strip().lower()
    if normalized == "api_key":
        return "api_keys"
    return f"{normalized}s"


def publish_config_change_event(
    *,
    action: str,
    resource_type: str,
    resource_id: int,
    actor: Optional[str],
) -> bool:
    """
    Publish a config CRUD event to the A2A server.

    Returns True on successful delivery to the A2A HTTP ingress, otherwise False.
    """
    topic = _resource_topic(resource_type)
    payload = {
        "action": str(action),
        "resource_type": str(resource_type),
        "resource_id": int(resource_id),
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "actor": str(actor or "system"),
    }
    try:
        response = requests.post(
            _a2a_broadcast_url(topic),
            json=payload,
            timeout=_event_timeout_seconds(),
        )
        response.raise_for_status()
        return True
    except Exception as exc:
        logger.warning(
            "Failed to publish A2A config event topic=%s action=%s resource_id=%s: %s",
            topic,
            action,
            resource_id,
            exc,
        )
        return False
