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


pytestmark = pytest.mark.integration


def _api_base() -> str:
    base = get_config("api_server.base_url")
    if base:
        return str(base).rstrip("/")
    h, p = get_config("api_server.host"), get_config("api_server.port")
    if not h or p is None:
        pytest.fail("api_server.host/api_server.port not configured")
    return f"http://{h}:{int(p)}"
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-047")


def test_it225_external_service_registry_handshake_and_health(test_env_file):
    load_config.cache_clear()
    key = get_config("test.api_key")
    if not key:
        pytest.fail("test.api_key not configured")

    s = requests.Session()
    s.headers.update({"X-API-Key": str(key)})
    base = _api_base()
    timeout = float(get_config("test.http_timeout_seconds") or 60)

    unique = uuid.uuid4().hex[:8]
    payload = {
        "name": f"it225_service_{unique}",
        "service_type": "mcp",
        "endpoint_url": f"{base}/health",
        "auth_config": {"type": "api_key", "header": "X-API-Key"},
        "metadata": {"suite": "IT2.25", "token": unique},
    }

    created = s.post(f"{base}/services", json=payload, timeout=timeout)
    assert created.status_code == 200, created.text
    service_id = int(created.json()["id"])

    try:
        listed = s.get(f"{base}/services", timeout=timeout)
        assert listed.status_code == 200, listed.text
        assert any(int(item["id"]) == service_id for item in listed.json().get("services", []))

        checked = s.post(f"{base}/services/{service_id}/health", timeout=timeout)
        assert checked.status_code == 200, checked.text
        data = checked.json()
        assert int(data["service_id"]) == service_id
        assert data["healthy"] is True
        assert data["health_status"] == "healthy"
    finally:
        s.delete(f"{base}/services/{service_id}", timeout=timeout)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.mcp, pytest.mark.heavy]
