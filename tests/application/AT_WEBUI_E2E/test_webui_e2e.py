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
Application Test: AT1.125 / W28A-408-A - WebUI E2E

Real browser validation of the current Expert Agent WebUI contract against a
live local stack. Uses Playwright with real HTTP setup/cleanup only.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
import requests

from src.config.loader import get_config, load_config


pytestmark = [pytest.mark.application, pytest.mark.llm, pytest.mark.heavy]

SCREENSHOT_DIR = Path("working/W28A-430-screenshots")
ADMIN_USERNAME = "admin"
ADMIN_EMAIL = "admin@example.com"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo[object]):
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


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


def _wait_for_health(session: requests.Session, base_url: str, path: str) -> None:
    timeout = float(getattr(session, "timeout_seconds", 30))
    last_error = None
    for _ in range(40):
        try:
            response = session.get(f"{base_url}{path}", timeout=timeout)
            if response.status_code == 200:
                return
            last_error = f"status={response.status_code} body={response.text[:200]}"
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(0.5)
    pytest.fail(f"Server not healthy at {base_url}{path}. last_error={last_error}")


def _assert_no_browser_failures(page_errors: list[str], request_failures: list[str], console_errors: list[str]) -> None:
    assert page_errors == [], f"page errors: {page_errors}"
    assert request_failures == [], f"request failures: {request_failures}"
    assert console_errors == [], f"console errors: {console_errors}"


