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
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from tests.browser_helpers import build_headless_chrome_options
from src.config.loader import get_config, load_config


pytestmark = pytest.mark.integration


ROUTES = [
    ("/", "Dashboard"),
    ("/chat", "Chat"),
    ("/channels", "Channels"),
    ("/sessions", "Sessions"),
    ("/experts", "Experts"),
    ("/services", "Services"),
    ("/knowledge", "Knowledge"),
    ("/files", "Files"),
    ("/jobs", "Jobs"),
    ("/admin/users", "Users"),
    ("/admin/groups", "Groups"),
    ("/admin/api-keys", "API Keys"),
    ("/admin/rbac", "RBAC"),
    ("/admin/prompts", "Prompts"),
    ("/admin/monitoring", "Monitoring"),
    ("/admin/settings", "Settings"),
    ("/api-docs", "API Docs"),
    ("/mcp-console", "MCP Console"),
    ("/a2a-console", "A2A Console"),
    ("/testing", "Testing"),
    ("/about", "About"),
]


TITLE_MATCHERS = {
    "/admin/rbac": ("RBAC", "RBAC Management"),
    "/mcp-console": ("MCP Console",),
    "/a2a-console": ("A2A Console",),
}


def _base(section: str) -> str:
    base_url = get_config(f"{section}.base_url")
    if base_url:
        return str(base_url).rstrip("/")
    h, p = get_config(f"{section}.host"), get_config(f"{section}.port")
    if not h or p is None:
        pytest.fail(f"{section}.host/{section}.port not configured")
    return f"http://{h}:{int(p)}"
@pytest.mark.IT
@pytest.mark.webui
@pytest.mark.req("FR-028")


def test_it217_web_ui_complete_panel_and_backing_api_coverage(test_env_file):
    # Covers: FR1.43
    load_config.cache_clear()
    api_key = get_config("test.api_key")
    username = get_config("test.user.username")
    password = get_config("test.user.password")
    timeout = float(get_config("test.http_timeout_seconds") or 60)
    if not api_key or not username or not password:
        pytest.fail("test.api_key/test.user.username/test.user.password not configured")

    api_url = _base("api_server")
    web_url = _base("web_server")

    # Backing APIs used by dashboard panels.
    api = requests.Session()
    api.headers.update({"X-API-Key": str(api_key)})
    for path in [
        "/health",
        "/channels",
        "/experts",
        "/jobs",
        "/knowledge?query=*&collection=default&n_results=1",
        "/users",
        "/groups",
        "/files",
        "/jobs/queue/status",
    ]:
        r = api.get(f"{api_url}{path}", timeout=timeout)
        assert r.status_code in {200, 404}, f"{path} -> {r.status_code}"

    browser = webdriver.Chrome(options=build_headless_chrome_options())
    browser.set_page_load_timeout(60)
    try:
        browser.get(f"{web_url}/")
        wait = WebDriverWait(browser, 60)
        wait.until(EC.presence_of_element_located((By.ID, "loginUsername")))
        browser.find_element(By.ID, "loginUsername").clear()
        browser.find_element(By.ID, "loginUsername").send_keys(str(username))
        browser.find_element(By.ID, "loginPassword").clear()
        browser.find_element(By.ID, "loginPassword").send_keys(str(password))
        browser.find_element(By.XPATH, "//button[normalize-space()='Sign in' or normalize-space()='Sign In']").click()
        wait.until(lambda d: "/login" not in d.current_url)

        for route, heading in ROUTES:
            browser.get(f"{web_url}{route}")
            expected_titles = TITLE_MATCHERS.get(route, (heading,))
            wait.until(
                lambda d, titles=expected_titles: any(
                    title.lower() in d.find_element(By.TAG_NAME, "body").text.lower()
                    for title in titles
                )
            )
    finally:
        browser.quit()

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.pure, pytest.mark.heavy]
