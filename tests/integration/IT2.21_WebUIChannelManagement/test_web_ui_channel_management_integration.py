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

import time
import uuid

import pytest
import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.browser_helpers import build_headless_chrome_options
from src.config.loader import get_config, load_config


pytestmark = pytest.mark.integration


def _base(section: str) -> str:
    base = get_config(f"{section}.base_url")
    if base:
        return str(base).rstrip("/")
    h, p = get_config(f"{section}.host"), get_config(f"{section}.port")
    if not h or p is None:
        pytest.fail(f"{section}.host/{section}.port not configured")
    return f"http://{h}:{int(p)}"


def _wait_for_health(session: requests.Session, base_url: str, path: str = "/health") -> None:
    timeout = float(get_config("test.http_timeout_seconds") or 60)
    last_error = None
    for _ in range(20):
        try:
            response = session.get(f"{base_url}{path}", timeout=timeout)
            if response.status_code == 200:
                return
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(0.5)
    pytest.fail(f"Server not healthy at {base_url}{path}; last_error={last_error}")


@pytest.fixture
def clients(test_env_file):
    load_config.cache_clear()
    api_key = get_config("test.api_key")
    timeout = float(get_config("test.http_timeout_seconds") or 60)
    if not api_key:
        pytest.fail("test.api_key not configured")
    api = requests.Session()
    api.headers.update({"X-API-Key": str(api_key)})
    api.timeout_seconds = timeout
    api_url = _base("api_server")
    web_url = _base("web_server")
    _wait_for_health(api, api_url)
    _wait_for_health(api, web_url)
    return {"api": api, "api_url": api_url, "web_url": web_url, "api_key": str(api_key)}


@pytest.fixture
def user_and_channel(clients):
    api, api_url = clients["api"], clients["api_url"]
    u = uuid.uuid4().hex[:8]
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    domain = str(base_email).split("@", 1)[1]

    user = api.post(
        f"{api_url}/users",
        json={
            "username": f"{base_username}_it221_{u}",
            "email": f"it221_{u}@{domain}",
            "password": str(password),
            "display_name": f"IT221 {u}",
        },
        timeout=api.timeout_seconds,
    )
    assert user.status_code == 200, user.text
    user_data = user.json()

    expert = api.post(
        f"{api_url}/experts",
        json={
            "name": f"it221_expert_{u}",
            "title": f"IT221 Channels Workflow Delta Matrix {u}",
            "description": (
                "IT2.21 integration validates channel orchestration, "
                f"permissions, synchronization, routing, telemetry, resilience {u}."
            ),
            "llm_provider": str(get_config("llm.provider")),
            "llm_model": str(get_config("llm.model")),
            "llm_base_url": str(get_config("llm.base_url")),
            "llm_api_key": get_config("llm.api_key"),
            "enabled": True,
        },
        timeout=api.timeout_seconds,
    )
    assert expert.status_code == 200, expert.text
    expert_data = expert.json()

    channel = api.post(
        f"{api_url}/channels",
        json={
            "name": f"IT221 Channel {u}",
            "expert_config_id": int(expert_data["id"]),
            "description": f"UI->API integration {u}",
            "enabled": True,
        },
        timeout=api.timeout_seconds,
    )
    assert channel.status_code == 200, channel.text
    channel_data = channel.json()

    yield {"user": user_data, "expert": expert_data, "channel": channel_data}

    api.delete(f"{api_url}/channels/{channel_data['id']}", timeout=api.timeout_seconds)
    api.delete(f"{api_url}/experts/{expert_data['id']}", timeout=api.timeout_seconds)
    api.delete(f"{api_url}/users/{user_data['id']}", timeout=api.timeout_seconds)
@pytest.mark.IT
@pytest.mark.webui
@pytest.mark.req("FR-047")


def test_it221_web_ui_channels_panel_reflects_api_data(clients, user_and_channel):
    browser = webdriver.Chrome(options=build_headless_chrome_options())
    browser.set_page_load_timeout(60)
    try:
        browser.get(f"{clients['web_url']}/")
        username = get_config("test.user.username")
        password = get_config("test.user.password")
        if not username or not password:
            pytest.fail("test.user.username/test.user.password not configured")
        wait = WebDriverWait(browser, 60)
        wait.until(EC.presence_of_element_located((By.ID, "loginUsername")))
        browser.find_element(By.ID, "loginUsername").clear()
        browser.find_element(By.ID, "loginUsername").send_keys(str(username))
        browser.find_element(By.ID, "loginPassword").clear()
        browser.find_element(By.ID, "loginPassword").send_keys(str(password))
        browser.find_element(By.XPATH, "//button[normalize-space()='Sign in' or normalize-space()='Sign In']").click()
        wait.until(lambda d: "/login" not in d.current_url)

        browser.get(f"{clients['web_url']}/channels")
        wait.until(
            lambda d: "IT221 Channel" in d.find_element(By.TAG_NAME, "body").text
            and str(user_and_channel["channel"]["id"]) in d.find_element(By.TAG_NAME, "body").text
        )
        text = browser.find_element(By.TAG_NAME, "body").text
        assert "IT221 Channel" in text
        assert str(user_and_channel["channel"]["id"]) in text
    finally:
        browser.quit()

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.smtp, pytest.mark.heavy]
