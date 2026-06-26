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


def test_it226_log_search_and_export_pipeline(test_env_file):
    load_config.cache_clear()
    key = get_config("test.api_key")
    if not key:
        pytest.fail("test.api_key not configured")

    s = requests.Session()
    s.headers.update({"X-API-Key": str(key)})
    base = _api_base()
    timeout = float(get_config("test.http_timeout_seconds") or 60)

    events = s.get(f"{base}/audit", params={"limit": 10}, timeout=timeout)
    assert events.status_code == 200, events.text
    assert isinstance(events.json().get("events"), list)

    export_json = s.get(f"{base}/audit/export/json", timeout=timeout)
    assert export_json.status_code == 200, export_json.text
    assert "application/json" in export_json.headers.get("content-type", "")

    export_csv = s.get(f"{base}/audit/export/csv", timeout=timeout)
    assert export_csv.status_code == 200, export_csv.text
    assert "text/csv" in export_csv.headers.get("content-type", "")

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.pure, pytest.mark.heavy]

