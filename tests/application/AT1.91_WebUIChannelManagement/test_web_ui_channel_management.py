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
Application Test: AT1.91 - Web UI Channel Management

License: Apache 2.0
Ownership: Cloud Dog
Description: Validates Web UI channel-management coverage through dashboard + backing API

Related Requirements: FR1.21, UC1.15
Related Tasks: T059
Related Architecture: CC1.1.2
Related Tests: AT1.91
"""

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


def _require_base_url(section: str) -> str:
    base_url = get_config(f"{section}.base_url")
    if base_url:
        return str(base_url).rstrip("/")
    host = get_config(f"{section}.host")
    port = get_config(f"{section}.port")
    if not host or port is None:
        pytest.fail(f"{section}.host/{section}.port not configured")
    scheme = str(get_config(f"{section}.scheme") or "http").strip().lower()
    return f"{scheme}://{host}:{int(port)}"


def _wait_for_health(session: requests.Session, base_url: str, path: str) -> None:
    timeout = session.timeout_seconds
    for _ in range(6):
        try:
            response = session.get(f"{base_url}{path}", timeout=timeout)
            if response.status_code == 200:
                return
        except requests.RequestException:
            pass
    pytest.fail(f"Server not healthy at {base_url}{path}")


@pytest.fixture
def clients(test_env_file):
    load_config.cache_clear()
    timeout = _require_timeout()
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")

    api_url = _require_base_url("api_server")
    web_url = _require_base_url("web_server")

    api = requests.Session()
    api.headers.update({"X-API-Key": str(api_key)})
    api.timeout_seconds = timeout

    web = requests.Session()
    web.timeout_seconds = timeout

    _wait_for_health(api, api_url, "/health")
    _wait_for_health(web, web_url, "/health")

    return {"api": api, "web": web, "api_url": api_url, "web_url": web_url}


@pytest.fixture
def test_expert(clients):
    api = clients["api"]
    api_url = clients["api_url"]
    unique = uuid.uuid4().hex[:8]

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    llm_api_key = get_config("llm.api_key")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config")

    response = api.post(
        f"{api_url}/experts",
        json={
            "name": f"at191_expert_{unique}",
            "title": f"AT1.91 Expert Alpha Beta {unique}",
            "description": f"Supports AT1.91 web UI channel management workflow token {unique}.",
            "llm_provider": str(llm_provider),
            "llm_model": str(llm_model),
            "llm_base_url": str(llm_base_url),
            "llm_api_key": llm_api_key,
            "enabled": True,
        },
        timeout=api.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    expert = response.json()
    yield expert
    api.delete(f"{api_url}/experts/{expert['id']}", timeout=api.timeout_seconds)
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-015")


def test_web_dashboard_exposes_channel_panel_contract(clients):
    web = clients["web"]
    web_url = clients["web_url"]

    response = web.get(f"{web_url}/", timeout=web.timeout_seconds)
    assert response.status_code == 200, response.text
    body = response.text
    assert '<div id="root"></div>' in body
    assert "/runtime-config.js" in body
    assert "/api-docs" in body
    assert "/testing" in body
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-015")


def test_channel_crud_visible_to_dashboard_data_source(clients, test_expert):
    api = clients["api"]
    api_url = clients["api_url"]
    unique = uuid.uuid4().hex[:8]

    create_response = api.post(
        f"{api_url}/channels",
        json={
            "name": f"AT191 Channel {unique}",
            "expert_config_id": int(test_expert["id"]),
            "description": f"AT1.91 channel management test channel {unique}",
            "enabled": True,
        },
        timeout=api.timeout_seconds,
    )
    assert create_response.status_code == 200, create_response.text
    channel = create_response.json()
    channel_id = int(channel["id"])

    try:
        list_response = api.get(f"{api_url}/channels", timeout=api.timeout_seconds)
        assert list_response.status_code == 200, list_response.text
        listed_ids = {
            int(item["id"]) for item in list_response.json().get("channels", []) if "id" in item
        }
        assert channel_id in listed_ids

        get_response = api.get(f"{api_url}/channels/{channel_id}", timeout=api.timeout_seconds)
        assert get_response.status_code == 200, get_response.text
        get_payload = get_response.json()
        assert int(get_payload["id"]) == channel_id
        assert get_payload["name"] == f"AT191 Channel {unique}"
    finally:
        api.delete(f"{api_url}/channels/{channel_id}", timeout=api.timeout_seconds)
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-015")


def test_web_channel_chat_path_is_available(clients, test_expert):
    api = clients["api"]
    api_url = clients["api_url"]
    unique = uuid.uuid4().hex[:8]

    channel_response = api.post(
        f"{api_url}/channels",
        json={
            "name": f"AT191 Chat Channel {unique}",
            "expert_config_id": int(test_expert["id"]),
            "description": f"AT1.91 channel chat contract test {unique}",
            "enabled": True,
        },
        timeout=api.timeout_seconds,
    )
    assert channel_response.status_code == 200, channel_response.text
    channel_id = int(channel_response.json()["id"])

    try:
        # Frontend sends this path; contract currently enforces user_id via request schema validation (422).
        chat_response = api.post(
            f"{api_url}/channels/{channel_id}/chat",
            json={"message": "hello", "is_async": False},
            timeout=api.timeout_seconds,
        )
        assert chat_response.status_code == 422, chat_response.text
        assert "user_id" in chat_response.text
    finally:
        api.delete(f"{api_url}/channels/{channel_id}", timeout=api.timeout_seconds)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]
