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
Application Test: AT1.92 - Web UI Testing Interface

License: Apache 2.0
Ownership: Cloud Dog
Description: Validates Web UI testing panel contract and /testing expert-suite flow

Related Requirements: FR1.22, UC1.16
Related Tasks: T060
Related Architecture: CC1.1.2
Related Tests: AT1.92
"""

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
    last_error = None
    for _ in range(8):
        try:
            response = session.get(f"{base_url}{path}", timeout=timeout)
            if response.status_code == 200:
                return
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(0.5)
    pytest.fail(f"Server not healthy at {base_url}{path}. last_error={last_error}")


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
def test_entities(clients):
    api = clients["api"]
    api_url = clients["api_url"]
    timeout = api.timeout_seconds
    unique = uuid.uuid4().hex[:8]

    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in config")
    if "@" not in str(base_email):
        pytest.fail("test.user.email must include a domain")
    domain = str(base_email).split("@", 1)[1]

    user_response = api.post(
        f"{api_url}/users",
        json={
            "username": f"{base_username}_at192_{unique}",
            "email": f"at192_{unique}@{domain}",
            "password": str(password),
            "display_name": f"AT1.92 User {unique}",
        },
        timeout=timeout,
    )
    assert user_response.status_code == 200, user_response.text
    user = user_response.json()

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    llm_api_key = get_config("llm.api_key")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config")

    expert_response = api.post(
        f"{api_url}/experts",
        json={
            "name": f"at192_expert_{unique}",
            "title": f"AT1.92 Expert Alpha Beta {unique}",
            "description": f"Supports AT1.92 test interface workflow token {unique}.",
            "llm_provider": str(llm_provider),
            "llm_model": str(llm_model),
            "llm_base_url": str(llm_base_url),
            "llm_api_key": llm_api_key,
            "enabled": True,
        },
        timeout=timeout,
    )
    assert expert_response.status_code == 200, expert_response.text
    expert = expert_response.json()

    channel_response = api.post(
        f"{api_url}/channels",
        json={
            "name": f"AT192 Channel {unique}",
            "expert_config_id": int(expert["id"]),
            "description": f"AT1.92 testing interface channel {unique}",
            "enabled": True,
        },
        timeout=timeout,
    )
    assert channel_response.status_code == 200, channel_response.text
    channel = channel_response.json()

    yield {"user": user, "expert": expert, "channel": channel}

    api.delete(f"{api_url}/channels/{channel['id']}", timeout=timeout)
    api.delete(f"{api_url}/experts/{expert['id']}", timeout=timeout)
    api.delete(f"{api_url}/users/{user['id']}", timeout=timeout)
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-016")


def test_web_dashboard_exposes_testing_panel_contract(clients):
    web = clients["web"]
    web_url = clients["web_url"]

    response = web.get(f"{web_url}/testing", timeout=web.timeout_seconds)
    assert response.status_code == 200, response.text
    body = response.text

    assert 'runtime-config.js' in body
    assert 'id="root"' in body
    assert "/testing" in body
    assert "/docs/api" in body
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-016")


def test_testing_interface_backend_endpoint_contract(clients, test_entities):
    api = clients["api"]
    api_url = clients["api_url"]
    channel_id = int(test_entities["channel"]["id"])

    response = api.post(
        f"{api_url}/testing/expert-suite",
        json={
            "channel_id": channel_id,
            "user_id": int(test_entities["user"]["id"]),
            "test_cases": [],
        },
        timeout=api.timeout_seconds,
    )
    assert response.status_code == 200, response.text

    payload = response.json()
    assert isinstance(payload, dict)
    assert payload
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-016")


def test_testing_interface_validates_required_channel_id(clients):
    api = clients["api"]
    api_url = clients["api_url"]

    response = api.post(
        f"{api_url}/testing/expert-suite",
        json={},
        timeout=api.timeout_seconds,
    )
    assert response.status_code == 422, response.text
    assert "channel_id" in response.text

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]
