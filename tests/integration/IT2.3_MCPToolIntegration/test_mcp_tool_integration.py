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
Integration Test: IT2.3 - MCP Tool Integration

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for MCP tool integration

Related Requirements: FR1.7, FR1.24
Related Tasks: T039, T040, T041, T042, T043
Related Architecture: AI1.2
Related Tests: IT2.3

Recent Changes:
- Initial implementation
"""

import pytest
import requests
import time
import uuid

from src.config.loader import get_config, load_config


def _require_bool(path: str, default: bool) -> bool:
    value = get_config(path)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _require_base_url(host_key: str, port_key: str, scheme_key: str) -> str:
    section = host_key.rsplit(".", 1)[0]
    configured_base_url = get_config(f"{section}.base_url")
    if configured_base_url:
        return str(configured_base_url).rstrip("/")
    host = get_config(host_key)
    port = get_config(port_key)
    if not host or port is None:
        pytest.fail(f"{host_key}/{port_key} not configured")
    scheme = str(get_config(scheme_key) or "http").strip().lower()
    if scheme not in {"http", "https"}:
        pytest.fail(f"Unsupported scheme for {scheme_key}: {scheme}")
    return f"{scheme}://{host}:{int(port)}"


def _mcp_health_url(base_url: str) -> str:
    return f"{base_url}/health" if base_url.endswith("/mcp") else f"{base_url}/mcp/health"


def _mcp_endpoint(base_url: str, path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    if base_url.endswith("/mcp"):
        return f"{base_url}{normalized_path}"
    return f"{base_url}/mcp{normalized_path}"


def _require_health(
    session: requests.Session, url: str, timeout_seconds: float, label: str
) -> None:
    last_status = None
    last_error = None
    for attempt in range(3):
        try:
            response = session.get(url, timeout=timeout_seconds)
            last_status = response.status_code
            if response.status_code == 200:
                return
        except requests.RequestException as exc:
            last_error = exc
        if attempt < 2:
            time.sleep(1)
    if last_status is not None:
        pytest.fail(f"{label} not healthy at {url} (status {last_status})")
    pytest.fail(f"{label} not reachable at {url}: {last_error}")


@pytest.fixture
def api_client(test_env_file):
    """Requests client to a real running API server."""
    load_config.cache_clear()
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured (set TEST_API_KEY in private/env-*-secrets)")
    verify_tls = _require_bool("test.http_verify_tls", True)
    base_url = _require_base_url("api_server.host", "api_server.port", "api_server.scheme")

    session = requests.Session()
    session.headers.update({"X-API-Key": str(api_key)})
    session.verify = verify_tls
    _require_health(session, f"{base_url}/health", float(timeout), "API server")

    session.base_url = base_url
    session.timeout_seconds = float(timeout)
    return session


@pytest.fixture
def mcp_client(test_env_file):
    """Requests client to a real running MCP server."""
    load_config.cache_clear()
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    verify_tls = _require_bool("test.http_verify_tls", True)
    base_url = _require_base_url("mcp_server.host", "mcp_server.port", "mcp_server.scheme")
    # MCP tool calls are auth-gated (W28C-1704: anon -> 401). Authenticate the
    # client the same way api_client does; the anonymous-denied path is covered
    # separately by UT1.131.
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured (set TEST_API_KEY in private/env-*-secrets)")

    session = requests.Session()
    session.headers.update({"X-API-Key": str(api_key)})
    session.verify = verify_tls
    _require_health(session, _mcp_health_url(base_url), float(timeout), "MCP server")

    session.base_url = base_url
    session.timeout_seconds = float(timeout)
    return session


@pytest.fixture
def test_user(api_client):
    """Create a test user via API."""
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    display_name = get_config("test.user.display_name")
    if not base_username or not base_email or not password or not display_name:
        pytest.fail("Missing test.user.* in config (--env)")
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    unique = uuid.uuid4().hex[:8]
    domain = base_email.split("@", 1)[1]

    response = api_client.post(
        f"{api_client.base_url}/users",
        json={
            "username": f"{base_username}_it2_3_{unique}",
            "email": f"it2_3_{unique}@{domain}",
            "password": password,
            "display_name": display_name,
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
    """Create a test expert configuration via API."""
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")
    unique = uuid.uuid4().hex[:8]
    response = api_client.post(
        f"{api_client.base_url}/experts",
        json={
            "name": f"test_expert_it2_3_{unique}",
            "title": f"MCP Integration Expert Alpha Beta {unique}",
            "description": (
                "Validates chat, session history, vector search workflows across "
                f"API and MCP services with unique token {unique}."
            ),
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_base_url": llm_base_url,
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


def _start_mcp_session(mcp_client, user_id: int, expert_id: int, title: str) -> int:
    response = mcp_client.post(
        _mcp_endpoint(mcp_client.base_url, "/start_session"),
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": title,
        },
        timeout=mcp_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    if data.get("error"):
        pytest.fail(f"MCP start_session failed: {data['error']}")
    session_id = data.get("session_id")
    if not session_id:
        pytest.fail("MCP start_session missing session_id")
    return session_id
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_chat_tool_integration(api_client, mcp_client, test_user, test_expert):
    """Test MCP chat tool integration with API server."""
    session_id = _start_mcp_session(
        mcp_client,
        user_id=test_user["id"],
        expert_id=test_expert["id"],
        title="MCP Chat Session",
    )

    response = mcp_client.post(
        _mcp_endpoint(mcp_client.base_url, "/chat"),
        json={
            "session_id": session_id,
            "message": "Hello from MCP chat tool.",
        },
        timeout=mcp_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    if data.get("error"):
        pytest.fail(f"MCP chat failed: {data['error']}")
    assert data.get("response")
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_session_tools_integration(api_client, mcp_client, test_user, test_expert):
    """Test MCP session tools integration."""
    session_id = _start_mcp_session(
        mcp_client,
        user_id=test_user["id"],
        expert_id=test_expert["id"],
        title="MCP Session Tools",
    )

    status_response = mcp_client.get(
        _mcp_endpoint(mcp_client.base_url, f"/session/{session_id}/status"),
        timeout=mcp_client.timeout_seconds,
    )
    assert status_response.status_code == 200, status_response.text
    status_data = status_response.json()
    if status_data.get("error"):
        pytest.fail(f"MCP session status failed: {status_data['error']}")
    assert status_data.get("session_id") == session_id

    list_response = mcp_client.get(
        _mcp_endpoint(mcp_client.base_url, "/sessions"),
        params={"user_id": test_user["id"]},
        timeout=mcp_client.timeout_seconds,
    )
    assert list_response.status_code == 200, list_response.text
    list_data = list_response.json()
    if list_data.get("error"):
        pytest.fail(f"MCP list sessions failed: {list_data['error']}")
    session_ids = [entry.get("id") for entry in list_data.get("sessions", [])]
    assert session_id in session_ids
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_history_tools_integration(api_client, mcp_client, test_user, test_expert):
    """Test MCP history tools integration."""
    session_id = _start_mcp_session(
        mcp_client,
        user_id=test_user["id"],
        expert_id=test_expert["id"],
        title="MCP History Tools",
    )

    message_response = api_client.post(
        f"{api_client.base_url}/sessions/{session_id}/messages",
        json={
            "role": "user",
            "content": "Hello, MCP!",
        },
        timeout=api_client.timeout_seconds,
    )
    assert message_response.status_code == 200, message_response.text

    history_response = mcp_client.get(
        _mcp_endpoint(mcp_client.base_url, f"/session/{session_id}/history"),
        timeout=mcp_client.timeout_seconds,
    )
    assert history_response.status_code == 200, history_response.text
    history_data = history_response.json()
    if history_data.get("error"):
        pytest.fail(f"MCP get history failed: {history_data['error']}")
    contents = [msg.get("content") for msg in history_data.get("messages", [])]
    assert "Hello, MCP!" in contents
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_expert_tools_integration(api_client, mcp_client, test_expert):
    """Test MCP expert tools integration."""
    response = mcp_client.get(
        _mcp_endpoint(mcp_client.base_url, f"/expert/{test_expert['id']}"),
        timeout=mcp_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    if data.get("error"):
        pytest.fail(f"MCP get expert failed: {data['error']}")
    assert data.get("id") == test_expert["id"]
    assert data.get("name") == test_expert["name"]
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_vector_tools_integration(api_client, mcp_client, test_user, test_expert):
    """Test MCP vector tools integration."""
    qdrant_cfg = get_config("vector_stores_config.qdrant._DEFAULT_")
    if not isinstance(qdrant_cfg, dict):
        pytest.fail("Missing vector_stores_config.qdrant._DEFAULT_ config (--env)")
    collection = qdrant_cfg.get("collection_name")
    if not collection:
        pytest.fail(
            "Missing vector_stores_config.qdrant._DEFAULT_.collection_name in config (--env)"
        )

    store_name = "bootstrap_qdrant_default"
    unique = uuid.uuid4().hex[:8]
    documents = [
        f"MCP integration test document {unique}",
        f"MCP integration test document alt {unique}",
    ]

    add_response = mcp_client.post(
        _mcp_endpoint(mcp_client.base_url, "/vector/add"),
        json={
            "documents": documents,
            "collection": collection,
            "vector_store_name": store_name,
        },
        timeout=mcp_client.timeout_seconds,
    )
    assert add_response.status_code == 200, add_response.text
    add_data = add_response.json()
    if add_data.get("error"):
        pytest.fail(f"MCP vector add failed: {add_data['error']}")
    assert add_data.get("count") == len(documents)

    search_response = mcp_client.post(
        _mcp_endpoint(mcp_client.base_url, "/vector/search"),
        json={
            "query": unique,
            "collection": collection,
            "vector_store_name": store_name,
        },
        timeout=mcp_client.timeout_seconds,
    )
    assert search_response.status_code == 200, search_response.text
    search_data = search_response.json()
    if search_data.get("error"):
        pytest.fail(f"MCP vector search failed: {search_data['error']}")
    assert search_data.get("count", 0) > 0
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_tools_with_api_server(api_client, mcp_client, test_user, test_expert):
    """Test that MCP tools work correctly with API server running."""
    create_response = api_client.post(
        f"{api_client.base_url}/sessions",
        json={
            "user_id": test_user["id"],
            "expert_config_id": test_expert["id"],
            "title": "API-created session",
        },
        timeout=api_client.timeout_seconds,
    )
    assert create_response.status_code == 200, create_response.text
    create_data = create_response.json()
    if "id" not in create_data:
        pytest.fail(f"API session creation failed: {create_data}")
    session_id = create_data["id"]

    status_response = mcp_client.get(
        _mcp_endpoint(mcp_client.base_url, f"/session/{session_id}/status"),
        timeout=mcp_client.timeout_seconds,
    )
    assert status_response.status_code == 200, status_response.text
    status_data = status_response.json()
    if status_data.get("error"):
        pytest.fail(f"MCP session status failed: {status_data['error']}")
    assert status_data.get("session_id") == session_id
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_tool_error_handling(mcp_client):
    """Test MCP tool error handling."""
    response = mcp_client.get(
        _mcp_endpoint(mcp_client.base_url, "/session/999999/status"),
        timeout=mcp_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("error")
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_tools_concurrent_access(api_client, mcp_client, test_user, test_expert):
    """Test MCP tools with concurrent access."""
    session_ids = []
    for i in range(3):
        session_id = _start_mcp_session(
            mcp_client,
            user_id=test_user["id"],
            expert_id=test_expert["id"],
            title=f"MCP concurrent session {i}",
        )
        session_ids.append(session_id)

    for session_id in session_ids:
        status_response = mcp_client.get(
            _mcp_endpoint(mcp_client.base_url, f"/session/{session_id}/status"),
            timeout=mcp_client.timeout_seconds,
        )
        assert status_response.status_code == 200, status_response.text
        status_data = status_response.json()
        if status_data.get("error"):
            pytest.fail(f"MCP session status failed: {status_data['error']}")
        assert status_data.get("session_id") == session_id

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.vdb, pytest.mark.smtp, pytest.mark.mcp, pytest.mark.heavy]
