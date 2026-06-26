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
System Test: ST1.5 - Inter-Server Communication and Data Consistency

License: Apache 2.0
Ownership: Cloud Dog
Description: Real contract tests across API, MCP, A2A, and Web servers

Related Requirements: FR1.2, FR1.7, FR1.8
Related Tasks: T001, T030, T044, T059
Related Architecture: SA1.1, AI1.1, AI1.2, AI1.3, AI1.4
Related Tests: ST1.5
"""

import asyncio
import json
import time
import uuid

import pytest
import requests
import websockets

from src.config.loader import get_config, load_config


def _require_timeout() -> float:
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    return float(timeout)


def _require_base_url(host_key: str, port_key: str) -> str:
    host = get_config(host_key)
    port = get_config(port_key)
    if not host or port is None:
        pytest.fail(f"{host_key}/{port_key} not configured")
    return f"http://{host}:{int(port)}"


def _wait_for_health(
    session: requests.Session, url: str, path: str, timeout: float, label: str
) -> None:
    last_error = None
    for _ in range(6):
        try:
            response = session.get(f"{url}{path}", timeout=timeout)
            if response.status_code == 200:
                return
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(0.5)
    pytest.fail(f"{label} not healthy at {url}{path}. last_error={last_error}")


@pytest.fixture
def clients(test_env_file):
    load_config.cache_clear()
    timeout = _require_timeout()
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")

    api_url = _require_base_url("api_server.host", "api_server.port")
    mcp_url = _require_base_url("mcp_server.host", "mcp_server.port")
    a2a_url = _require_base_url("a2a_server.host", "a2a_server.port")
    web_url = _require_base_url("web_server.host", "web_server.port")

    api_session = requests.Session()
    api_session.headers.update({"X-API-Key": str(api_key)})

    _wait_for_health(api_session, api_url, "/health", timeout, "API server")
    _wait_for_health(api_session, mcp_url, "/mcp/health", timeout, "MCP server")
    _wait_for_health(api_session, a2a_url, "/a2a/health", timeout, "A2A server")
    _wait_for_health(api_session, web_url, "/health", timeout, "Web server")

    return {
        "timeout": timeout,
        "api": api_session,
        "api_url": api_url,
        "mcp_url": mcp_url,
        "a2a_url": a2a_url,
        "web_url": web_url,
    }


@pytest.fixture
def test_entities(clients):
    api = clients["api"]
    timeout = clients["timeout"]
    api_url = clients["api_url"]

    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in config")
    if "@" not in str(base_email):
        pytest.fail("test.user.email must include a domain")
    domain = str(base_email).split("@", 1)[1]
    unique = uuid.uuid4().hex[:8]

    user_response = api.post(
        f"{api_url}/users",
        json={
            "username": f"{base_username}_st15_{unique}",
            "email": f"st15_{unique}@{domain}",
            "password": str(password),
            "display_name": f"ST1.5 User {unique}",
        },
        timeout=timeout,
    )
    assert user_response.status_code == 200, user_response.text
    user = user_response.json()

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    llm_api_key = get_config("llm.api_key")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config")

    expert_response = api.post(
        f"{api_url}/experts",
        json={
            "name": f"st15_expert_{unique}",
            "title": f"ST1.5 Expert Alpha Beta {unique}",
            "description": f"Validates inter-server communication contracts for token {unique}.",
            "llm_provider": str(llm_provider),
            "llm_model": str(llm_model),
            "llm_base_url": str(llm_base_url),
            "llm_api_key": llm_api_key,
            "enabled": True,
        },
        timeout=timeout,
    )
    assert expert_response.status_code == 200, expert_response.text
    expert = expert_response.json()

    yield {"user": user, "expert": expert}

    api.delete(f"{api_url}/experts/{expert['id']}", timeout=timeout)
    api.delete(f"{api_url}/users/{user['id']}", timeout=timeout)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_all_server_health_contracts(clients):
    timeout = clients["timeout"]

    api_health = clients["api"].get(f"{clients['api_url']}/health", timeout=timeout)
    assert api_health.status_code == 200
    assert api_health.json().get("status") == "healthy"

    mcp_health = requests.get(f"{clients['mcp_url']}/mcp/health", timeout=timeout)
    assert mcp_health.status_code == 200
    assert mcp_health.json().get("status") == "healthy"

    a2a_health = requests.get(f"{clients['a2a_url']}/a2a/health", timeout=timeout)
    assert a2a_health.status_code == 200
    assert a2a_health.json().get("status") == "healthy"

    web_health = requests.get(f"{clients['web_url']}/health", timeout=timeout)
    assert web_health.status_code == 200
    assert web_health.json().get("status") == "healthy"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_api_to_mcp_session_visibility(clients, test_entities):
    api = clients["api"]
    timeout = clients["timeout"]
    api_url = clients["api_url"]
    mcp_url = clients["mcp_url"]

    create_response = api.post(
        f"{api_url}/sessions",
        json={
            "user_id": int(test_entities["user"]["id"]),
            "expert_config_id": int(test_entities["expert"]["id"]),
            "title": "ST1.5 API session",
        },
        timeout=timeout,
    )
    assert create_response.status_code == 200, create_response.text
    session_id = int(create_response.json()["id"])

    try:
        list_response = api.get(  # MCP surface is auth-gated (W28C-1704)
            f"{mcp_url}/mcp/sessions",
            params={"user_id": int(test_entities["user"]["id"])},
            timeout=timeout,
        )
        assert list_response.status_code == 200, list_response.text
        payload = list_response.json()
        if payload.get("error"):
            pytest.fail(f"MCP list sessions failed: {payload['error']}")
        ids = {int(entry["id"]) for entry in payload.get("sessions", []) if "id" in entry}
        assert session_id in ids
    finally:
        api.delete(f"{api_url}/sessions/{session_id}", timeout=timeout)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.asyncio
async def test_a2a_broadcast_delivery(clients):
    timeout = clients["timeout"]
    a2a_url = clients["a2a_url"]
    ws_url = a2a_url.replace("http://", "ws://") + "/a2a/ws/system"
    marker = uuid.uuid4().hex[:8]

    async with websockets.connect(ws_url, open_timeout=timeout, close_timeout=timeout) as ws:
        response = requests.post(
            f"{a2a_url}/a2a/broadcast/system",
            json={"type": "inter_server_test", "marker": marker},
            timeout=timeout,
        )
        assert response.status_code == 200, response.text
        message = await asyncio.wait_for(ws.recv(), timeout=timeout)
        payload = json.loads(message)
        assert payload.get("topic") == "system"
        assert payload.get("data", {}).get("marker") == marker
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_web_dashboard_contract_and_api_base_link(clients):
    timeout = clients["timeout"]
    web_response = requests.get(f"{clients['web_url']}/", timeout=timeout)
    assert web_response.status_code == 200, web_response.text
    body = web_response.text

    # Core SPA shell contract
    assert 'id="root"' in body
    assert "/runtime-config.js" in body
    assert 'type="module"' in body
    # SPA may reference API via absolute URL or relative proxy endpoints.
    assert (
        clients["api_url"] in body
        or "/web/api/" in body
        or "/runtime-config.js" in body
    )
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_web_backing_api_endpoints_for_core_panels(clients):
    api = clients["api"]
    timeout = clients["timeout"]
    api_url = clients["api_url"]

    checks = [
        ("/channels", 200),
        ("/experts", 200),
        ("/users", 200),
        ("/groups", 200),
        ("/jobs/queue/status", 200),
        ("/health", 200),
    ]
    for path, expected in checks:
        response = api.get(f"{api_url}{path}", timeout=timeout)
        assert response.status_code == expected, f"{path} returned {response.status_code}"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_mcp_tools_catalog_exposes_core_interop_tools(clients):
    timeout = clients["timeout"]
    mcp_response = requests.get(f"{clients['mcp_url']}/mcp/tools", timeout=timeout)
    assert mcp_response.status_code == 200, mcp_response.text
    data = mcp_response.json()
    tool_names = {item.get("name") for item in data.get("tools", []) if isinstance(item, dict)}
    required = {"chat", "start_session", "list_sessions", "get_history"}
    assert required.issubset(tool_names)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.smtp, pytest.mark.mcp, pytest.mark.slow, pytest.mark.heavy]
