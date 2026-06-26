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
Integration Test: IT2.5 - A2A Protocol Tests

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for A2A protocol and real-time updates

Related Requirements: FR1.2, FR1.7
Related Tasks: T044, T045, T046, T047
Related Architecture: AI1.3
Related Tests: IT2.5

Recent Changes:
- Initial implementation
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


def _require_bool(path: str, default: bool) -> bool:
    value = get_config(path)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _require_a2a_ready():
    base_url_cfg = get_config("a2a_server.base_url")
    a2a_host = get_config("a2a_server.host")
    a2a_port = get_config("a2a_server.port")
    a2a_scheme = str(get_config("a2a_server.scheme") or "http").strip().lower()
    timeout = get_config("test.http_timeout_seconds")
    if base_url_cfg:
        base_url = str(base_url_cfg).rstrip("/")
        # Derive host/port/scheme from base_url for WebSocket construction
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        a2a_host = parsed.hostname or a2a_host
        a2a_port = parsed.port or (443 if parsed.scheme == "https" else 80)
        a2a_scheme = parsed.scheme or a2a_scheme
    else:
        if not a2a_host or a2a_port is None:
            pytest.fail("a2a_server.base_url or a2a_server.host/a2a_server.port not configured (--env)")
        if a2a_scheme not in {"http", "https"}:
            pytest.fail(f"Unsupported a2a_server.scheme: {a2a_scheme}")
        base_url = f"{a2a_scheme}://{a2a_host}:{int(a2a_port)}"
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    verify_tls = _require_bool("test.http_verify_tls", True)
    # base_url may already include the /a2a prefix (preprod base_url config).
    has_a2a_prefix = base_url.rstrip("/").endswith("/a2a")
    health_path = "/health" if has_a2a_prefix else "/a2a/health"
    try:
        response = requests.get(f"{base_url}{health_path}", timeout=float(timeout), verify=verify_tls)
        if response.status_code != 200:
            pytest.fail(f"A2A server not healthy at {base_url} (status {response.status_code})")
    except requests.RequestException as exc:
        pytest.fail(f"Cannot reach A2A server at {base_url}: {exc}")
    return a2a_host, int(a2a_port), float(timeout), a2a_scheme, verify_tls, base_url


def _a2a_url(base_url: str, path: str) -> str:
    """Build an A2A endpoint URL, avoiding double /a2a prefix."""
    if base_url.rstrip("/").endswith("/a2a"):
        return f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    return f"{base_url.rstrip('/')}/a2a/{path.lstrip('/')}"


def _ws_url(host: str, port: int, topic: str, http_scheme: str, base_url: str = "") -> str:
    ws_scheme = "wss" if http_scheme == "https" else "ws"
    if base_url:
        from urllib.parse import urlparse
        parsed = urlparse(base_url)
        ws_base = f"{ws_scheme}://{parsed.hostname}"
        if parsed.port:
            ws_base += f":{parsed.port}"
        path = parsed.path.rstrip("/")
        if not path.endswith("/a2a"):
            path = f"{path}/a2a" if path else "/a2a"
        return f"{ws_base}{path}/ws/{topic}"
    return f"{ws_scheme}://{host}:{int(port)}/a2a/ws/{topic}"


def _ws_connect_kwargs(http_scheme: str, verify_tls: bool) -> dict:
    if http_scheme != "https":
        return {}
    if verify_tls:
        return {"ssl": ssl.create_default_context()}
    return {"ssl": ssl._create_unverified_context()}


@pytest.fixture
def api_client(test_env_file):
    """Requests client to a real running API server."""
    load_config.cache_clear()
    base_url_cfg = get_config("api_server.base_url")
    if base_url_cfg:
        base_url = str(base_url_cfg).rstrip("/")
    else:
        host = get_config("api_server.host")
        port = get_config("api_server.port")
        scheme = str(get_config("api_server.scheme") or "http").strip().lower()
        if not host or port is None:
            pytest.fail("api_server.base_url or api_server.host/api_server.port not configured (use --env <env-file>)")
        if scheme not in {"http", "https"}:
            pytest.fail(f"Unsupported api_server.scheme: {scheme}")
        base_url = f"{scheme}://{host}:{int(port)}"
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured (set TEST_API_KEY in private/env-*-secrets)")
    verify_tls = _require_bool("test.http_verify_tls", True)
    session = requests.Session()
    session.headers.update({"X-API-Key": str(api_key)})
    session.verify = verify_tls
    for attempt in range(3):
        try:
            r = session.get(f"{base_url}/health", timeout=float(timeout))
            if r.status_code == 200:
                break
        except requests.RequestException:
            if attempt < 2:
                time.sleep(1)
            else:
                pytest.fail(
                    f"API server not running at {base_url}. Start it with: "
                    "./server_control.sh start api --env <env-file>"
                )
    session.base_url = base_url
    session.timeout_seconds = float(timeout)
    return session


