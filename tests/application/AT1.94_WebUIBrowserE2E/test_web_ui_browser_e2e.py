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
Application Test: AT1.94 - Web UI Browser E2E

License: Apache 2.0
Ownership: Cloud Dog
Description: Real browser-driven Web UI critical-flow coverage against the
current SPA routes (dashboard, channels, chat, files, prompts, knowledge).

Related Requirements: FR1.8, FR1.21, FR1.43
# Covers: FR1.35, FR1.36
Related Tasks: T124, T128, T131
Related Architecture: CC1.1.2, AI1.4
Related Tests: AT1.94
"""

import base64
import uuid

import pytest
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from tests.browser_helpers import resolve_chrome_binary
from src.config.loader import get_config, load_config


pytestmark = pytest.mark.application


def _ensure_strong_password(raw: str | None) -> str:
    candidate = str(raw or "").strip()
    if (
        len(candidate) >= 8
        and any(c.islower() for c in candidate)
        and any(c.isupper() for c in candidate)
        and any(c.isdigit() for c in candidate)
    ):
        return candidate
    return "StrongPass1!"


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
    if scheme not in {"http", "https"}:
        pytest.fail(f"{section}.scheme must be http or https")
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
    pytest.fail(f"Server not healthy at {base_url}{path}. last_error={last_error}")


def _body_text(driver) -> str:
    return driver.find_element(By.TAG_NAME, "body").text


def _goto(driver, web_url: str, path: str, ready_text: str, timeout: int = 20) -> None:
    driver.get(f"{web_url}{path}")
    WebDriverWait(driver, timeout).until(lambda d: ready_text in _body_text(d))


def _search(driver, aria_label: str, value: str) -> None:
    field = driver.find_element(By.CSS_SELECTOR, f"[aria-label='{aria_label}']")
    field.clear()
    field.send_keys(value)


def _row_with_text(driver, text: str, timeout: int = 20):
    quoted = repr(text)
    return WebDriverWait(driver, timeout).until(
        lambda d: d.find_element(By.XPATH, f"//tr[contains(normalize-space(.), {quoted})]")
    )


def _click_row_action(row, label: str) -> None:
    row.find_element(By.XPATH, f".//button[normalize-space()='{label}']").click()


def _select_chat_expert(driver, expert: dict[str, object]) -> None:
    def _loaded_select(d):
        select = Select(d.find_element(By.ID, "chat-expert"))
        visible_labels = [
            option.text.strip() for option in select.options if option.text and option.text.strip()
        ]
        return (select, visible_labels) if len(visible_labels) > 1 else False

    select, visible_labels = WebDriverWait(driver, 30).until(_loaded_select)
    for candidate in (expert.get("name"), expert.get("title")):
        label = str(candidate or "").strip()
        if label and label in visible_labels:
            select.select_by_visible_text(label)
            return
    pytest.fail(f"Chat expert option not found. expected one of name/title in {visible_labels!r}")


def _accept_alert(driver, timeout: int = 20) -> None:
    WebDriverWait(driver, timeout).until(EC.alert_is_present())
    driver.switch_to.alert.accept()


def _latest_response_text(driver) -> str:
    return driver.find_element(
        By.XPATH,
        "//h3[normalize-space()='Latest response']/ancestor::div[contains(@class,'rounded-xl')][1]//p[contains(@class,'whitespace-pre-wrap')]",
    ).text.strip()


def _login(driver, web_url: str, username: str, password: str, timeout: int = 20) -> None:
    wait = WebDriverWait(driver, timeout)
    driver.delete_all_cookies()
    driver.get(f"{web_url}/login")
    wait.until(EC.presence_of_element_located((By.ID, "loginUsername")))
    driver.find_element(By.ID, "loginUsername").clear()
    driver.find_element(By.ID, "loginUsername").send_keys(username)
    driver.find_element(By.ID, "loginPassword").clear()
    driver.find_element(By.ID, "loginPassword").send_keys(password)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    wait.until(lambda d: "/login" not in d.current_url)
    wait.until(
        lambda d: "Sessions" in _body_text(d)
        and "Channels" in _body_text(d)
        and "Experts" in _body_text(d)
    )


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

    _wait_for_health(api, api_url, "/health")
    _wait_for_health(api, web_url, "/health")

    return {
        "api": api,
        "api_url": api_url,
        "web_url": web_url,
        "api_key": str(api_key),
        "timeout": timeout,
    }


@pytest.fixture
def test_entities(clients):
    api = clients["api"]
    api_url = clients["api_url"]
    timeout = api.timeout_seconds
    unique = uuid.uuid4().hex[:8]

    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = _ensure_strong_password(get_config("test.user.password"))
    if not base_username or not base_email or not password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in config")
    if "@" not in str(base_email):
        pytest.fail("test.user.email must include a domain")
    domain = str(base_email).split("@", 1)[1]

    user_response = api.post(
        f"{api_url}/users",
        json={
            "username": f"{base_username}_at194_{unique}",
            "email": f"at194_{unique}@{domain}",
            "password": str(password),
            "display_name": f"AT1.94 User {unique}",
            "role": "admin",
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
            "name": f"at194_expert_{unique}",
            "title": f"AT1.94 Expert Alpha Beta {unique}",
            "description": f"Supports browser-driven web UI E2E validation token {unique}.",
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
            "name": f"AT194 Channel {unique}",
            "expert_config_id": int(expert["id"]),
            "description": f"AT1.94 browser E2E channel {unique}",
            "enabled": True,
        },
        timeout=timeout,
    )
    assert channel_response.status_code == 200, channel_response.text
    channel = channel_response.json()

    yield {"user": user, "user_password": str(password), "expert": expert, "channel": channel}

    api.delete(f"{api_url}/channels/{channel['id']}", timeout=timeout)
    api.delete(f"{api_url}/experts/{expert['id']}", timeout=timeout)
    api.delete(f"{api_url}/users/{user['id']}", timeout=timeout)


@pytest.fixture
def browser(clients, test_entities):
    options = Options()
    options.binary_location = resolve_chrome_binary()
    options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--window-size=1440,1080")

    driver = webdriver.Chrome(options=options)
    try:
        _login(
            driver,
            clients["web_url"],
            test_entities["user"]["username"],
            test_entities["user_password"],
            timeout=int(max(10, clients["timeout"])),
        )
        yield driver
    finally:
        driver.quit()
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_browser_dashboard_navigation_contract(browser, clients):
    _goto(browser, clients["web_url"], "/", "Dashboard")
    assert "Sessions" in _body_text(browser)
    _goto(browser, clients["web_url"], "/channels", "Channel inventory")
    _goto(browser, clients["web_url"], "/testing", "Testing workbench")
    _goto(browser, clients["web_url"], "/services", "Registered services")
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_browser_channels_panel_lists_created_channel(browser, clients, test_entities):
    _goto(browser, clients["web_url"], "/channels", "Channel inventory")
    _search(browser, "Search channels", test_entities["channel"]["name"])
    _row_with_text(browser, test_entities["channel"]["name"])
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_browser_chat_round_trip_no_validation_error(browser, clients, test_entities):
    _goto(browser, clients["web_url"], "/chat", "Conversation workbench")
    _select_chat_expert(browser, test_entities["expert"])
    message = f"AT194 browser chat token {uuid.uuid4().hex[:6]}"
    chat_input = browser.find_element(By.ID, "chat-message")
    chat_input.clear()
    chat_input.send_keys(message)
    browser.find_element(By.XPATH, "//button[normalize-space()='Send']").click()
    WebDriverWait(browser, 120).until(
        lambda d: _latest_response_text(d) not in {"", "No response yet."}
    )
    assert not browser.find_elements(
        By.XPATH,
        "//*[contains(normalize-space(.), 'user_id is required')]",
    )
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_browser_chat_session_rejoin_loads_prior_messages(browser, clients, test_entities):
    _goto(browser, clients["web_url"], "/chat", "Conversation workbench")
    _select_chat_expert(browser, test_entities["expert"])
    message = f"AT194 rejoin token {uuid.uuid4().hex[:6]}"
    chat_input = browser.find_element(By.ID, "chat-message")
    chat_input.clear()
    chat_input.send_keys(message)
    browser.find_element(By.XPATH, "//button[normalize-space()='Send']").click()
    WebDriverWait(browser, 120).until(
        lambda d: _latest_response_text(d) not in {"", "No response yet."}
    )
    browser.find_element(By.XPATH, "//button[normalize-space()='View Timeline']").click()
    WebDriverWait(browser, 30).until(
        lambda d: d.find_elements(By.XPATH, f"//p[contains(normalize-space(.), {message!r})]")
    )
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_browser_files_upload_lists_row_and_download_via_api_round_trip(browser, clients):
    api = clients["api"]
    api_url = clients["api_url"]
    timeout = api.timeout_seconds
    unique = uuid.uuid4().hex[:8]
    token = f"AT194_FILE_{unique}"
    content = f"AT1.94 file upload token {token}\n"
    filename = f"at194_{unique}.txt"
    file_id = None

    try:
        created = api.post(
            f"{api_url}/files/upload_base64",
            json={
                "filename": filename,
                "content_base64": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "metadata": {"origin": "at194"},
            },
            timeout=timeout,
        )
        assert created.status_code == 200, created.text
        file_id = int(created.json()["file"]["id"])

        _goto(browser, clients["web_url"], "/files", "File inventory")
        _search(browser, "Search files", filename)
        row = _row_with_text(browser, filename)
        _click_row_action(row, "Metadata")
        WebDriverWait(browser, 20).until(lambda d: filename in _body_text(d))

        downloaded = api.get(f"{api_url}/files/{file_id}/download", timeout=timeout)
        assert downloaded.status_code == 200, downloaded.text
        assert downloaded.content.decode("utf-8") == content
    finally:
        if file_id:
            api.delete(f"{api_url}/files/{file_id}", timeout=timeout)
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_browser_files_bulk_delete_selected_rows(browser, clients):
    api = clients["api"]
    api_url = clients["api_url"]
    timeout = api.timeout_seconds
    unique = uuid.uuid4().hex[:8]
    file_ids: list[int] = []

    try:
        for idx in range(2):
            created = api.post(
                f"{api_url}/files/upload_base64",
                json={
                    "filename": f"at194_bulk_{unique}_{idx}.txt",
                    "content_base64": base64.b64encode(
                        f"AT1.94 bulk delete token {idx}".encode("utf-8")
                    ).decode("ascii"),
                    "metadata": {"origin": "at194-bulk"},
                },
                timeout=timeout,
            )
            assert created.status_code == 200, created.text
            file_ids.append(int(created.json()["file"]["id"]))

        _goto(browser, clients["web_url"], "/files", "File inventory")
        _search(browser, "Search files", f"at194_bulk_{unique}")
        rows = [
            _row_with_text(browser, f"at194_bulk_{unique}_{idx}.txt")
            for idx in range(2)
        ]
        for row in rows:
            row.find_element(By.CSS_SELECTOR, "input[type='checkbox']").click()
        browser.find_element(By.XPATH, "//button[normalize-space()='Delete Selected']").click()
        _accept_alert(browser)
        WebDriverWait(browser, 20).until(
            lambda d: f"Deleted {len(file_ids)} files." in _body_text(d)
        )
        for fid in file_ids:
            response = api.get(f"{api_url}/files/{fid}", timeout=timeout)
            assert response.status_code == 404
    finally:
        for fid in file_ids:
            api.delete(f"{api_url}/files/{fid}", timeout=timeout)
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_browser_prompts_history_visibility_and_actions(browser, clients):
    api = clients["api"]
    api_url = clients["api_url"]
    timeout = api.timeout_seconds
    unique = uuid.uuid4().hex[:8]
    prompt_name = f"AT194 Prompt {unique}"
    prompt_content = f"AT1.94 prompt history contract details {unique}"
    prompt_id = None

    try:
        created = api.post(
            f"{api_url}/prompts",
            json={"name": prompt_name, "content": prompt_content},
            timeout=timeout,
        )
        assert created.status_code == 200, created.text
        prompt_id = int(created.json()["id"])

        _goto(browser, clients["web_url"], "/prompts", "Prompts", timeout=60)
    finally:
        if prompt_id:
            api.delete(f"{api_url}/prompts/{prompt_id}", timeout=timeout)
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_browser_knowledge_panel_lists_entries_and_supports_delete(browser, clients, test_entities):
    api = clients["api"]
    api_url = clients["api_url"]
    timeout = api.timeout_seconds
    user_id = int(test_entities["user"]["id"])
    token = f"AT194_KNOWLEDGE_{uuid.uuid4().hex[:8]}"

    created = api.post(
        f"{api_url}/knowledge",
        json={
            "knowledge_type": "user",
            "knowledge_id": user_id,
            "content": f"Knowledge content {token}",
            "metadata": {"source": "at194"},
        },
        timeout=timeout,
    )
    assert created.status_code == 200, created.text

    _goto(browser, clients["web_url"], "/knowledge", "Knowledge inventory")
    _search(browser, "Search knowledge entries", token)
    row = _row_with_text(browser, token)
    _click_row_action(row, "Delete")
    _accept_alert(browser)
    WebDriverWait(browser, 20).until(lambda d: token not in _body_text(d))
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_browser_files_panel_can_preview_text_file(browser, clients):
    api = clients["api"]
    api_url = clients["api_url"]
    timeout = api.timeout_seconds
    token = f"AT194_PREVIEW_{uuid.uuid4().hex[:8]}"
    filename = f"at194_preview_{uuid.uuid4().hex[:6]}.txt"

    created = api.post(
        f"{api_url}/files/upload_base64",
        json={
            "filename": filename,
            "content_base64": base64.b64encode(f"preview token {token}".encode("utf-8")).decode(
                "ascii"
            ),
            "metadata": {"origin": "at194"},
        },
        timeout=timeout,
    )
    assert created.status_code == 200, created.text
    file_id = int(created.json()["file"]["id"])

    try:
        _goto(browser, clients["web_url"], "/files", "File inventory")
        _search(browser, "Search files", filename)
        row = _row_with_text(browser, filename)
        _click_row_action(row, "Metadata")
        WebDriverWait(browser, 20).until(lambda d: filename in _body_text(d))
    finally:
        api.delete(f"{api_url}/files/{file_id}", timeout=timeout)
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_browser_files_ingest_to_user_knowledge_visible_in_knowledge_panel(
    browser, clients, test_entities
):
    api = clients["api"]
    api_url = clients["api_url"]
    timeout = api.timeout_seconds
    user_id = int(test_entities["user"]["id"])
    unique = uuid.uuid4().hex[:8]
    token = f"AT194_INGEST_{unique}"
    filename = f"at194_ingest_{unique}.txt"
    content = f"Ingest token {token}\n"
    file_id = None

    try:
        created = api.post(
            f"{api_url}/files/upload_base64",
            json={
                "filename": filename,
                "content_base64": base64.b64encode(content.encode("utf-8")).decode("ascii"),
                "metadata": {"origin": "at194-ingest"},
            },
            timeout=timeout,
        )
        assert created.status_code == 200, created.text
        file_id = int(created.json()["file"]["id"])

        _goto(browser, clients["web_url"], "/files", "File inventory")
        _search(browser, "Search files", filename)
        row = _row_with_text(browser, filename)
        _click_row_action(row, "Ingest")

        dialog = WebDriverWait(browser, 20).until(
            lambda d: d.find_element(By.XPATH, "//div[@role='dialog']")
        )
        Select(dialog.find_element(By.XPATH, ".//select[@aria-label='Knowledge type']")).select_by_visible_text("user")
        knowledge_id = dialog.find_element(By.XPATH, ".//input[@aria-label='Knowledge ID']")
        knowledge_id.clear()
        knowledge_id.send_keys(str(user_id))
        dialog.find_element(By.XPATH, ".//button[normalize-space()='Save']").click()
        WebDriverWait(browser, 20).until(lambda d: "Ingested" in _body_text(d))

        _goto(browser, clients["web_url"], "/knowledge", "Knowledge inventory")
        _search(browser, "Search knowledge entries", token)
        _row_with_text(browser, token)
    finally:
        if file_id:
            entries = api.get(f"{api_url}/knowledge", timeout=timeout).json().get("entries", [])
            for entry in entries:
                metadata = entry.get("metadata") or {}
                if int(metadata.get("source_file_id", -1)) != int(file_id):
                    continue
                ktype = entry.get("knowledge_type")
                kid = int(entry.get("knowledge_id"))
                eid = entry.get("id")
                api.delete(f"{api_url}/knowledge/{ktype}/{kid}?entry_id={eid}", timeout=timeout)
            api.delete(f"{api_url}/files/{file_id}", timeout=timeout)


# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.llm, pytest.mark.smtp, pytest.mark.heavy]
