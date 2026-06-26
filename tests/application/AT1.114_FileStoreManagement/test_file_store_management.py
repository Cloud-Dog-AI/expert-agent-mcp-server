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
Application Test: AT1.114 - File Store Management (Admin)

License: Apache 2.0
Ownership: Cloud Dog
Copyright:
  (C) Cloud-Dog, Viewdeck Engineering Ltd.

Description:
Validates the admin file store management endpoints against a running API server:
- Upload via /files/upload_base64
- List via /files
- Download via /files/{id}/download
- Delete via /files/{id}

Rules alignment:
- No mocks/stubs/TestClient.
- Uses config via get_config (--env) and requires real running API server.

# Covers: FR1.34
"""

import base64
import time
import uuid

import pytest
import requests

from src.config.loader import get_config, load_config


pytestmark = pytest.mark.application


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
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-026")


def test_file_store_upload_list_download_delete(api_client):
    unique = uuid.uuid4().hex[:8]
    token = f"AT114_TOKEN_{unique}"
    text = f"AT1.114 file store token {token}\n"

    created = api_client.post(
        f"{api_client.base_url}/files/upload_base64",
        json={
            "filename": f"at114_{unique}.txt",
            "content_base64": base64.b64encode(text.encode("utf-8")).decode("ascii"),
            "metadata": {"token": token},
        },
        timeout=api_client.timeout_seconds,
    )
    assert created.status_code == 200, created.text
    file_id = int(created.json()["file"]["id"])

    try:
        listed = api_client.get(
            f"{api_client.base_url}/files",
            timeout=api_client.timeout_seconds,
        )
        assert listed.status_code == 200, listed.text
        files = listed.json().get("files") or []
        assert any(int(f.get("id")) == file_id for f in files)

        downloaded = api_client.get(
            f"{api_client.base_url}/files/{file_id}/download",
            timeout=api_client.timeout_seconds,
        )
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content.decode("utf-8") == text
    finally:
        deleted = api_client.delete(
            f"{api_client.base_url}/files/{file_id}",
            timeout=api_client.timeout_seconds,
        )
        assert deleted.status_code == 200, deleted.text
        assert deleted.json().get("success") is True
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-026")


def test_file_store_ingest_to_group_knowledge(api_client):
    unique = uuid.uuid4().hex[:8]
    token = f"AT114_KNOWLEDGE_{unique}"
    text = f"Knowledge ingest token {token}\n"

    me = api_client.get(
        f"{api_client.base_url}/api-keys/me",
        timeout=api_client.timeout_seconds,
    )
    assert me.status_code == 200, me.text
    owner_user_id = int(me.json()["user_id"])

    # Create a dedicated group for deterministic knowledge scope.
    group = api_client.post(
        f"{api_client.base_url}/groups",
        json={
            "name": f"at114_k_group_{unique}",
            "description": "AT1.114 ingest test group",
            "enabled": True,
        },
        timeout=api_client.timeout_seconds,
    )
    assert group.status_code == 200, group.text
    group_id = int(group.json()["id"])

    # Ensure API key owner is a group member so group knowledge access is valid.
    add_member = api_client.post(
        f"{api_client.base_url}/groups/{group_id}/members",
        json={"user_id": owner_user_id, "role": "member"},
        timeout=api_client.timeout_seconds,
    )
    assert add_member.status_code in (200, 400), add_member.text

    created = api_client.post(
        f"{api_client.base_url}/files/upload_base64",
        json={
            "filename": f"at114_knowledge_{unique}.txt",
            "content_base64": base64.b64encode(text.encode("utf-8")).decode("ascii"),
            "metadata": {"token": token},
        },
        timeout=api_client.timeout_seconds,
    )
    assert created.status_code == 200, created.text
    file_id = int(created.json()["file"]["id"])

    try:
        ingested = api_client.post(
            f"{api_client.base_url}/files/{file_id}/ingest_to_knowledge",
            json={
                "knowledge_type": "group",
                "knowledge_id": group_id,
                "metadata": {"token": token, "suite": "AT1.114"},
            },
            timeout=api_client.timeout_seconds,
        )
        assert ingested.status_code == 200, ingested.text
        payload = ingested.json()
        assert payload.get("success") is True
        assert int(payload["file_id"]) == file_id
        assert payload.get("knowledge_type") == "group"
        assert int(payload.get("knowledge_id")) == group_id
        assert token in str(payload.get("entry", {}).get("content", ""))

        history = api_client.get(
            f"{api_client.base_url}/knowledge/group/{group_id}",
            timeout=api_client.timeout_seconds,
        )
        assert history.status_code == 200, history.text
        entries = history.json().get("entries", [])
        assert any(token in str(e.get("content", "")) for e in entries)
    finally:
        api_client.delete(
            f"{api_client.base_url}/files/{file_id}",
            timeout=api_client.timeout_seconds,
        )
        api_client.delete(
            f"{api_client.base_url}/groups/{group_id}",
            timeout=api_client.timeout_seconds,
        )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]