def _is_benign_console_error(message: str) -> bool:
    text = str(message or "")
    return (
        ("401" in text and "Unauthorized" in text)
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


def _find_user_by_username(api: requests.Session, api_url: str, username: str, timeout: float) -> dict[str, Any] | None:
    response = api.get(f"{api_url}/users", timeout=timeout)
    assert response.status_code == 200, response.text
    for user in response.json().get("users", []):
        if user.get("username") == username:
            return user
    return None


def _find_group_by_name(api: requests.Session, api_url: str, name: str, timeout: float) -> dict[str, Any] | None:
    response = api.get(f"{api_url}/groups", timeout=timeout)
    assert response.status_code == 200, response.text
    items = response.json().get("items") or response.json().get("groups") or []
    for group in items:
        if group.get("name") == name:
            return group
    return None


def _find_expert_by_name(api: requests.Session, api_url: str, name: str, timeout: float) -> dict[str, Any] | None:
    response = api.get(f"{api_url}/experts", timeout=timeout)
    assert response.status_code == 200, response.text
    for expert in response.json().get("experts", []):
        if expert.get("name") == name:
            return expert
    return None


def _find_channel_by_name(api: requests.Session, api_url: str, name: str, timeout: float) -> dict[str, Any] | None:
    response = api.get(f"{api_url}/channels", timeout=timeout)
    assert response.status_code == 200, response.text
    for channel in response.json().get("channels", []):
        if channel.get("name") == name:
            return channel
    return None


def _find_api_key_by_name(api: requests.Session, api_url: str, user_id: int, name: str, timeout: float) -> dict[str, Any] | None:
    response = api.get(
        f"{api_url}/api-keys",
        params={"user_id": user_id, "include_revoked": "true"},
        timeout=timeout,
    )
    assert response.status_code == 200, response.text
    for api_key in response.json().get("api_keys", []):
        if api_key.get("name") == name:
            return api_key
    return None


def _delete_if_exists(api: requests.Session, url: str, timeout: float) -> None:
    try:
        api.delete(url, timeout=timeout)
    except requests.RequestException:
        pass


class ResourceTracker:
    def __init__(self) -> None:
        self.user_ids: set[int] = set()
        self.group_ids: set[int] = set()
        self.expert_ids: set[int] = set()
        self.channel_ids: set[int] = set()
        self.api_key_ids: set[int] = set()

    def cleanup(self, api: requests.Session, api_url: str, timeout: float) -> None:
        for key_id in sorted(self.api_key_ids, reverse=True):
            _delete_if_exists(api, f"{api_url}/api-keys/{key_id}", timeout)
        for channel_id in sorted(self.channel_ids, reverse=True):
            _delete_if_exists(api, f"{api_url}/channels/{channel_id}", timeout)
        for expert_id in sorted(self.expert_ids, reverse=True):
            _delete_if_exists(api, f"{api_url}/experts/{expert_id}", timeout)
        for group_id in sorted(self.group_ids, reverse=True):
            _delete_if_exists(api, f"{api_url}/groups/{group_id}", timeout)
        for user_id in sorted(self.user_ids, reverse=True):
            if user_id == 1:
                continue
            _delete_if_exists(api, f"{api_url}/users/{user_id}", timeout)


@pytest.fixture
def e2e_context(test_env_file):
    load_config.cache_clear()
    timeout = _require_timeout()
    api_key = get_config("api_server.api_key") or get_config("test.api_key")
    web_password = get_config("test.user.password")
    if not api_key:
        pytest.fail("test.api_key not configured")
    if not web_password:
        pytest.fail("test.user.password not configured")

    api_url = _require_base_url("api_server")
    web_url = _require_base_url("web_server")

    api = requests.Session()
    api.headers.update({"X-API-Key": str(api_key)})
    api.timeout_seconds = timeout

    _wait_for_health(api, api_url, "/health")
    _wait_for_health(api, web_url, "/health")

    existing = _find_user_by_username(api, api_url, ADMIN_USERNAME, timeout)
    if existing is None:
        created = api.post(
            f"{api_url}/users",
            json={
                "username": ADMIN_USERNAME,
                "email": ADMIN_EMAIL,
                "password": str(web_password),
                "display_name": "Admin",
                "role": "admin",
            },
            timeout=timeout,
        )
        assert created.status_code == 200, created.text
        admin_user_id = int(created.json()["id"])
    else:
        admin_user_id = int(existing["id"])
        updated = api.put(
            f"{api_url}/users/{admin_user_id}",
            json={
                "username": ADMIN_USERNAME,
                "email": ADMIN_EMAIL,
                "password": str(web_password),
                "display_name": "Admin",
                "role": "admin",
                "enabled": True,
            },
            timeout=timeout,
        )
        assert updated.status_code == 200, updated.text

    login = requests.post(
        f"{api_url}/auth/login",
        json={"username": ADMIN_USERNAME, "password": str(web_password)},
        timeout=timeout,
    )
    assert login.status_code == 200, login.text

    tracker = ResourceTracker()
    try:
        yield {
            "api": api,
            "api_url": api_url,
            "web_url": web_url,
            "timeout": timeout,
            "admin_username": ADMIN_USERNAME,
            "admin_password": str(web_password),
            "admin_user_id": admin_user_id,
            "tracker": tracker,
        }
    finally:
        tracker.cleanup(api, api_url, timeout)
        api.close()


@pytest.fixture
def browser_page(e2e_context, request):
    try:
        from playwright.sync_api import sync_playwright
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"Playwright not installed/available: {exc}")

    page_errors: list[str] = []
    request_failures: list[str] = []
    console_errors: list[str] = []

    with sync_playwright() as playwright:
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

        page.goto(
            f"{e2e_context['web_url']}/web/auth/login",
            wait_until="domcontentloaded",
            timeout=int(e2e_context["timeout"] * 1000),
        )
        page.wait_for_selector("#loginUsername", timeout=30_000)
        page.fill("#loginUsername", e2e_context["admin_username"])
        page.fill("#loginPassword", e2e_context["admin_password"])
        page.click("button:has-text('Sign in')")
        page.wait_for_function(
            "() => window.location.pathname === '/' || window.location.pathname === '/chat'",
            timeout=30_000,
        )
        page.wait_for_function(
            "() => document.body.innerText.includes('Sessions') && document.body.innerText.includes('Channels') && document.body.innerText.includes('Experts')",
            timeout=30_000,
        )

        yield page, page_errors, request_failures, console_errors

        rep = getattr(request.node, "rep_call", None)
        if rep is not None:
            SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)
            screenshot_path = SCREENSHOT_DIR / f"{request.node.name}.png"
            page.screenshot(path=str(screenshot_path), full_page=True)

        context.close()
        browser.close()


