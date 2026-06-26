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

import uuid

import pytest
import requests

from src.config.loader import get_config, load_config


pytestmark = pytest.mark.application


def _api_base() -> str:
    h, p = get_config("api_server.host"), get_config("api_server.port")
    if not h or p is None:
        pytest.fail("api_server.host/api_server.port not configured")
    return f"http://{h}:{int(p)}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-011")


def test_at195_external_service_registry_lifecycle_and_access_control(test_env_file):
    # Covers: FR1.16, FR1.19
    load_config.cache_clear()
    key = get_config("test.api_key")
    bad_key = "invalid-test-key"
    if not key:
        pytest.fail("test.api_key not configured")

    s = requests.Session()
    s.headers.update({"X-API-Key": str(key)})
    base = _api_base()
    timeout = float(get_config("test.http_timeout_seconds") or 60)

    token = uuid.uuid4().hex[:8]
    create_payload = {
        "name": f"at195_service_{token}",
        "service_type": "mcp",
        "endpoint_url": f"{base}/health",
        "auth_config": {"kind": "none"},
        "metadata": {"suite": "AT1.95", "token": token, "stage": "created"},
    }

    created = s.post(f"{base}/services", json=create_payload, timeout=timeout)
    assert created.status_code == 200, created.text
    service_id = int(created.json()["id"])

    try:
        updated = s.put(
            f"{base}/services/{service_id}",
            json={
                "endpoint_url": f"{base}/mcp/health",
                "metadata": {"suite": "AT1.95", "token": token, "stage": "updated"},
            },
            timeout=timeout,
        )
        assert updated.status_code == 200, updated.text
        assert updated.json().get("metadata", {}).get("stage") == "updated"

        health = s.post(f"{base}/services/{service_id}/health", timeout=timeout)
        assert health.status_code == 200, health.text

        unauth = requests.get(f"{base}/services", headers={"X-API-Key": bad_key}, timeout=timeout)
        assert unauth.status_code == 401, unauth.text
    finally:
        s.delete(f"{base}/services/{service_id}", timeout=timeout)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.mcp, pytest.mark.heavy]
