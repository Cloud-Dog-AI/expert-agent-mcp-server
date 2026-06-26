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
System Test: ST1.3 - A2A Server WebSocket Resilience and Protocol Contract

License: Apache 2.0
Ownership: Cloud Dog
Description: Real A2A server websocket/topic contract validation

Related Requirements: FR1.2, FR1.7
Related Tasks: T044, T045, T046, T047
Related Architecture: CC1.1.4, AI1.3
Related Tests: ST1.3
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


def _ws_url(base_url: str, topic: str) -> str:
    return base_url.replace("http://", "ws://") + f"/a2a/ws/{topic}"


@pytest.fixture
def a2a_client(test_env_file):
    load_config.cache_clear()
    timeout = _require_timeout()
    base_url = _require_base_url("a2a_server.host", "a2a_server.port")
    session = requests.Session()
    _wait_for_health(session, f"{base_url}/a2a/health", timeout, "A2A server")
    session.base_url = base_url
    session.timeout_seconds = timeout
    return session
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.asyncio
async def test_a2a_websocket_echo_contract(a2a_client):
    ws_url = _ws_url(a2a_client.base_url, "system")
    message = {"type": "ping", "id": uuid.uuid4().hex[:8]}

    async with websockets.connect(
        ws_url,
        open_timeout=a2a_client.timeout_seconds,
        close_timeout=a2a_client.timeout_seconds,
    ) as ws:
        await ws.send(json.dumps(message))
        received = await asyncio.wait_for(ws.recv(), timeout=a2a_client.timeout_seconds)
        payload = json.loads(received)
        assert payload.get("topic") == "system"
        assert payload.get("echo", {}).get("type") == "ping"
        assert payload.get("echo", {}).get("id") == message["id"]
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.asyncio
async def test_a2a_unknown_command_contract(a2a_client):
    ws_url = _ws_url(a2a_client.base_url, "system")
    unknown_cmd = f"noop-{uuid.uuid4().hex[:6]}"

    async with websockets.connect(
        ws_url,
        open_timeout=a2a_client.timeout_seconds,
        close_timeout=a2a_client.timeout_seconds,
    ) as ws:
        await ws.send(json.dumps({"type": "command", "command": unknown_cmd}))
        received = await asyncio.wait_for(ws.recv(), timeout=a2a_client.timeout_seconds)
        payload = json.loads(received)
        assert payload.get("type") == "command_response"
        result = payload.get("result", {})
        assert result.get("type") == "unknown"
        assert result.get("command") == unknown_cmd
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.asyncio
async def test_a2a_topic_isolation(a2a_client):
    system_ws = _ws_url(a2a_client.base_url, "system")
    sessions_ws = _ws_url(a2a_client.base_url, "sessions")
    marker = uuid.uuid4().hex[:8]

    async with websockets.connect(
        system_ws,
        open_timeout=a2a_client.timeout_seconds,
        close_timeout=a2a_client.timeout_seconds,
    ) as ws_system:
        async with websockets.connect(
            sessions_ws,
            open_timeout=a2a_client.timeout_seconds,
            close_timeout=a2a_client.timeout_seconds,
        ) as ws_sessions:
            response = requests.post(
                f"{a2a_client.base_url}/a2a/broadcast/system",
                json={"type": "system_notice", "marker": marker},
                timeout=a2a_client.timeout_seconds,
            )
            assert response.status_code == 200, response.text

            system_msg = await asyncio.wait_for(
                ws_system.recv(), timeout=a2a_client.timeout_seconds
            )
            system_payload = json.loads(system_msg)
            assert system_payload.get("topic") == "system"
            assert system_payload.get("data", {}).get("marker") == marker

            with pytest.raises(asyncio.TimeoutError):
                await asyncio.wait_for(ws_sessions.recv(), timeout=1.0)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.asyncio
async def test_a2a_broadcast_fanout(a2a_client):
    ws_url = _ws_url(a2a_client.base_url, "system")
    marker = uuid.uuid4().hex[:8]

    async with websockets.connect(
        ws_url,
        open_timeout=a2a_client.timeout_seconds,
        close_timeout=a2a_client.timeout_seconds,
    ) as ws_one:
        async with websockets.connect(
            ws_url,
            open_timeout=a2a_client.timeout_seconds,
            close_timeout=a2a_client.timeout_seconds,
        ) as ws_two:
            response = requests.post(
                f"{a2a_client.base_url}/a2a/broadcast/system",
                json={"type": "fanout", "marker": marker},
                timeout=a2a_client.timeout_seconds,
            )
            assert response.status_code == 200, response.text

            recv_one = json.loads(
                await asyncio.wait_for(ws_one.recv(), timeout=a2a_client.timeout_seconds)
            )
            recv_two = json.loads(
                await asyncio.wait_for(ws_two.recv(), timeout=a2a_client.timeout_seconds)
            )
            assert recv_one.get("data", {}).get("marker") == marker
            assert recv_two.get("data", {}).get("marker") == marker
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.asyncio
async def test_a2a_reconnect_sequence(a2a_client):
    ws_url = _ws_url(a2a_client.base_url, "system")
    marker_first = uuid.uuid4().hex[:8]
    marker_second = uuid.uuid4().hex[:8]

    async with websockets.connect(
        ws_url,
        open_timeout=a2a_client.timeout_seconds,
        close_timeout=a2a_client.timeout_seconds,
    ) as ws:
        await ws.send(json.dumps({"type": "ping", "marker": marker_first}))
        _ = await asyncio.wait_for(ws.recv(), timeout=a2a_client.timeout_seconds)

    async with websockets.connect(
        ws_url,
        open_timeout=a2a_client.timeout_seconds,
        close_timeout=a2a_client.timeout_seconds,
    ) as ws_reconnected:
        await ws_reconnected.send(json.dumps({"type": "ping", "marker": marker_second}))
        msg = await asyncio.wait_for(ws_reconnected.recv(), timeout=a2a_client.timeout_seconds)
        payload = json.loads(msg)
        assert payload.get("echo", {}).get("marker") == marker_second
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_a2a_topics_endpoint_contract(a2a_client):
    response = a2a_client.get(
        f"{a2a_client.base_url}/a2a/topics",
        timeout=a2a_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert "topics" in data and isinstance(data["topics"], dict)
    assert "active_connections" in data and isinstance(data["active_connections"], dict)
    required_topics = {"conversations", "sessions", "experts", "jobs", "system"}
    assert required_topics.issubset(set(data["topics"].keys()))
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_a2a_health_contract(a2a_client):
    response = a2a_client.get(
        f"{a2a_client.base_url}/a2a/health",
        timeout=a2a_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data.get("status") == "healthy"
    assert "connections" in data
    assert "topics" in data
    assert data.get("application") == "expert-agent-mcp-server"
    assert data.get("version")
    env = data.get("env")
    assert isinstance(env, dict)
    assert isinstance(env.get("config_env_file"), str) and env.get("config_env_file")

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.mcp, pytest.mark.slow, pytest.mark.heavy]

