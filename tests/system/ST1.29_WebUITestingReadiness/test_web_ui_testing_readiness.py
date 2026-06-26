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


def _base(section: str) -> str:
    h, p = get_config(f"{section}.host"), get_config(f"{section}.port")
    if not h or p is None:
        pytest.fail(f"{section}.host/{section}.port not configured")
    return f"http://{h}:{int(p)}"
@pytest.mark.ST
@pytest.mark.webui
@pytest.mark.req("FR-045")


def test_st129_web_ui_testing_interface_readiness(test_env_file):
    load_config.cache_clear()
    timeout = float(get_config("test.http_timeout_seconds") or 60)
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")

    web_url = _base("web_server")
    api_url = _base("api_server")

    html = requests.get(f"{web_url}/admin/prompts", timeout=timeout)
    assert html.status_code == 200, html.text
    body = html.text
    assert 'id="root"' in body
    assert "/runtime-config.js" in body
    assert "type=\"module\"" in body

    # API path ready and validated
    no_payload = requests.post(
        f"{api_url}/testing/expert-suite",
        headers={"X-API-Key": str(api_key)},
        json={},
        timeout=timeout,
    )
    assert no_payload.status_code == 422, no_payload.text
    assert "channel_id" in no_payload.text

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.pure, pytest.mark.slow, pytest.mark.heavy]
