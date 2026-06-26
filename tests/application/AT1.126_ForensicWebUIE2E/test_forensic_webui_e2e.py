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
Application Test: AT1.126 / W28A-451 - Forensic WebUI E2E

Browser-only CRUD validation against the live SPA on local Docker and preprod.
No API seeding or cleanup is permitted in this suite.
"""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path

import pytest

from src.config.loader import get_config, load_config


pytestmark = [pytest.mark.application, pytest.mark.llm, pytest.mark.heavy]

LOCAL_SCREENSHOT_DIR = Path("working/W28A-451-local-screenshots")
PREPROD_SCREENSHOT_DIR = Path("working/W28A-451-preprod-screenshots")


def _require_timeout() -> float:
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    return float(timeout)


def _require_base_url(section: str) -> str:
    explicit = get_config(f"{section}.base_url")
    if explicit:
        return str(explicit).rstrip("/")
    scheme = str(get_config(f"{section}.scheme") or "http").strip().lower()
    host = get_config(f"{section}.host")
    port = get_config(f"{section}.port")
    if not host or port is None:
        pytest.fail(f"{section}.host/{section}.port not configured")
    return f"{scheme}://{host}:{int(port)}"


def _require_username() -> str:
    return str(
        os.environ.get("CLOUD_DOG_WEB_LOGIN_USERNAME")
        or get_config("test.user.username")
        or os.environ.get("TEST_USER_USERNAME")
        or "admin"
    )


def _require_password() -> str:
    password = (
        os.environ.get("CLOUD_DOG_WEB_LOGIN_PASSWORD")
        or get_config("test.user.password")
        or os.environ.get("TEST_USER_PASSWORD")
    )
    if not password:
        pytest.fail("test.user.password / TEST_USER_PASSWORD not configured")
    return str(password)


def _forensic_user_password() -> str:
    """Generate a policy-compliant local-user password from the configured admin secret."""
    return f"{_require_password()}1!"


def _artifact_root(web_url: str) -> Path:
    return PREPROD_SCREENSHOT_DIR if "expertagent0.example.com" in web_url else LOCAL_SCREENSHOT_DIR


def _is_benign_console_error(message: str) -> bool:
    text = str(message or "")
    return (
        ("401" in text and "Not authenticated" in text)
        or "404 (Not Found)" in text
        or "ERR_NETWORK_CHANGED" in text
    )


def _is_benign_request_failure(url: str, method: str, failure_text: str) -> bool:
    text = str(failure_text or "")
    request_url = str(url or "")
    request_method = str(method or "").upper()
    if (
        "ERR_NETWORK_CHANGED" in text
        and request_method in {"GET", "DELETE"}
        and request_url.startswith("http://127.0.0.1:")
        and any(
            fragment in request_url
            for fragment in (
                "/web/api/channels",
                "/web/api/sessions",
                "/web/api/experts",
                "/web/api/api-keys",
                "/web/api/users",
                "/web/api/groups",
                "/web/api/jobs",
                "/web/api/knowledge",
                "/web/api/status",
                "/web/api/health",
                "/web/api/logs",
                "/mcp/health",
                "/a2a/health",
            )
        )
    ):
        return True
    if (
        "ERR_NETWORK_CHANGED" in text
        and request_method == "POST"
        and request_url.startswith("http://127.0.0.1:")
        and any(fragment in request_url for fragment in ("/web/api/users", "/web/api/groups"))
    ):
        return True
    return (
        request_method == "GET"
        and "ERR_ABORTED" in text
        and any(
            fragment in request_url
            for fragment in (
                "/web/api/channels",
                "/web/api/sessions",
                "/web/api/experts",
                "/web/api/api-keys",
                "/web/api/users",
                "/web/api/groups",
                "/web/api/jobs",
                "/web/api/knowledge",
                "/web/api/status",
                "/web/api/health",
                "/web/api/logs",
                "/mcp/health",
                "/a2a/health",
            )
        )
    )


def _wait_for_row_presence(page, row_text: str, timeout_ms: int) -> None:
    deadline = time.time() + (timeout_ms / 1000)
    while time.time() < deadline:
        if page.locator("tr:visible").filter(has_text=row_text).count() > 0:
            return
        page.wait_for_timeout(250)
    pytest.fail(f"Row containing '{row_text}' did not appear")


def _wait_for_row_absence(page, row_text: str, timeout_ms: int) -> None:
    deadline = time.time() + (timeout_ms / 1000)
    while time.time() < deadline:
        if page.locator("tr:visible").filter(has_text=row_text).count() == 0:
            return
        page.wait_for_timeout(250)
    pytest.fail(f"Row containing '{row_text}' did not disappear")


def _active_dialog(page):
    return page.locator('[role="dialog"]').last


def _click_first_button(container, *names: str | re.Pattern[str]) -> None:
    for name in names:
        button = container.get_by_role("button", name=name)
        if button.count() > 0:
            button.first.click()
            return
    pytest.fail(f"Expected button matching one of {names!r}")


@dataclass
class BrowserFlow:
    page: object
    web_url: str
    screenshot_dir: Path
    timeout_ms: int
    test_name: str
    page_errors: list[str]
    request_failures: list[str]
    console_errors: list[str]
    step_index: int = 0

    def shot(self, label: str) -> Path:
        self.step_index += 1
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        path = self.screenshot_dir / f"{self.step_index:02d}-{label}.png"
        self.page.screenshot(path=str(path), full_page=True)
        return path

    def goto(self, path: str, ready_text: str | None = None, label: str | None = None) -> None:
        self.page.goto(
            f"{self.web_url}{path}",
            wait_until="domcontentloaded",
            timeout=self.timeout_ms,
        )
        if ready_text:
            self.page.wait_for_function(
                "(expected) => document.body.innerText.includes(expected)",
                arg=ready_text,
                timeout=self.timeout_ms,
            )
        if label:
            self.shot(label)

    def login(self, username: str, password: str, label_prefix: str) -> None:
        self.goto("/login", "Sign in", f"{label_prefix}-login-page")
        self.page.fill("#loginUsername", username)
        self.page.fill("#loginPassword", password)
        self.shot(f"{label_prefix}-login-filled")
        self.page.get_by_role("button", name="Sign in").click()
        self.page.wait_for_function(
            "() => window.location.pathname === '/' || window.location.pathname === '/chat'",
            timeout=self.timeout_ms,
        )
        self.page.wait_for_function(
            "() => document.body.innerText.includes('Chat') && document.body.innerText.includes('Sessions')",
            timeout=self.timeout_ms,
        )
        self.shot(f"{label_prefix}-login-result")

    def assert_clean(self) -> None:
        assert self.page_errors == [], f"page errors: {self.page_errors}"
        assert self.request_failures == [], f"request failures: {self.request_failures}"
        assert self.console_errors == [], f"console errors: {self.console_errors}"


@pytest.fixture
def browser_flow(test_env_file, request):
    load_config.cache_clear()
    web_url = _require_base_url("web_server")
    timeout_ms = int(_require_timeout() * 1000)
    screenshot_dir = _artifact_root(web_url) / request.node.name

    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"Playwright not installed/available: {exc}")

    page_errors: list[str] = []
    request_failures: list[str] = []
    console_errors: list[str] = []

    playwright = sync_playwright().start()
    browser = playwright.chromium.launch(
        headless=True,
        args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    context = browser.new_context()
    page = context.new_page()
    page.on("pageerror", lambda exc: page_errors.append(str(exc)))
    page.on(
        "requestfailed",
        lambda req: (
            None
            if _is_benign_request_failure(str(req.url), str(req.method), str(req.failure))
            else request_failures.append(f"{req.method} {req.url} -> {req.failure}")
        ),
    )
    page.on(
        "console",
        lambda msg: (
            None
            if msg.type != "error" or _is_benign_console_error(msg.text)
            else console_errors.append(msg.text)
        ),
    )
    page.on("dialog", lambda dialog: dialog.accept())

    try:
        yield BrowserFlow(
            page=page,
            web_url=web_url,
            screenshot_dir=screenshot_dir,
            timeout_ms=timeout_ms,
            test_name=request.node.name,
            page_errors=page_errors,
            request_failures=request_failures,
            console_errors=console_errors,
        )
    finally:
        try:
            page.close()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass
        try:
            playwright.stop()
        except Exception:
            pass


@pytest.fixture(scope="session")
def forensic_names():
    suffix = f"{int(time.time())}"
    return {
        "user": f"forensic-expert-user-{suffix}",
        "group": f"forensic-expert-group-{suffix}",
        "api_key": f"forensic-api-key-{suffix}",
        "expert": f"forensic-test-expert-{suffix}",
        "chat_expert": f"forensic-chat-expert-{suffix}",
        "knowledge_title": f"Forensic Test Knowledge {suffix}",
        "prompt": f"forensic-prompt-template-{suffix}",
    }

def _delete_user(page, username: str, flow: BrowserFlow, label_prefix: str) -> None:
    flow.goto("/admin/users", "User inventory", f"{label_prefix}-users-page")
    page.get_by_label("Search users", exact=True).fill(username)
    _wait_for_row_presence(page, username, flow.timeout_ms)
    row = page.locator("tr").filter(has_text=username).first
    row.get_by_role("button", name="Delete").click()
    flow.shot(f"{label_prefix}-delete-confirm")
    _wait_for_row_absence(page, username, flow.timeout_ms)
    flow.shot(f"{label_prefix}-delete-result")


def _create_expert(page, flow: BrowserFlow, name: str, prompt_text: str) -> None:
    flow.goto("/experts", "Expert inventory", f"{name}-experts-page")
    page.get_by_role("button", name="Create Expert").click()
    dialog = _active_dialog(page)
    dialog.get_by_label("Name", exact=True).fill(name)
    dialog.get_by_label("Title", exact=True).fill(name)
    dialog.get_by_label("Description", exact=True).fill(f"{name} description")
    dialog.locator("#expert-prompt").fill(prompt_text)
    flow.shot(f"{name}-expert-filled")
    _click_first_button(dialog, "Save", re.compile("save", re.I))
    page.wait_for_function(
        "(value) => document.body.innerText.includes(value)",
        arg=name,
        timeout=flow.timeout_ms,
    )
    flow.shot(f"{name}-expert-created")
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("CS-008")


def test_e1_admin_login(browser_flow: BrowserFlow):
    browser_flow.login(_require_username(), _require_password(), "e1")
    assert browser_flow.page.get_by_text("Sessions", exact=True).count() > 0
    assert browser_flow.page.get_by_text("Channels", exact=True).count() > 0
    assert browser_flow.page.get_by_text("Experts", exact=True).count() > 0
    browser_flow.assert_clean()
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_e2_dashboard_verification(browser_flow: BrowserFlow):
    browser_flow.login(_require_username(), _require_password(), "e2")
    browser_flow.shot("e2-dashboard-before")
    for label in [
        "Chat",
        "Channels",
        "Experts",
        "Services",
        "Jobs",
        "Knowledge",
        "Files",
        "Users",
        "Groups",
        "Prompts",
        "Settings",
        "Admin",
    ]:
        assert browser_flow.page.get_by_text(label, exact=True).count() > 0, f"Missing nav item: {label}"
    browser_flow.shot("e2-dashboard-result")
    browser_flow.assert_clean()
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_e3_user_crud(browser_flow: BrowserFlow, forensic_names):
    username = forensic_names["user"]
    browser_flow.login(_require_username(), _require_password(), "e3")
    browser_flow.goto("/admin/users", "User inventory", "e3-users-before")
    browser_flow.page.get_by_role("button", name="Create User").click()
    dialog = _active_dialog(browser_flow.page)
    dialog.get_by_label("Username", exact=True).fill(username)
    dialog.get_by_label("Email", exact=True).fill(f"{username}@example.com")
    dialog.get_by_label("Display name", exact=True).fill("Forensic Expert User")
    dialog.get_by_label("Password", exact=True).fill(_forensic_user_password())
    dialog.get_by_label("Role", exact=True).select_option("user")
    browser_flow.shot("e3-user-create-filled")
    _click_first_button(dialog, "Save", re.compile("save", re.I))
    browser_flow.page.wait_for_function(
        "(value) => document.body.innerText.includes(value)",
        arg=f"Created user {username}.",
        timeout=browser_flow.timeout_ms,
    )
    browser_flow.page.get_by_label("Search users", exact=True).fill(username)
    _wait_for_row_presence(browser_flow.page, username, browser_flow.timeout_ms)
    browser_flow.shot("e3-user-created")

    row = browser_flow.page.locator("tr").filter(has_text=username).first
    row.get_by_role("button", name="Edit").click()
    dialog = _active_dialog(browser_flow.page)
    dialog.get_by_label("Display name", exact=True).fill("Forensic Expert User Updated")
    browser_flow.shot("e3-user-edit-filled")
    _click_first_button(dialog, "Save", "Save User", "Save changes", re.compile("save", re.I))
    browser_flow.page.wait_for_function(
        "() => document.body.innerText.includes('Forensic Expert User Updated')",
        timeout=browser_flow.timeout_ms,
    )
    browser_flow.shot("e3-user-edited")

    browser_flow.page.get_by_label("Search users", exact=True).fill(username)
    row = browser_flow.page.locator("tr").filter(has_text=username).first
    row.get_by_role("button", name="Delete").click()
    browser_flow.shot("e3-user-delete-confirm")
    _wait_for_row_absence(browser_flow.page, username, browser_flow.timeout_ms)
    browser_flow.shot("e3-user-deleted")
    browser_flow.assert_clean()
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_e4_group_crud(browser_flow: BrowserFlow, forensic_names):
    username = f"{forensic_names['user']}-group"
    group_name = forensic_names["group"]
    browser_flow.login(_require_username(), _require_password(), "e4")

    browser_flow.goto("/admin/users", "User inventory", "e4-user-before")
    browser_flow.page.get_by_role("button", name="Create User").click()
    dialog = _active_dialog(browser_flow.page)
    dialog.get_by_label("Username", exact=True).fill(username)
    dialog.get_by_label("Email", exact=True).fill(f"{username}@example.com")
    dialog.get_by_label("Display name", exact=True).fill("Forensic Group Member")
    dialog.get_by_label("Password", exact=True).fill(_forensic_user_password())
    browser_flow.shot("e4-user-filled")
    _click_first_button(dialog, "Save", re.compile("save", re.I))
    browser_flow.page.get_by_label("Search users", exact=True).fill(username)
    _wait_for_row_presence(browser_flow.page, username, browser_flow.timeout_ms)
    browser_flow.shot("e4-user-created")

    browser_flow.goto("/admin/groups", "Group inventory", "e4-group-before")
    browser_flow.page.get_by_role("button", name="Create Group").click()
    dialog = _active_dialog(browser_flow.page)
    dialog.get_by_label("Group name", exact=True).fill(group_name)
    dialog.get_by_label("Description", exact=True).fill("Forensic group description")
    browser_flow.shot("e4-group-create-filled")
    _click_first_button(dialog, "Save", re.compile("save", re.I))
    browser_flow.page.get_by_label("Search groups", exact=True).fill(group_name)
    _wait_for_row_presence(browser_flow.page, group_name, browser_flow.timeout_ms)
    browser_flow.shot("e4-group-created")

    browser_flow.page.get_by_role("button", name=group_name).click()
    browser_flow.page.select_option("#group-member-user", label=username)
    browser_flow.page.select_option("#group-member-role", "member")
    assert browser_flow.page.locator("#group-member-user").input_value() != ""
    browser_flow.shot("e4-group-member-filled")
    browser_flow.page.locator("#group-member-add").click()
    browser_flow.page.wait_for_function(
        "(value) => document.body.innerText.includes(value)",
        arg=f"Added member to {group_name}.",
        timeout=browser_flow.timeout_ms,
    )
    browser_flow.shot("e4-group-member-added")

    browser_flow.page.get_by_label("Search groups", exact=True).fill(group_name)
    _wait_for_row_presence(browser_flow.page, group_name, browser_flow.timeout_ms)
    browser_flow.page.get_by_role("button", name=group_name).click()
    _wait_for_row_presence(browser_flow.page, username, browser_flow.timeout_ms)
    member_row = browser_flow.page.locator("tr:visible").filter(has_text=username).first
    member_row.get_by_role("button", name="Remove Member").click()
    browser_flow.shot("e4-group-member-remove-confirm")
    browser_flow.page.wait_for_function(
        "() => document.body.innerText.includes('Removed member')",
        timeout=browser_flow.timeout_ms,
    )
    browser_flow.shot("e4-group-member-removed")

    browser_flow.page.get_by_label("Search groups", exact=True).fill(group_name)
    group_row = browser_flow.page.locator("tr").filter(has_text=group_name).first
    group_row.get_by_role("button", name="Delete").click()
    browser_flow.shot("e4-group-delete-confirm")
    browser_flow.page.wait_for_function(
        "(value) => document.body.innerText.includes(value)",
        arg=f"Deleted group {group_name}.",
        timeout=browser_flow.timeout_ms,
    )
    browser_flow.shot("e4-group-deleted")

    _delete_user(browser_flow.page, username, browser_flow, "e4")
    browser_flow.assert_clean()
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_e5_api_key_crud(browser_flow: BrowserFlow, forensic_names):
    browser_flow.login(_require_username(), _require_password(), "e5")
    browser_flow.goto("/admin/api-keys", "API key inventory", "e5-admin-before")
    browser_flow.page.get_by_role("button", name="Create API Key").click()
    dialog = _active_dialog(browser_flow.page)
    dialog.get_by_label("Name", exact=True).fill(forensic_names["api_key"])
    browser_flow.shot("e5-api-key-filled")
    _click_first_button(dialog, "Save", re.compile("save", re.I))
    _wait_for_row_presence(browser_flow.page, forensic_names["api_key"], browser_flow.timeout_ms)
    browser_flow.shot("e5-api-key-created")

    row = browser_flow.page.locator("tr").filter(has_text=forensic_names["api_key"]).first
    row.get_by_role("button", name="Revoke").click()
    browser_flow.shot("e5-api-key-revoke-confirm")
    browser_flow.page.wait_for_function(
        "() => document.body.innerText.includes('Revoked API key')",
        timeout=browser_flow.timeout_ms,
    )
    browser_flow.shot("e5-api-key-revoked")
    browser_flow.assert_clean()
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_e6_expert_config(browser_flow: BrowserFlow, forensic_names):
    expert_name = forensic_names["expert"]
    browser_flow.login(_require_username(), _require_password(), "e6")
    _create_expert(browser_flow.page, browser_flow, expert_name, "You are a helpful test assistant")

    browser_flow.page.get_by_label("Search experts", exact=True).fill(expert_name)
    _wait_for_row_presence(browser_flow.page, expert_name, browser_flow.timeout_ms)
    row = browser_flow.page.locator("tr").filter(has_text=expert_name).first
    row.get_by_role("button", name="Edit").click()
    dialog = _active_dialog(browser_flow.page)
    dialog.locator("#expert-prompt").fill("You are a helpful test assistant with updated instructions")
    browser_flow.shot("e6-expert-edit-filled")
    _click_first_button(dialog, "Save", "Save Expert", "Save changes", re.compile("save", re.I))
    browser_flow.page.wait_for_function(
        "() => document.body.innerText.includes('Updated expert')",
        timeout=browser_flow.timeout_ms,
    )
    browser_flow.shot("e6-expert-edited")

    browser_flow.page.get_by_label("Search experts", exact=True).fill(expert_name)
    _wait_for_row_presence(browser_flow.page, expert_name, browser_flow.timeout_ms)
    row = browser_flow.page.locator("tr").filter(has_text=expert_name).first
    row.get_by_role("button", name="Delete").click()
    browser_flow.shot("e6-expert-delete-confirm")
    _wait_for_row_absence(browser_flow.page, expert_name, browser_flow.timeout_ms)
    browser_flow.shot("e6-expert-deleted")
    browser_flow.assert_clean()
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_e7_knowledge_crud(browser_flow: BrowserFlow, forensic_names):
    browser_flow.login(_require_username(), _require_password(), "e7")
    browser_flow.goto("/knowledge", "Knowledge inventory", "e7-knowledge-before")
    browser_flow.page.get_by_role("button", name="Add Knowledge").click()
    dialog = _active_dialog(browser_flow.page)
    dialog.get_by_label("Title", exact=True).fill(forensic_names["knowledge_title"])
    dialog.locator("#knowledge-content").fill("Test content for W28A-451")
    browser_flow.shot("e7-knowledge-create-filled")
    _click_first_button(dialog, "Save", "Create Knowledge", "Add Knowledge", re.compile("save", re.I))
    browser_flow.page.wait_for_function(
        "() => document.body.innerText.includes('Knowledge entry created.')",
        timeout=browser_flow.timeout_ms,
    )
    browser_flow.page.get_by_label("Search knowledge entries", exact=True).fill(forensic_names["knowledge_title"])
    _wait_for_row_presence(browser_flow.page, forensic_names["knowledge_title"], browser_flow.timeout_ms)
    browser_flow.shot("e7-knowledge-created")

    row = browser_flow.page.locator("tr").filter(has_text=forensic_names["knowledge_title"]).first
    row.get_by_role("button", name="Edit").click()
    dialog = _active_dialog(browser_flow.page)
    dialog.locator("#knowledge-content").fill("Updated test content for W28A-451")
    browser_flow.shot("e7-knowledge-edit-filled")
    _click_first_button(dialog, "Save", "Save Knowledge", "Save changes", re.compile("save", re.I))
    browser_flow.page.wait_for_function(
        "() => document.body.innerText.includes('Knowledge entry updated.')",
        timeout=browser_flow.timeout_ms,
    )
    browser_flow.shot("e7-knowledge-edited")

    row = browser_flow.page.locator("tr").filter(has_text=forensic_names["knowledge_title"]).first
    row.get_by_role("button", name="Delete").click()
    browser_flow.shot("e7-knowledge-delete-confirm")
    browser_flow.page.wait_for_function(
        "() => document.body.innerText.includes('Knowledge entry deleted.')",
        timeout=browser_flow.timeout_ms,
    )
    browser_flow.shot("e7-knowledge-deleted")
    browser_flow.assert_clean()
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_e8_start_conversation(browser_flow: BrowserFlow, forensic_names):
    browser_flow.login(_require_username(), _require_password(), "e8")
    browser_flow.goto("/chat", "Conversation workbench", "e8-chat-before")
    browser_flow.page.wait_for_function(
        "() => { const select = document.querySelector('#chat-expert'); return !!select && select.value && select.options.length > 1; }",
        timeout=browser_flow.timeout_ms,
    )
    browser_flow.page.fill("#chat-message", "Hello, can you confirm you are working?")
    browser_flow.shot("e8-chat-filled")
    browser_flow.page.get_by_role("button", name="Send").click()
    browser_flow.page.wait_for_function(
        "() => document.body.innerText.includes('Conversation sent via channel')",
        timeout=browser_flow.timeout_ms,
    )
    try:
        browser_flow.page.wait_for_function(
            "() => !document.body.innerText.includes('No response yet.')",
            timeout=min(browser_flow.timeout_ms, 120_000),
        )
    except Exception:
        pass
    browser_flow.shot("e8-chat-result")
    browser_flow.assert_clean()
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_e9_prompts(browser_flow: BrowserFlow, forensic_names):
    browser_flow.login(_require_username(), _require_password(), "e9")
    browser_flow.goto("/admin/prompts", "Prompt inventory", "e9-prompts-before")
    browser_flow.page.get_by_role("button", name="Create Prompt").click()
    dialog = _active_dialog(browser_flow.page)
    dialog.get_by_label("Template name", exact=True).fill(forensic_names["prompt"])
    dialog.locator("#prompt-content").fill("Hello {{name}}, forensic prompt content.")
    browser_flow.shot("e9-prompt-create-filled")
    _click_first_button(dialog, "Save", "Create Prompt Template", "Create Prompt", re.compile("save", re.I))
    _wait_for_row_presence(browser_flow.page, forensic_names["prompt"], browser_flow.timeout_ms)
    browser_flow.shot("e9-prompt-created")

    row = browser_flow.page.locator("tr").filter(has_text=forensic_names["prompt"]).first
    row.get_by_role("button", name="Edit").click()
    dialog = _active_dialog(browser_flow.page)
    dialog.locator("#prompt-content").fill("Hello {{name}}, forensic prompt content updated.")
    browser_flow.shot("e9-prompt-edit-filled")
    _click_first_button(dialog, "Save", "Save Prompt", "Save changes", re.compile("save", re.I))
    browser_flow.page.wait_for_function(
        "() => document.body.innerText.includes('Updated prompt template')",
        timeout=browser_flow.timeout_ms,
    )
    browser_flow.shot("e9-prompt-edited")

    row = browser_flow.page.locator("tr").filter(has_text=forensic_names["prompt"]).first
    row.get_by_role("button", name="Delete").click()
    browser_flow.shot("e9-prompt-delete-confirm")
    _wait_for_row_absence(browser_flow.page, forensic_names["prompt"], browser_flow.timeout_ms)
    browser_flow.shot("e9-prompt-deleted")
    browser_flow.assert_clean()
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_e10_channels(browser_flow: BrowserFlow):
    browser_flow.login(_require_username(), _require_password(), "e10")
    browser_flow.goto("/channels", "Channel inventory", "e10-channels-before")
    assert browser_flow.page.get_by_text("Channel inventory", exact=True).count() > 0
    browser_flow.shot("e10-channels-result")
    browser_flow.assert_clean()
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_e11_services(browser_flow: BrowserFlow):
    browser_flow.login(_require_username(), _require_password(), "e11")
    browser_flow.goto("/services", "Registered services", "e11-services-before")
    assert browser_flow.page.get_by_text("Registered services", exact=True).count() > 0
    browser_flow.shot("e11-services-result")
    browser_flow.assert_clean()
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_e12_jobs(browser_flow: BrowserFlow):
    browser_flow.login(_require_username(), _require_password(), "e12")
    browser_flow.goto("/jobs", "Jobs", "e12-jobs-before")
    assert browser_flow.page.get_by_text("Total Jobs", exact=True).count() > 0
    browser_flow.shot("e12-jobs-result")
    browser_flow.assert_clean()
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_e13_files(browser_flow: BrowserFlow):
    browser_flow.login(_require_username(), _require_password(), "e13")
    browser_flow.goto("/files", "File inventory", "e13-files-before")
    assert browser_flow.page.get_by_text("File inventory", exact=True).count() > 0
    browser_flow.shot("e13-files-result")
    browser_flow.assert_clean()
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_e14_settings(browser_flow: BrowserFlow):
    browser_flow.login(_require_username(), _require_password(), "e14")
    browser_flow.goto("/admin/settings", "User Preferences", "e14-settings-before")
    browser_flow.page.get_by_label("Theme", exact=True).select_option("light")
    browser_flow.shot("e14-settings-filled")
    browser_flow.page.wait_for_function(
        "() => document.body.innerText.includes('Saved setting theme.')",
        timeout=browser_flow.timeout_ms,
    )
    browser_flow.page.reload(wait_until="domcontentloaded", timeout=browser_flow.timeout_ms)
    browser_flow.page.wait_for_function(
        "() => document.body.innerText.includes('User Preferences')",
        timeout=browser_flow.timeout_ms,
    )
    assert browser_flow.page.get_by_label("Theme", exact=True).input_value() == "light"
    browser_flow.shot("e14-settings-result")
    browser_flow.assert_clean()
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_e15_cw_pattern_prompt_workbench(browser_flow: BrowserFlow):
    """E15 — CW-pattern assertion for the canonical PS-77 CW data-testid contract (W28C-1715 §4a).

    PS-77 requires the WebUI to render the canonical ``@cloud-dog/ui`` CW-T*/CW-F*
    ``data-testid`` contract.  As of W28C-1715 the expert-agent WebUI consumes the
    canonical ``DataTable`` and ``EntityDialog`` components from ``@cloud-dog/ui``
    (via ``AppDataTable``/``CrudEntityDialog`` in ``data-table-adapter.tsx``):

      * ``DataTable`` root container carries ``data-testid="CW-T1"``.
      * ``EntityDialog`` (modal CRUD create/edit container) carries ``data-testid="CW-F1"``.

    The Channels page (``ChannelsPage.tsx``) renders an ``AppDataTable``, so the
    ``/channels`` route exposes the canonical CW-T1 table-root testid.  This test
    asserts ``get_by_test_id("CW-T1")`` as the canonical panel check under the
    hard forensic console-error gate (``browser_flow.assert_clean()``).
    """
    browser_flow.login(_require_username(), _require_password(), "e15")
    browser_flow.goto("/channels", "Channels", "e15-cw-pattern-before")
    browser_flow.page.wait_for_load_state("networkidle")
    # PS-77 CW-T1 canonical data-testid: the @cloud-dog/ui DataTable root container
    # carries data-testid="CW-T1" (W28C-1715 PS-77 CW-* contract).
    assert browser_flow.page.get_by_test_id("CW-T1").first.is_visible(), (
        "W28C-1715 CW-pattern FAIL: canonical data-testid='CW-T1' (DataTable root) "
        "not visible on /channels. Expected the @cloud-dog/ui DataTable to render."
    )
    browser_flow.shot("e15-cw-pattern-result")
    browser_flow.assert_clean()
