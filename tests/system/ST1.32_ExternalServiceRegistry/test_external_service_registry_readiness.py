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


pytestmark = pytest.mark.system


def _api_base() -> str:
    h, p = get_config("api_server.host"), get_config("api_server.port")
    if not h or p is None:
        pytest.fail("api_server.host/api_server.port not configured")
    return f"http://{h}:{int(p)}"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-045")


def test_st132_registry_persistence_and_health_scheduling_contract(test_env_file):
    load_config.cache_clear()
    key = get_config("test.api_key")
    if not key:
        pytest.fail("test.api_key not configured")

    s = requests.Session()
    s.headers.update({"X-API-Key": str(key)})
    base = _api_base()
    timeout = float(get_config("test.http_timeout_seconds") or 60)

    token = uuid.uuid4().hex[:8]
    created = s.post(
        f"{base}/services",
        json={
            "name": f"st132_service_{token}",
            "service_type": "a2a",
            "endpoint_url": f"{base}/health",
            "metadata": {"suite": "ST1.32", "token": token},
        },
        timeout=timeout,
    )
    assert created.status_code == 200, created.text
    service_id = int(created.json()["id"])

    try:
        fetched = s.get(f"{base}/services/{service_id}", timeout=timeout)
        assert fetched.status_code == 200, fetched.text
        assert fetched.json()["metadata"].get("token") == token

        checked = s.post(f"{base}/services/{service_id}/health", timeout=timeout)
        assert checked.status_code == 200, checked.text
        assert checked.json().get("health_status") in {"healthy", "unhealthy"}

        fetched_after = s.get(f"{base}/services/{service_id}", timeout=timeout)
        assert fetched_after.status_code == 200, fetched_after.text
        assert fetched_after.json().get("health_status") in {"healthy", "unhealthy"}
    finally:
        s.delete(f"{base}/services/{service_id}", timeout=timeout)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.pure, pytest.mark.slow, pytest.mark.heavy]

