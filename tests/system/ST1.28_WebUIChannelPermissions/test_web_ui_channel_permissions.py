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
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from tests.browser_helpers import resolve_chrome_binary
from src.config.loader import get_config, load_config


def _base(section: str) -> str:
    h, p = get_config(f"{section}.host"), get_config(f"{section}.port")
    if not h or p is None:
        pytest.fail(f"{section}.host/{section}.port not configured")
    return f"http://{h}:{int(p)}"


def _create_temp_user(api_url: str, api_key: str, timeout: float) -> tuple[requests.Session, int, str, str]:
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    username_seed = get_config("test.user.username")
    if not base_email or not password or not username_seed:
        pytest.fail("test.user.email/test.user.password/test.user.username not configured")
    if "@" not in str(base_email):
        pytest.fail("test.user.email must include a domain")

    unique = uuid.uuid4().hex[:8]
    domain = str(base_email).split("@", 1)[1]
    username = f"{username_seed}_st128_{unique}"

    api = requests.Session()
    api.headers.update({"X-API-Key": str(api_key)})
    response = api.post(
        f"{api_url}/users",
        json={
            "username": username,
            "email": f"st128_{unique}@{domain}",
            "password": str(password),
            "display_name": f"ST1.28 User {unique}",
        },
        timeout=timeout,
    )
    assert response.status_code == 200, response.text
    return api, int(response.json()["id"]), username, str(password)
@pytest.mark.ST
@pytest.mark.webui
@pytest.mark.req("FR-045")


def test_st128_web_ui_channel_routes_and_auth_contract(test_env_file):
    load_config.cache_clear()
    timeout = float(get_config("test.http_timeout_seconds") or 60)
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")

    web_url = _base("web_server")
    api_url = _base("api_server")

    # Route-level contracts
    ch_page = requests.get(f"{web_url}/channels", timeout=timeout)
    assert ch_page.status_code == 200, ch_page.text

    # API auth boundary (invalid key rejected)
    invalid = requests.get(
        f"{api_url}/sessions", headers={"X-API-Key": "invalid-key"}, timeout=timeout
    )
    assert invalid.status_code == 401, invalid.text

    opts = Options()
    opts.binary_location = resolve_chrome_binary()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")

    browser = webdriver.Chrome(options=opts)
    api_session, user_id, username, password = _create_temp_user(api_url, str(api_key), timeout)
    try:
        web_login = requests.post(
            f"{web_url}/web/auth/login",
            json={"username": username, "password": password},
            timeout=timeout,
        )
        assert web_login.status_code == 200, web_login.text

        browser.get(f"{web_url}/")
        for cookie in web_login.cookies:
            browser.add_cookie(
                {
                    "name": cookie.name,
                    "value": cookie.value,
                    "path": cookie.path or "/",
                }
            )

        browser.get(f"{web_url}/channels")
        WebDriverWait(browser, 20).until(
            lambda d: d.find_element(By.XPATH, "//h1[normalize-space()='Channels']").is_displayed()
        )
        channels_text = browser.find_element(By.TAG_NAME, "body").text
        assert "Error:" not in channels_text
        assert "Channel inventory" in channels_text
    finally:
        browser.quit()
        api_session.delete(f"{api_url}/users/{user_id}", timeout=timeout)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.pure, pytest.mark.slow, pytest.mark.heavy]