def _goto_route(page, base_url: str, path: str, ready_text: str) -> None:
    page.goto(f"{base_url}{path}", wait_until="domcontentloaded", timeout=30_000)
    page.wait_for_function(
        "(expected) => document.body.innerText.includes(expected)",
        arg=ready_text,
        timeout=30_000,
    )


def _assert_missing_control(page, description: str, selectors: list[str]) -> None:
    for selector in selectors:
        if page.locator(selector).count() > 0:
            return
    pytest.fail(description)
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_t1_admin_login(browser_page):
    page, page_errors, request_failures, console_errors = browser_page
    page.wait_for_function("() => window.location.pathname === '/' || window.location.pathname === '/chat'", timeout=30_000)
    assert page.locator("text=Chat").count() > 0
    cookies = page.context.cookies()
    assert any(cookie["name"] == "expert_web_session" for cookie in cookies)
    _assert_no_browser_failures(page_errors, request_failures, console_errors)
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_t2_user_crud(browser_page, e2e_context):
    page, page_errors, request_failures, console_errors = browser_page
    _goto_route(page, e2e_context["web_url"], "/admin/users", "User inventory")
    _assert_missing_control(
        page,
        "T2 requires WebUI user create/edit/delete controls, but the migrated SPA Users page is read-only.",
        ["text=Create User", "text=Edit", "text=Delete", "button:has-text('Create')"],
    )
    _assert_no_browser_failures(page_errors, request_failures, console_errors)
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_t3_group_crud(browser_page, e2e_context):
    page, page_errors, request_failures, console_errors = browser_page
    _goto_route(page, e2e_context["web_url"], "/admin/groups", "Group inventory")
    _assert_missing_control(
        page,
        "T3 requires WebUI group create/edit/delete controls, but the migrated SPA Groups page is read-only.",
        ["text=Create Group", "text=Edit", "text=Delete", "button:has-text('Create')"],
    )
    _assert_no_browser_failures(page_errors, request_failures, console_errors)
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_t4_api_key_crud(browser_page, e2e_context):
    page, page_errors, request_failures, console_errors = browser_page
    _goto_route(page, e2e_context["web_url"], "/admin/api-keys", "API key inventory")
    _assert_missing_control(
        page,
        "T4 requires WebUI API key create/revoke controls, but the migrated SPA Admin page only exposes a read-only API key inventory.",
        ["text=Create API Key", "text=Rotate", "text=Revoke", "button:has-text('Create')"],
    )
    _assert_no_browser_failures(page_errors, request_failures, console_errors)
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_t5_rbac(browser_page, e2e_context):
    page, page_errors, request_failures, console_errors = browser_page
    _goto_route(page, e2e_context["web_url"], "/admin/groups", "Group contract surface")
    _assert_missing_control(
        page,
        "T5 requires interactive RBAC assignment/removal controls, but the migrated SPA exposes only group inventory and endpoint documentation.",
        ["text=Assign role", "text=Add Member", "text=Remove Member", "select[name='role']"],
    )
    _assert_no_browser_failures(page_errors, request_failures, console_errors)
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_t6_start_conversation(browser_page, e2e_context):
    page, page_errors, request_failures, console_errors = browser_page
    _goto_route(page, e2e_context["web_url"], "/chat", "Send a message")
    _assert_missing_control(
        page,
        "T6 requires an interactive conversation composer, but the migrated SPA Chat page is a read-only contract/status view.",
        ["textarea", "button:has-text('Send')", "input[placeholder*='message']"],
    )
    _assert_no_browser_failures(page_errors, request_failures, console_errors)
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_t7_expert_config_crud(browser_page, e2e_context):
    page, page_errors, request_failures, console_errors = browser_page
    _goto_route(page, e2e_context["web_url"], "/experts", "Expert inventory")
    _assert_missing_control(
        page,
        "T7 requires expert create/edit/delete controls, but the migrated SPA Experts page is read-only.",
        ["text=Create Expert", "text=Edit", "text=Delete", "button:has-text('Create')"],
    )
    _assert_no_browser_failures(page_errors, request_failures, console_errors)
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_t8_user_preferences(browser_page, e2e_context):
    page, page_errors, request_failures, console_errors = browser_page
    _goto_route(page, e2e_context["web_url"], "/admin/settings", "Settings")
    assert page.locator("text=Settings").count() > 0, (
        "T8 requires a user preferences/settings surface, but the migrated SPA does not expose one."
    )
    _assert_no_browser_failures(page_errors, request_failures, console_errors)
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_t9_knowledge_management(browser_page, e2e_context):
    page, page_errors, request_failures, console_errors = browser_page
    _goto_route(page, e2e_context["web_url"], "/knowledge", "Knowledge inventory")
    _assert_missing_control(
        page,
        "T9 requires knowledge create/edit/delete controls, but the migrated SPA Knowledge page is read-only.",
        ["text=Add Knowledge", "text=Edit", "text=Delete", "button:has-text('Create')"],
    )
    _assert_no_browser_failures(page_errors, request_failures, console_errors)
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_t10_group_api_key_combo(browser_page, e2e_context):
    page, page_errors, request_failures, console_errors = browser_page
    _goto_route(page, e2e_context["web_url"], "/admin/api-keys", "API key inventory")
    page.get_by_role("button", name="Create API Key").click()
    page.wait_for_function(
        "() => document.body.innerText.includes('Create API Key') && document.body.innerText.includes('Bind key to group')",
        timeout=30_000,
    )
    _assert_missing_control(
        page,
        "T10 requires a group-to-API-key binding workflow, but the migrated SPA Admin/Groups pages do not expose one.",
        ["text=Bind key to group", "text=Group API key", "input[name='group_id']"],
    )
    _assert_no_browser_failures(page_errors, request_failures, console_errors)
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_t11_system_health(browser_page, e2e_context):
    page, page_errors, request_failures, console_errors = browser_page
    _goto_route(page, e2e_context["web_url"], "/admin", "Operational diagnostics")
    assert page.locator("text=Health status").count() > 0
    assert page.locator("text=Queue depth").count() > 0
    assert page.locator("text=API key inventory").count() > 0
    assert page.locator("text=Service registry").count() > 0
    _assert_no_browser_failures(page_errors, request_failures, console_errors)
