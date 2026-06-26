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
System Test: ST1.2 - MCP Modes Compliance

License: Apache 2.0
Ownership: Cloud Dog
Description: Validates MCP JSON-RPC modes, legacy SSE mode, async wait=false, and session termination semantics

Related Requirements: FR1.7, FR1.24, FR1.25
Related Tasks: T039, T063
Related Architecture: CC1.1.3, AI1.2
Related Tests: ST1.2
"""

import json
import time

import pytest
import requests

from src.config.loader import get_config, load_config


def _require_timeout() -> float:
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    return float(timeout)


def _require_bool(path: str, default: bool) -> bool:
    value = get_config(path)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _require_base_url(host_key: str, port_key: str, scheme_key: str) -> str:
    host = get_config(host_key)
    port = get_config(port_key)
    if not host or port is None:
        pytest.fail(f"{host_key}/{port_key} not configured")
    scheme = str(get_config(scheme_key) or "http").strip().lower()
    if scheme not in {"http", "https"}:
        pytest.fail(f"Unsupported scheme for {scheme_key}: {scheme}")
    return f"{scheme}://{host}:{int(port)}"


def _wait_for_health(session: requests.Session, url: str, timeout: float, label: str) -> None:
    last_error = None
    # MCP startup can include DB and provider initialization; allow a small warmup window.
    for _ in range(30):
        try:
            response = session.get(url, timeout=timeout)
            if response.status_code == 200:
                return
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(0.5)
    pytest.fail(f"{label} not healthy at {url}. last_error={last_error}")


def _next_sse_event(lines_iter, timeout_seconds: float):
    deadline = time.time() + timeout_seconds
    event_name = None
    data_lines = []
    while time.time() < deadline:
        line = next(lines_iter)
        if line is None:
            continue
        if line == "":
            if data_lines:
                payload = "\n".join(data_lines)
                return event_name, payload
            event_name = None
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line.split(":", 1)[1].strip()
            continue
        if line.startswith("data:"):
            data_lines.append(line.split(":", 1)[1].strip())
    raise TimeoutError("Timed out waiting for SSE event")


@pytest.fixture
def mcp_client(test_env_file):
    load_config.cache_clear()
    timeout = _require_timeout()
    base_url = _require_base_url("mcp_server.host", "mcp_server.port", "mcp_server.scheme")
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")
    session = requests.Session()
    session.headers.update({"X-API-Key": str(api_key)})  # MCP auth-gated (W28C-1704)
    session.verify = _require_bool("test.http_verify_tls", True)
    _wait_for_health(session, f"{base_url}/mcp/health", timeout, "MCP server")
    session.base_url = base_url
    session.timeout_seconds = timeout
    return session


def _initialize_streamable_session(mcp_client: requests.Session) -> str:
    response = mcp_client.post(
        f"{mcp_client.base_url}/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "st12", "version": "1.0"},
            },
        },
        timeout=mcp_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("jsonrpc") == "2.0"
    assert payload.get("id") == 1
    assert payload.get("result", {}).get("protocolVersion") == "2024-11-05"

    session_id = response.headers.get("Mcp-Session-Id")
    assert session_id, "Expected Mcp-Session-Id response header"
    return session_id
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_streamable_http_initialize_and_tools_list(mcp_client):
    session_id = _initialize_streamable_session(mcp_client)

    initialized = mcp_client.post(
        f"{mcp_client.base_url}/mcp",
        headers={"Mcp-Session-Id": session_id},
        json={
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        },
        timeout=mcp_client.timeout_seconds,
    )
    assert initialized.status_code == 204, initialized.text

    tools_list = mcp_client.post(
        f"{mcp_client.base_url}/mcp",
        headers={"Mcp-Session-Id": session_id},
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        timeout=mcp_client.timeout_seconds,
    )
    assert tools_list.status_code == 200, tools_list.text
    payload = tools_list.json()
    assert payload.get("jsonrpc") == "2.0"
    tools = payload.get("result", {}).get("tools", [])
    names = {tool.get("name") for tool in tools if isinstance(tool, dict)}
    assert "chat" in names
    assert "start_session" in names
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_streamable_http_tools_call_invalid_tool_returns_jsonrpc_error(mcp_client):
    session_id = _initialize_streamable_session(mcp_client)

    response = mcp_client.post(
        f"{mcp_client.base_url}/mcp",
        headers={"Mcp-Session-Id": session_id},
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "non_existent_tool", "arguments": {}},
        },
        timeout=mcp_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("error", {}).get("code") == -32602
    assert "Unknown tool" in payload.get("error", {}).get("message", "")
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_streamable_http_wait_false_job_polling(mcp_client):
    session_id = _initialize_streamable_session(mcp_client)

    response = mcp_client.post(
        f"{mcp_client.base_url}/mcp",
        headers={"Mcp-Session-Id": session_id},
        json={
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "list_experts", "arguments": {"wait": False}},
        },
        timeout=mcp_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    job_id = payload.get("result", {}).get("job_id")
    assert job_id

    final = None
    for _ in range(10):
        status = mcp_client.get(
            f"{mcp_client.base_url}/jobs/{job_id}",
            timeout=mcp_client.timeout_seconds,
        )
        assert status.status_code == 200, status.text
        status_payload = status.json()
        if status_payload.get("status") == "completed":
            final = status_payload
            break
        if status_payload.get("status") == "failed":
            pytest.fail(f"Async MCP job failed: {status_payload}")
        time.sleep(0.3)

    assert final is not None, "Expected async job to complete"
    result = final.get("result", {})
    assert isinstance(result.get("content"), list)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_streamable_http_session_termination(mcp_client):
    session_id = _initialize_streamable_session(mcp_client)

    terminate = mcp_client.delete(
        f"{mcp_client.base_url}/mcp",
        headers={"Mcp-Session-Id": session_id},
        timeout=mcp_client.timeout_seconds,
    )
    assert terminate.status_code == 200, terminate.text
    assert terminate.json().get("status") == "terminated"

    post_terminate = mcp_client.post(
        f"{mcp_client.base_url}/mcp",
        headers={"Mcp-Session-Id": session_id},
        json={"jsonrpc": "2.0", "id": 5, "method": "tools/list"},
        timeout=mcp_client.timeout_seconds,
    )
    assert post_terminate.status_code == 200, post_terminate.text
    payload = post_terminate.json()
    assert payload.get("error", {}).get("code") == -32001
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_legacy_sse_request_response_correlation(mcp_client):
    response = mcp_client.get(
        f"{mcp_client.base_url}/sse",
        stream=True,
        timeout=(mcp_client.timeout_seconds, mcp_client.timeout_seconds),
    )
    assert response.status_code == 200

    try:
        lines = response.iter_lines(decode_unicode=True)
        event_name, raw_data = _next_sse_event(lines, timeout_seconds=mcp_client.timeout_seconds)
        assert event_name == "endpoint"
        bootstrap = json.loads(raw_data)
        session_id = bootstrap.get("session_id")
        assert session_id
        assert bootstrap.get("messages_path") == "/message"
        assert bootstrap.get("sessionId") == session_id
        endpoint = str(bootstrap.get("endpoint") or "")
        assert endpoint.startswith("/message?")
        assert "session_id=" in endpoint

        post_ack = mcp_client.post(
            f"{mcp_client.base_url}/message",
            params={"session_id": session_id},
            json={"jsonrpc": "2.0", "id": 10, "method": "tools/list"},
            timeout=mcp_client.timeout_seconds,
        )
        assert post_ack.status_code == 200, post_ack.text
        assert post_ack.json().get("accepted") is True

        event_name, raw_data = _next_sse_event(lines, timeout_seconds=mcp_client.timeout_seconds)
        assert event_name == "message"
        rpc_payload = json.loads(raw_data)
        assert rpc_payload.get("jsonrpc") == "2.0"
        assert rpc_payload.get("id") == 10
        assert isinstance(rpc_payload.get("result", {}).get("tools"), list)
    finally:
        response.close()
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_http_jsonrpc_messages_mode_initialize_and_tools_list(mcp_client):
    """
    Validates the /messages endpoint transport mode expected by chat-client harness.

    Contract:
    - JSON-RPC payloads are accepted at POST /messages
    - initialize yields protocolVersion and returns a session id (header)
    - tools/list works when replayed with explicit session_id query parameter
    """
    # Initialize without providing session_id; server returns one via header.
    init = mcp_client.post(
        f"{mcp_client.base_url}/messages",
        json={
            "jsonrpc": "2.0",
            "id": 20,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "st12", "version": "1.0"},
            },
        },
        timeout=mcp_client.timeout_seconds,
    )
    assert init.status_code == 200, init.text
    sid = init.headers.get("Mcp-Session-Id")
    assert sid, "Expected Mcp-Session-Id response header from /messages initialize"
    payload = init.json()
    assert payload.get("jsonrpc") == "2.0"
    assert payload.get("id") == 20
    assert payload.get("result", {}).get("protocolVersion") == "2024-11-05"

    tools_list = mcp_client.post(
        f"{mcp_client.base_url}/messages",
        params={"session_id": sid},
        json={"jsonrpc": "2.0", "id": 21, "method": "tools/list"},
        timeout=mcp_client.timeout_seconds,
    )
    assert tools_list.status_code == 200, tools_list.text
    tools_payload = tools_list.json()
    assert tools_payload.get("jsonrpc") == "2.0"
    assert tools_payload.get("id") == 21
    tools = tools_payload.get("result", {}).get("tools", [])
    names = {tool.get("name") for tool in tools if isinstance(tool, dict)}
    assert "chat" in names

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.mcp, pytest.mark.slow, pytest.mark.heavy]

