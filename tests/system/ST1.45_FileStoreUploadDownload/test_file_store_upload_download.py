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
System Test: ST1.45 - File Store Upload/Download Contract

License: Apache 2.0
Ownership: Cloud Dog
Copyright:
  (C) Cloud-Dog, Viewdeck Engineering Ltd.

Description:
Validates the REST file store endpoints against a running API server:
- upload via base64 JSON payload
- download via /files/{id}/download
- delete via /files/{id}

Rules alignment:
- No mocks/stubs/TestClient.
- Uses config via get_config (--env) and requires real running API server.

# Covers: FR1.13
"""

import base64
import time
import uuid

import pytest
import requests

from src.config.loader import get_config, load_config


pytestmark = pytest.mark.system


def _require_timeout() -> float:
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    return float(timeout)


def _require_api_base_url() -> str:
    host = get_config("api_server.host")
    port = get_config("api_server.port")
    if not host or port is None:
        pytest.fail("api_server.host/api_server.port not configured")
    return f"http://{host}:{int(port)}"


def _wait_for_health(session: requests.Session, base_url: str, timeout: float) -> None:
    last_error = None
    for _ in range(20):
        try:
            r = session.get(f"{base_url}/health", timeout=timeout)
            if r.status_code == 200:
                return
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(0.5)
    pytest.fail(f"API server not healthy at {base_url}/health. last_error={last_error}")


@pytest.fixture
def api_client(test_env_file):
    load_config.cache_clear()
    timeout = _require_timeout()
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")

    base_url = _require_api_base_url()
    s = requests.Session()
    s.headers.update({"X-API-Key": str(api_key)})
    _wait_for_health(s, base_url, timeout)
    s.base_url = base_url
    s.timeout_seconds = timeout
    return s
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-008")


def test_file_upload_base64_download_delete_round_trip(api_client):
    token = uuid.uuid4().hex[:8]
    original_text = f"ST1.45 file token {token}\nSecond line.\n"
    payload = {
        "filename": f"st145_{token}.txt",
        "content_base64": base64.b64encode(original_text.encode("utf-8")).decode("ascii"),
        "metadata": {"st": True, "token": token},
    }

    created = api_client.post(
        f"{api_client.base_url}/files/upload_base64",
        json=payload,
        timeout=api_client.timeout_seconds,
    )
    assert created.status_code == 200, created.text
    created_data = created.json()
    assert created_data.get("success") is True
    file_id = int(created_data["file"]["id"])

    downloaded = api_client.get(
        f"{api_client.base_url}/files/{file_id}/download",
        timeout=api_client.timeout_seconds,
    )
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.content.decode("utf-8") == original_text

    deleted = api_client.delete(
        f"{api_client.base_url}/files/{file_id}",
        timeout=api_client.timeout_seconds,
    )
    assert deleted.status_code == 200, deleted.text
    assert deleted.json().get("success") is True

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.pure, pytest.mark.slow, pytest.mark.heavy]