@pytest.fixture
def test_user(api_client, test_env_file):
    """Create a test user via API."""
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail(
            "Missing test.user.username/test.user.email/test.user.password in config (--env)"
        )
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    unique = uuid.uuid4().hex[:8]
    domain = base_email.split("@", 1)[1]
    response = api_client.post(
        f"{api_client.base_url}/users",
        json={
            "username": f"{base_username}_it2_5_{unique}",
            "email": f"it2_5_{unique}@{domain}",
            "password": password,
            "display_name": "A2A Integration User",
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
def test_expert(api_client, test_env_file):
    """Create a test expert configuration via API."""
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    llm_api_key = get_config("llm.api_key")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")
    unique = uuid.uuid4().hex[:8]
    response = api_client.post(
        f"{api_client.base_url}/experts",
        json={
            "name": f"test_expert_it2_5_a2a_{unique}",
            "title": f"A2A Integration Expert Alpha Beta {unique}",
            "description": (
                "Validates A2A websocket routing, command handling, and broadcast "
                f"delivery with unique token {unique}."
            ),
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_base_url": llm_base_url,
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


def _create_session(api_client, user_id: int, expert_id: int) -> dict:
    response = api_client.post(
        f"{api_client.base_url}/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": "A2A Integration Session",
        },
        timeout=api_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "id" in data, response.text
    return data
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.asyncio
async def test_a2a_websocket_connection(test_env_file):
    """Test A2A WebSocket connection."""
    a2a_host, a2a_port, timeout, a2a_scheme, verify_tls, base_url = _require_a2a_ready()
    ws_url = _ws_url(a2a_host, a2a_port, "system", a2a_scheme, base_url=base_url)
    async with websockets.connect(
        ws_url,
        open_timeout=timeout,
        close_timeout=timeout,
        **_ws_connect_kwargs(a2a_scheme, verify_tls),
    ) as ws:
        payload = {"type": "ping", "message": "hello"}
        await ws.send(json.dumps(payload))
        msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
        data = json.loads(msg)
        assert data.get("topic") == "system"
        assert data.get("echo", {}).get("type") == "ping"
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.asyncio
async def test_a2a_topic_subscription(test_env_file):
    """Test A2A topic subscription."""
    a2a_host, a2a_port, timeout, a2a_scheme, verify_tls, base_url = _require_a2a_ready()
    ws_url = _ws_url(a2a_host, a2a_port, "sessions", a2a_scheme, base_url=base_url)
    async with websockets.connect(
        ws_url,
        open_timeout=timeout,
        close_timeout=timeout,
        **_ws_connect_kwargs(a2a_scheme, verify_tls),
    ) as ws:
        await ws.send(json.dumps({"type": "subscribe", "topic": "sessions"}))
        msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
        data = json.loads(msg)
        assert data.get("topic") == "sessions"
        assert data.get("echo", {}).get("topic") == "sessions"
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.asyncio
async def test_a2a_session_state_updates(api_client, test_user, test_expert, test_env_file):
    """Test real-time session state updates via A2A."""
    a2a_host, a2a_port, timeout, a2a_scheme, verify_tls, base_url = _require_a2a_ready()
    session = _create_session(api_client, test_user["id"], test_expert["id"])
    ws_url = _ws_url(a2a_host, a2a_port, "sessions", a2a_scheme, base_url=base_url)
    try:
        async with websockets.connect(
            ws_url,
            open_timeout=timeout,
            close_timeout=timeout,
            **_ws_connect_kwargs(a2a_scheme, verify_tls),
        ) as ws:
            event = {
                "type": "session_state_change",
                "session_id": session["id"],
                "state": "active",
            }
            response = requests.post(
                _a2a_url(base_url, "broadcast/sessions"),
                json=event,
                timeout=timeout,
                verify=verify_tls,
            )
            assert response.status_code == 200, response.text
            msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
            data = json.loads(msg)
            assert data.get("topic") == "sessions"
            payload = data.get("data", {})
            assert payload.get("type") == "session_state_change"
            assert payload.get("session_id") == session["id"]
            assert payload.get("state") == "active"
    finally:
        api_client.delete(
            f"{api_client.base_url}/sessions/{session['id']}",
            timeout=api_client.timeout_seconds,
        )
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.asyncio
async def test_a2a_event_topics(test_env_file):
    """Test A2A event topics."""
    a2a_host, a2a_port, timeout, a2a_scheme, verify_tls, base_url = _require_a2a_ready()
    r = requests.get(
        _a2a_url(base_url, "topics"), timeout=timeout, verify=verify_tls
    )
    assert r.status_code == 200, r.text
    data = r.json()
    assert "topics" in data
    assert "sessions" in data["topics"]
    assert "system" in data["topics"]
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.asyncio
async def test_a2a_nlp_command_processing(test_env_file):
    """Test A2A NLP command processing."""
    a2a_host, a2a_port, timeout, a2a_scheme, verify_tls, base_url = _require_a2a_ready()
    ws_url = _ws_url(a2a_host, a2a_port, "system", a2a_scheme, base_url=base_url)
    async with websockets.connect(
        ws_url,
        open_timeout=timeout,
        close_timeout=timeout,
        **_ws_connect_kwargs(a2a_scheme, verify_tls),
    ) as ws:
        await ws.send(json.dumps({"type": "command", "command": "status"}))
        msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
        data = json.loads(msg)
        assert data.get("type") == "command_response"
        result = data.get("result", {})
        assert result.get("type") == "status"
        assert result.get("status") == "healthy"
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.asyncio
async def test_a2a_multiple_clients(test_env_file):
    """Test A2A with multiple clients."""
    a2a_host, a2a_port, timeout, a2a_scheme, verify_tls, base_url = _require_a2a_ready()
    ws_url = _ws_url(a2a_host, a2a_port, "system", a2a_scheme, base_url=base_url)
    ws_kwargs = _ws_connect_kwargs(a2a_scheme, verify_tls)
    async with websockets.connect(
        ws_url, open_timeout=timeout, close_timeout=timeout, **ws_kwargs
    ) as ws1:
        async with websockets.connect(
            ws_url, open_timeout=timeout, close_timeout=timeout, **ws_kwargs
        ) as ws2:
            await ws1.send(json.dumps({"type": "ping", "message": "one"}))
            await ws2.send(json.dumps({"type": "ping", "message": "two"}))
            msg1 = await asyncio.wait_for(ws1.recv(), timeout=timeout)
            msg2 = await asyncio.wait_for(ws2.recv(), timeout=timeout)
            data1 = json.loads(msg1)
            data2 = json.loads(msg2)
            assert data1.get("topic") == "system"
            assert data2.get("topic") == "system"
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.asyncio
async def test_a2a_message_broadcast(test_env_file):
    """Test A2A message broadcasting."""
    a2a_host, a2a_port, timeout, a2a_scheme, verify_tls, base_url = _require_a2a_ready()
    ws_url = _ws_url(a2a_host, a2a_port, "system", a2a_scheme, base_url=base_url)
    async with websockets.connect(
        ws_url,
        open_timeout=timeout,
        close_timeout=timeout,
        **_ws_connect_kwargs(a2a_scheme, verify_tls),
    ) as ws:
        r = requests.post(
            _a2a_url(base_url, "broadcast/system"),
            json={"message": "test broadcast"},
            timeout=timeout,
            verify=verify_tls,
        )
        assert r.status_code == 200, r.text
        msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
        data = json.loads(msg)
        assert data.get("topic") == "system"
        assert data.get("data", {}).get("message") == "test broadcast"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.smtp, pytest.mark.heavy]
