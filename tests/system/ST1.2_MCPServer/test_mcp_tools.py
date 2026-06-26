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
System Test: ST1.2 - MCP Server Tool Contract and Resilience

License: Apache 2.0
Ownership: Cloud Dog
Description: Real MCP endpoint validation against a running MCP server

Related Requirements: FR1.7, FR1.25
Related Tasks: T039, T040, T041, T042, T043
Related Architecture: CC1.1.3, AI1.2
Related Tests: ST1.2
"""

import time
import uuid

import pytest
import requests

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


def _wait_for_health(session: requests.Session, url: str, timeout: float, label: str) -> None:
    last_error = None
    for _ in range(5):
        try:
            response = session.get(url, timeout=timeout)
            if response.status_code == 200:
                return
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(0.5)
    pytest.fail(f"{label} not healthy at {url}. last_error={last_error}")


@pytest.fixture
def api_client(test_env_file):
    load_config.cache_clear()
    timeout = _require_timeout()
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")
    base_url = _require_base_url("api_server.host", "api_server.port")
    session = requests.Session()
    session.headers.update({"X-API-Key": str(api_key)})
    _wait_for_health(session, f"{base_url}/health", timeout, "API server")
    session.base_url = base_url
    session.timeout_seconds = timeout
    return session


@pytest.fixture
def mcp_client(test_env_file):
    load_config.cache_clear()
    timeout = _require_timeout()
    base_url = _require_base_url("mcp_server.host", "mcp_server.port")
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")
    session = requests.Session()
    session.headers.update({"X-API-Key": str(api_key)})  # MCP auth-gated (W28C-1704)
    _wait_for_health(session, f"{base_url}/mcp/health", timeout, "MCP server")
    session.base_url = base_url
    session.timeout_seconds = timeout
    return session


@pytest.fixture
def test_user(api_client):
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in config")
    if "@" not in str(base_email):
        pytest.fail("test.user.email must include a domain")
    domain = str(base_email).split("@", 1)[1]
    unique = uuid.uuid4().hex[:8]

    response = api_client.post(
        f"{api_client.base_url}/users",
        json={
            "username": f"{base_username}_st12_{unique}",
            "email": f"st12_{unique}@{domain}",
            "password": str(password),
            "display_name": f"ST1.2 User {unique}",
        },
        timeout=api_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    user = response.json()
    yield user
    api_client.delete(
        f"{api_client.base_url}/users/{user['id']}",
        timeout=api_client.timeout_seconds,
    )


@pytest.fixture
def test_expert(api_client):
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    llm_api_key = get_config("llm.api_key")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config")
    unique = uuid.uuid4().hex[:8]

    response = api_client.post(
        f"{api_client.base_url}/experts",
        json={
            "name": f"st12_expert_{unique}",
            "title": f"MCP System Expert Alpha Beta {unique}",
            "description": f"Validates MCP protocol contract integrity with token {unique}.",
            "llm_provider": str(llm_provider),
            "llm_model": str(llm_model),
            "llm_base_url": str(llm_base_url),
            "llm_api_key": llm_api_key,
            "enabled": True,
        },
        timeout=api_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    expert = response.json()
    yield expert
    api_client.delete(
        f"{api_client.base_url}/experts/{expert['id']}",
        timeout=api_client.timeout_seconds,
    )


def _start_session(mcp_client: requests.Session, user_id: int, expert_id: int, title: str) -> int:
    response = mcp_client.post(
        f"{mcp_client.base_url}/mcp/start_session",
        json={"user_id": user_id, "expert_config_id": expert_id, "title": title},
        timeout=mcp_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    if payload.get("error"):
        pytest.fail(f"mcp/start_session error: {payload['error']}")
    session_id = payload.get("session_id")
    if not session_id:
        pytest.fail("mcp/start_session missing session_id")
    return int(session_id)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_health_contract(mcp_client):
    response = mcp_client.get(
        f"{mcp_client.base_url}/mcp/health",
        timeout=mcp_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("status") == "healthy"
    assert data.get("transport") in {"sse", "stdio"}
    assert data.get("application") == "expert-agent-mcp-server"
    assert data.get("version")
    env = data.get("env")
    assert isinstance(env, dict)
    assert isinstance(env.get("config_env_file"), str) and env.get("config_env_file")
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_tools_catalog_contract(mcp_client):
    response = mcp_client.get(
        f"{mcp_client.base_url}/mcp/tools",
        timeout=mcp_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "tools" in data and isinstance(data["tools"], list)
    tool_names = {item.get("name") for item in data["tools"] if isinstance(item, dict)}
    required = {
        "chat",
        "start_session",
        "resume_session",
        "end_session",
        "list_sessions",
        "session_status",
        "get_history",
        "list_experts",
        "get_expert",
        "vector_search",
        "vector_add",
    }
    assert required.issubset(tool_names)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_start_resume_end_lifecycle(mcp_client, test_user, test_expert):
    session_id = _start_session(
        mcp_client,
        user_id=int(test_user["id"]),
        expert_id=int(test_expert["id"]),
        title="ST1.2 lifecycle",
    )

    status_response = mcp_client.get(
        f"{mcp_client.base_url}/mcp/session/{session_id}/status",
        timeout=mcp_client.timeout_seconds,
    )
    assert status_response.status_code == 200, status_response.text
    status_data = status_response.json()
    assert int(status_data.get("session_id")) == session_id

    resume_response = mcp_client.post(
        f"{mcp_client.base_url}/mcp/resume_session",
        json={"session_id": session_id},
        timeout=mcp_client.timeout_seconds,
    )
    assert resume_response.status_code == 200, resume_response.text
    resume_data = resume_response.json()
    assert int(resume_data.get("session_id")) == session_id
    assert resume_data.get("status") == "active"

    end_response = mcp_client.post(
        f"{mcp_client.base_url}/mcp/end_session",
        json={"session_id": session_id},
        timeout=mcp_client.timeout_seconds,
    )
    assert end_response.status_code == 200, end_response.text
    end_data = end_response.json()
    assert int(end_data.get("session_id")) == session_id
    assert end_data.get("status") == "completed"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_chat_requires_required_fields(mcp_client):
    response = mcp_client.post(
        f"{mcp_client.base_url}/mcp/chat",
        json={"session_id": None, "message": ""},
        timeout=mcp_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("error") == "session_id and message required"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_invalid_session_error_contract(mcp_client):
    response = mcp_client.get(
        f"{mcp_client.base_url}/mcp/session/99999999/status",
        timeout=mcp_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("error") == "Session not found"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_session_history_round_trip(mcp_client, api_client, test_user, test_expert):
    session_id = _start_session(
        mcp_client,
        user_id=int(test_user["id"]),
        expert_id=int(test_expert["id"]),
        title="ST1.2 history round trip",
    )

    message = f"history-msg-{uuid.uuid4().hex[:8]}"
    add_msg = api_client.post(
        f"{api_client.base_url}/sessions/{session_id}/messages",
        json={"role": "user", "content": message},
        timeout=api_client.timeout_seconds,
    )
    assert add_msg.status_code == 200, add_msg.text

    history_response = mcp_client.get(
        f"{mcp_client.base_url}/mcp/session/{session_id}/history",
        timeout=mcp_client.timeout_seconds,
    )
    assert history_response.status_code == 200, history_response.text
    history_data = history_response.json()
    contents = [entry.get("content") for entry in history_data.get("messages", [])]
    assert message in contents

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.smtp, pytest.mark.mcp, pytest.mark.slow, pytest.mark.heavy]

