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

from src.config.loader import get_config, load_config

pytestmark = pytest.mark.system


def _base(section: str) -> str:
    h, p = get_config(f"{section}.host"), get_config(f"{section}.port")
    if not h or p is None:
        pytest.fail(f"{section}.host/{section}.port not configured")
    return f"http://{h}:{int(p)}"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-045")


def test_st134_external_agentic_gateway_readiness_contract(test_env_file):
    load_config.cache_clear()
    key = get_config("test.api_key")
    timeout = float(get_config("test.http_timeout_seconds") or 60)
    if not key:
        pytest.fail("test.api_key not configured")

    api = _base("api_server")
    session = requests.Session()
    session.headers.update({"X-API-Key": str(key)})

    mcp_health = session.get(f"{api}/mcp/health", timeout=timeout)
    assert mcp_health.status_code == 200, mcp_health.text

    a2a_health = session.get(f"{api}/a2a/health", timeout=timeout)
    assert a2a_health.status_code == 200, a2a_health.text

    invalid_chat = session.post(
        f"{api}/mcp/chat", json={"message": "missing session"}, timeout=timeout
    )
    assert invalid_chat.status_code == 200, invalid_chat.text
    assert "error" in invalid_chat.json()

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.mcp, pytest.mark.slow, pytest.mark.heavy]

