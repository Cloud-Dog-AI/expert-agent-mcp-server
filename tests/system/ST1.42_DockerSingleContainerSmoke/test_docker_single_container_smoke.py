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

import pytest
import requests
import time

from src.config.loader import get_config, load_config


pytestmark = pytest.mark.system


def _base(section: str) -> str:
    host = get_config(f"{section}.host")
    port = get_config(f"{section}.port")
    if not host or port is None:
        pytest.fail(f"{section}.host/{section}.port not configured")
    return f"http://{host}:{int(port)}"


def _wait_health(
    url: str, timeout: float, attempts: int = 30, delay: float = 0.5
) -> requests.Response:
    last_error = None
    for _ in range(attempts):
        try:
            response = requests.get(url, timeout=timeout)
            if response.status_code == 200:
                return response
            last_error = f"status={response.status_code} body={response.text}"
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(delay)
    pytest.fail(f"Health check failed after retries for {url}: {last_error}")
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-045")


def test_st142_all_servers_health(test_env_file):
    load_config.cache_clear()
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    timeout = float(timeout)

    _wait_health(f"{_base('api_server')}/health", timeout=timeout)
    _wait_health(f"{_base('web_server')}/health", timeout=timeout)
    _wait_health(f"{_base('mcp_server')}/mcp/health", timeout=timeout)
    _wait_health(f"{_base('a2a_server')}/a2a/health", timeout=timeout)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-045")


def test_st142_api_auth_smoke(test_env_file):
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    timeout = float(timeout)
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")

    res = requests.get(
        f"{_base('api_server')}/sessions",
        headers={"X-API-Key": str(api_key)},
        timeout=timeout,
    )
    assert res.status_code == 200, res.text
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-045")


def test_st142_mcp_jsonrpc_smoke(test_env_file):
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    timeout = float(timeout)
    base = _base("mcp_server")
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")
    auth = {"X-API-Key": str(api_key)}  # MCP auth-gated (W28C-1704)

    init_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {"protocolVersion": "2024-11-05"},
    }
    init = requests.post(f"{base}/mcp", json=init_payload, headers=auth, timeout=timeout)
    assert init.status_code == 200, init.text
    session_id = init.headers.get("Mcp-Session-Id")
    assert session_id, "missing Mcp-Session-Id"

    tools_payload = {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}
    tools = requests.post(
        f"{base}/mcp",
        json=tools_payload,
        headers={**auth, "Mcp-Session-Id": session_id},
        timeout=timeout,
    )
    assert tools.status_code == 200, tools.text
    body = tools.json()
    assert "result" in body and "tools" in body["result"], body

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.mcp, pytest.mark.slow, pytest.mark.heavy]

