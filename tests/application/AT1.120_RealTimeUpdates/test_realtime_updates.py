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
Application Test: AT1.12 - Real-time Update Workflows

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for real-time update workflows

Related Requirements: FR1.2, FR1.7
Related Tasks: T047
Related Architecture: AI1.3
Related Tests: AT1.12

Recent Changes:
- Refactored to API-only + real A2A WebSocket verification
"""

import asyncio
import json

import pytest
import requests
import websockets

from src.config.loader import get_config

# Use shared application-test API client (requests-based)
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import create_api_client_fixture, validate_config_loaded


@pytest.fixture
def api_client():
    """Create API client that connects to real running API server."""
    validate_config_loaded()
    return create_api_client_fixture(check_health=True)()


@pytest.fixture
def a2a_base_url():
    host = get_config("a2a_server.host")
    port = get_config("a2a_server.port")
    if not host or port is None:
        pytest.fail("a2a_server.host/a2a_server.port not configured (--env)")
    return f"http://{host}:{int(port)}"


def _a2a_ws_url(a2a_base_url: str, topic: str) -> str:
    # a2a_base_url is http://host:port -> ws://host:port
    ws_base = a2a_base_url.replace("http://", "ws://").replace("https://", "wss://")
    return f"{ws_base}/a2a/ws/{topic}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.asyncio
async def test_a2a_websocket_echo_and_command(a2a_base_url):
    """
    Validate A2A WebSocket endpoint behaviour (echo + command_response).

    This is API-only from the application perspective: it uses the running A2A server
    and validates real-time messaging mechanics end-to-end.
    """
    ws_url = _a2a_ws_url(a2a_base_url, "system")
    async with websockets.connect(ws_url, open_timeout=5, close_timeout=5) as ws:
        await ws.send(json.dumps({"type": "ping", "message": "hello"}))
        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        assert "system" in msg

        await ws.send(json.dumps({"type": "command", "command": "status"}))
        cmd = await asyncio.wait_for(ws.recv(), timeout=5)
        assert "command_response" in cmd
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_a2a_topics_and_health(a2a_base_url):
    r = requests.get(f"{a2a_base_url}/a2a/health", timeout=10)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("status") == "healthy"

    r2 = requests.get(f"{a2a_base_url}/a2a/topics", timeout=10)
    assert r2.status_code == 200, r2.text
    topics = r2.json().get("topics", {})
    assert isinstance(topics, dict)
    # Expect baseline topics from server code
    assert "system" in topics
    assert "sessions" in topics
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.asyncio
async def test_a2a_broadcast_roundtrip(a2a_base_url):
    ws_url = _a2a_ws_url(a2a_base_url, "system")
    async with websockets.connect(ws_url, open_timeout=5, close_timeout=5) as ws:
        payload = {"message": "test broadcast"}
        r = requests.post(f"{a2a_base_url}/a2a/broadcast/system", json=payload, timeout=10)
        assert r.status_code == 200, r.text

        msg = await asyncio.wait_for(ws.recv(), timeout=5)
        decoded = json.loads(msg)
        assert decoded.get("topic") == "system"
        assert "data" in decoded
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_api_server_still_operational(api_client):
    """Sanity check: API server reachable during A2A tests."""
    resp = api_client.get("/health")
    assert resp.status_code == 200

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]