@pytest.mark.AT
@pytest.mark.webui
@pytest.mark.req("FR-044")


def test_t12_cw_pattern_prompt_workbench(browser_page, e2e_context):
    """T12 — CW-pattern assertion for the canonical PS-77 CW data-testid contract (W28C-1715 §4a).

    PS-77 requires the WebUI to render the canonical ``@cloud-dog/ui`` CW-T*/CW-F*
    ``data-testid`` contract.  As of W28C-1715 the expert-agent WebUI consumes the
    canonical ``DataTable`` and ``EntityDialog`` components from ``@cloud-dog/ui``
    (via ``AppDataTable``/``CrudEntityDialog`` in ``data-table-adapter.tsx``):

      * ``DataTable`` root container carries ``data-testid="CW-T1"``.
      * ``EntityDialog`` (modal CRUD create/edit container) carries ``data-testid="CW-F1"``.

    The Channels page (``ChannelsPage.tsx``) renders an ``AppDataTable``, so the
    ``/channels`` route exposes the canonical CW-T1 table-root testid.  This test
    asserts ``get_by_test_id("CW-T1")`` as the canonical panel check.  The console-error
    gate is already enforced in T1–T11 via ``_assert_no_browser_failures``.
    """
    page, page_errors, request_failures, console_errors = browser_page
    # Navigate to the Channels page which renders the @cloud-dog/ui DataTable (CW-T1 surface).
    _goto_route(page, e2e_context["web_url"], "/channels", "Channels")
    page.wait_for_load_state("networkidle")
    # PS-77 CW-T1 canonical data-testid: the DataTable root container carries
    # data-testid="CW-T1" (W28C-1715 PS-77 CW-* contract from @cloud-dog/ui).
    assert page.get_by_test_id("CW-T1").first.is_visible(), (
        "W28C-1715 CW-pattern FAIL: canonical data-testid='CW-T1' (DataTable root) "
        "not visible on /channels page. Expected the @cloud-dog/ui DataTable to render."
    )
    _assert_no_browser_failures(page_errors, request_failures, console_errors)
