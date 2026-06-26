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
Integration Test: IT2.5 - Cross-Interface Parity (REST, MCP, A2A, Web)

License: Apache 2.0
Ownership: Cloud Dog
Description: Verifies equivalent behaviour signals across interfaces

Related Requirements: FR1.7, FR1.8, FR1.24, FR1.25
Related Tasks: T126, T127, T128, T129, T130, T131
Related Architecture: AI1.1, AI1.2, AI1.3, AI1.4
Related Tests: IT2.5
"""

import asyncio
import json
import ssl
import time
import uuid

import pytest
import requests
import websockets

from src.config.loader import get_config, load_config


pytestmark = pytest.mark.integration


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
    section = host_key.rsplit(".", 1)[0]
    base_url_cfg = get_config(f"{section}.base_url")
    if base_url_cfg:
        return str(base_url_cfg).rstrip("/")
    host = get_config(host_key)
    port = get_config(port_key)
    if not host or port is None:
        pytest.fail(f"{section}.base_url or {host_key}/{port_key} not configured")
    scheme = str(get_config(scheme_key) or "http").strip().lower()
    if scheme not in {"http", "https"}:
        pytest.fail(f"Unsupported scheme for {scheme_key}: {scheme}")
    return f"{scheme}://{host}:{int(port)}"


def _prefixed_url(base_url: str, prefix: str, path: str) -> str:
    """Build a URL avoiding double service prefix (e.g. /mcp/mcp or /a2a/a2a)."""
    stripped = base_url.rstrip("/")
    if stripped.endswith(f"/{prefix}"):
        return f"{stripped}/{path.lstrip('/')}"
    return f"{stripped}/{prefix}/{path.lstrip('/')}"


def _wait_for_health(session: requests.Session, url: str, timeout: float, label: str) -> None:
    last_error = None
    for _ in range(6):
        try:
            response = session.get(url, timeout=timeout)
            if response.status_code == 200:
                return
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(0.5)
    pytest.fail(f"{label} not healthy at {url}. last_error={last_error}")


@pytest.fixture
def clients(test_env_file):
    load_config.cache_clear()
    timeout = _require_timeout()
    verify_tls = _require_bool("test.http_verify_tls", True)
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")

    api_url = _require_base_url("api_server.host", "api_server.port", "api_server.scheme")
    mcp_url = _require_base_url("mcp_server.host", "mcp_server.port", "mcp_server.scheme")
    a2a_url = _require_base_url("a2a_server.host", "a2a_server.port", "a2a_server.scheme")
    web_url = _require_base_url("web_server.host", "web_server.port", "web_server.scheme")

    api = requests.Session()
    api.headers.update({"X-API-Key": str(api_key)})
    api.verify = verify_tls
    # base_url may already include the service prefix (e.g. /mcp, /a2a) in preprod.
    def _health(url: str, prefix: str) -> str:
        return f"{url}/health" if url.rstrip("/").endswith(f"/{prefix}") else f"{url}/{prefix}/health"

    _wait_for_health(api, f"{api_url}/health", timeout, "API server")
    _wait_for_health(api, _health(mcp_url, "mcp"), timeout, "MCP server")
    _wait_for_health(api, _health(a2a_url, "a2a"), timeout, "A2A server")
    _wait_for_health(api, f"{web_url}/health", timeout, "Web server")

    return {
        "timeout": timeout,
        "api": api,
        "api_url": api_url,
        "mcp_url": mcp_url,
        "a2a_url": a2a_url,
        "web_url": web_url,
        "verify_tls": verify_tls,
    }


@pytest.fixture
def test_entities(clients):
    api = clients["api"]
    timeout = clients["timeout"]

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
        f"{clients['api_url']}/users",
        json={
            "username": f"{base_username}_it25p_{unique}",
            "email": f"it25p_{unique}@{domain}",
            "password": str(password),
            "display_name": f"IT2.5 User {unique}",
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
        f"{clients['api_url']}/experts",
        json={
            "name": f"it25_parity_expert_{unique}",
            "title": f"Parity Expert Alpha Beta {unique}",
            "description": (
                "Validates parity across REST, MCP, A2A, and Web interface contracts "
                f"for token {unique}."
            ),
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

    api.delete(f"{clients['api_url']}/experts/{expert['id']}", timeout=timeout)
    api.delete(f"{clients['api_url']}/users/{user['id']}", timeout=timeout)
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_uc132_api_critical_endpoints_discoverable(clients):
    timeout = clients["timeout"]
    api = clients["api"]
    api_url = clients["api_url"]

    openapi_response = api.get(f"{api_url}/openapi.json", timeout=timeout)
    assert openapi_response.status_code == 200, openapi_response.text
    spec = openapi_response.json()
    paths = set(spec.get("paths", {}).keys())
    required_paths = {
        "/sessions",
        "/users",
        "/experts",
        "/channels",
        "/jobs",
        "/knowledge/{knowledge_type}/{knowledge_id}",
    }
    missing = [path for path in required_paths if path not in paths]
    assert not missing, f"Missing API paths for UC1.32: {missing}"
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_uc133_web_critical_routes_discoverable(clients):
    timeout = clients["timeout"]
    web_url = clients["web_url"]
    verify_tls = clients["verify_tls"]
    web = requests.Session()
    web.verify = verify_tls
    web_user = get_config("web_server.username")
    web_pass = get_config("web_server.password")
    if web_user and web_pass:
        web.auth = (str(web_user), str(web_pass))

    for path in ["/", "/chat", "/channels", "/health"]:
        response = web.get(f"{web_url}{path}", timeout=timeout)
        assert response.status_code == 200, f"route {path} failed with {response.status_code}"
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_rest_mcp_session_id_parity(clients, test_entities):
    timeout = clients["timeout"]
    verify_tls = clients["verify_tls"]
    api = clients["api"]
    api_url = clients["api_url"]
    mcp_url = clients["mcp_url"]
    user_id = int(test_entities["user"]["id"])
    expert_id = int(test_entities["expert"]["id"])

    create_response = api.post(
        f"{api_url}/sessions",
        json={"user_id": user_id, "expert_config_id": expert_id, "title": "Parity via REST"},
        timeout=timeout,
    )
    assert create_response.status_code == 200, create_response.text
    session_id = int(create_response.json()["id"])

    try:
        # Use the authenticated api session: MCP surface is auth-gated (W28C-1704).
        list_response = api.get(
            _prefixed_url(mcp_url, "mcp", "sessions"),
            params={"user_id": user_id},
            timeout=timeout,
            verify=verify_tls,
        )
        assert list_response.status_code == 200, list_response.text
        payload = list_response.json()
        if payload.get("error"):
            pytest.fail(f"MCP list sessions error: {payload['error']}")
        ids = {int(item["id"]) for item in payload.get("sessions", []) if "id" in item}
        assert session_id in ids
    finally:
        api.delete(f"{api_url}/sessions/{session_id}", timeout=timeout)
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


@pytest.mark.asyncio
async def test_a2a_broadcast_visible_to_ws_subscriber(clients):
    timeout = clients["timeout"]
    a2a_url = clients["a2a_url"]
    verify_tls = clients["verify_tls"]
    a2a_ws_path = _prefixed_url(a2a_url, "a2a", "ws/sessions")
    if a2a_url.startswith("https://"):
        ws_url = a2a_ws_path.replace("https://", "wss://", 1)
    else:
        ws_url = a2a_ws_path.replace("http://", "ws://", 1)
    marker = uuid.uuid4().hex[:8]
    ssl_ctx = None
    if ws_url.startswith("wss://"):
        if verify_tls:
            ssl_ctx = ssl.create_default_context()
        else:
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

    async with websockets.connect(
        ws_url, open_timeout=timeout, close_timeout=timeout, ssl=ssl_ctx
    ) as ws:
        broadcast_response = requests.post(
            _prefixed_url(a2a_url, "a2a", "broadcast/sessions"),
            json={"type": "session_state_change", "marker": marker},
            timeout=timeout,
            verify=verify_tls,
        )
        assert broadcast_response.status_code == 200, broadcast_response.text
        message = await asyncio.wait_for(ws.recv(), timeout=timeout)
        payload = json.loads(message)
        assert payload.get("topic") == "sessions"
        assert payload.get("data", {}).get("marker") == marker
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_web_index_references_api_docs(clients):
    timeout = clients["timeout"]
    web_url = clients["web_url"]
    api_url = clients["api_url"]
    verify_tls = clients["verify_tls"]
    web_user = get_config("web_server.username")
    web_pass = get_config("web_server.password")
    auth = (str(web_user), str(web_pass)) if web_user and web_pass else None

    response = requests.get(f"{web_url}/", timeout=timeout, verify=verify_tls, auth=auth)
    assert response.status_code == 200, response.text
    body = response.text or ""
    has_absolute_api_ref = api_url in body
    has_relative_api_ref = any(
        token in body
        for token in (
            "apiCall('/health')",
            'apiCall("/health")',
            "/docs",
            "/sessions",
        )
    )
    assert has_absolute_api_ref or has_relative_api_ref
    assert ("dashboard" in response.text.lower()) or ("chat" in response.text.lower())

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.smtp, pytest.mark.mcp, pytest.mark.heavy]

