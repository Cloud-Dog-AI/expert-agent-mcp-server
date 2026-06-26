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
Integration Test: IT2.42 - MCP Config CRUD A2A

License: Apache 2.0
Ownership: Cloud Dog
Description: Validates MCP admin expert CRUD and A2A config event delivery

Related Requirements: FR1.7, FR1.11
Related Tasks: T039, T044
Related Architecture: CC1.1.3, CC1.1.4
Related Tests: UT1.101
"""

from __future__ import annotations

import asyncio
import json
import ssl
import time
import uuid

import pytest
import requests
import websockets

from src.config.loader import get_config, load_config


pytestmark = [pytest.mark.integration, pytest.mark.mcp, pytest.mark.smtp, pytest.mark.heavy]


def _require_bool(path: str, default: bool) -> bool:
    value = get_config(path)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _require_timeout() -> float:
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    return float(timeout)


def _base_url(section: str) -> str:
    base_url = get_config(f"{section}.base_url")
    if base_url:
        return str(base_url).rstrip("/")
    host = get_config(f"{section}.host")
    port = get_config(f"{section}.port")
    scheme = str(get_config(f"{section}.scheme") or "http").strip().lower()
    if not host or port is None:
        pytest.fail(f"{section}.base_url or {section}.host/{section}.port not configured")
    return f"{scheme}://{host}:{int(port)}"


def _mcp_endpoint(base_url: str) -> str:
    if base_url.endswith("/mcp"):
        return base_url
    return f"{base_url}/mcp"


def _a2a_ws_url(base_url: str, topic: str) -> str:
    ws_scheme = "wss" if base_url.startswith("https://") else "ws"
    if base_url.endswith("/a2a"):
        return base_url.replace("https://", f"{ws_scheme}://").replace(
            "http://", f"{ws_scheme}://"
        ) + f"/ws/{topic}"
    return base_url.replace("https://", f"{ws_scheme}://").replace(
        "http://", f"{ws_scheme}://"
    ) + f"/a2a/ws/{topic}"


def _ssl_kwargs(base_url: str, verify_tls: bool) -> dict:
    if not base_url.startswith("https://"):
        return {}
    if verify_tls:
        return {"ssl": ssl.create_default_context()}
    return {"ssl": ssl._create_unverified_context()}


def _health_url(base_url: str, suffix: str) -> str:
    if base_url.endswith(suffix):
        return f"{base_url}/health"
    return f"{base_url}{suffix}/health"


def _wait_for_health(session: requests.Session, url: str, timeout: float, label: str) -> None:
    for _ in range(10):
        try:
            response = session.get(url, timeout=timeout)
            if response.status_code == 200:
                return
        except requests.RequestException:
            pass
        time.sleep(0.5)
    pytest.fail(f"{label} not healthy at {url}")


def _initialise_mcp_session(session: requests.Session, timeout: float, mcp_url: str) -> str:
    response = session.post(
        mcp_url,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "it242", "version": "1.0"},
            },
        },
        timeout=timeout,
    )
    assert response.status_code == 200, response.text
    session_id = response.headers.get("Mcp-Session-Id")
    if not session_id:
        pytest.fail("Missing Mcp-Session-Id from MCP initialize")

    response = session.post(
        mcp_url,
        headers={"Mcp-Session-Id": session_id},
        json={"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}},
        timeout=timeout,
    )
    assert response.status_code == 204, response.text
    return session_id
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


@pytest.mark.asyncio
async def test_mcp_create_and_delete_expert_broadcasts_a2a_config_events(test_env_file):
    """Create expert via MCP, observe A2A expert events, then delete via MCP."""
    load_config.cache_clear()
    timeout = _require_timeout()
    verify_tls = _require_bool("test.http_verify_tls", True)
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")

    mcp_base = _base_url("mcp_server")
    a2a_base = _base_url("a2a_server")
    mcp_url = _mcp_endpoint(mcp_base)
    expert_name = f"it242_expert_{uuid.uuid4().hex[:8]}"

    client = requests.Session()
    client.verify = verify_tls
    client.headers.update({"X-API-Key": str(api_key)})  # MCP tool calls are auth-gated (W28C-1704)
    _wait_for_health(client, _health_url(mcp_base, "/mcp"), timeout, "MCP server")
    _wait_for_health(client, _health_url(a2a_base, "/a2a"), timeout, "A2A server")
    mcp_session_id = _initialise_mcp_session(client, timeout, mcp_url)

    ws_url = _a2a_ws_url(a2a_base, "experts")
    async with websockets.connect(
        ws_url,
        open_timeout=timeout,
        close_timeout=timeout,
        **_ssl_kwargs(a2a_base, verify_tls),
    ) as websocket:
        create_response = client.post(
            mcp_url,
            headers={"Mcp-Session-Id": mcp_session_id},
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "admin_create_expert",
                    "arguments": {
                        "name": expert_name,
                        "title": f"IT242 Expert Alpha Beta {expert_name}",
                        "description": (
                            "Expert created through MCP and verified through A2A config "
                            f"events with unique token {expert_name}."
                        ),
                        "llm_provider": str(get_config("llm.provider")),
                        "llm_model": str(get_config("llm.model")),
                        "llm_base_url": str(get_config("llm.base_url")),
                        "auth_context": {"api_key": str(api_key)},
                    },
                },
            },
            timeout=timeout,
        )
        assert create_response.status_code == 200, create_response.text
        create_payload = create_response.json()
        assert "error" not in create_payload
        expert = create_payload["result"]["structuredContent"]
        assert expert["name"] == expert_name

        created_event = json.loads(await asyncio.wait_for(websocket.recv(), timeout=timeout))
        assert created_event["topic"] == "experts"
        assert created_event["data"]["action"] == "create"
        assert created_event["data"]["resource_type"] == "expert"
        assert int(created_event["data"]["resource_id"]) == int(expert["id"])
        assert created_event["data"]["actor"]

        delete_response = client.post(
            mcp_url,
            headers={"Mcp-Session-Id": mcp_session_id},
            json={
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": "admin_delete_expert",
                    "arguments": {
                        "expert_id": int(expert["id"]),
                        "auth_context": {"api_key": str(api_key)},
                    },
                },
            },
            timeout=timeout,
        )
        assert delete_response.status_code == 200, delete_response.text
        delete_payload = delete_response.json()
        assert "error" not in delete_payload
        assert delete_payload["result"]["structuredContent"]["success"] is True

        deleted_event = json.loads(await asyncio.wait_for(websocket.recv(), timeout=timeout))
        assert deleted_event["topic"] == "experts"
        assert deleted_event["data"]["action"] == "delete"
        assert deleted_event["data"]["resource_type"] == "expert"
        assert int(deleted_event["data"]["resource_id"]) == int(expert["id"])
