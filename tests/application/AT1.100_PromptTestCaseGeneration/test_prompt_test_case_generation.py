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

pytestmark = pytest.mark.application


import requests  # noqa: E402

from src.config.loader import get_config, load_config  # noqa: E402


def _api_base() -> str:
    h, p = get_config("api_server.host"), get_config("api_server.port")
    if not h or p is None:
        pytest.fail("api_server.host/api_server.port not configured")
    return f"http://{h}:{int(p)}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_at1100_prompt_test_case_generation_validation(test_env_file):
    load_config.cache_clear()
    key = get_config("test.api_key")
    if not key:
        pytest.fail("test.api_key not configured")

    timeout = float(get_config("test.http_timeout_seconds") or 60)
    s = requests.Session()
    s.headers.update({"X-API-Key": str(key)})
    base = _api_base()

    generated = s.post(
        f"{base}/prompts/test-cases",
        json={
            "title": "PromptCase",
            "details": "Generate cases for endpoint contract testing.",
            "prompt": "You are a helpful assistant.",
            "num_cases": 3,
        },
        timeout=timeout,
    )
    assert generated.status_code == 200, generated.text
    body = generated.json()
    assert body.get("success") is True
    assert int(body.get("count", 0)) >= 1
    assert isinstance(body.get("test_cases"), list)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]

