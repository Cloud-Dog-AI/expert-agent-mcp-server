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
import uuid
import os

from src.config.loader import get_config, load_config


pytestmark = pytest.mark.integration


def _base(section: str) -> str:
    override_map = {
        "api_server": "CLOUD_DOG__EXPERT__TEST__API_BASE_URL",
        "mcp_server": "CLOUD_DOG__EXPERT__TEST__MCP_BASE_URL",
        "a2a_server": "CLOUD_DOG__EXPERT__TEST__A2A_BASE_URL",
    }
    override = os.environ.get(override_map.get(section, ""), "").strip()
    if override:
        return override.rstrip("/")
    base = get_config(f"{section}.base_url")
    if base:
        return str(base).rstrip("/")
    h, p = get_config(f"{section}.host"), get_config(f"{section}.port")
    if not h or p is None:
        pytest.fail(f"{section}.host/{section}.port not configured")
    return f"http://{h}:{int(p)}"
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-047")


def test_it224_api_key_auth_contracts_across_interfaces(test_env_file):
    load_config.cache_clear()
    timeout = float(get_config("test.http_timeout_seconds") or 60)
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")

    api_url = _base("api_server")
    mcp_url = _base("mcp_server")
    a2a_url = _base("a2a_server")

    # API protected route must reject missing key.
    unauth_api = requests.get(f"{api_url}/sessions", timeout=timeout)
    assert unauth_api.status_code == 401, unauth_api.text

    auth_api = requests.get(
        f"{api_url}/sessions", headers={"X-API-Key": str(api_key)}, timeout=timeout
    )
    assert auth_api.status_code == 200, auth_api.text

    # Create a fresh user-scoped key, rotate it, and revoke it to validate lifecycle across interface access.
    admin = requests.Session()
    admin.headers.update({"X-API-Key": str(api_key)})
    token = uuid.uuid4().hex[:8]
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail("test.user.username/test.user.email/test.user.password not configured")
    domain = str(base_email).split("@", 1)[1]

    created_user = admin.post(
        f"{api_url}/users",
        json={
            "username": f"{base_username}_it224_{token}",
            "email": f"it224_{token}@{domain}",
            "password": str(password),
            "display_name": f"IT224 {token}",
        },
        timeout=timeout,
    )
    assert created_user.status_code == 200, created_user.text
    user_id = int(created_user.json()["id"])

    try:
        key_resp = admin.post(
            f"{api_url}/api-keys",
            json={"user_id": user_id, "name": f"it224_live_{token}", "expires_days": 1},
            timeout=timeout,
        )
        assert key_resp.status_code == 200, key_resp.text
        live_key_id = int(key_resp.json()["id"])
        live_key = str(key_resp.json()["key"])

        live_api = requests.get(
            f"{api_url}/sessions",
            headers={"X-API-Key": live_key},
            timeout=timeout,
        )
        assert live_api.status_code == 200, live_api.text

        rotate = admin.post(f"{api_url}/api-keys/{live_key_id}/rotate", timeout=timeout)
        assert rotate.status_code == 200, rotate.text
        rotated = rotate.json()["new_key"]
        int(rotated["id"])
        rotated_key = str(rotated["key"])

        old_after_rotate = requests.get(
            f"{api_url}/sessions",
            headers={"X-API-Key": live_key},
            timeout=timeout,
        )
        assert old_after_rotate.status_code == 401, old_after_rotate.text
        rotated_probe = requests.get(
            f"{api_url}/sessions",
            headers={"X-API-Key": rotated_key},
            timeout=timeout,
        )
        assert rotated_probe.status_code == 200, rotated_probe.text
    finally:
        # User cleanup removes all user-bound keys.
        admin.delete(f"{api_url}/users/{user_id}", timeout=timeout)

    # MCP health/tools endpoints currently public but must return deterministic contracts.
    mcp_health = requests.get(f"{mcp_url}/mcp/health", timeout=timeout)
    assert mcp_health.status_code == 200, mcp_health.text

    mcp_tools = requests.post(
        f"{mcp_url}/mcp",
        headers={"X-API-Key": str(api_key)},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        timeout=timeout,
    )
    assert mcp_tools.status_code == 200, mcp_tools.text
    assert mcp_tools.json().get("jsonrpc") == "2.0"

    # A2A health currently public but must be deterministic/healthy.
    a2a_health = requests.get(f"{a2a_url}/a2a/health", timeout=timeout)
    assert a2a_health.status_code == 200, a2a_health.text
    assert a2a_health.json().get("status") == "healthy"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.smtp, pytest.mark.mcp, pytest.mark.heavy]
