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
**************************************************
License: Apache 2.0
Ownership: Cloud Dog
Description: REAL Application Test AT1.35 (extended) - Local auth additional coverage.

Covers:
- Password change flow (requires current password)
- Admin password reset flow
- Token refresh endpoint
- Account disable behaviour (login + bearer access denied once disabled)
- Account lockout after repeated failed logins (config-driven)

Related Requirements: CS1.1, FR1.5
Related Tests: AT1.35
**************************************************
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import uuid
from pathlib import Path

import pytest

from src.config.loader import get_config

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_helpers_common import (
    TestOutputStorage,
    APIClient,
    assert_all_validations_passed,
    build_test_email,
    print_summary_table,
)


def _require_env_file(request: pytest.FixtureRequest) -> str:
    env_file = request.config.getoption("--env")
    if not env_file:
        pytest.fail("--env is REQUIRED (see RULES.md)")
    return env_file


def _run_server_control(
    env_file: str,
    args: list[str],
    env_overrides: dict[str, str] | None = None,
    timeout_s: int = 240,
) -> subprocess.CompletedProcess:
    cmd = ["./server_control.sh", "--env", env_file, *args]
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_s, env=env)


def _admin_client(base_url: str, store: TestOutputStorage) -> APIClient:
    admin_username = get_config("test.user.username")
    admin_password = get_config("test.user.password")
    if not admin_username or not admin_password:
        pytest.fail(
            "test.user.username and test.user.password must be configured for local auth tests"
        )
    admin = APIClient(base_url)
    login = admin.post(
        "/auth/login",
        json={"username": admin_username, "password": admin_password, "expires_in_seconds": 300},
    )
    store.save_operation(
        "admin_login",
        {"username": admin_username},
        {
            "status_code": login.status_code,
            "body": login.json() if login.status_code == 200 else login.text,
        },
    )
    store.save_validation(
        "admin_login_200", {"actual": login.status_code}, passed=(login.status_code == 200)
    )
    token = login.json().get("token") if login.status_code == 200 else None
    store.save_validation("admin_token_present", {"has_token": bool(token)}, passed=bool(token))
    admin.session.headers.update({"Authorization": f"Bearer {token}"})
    return admin
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_35_password_change_and_admin_reset(request: pytest.FixtureRequest):
    env_file = _require_env_file(request)
    store = TestOutputStorage(
        "AT1.35_LocalAuthentication", "test_AT1_35_password_change_and_admin_reset"
    )

    _run_server_control(env_file, ["restart", "api"], timeout_s=240)

    cfg = get_config()
    base_url = f"http://{cfg['api_server']['host']}:{int(cfg['api_server']['port'])}"
    admin = _admin_client(base_url, store)

    suffix = uuid.uuid4().hex[:8]
    username = f"at135_pw_{suffix}"
    old_pw = get_config("test.user.password")
    new_pw = get_config("test.user.password_new")
    if not old_pw or not new_pw:
        pytest.fail("Missing test.user.password/test.user.password_new in --env file")

    # Create user
    resp = admin.post(
        "/users",
        json={
            "username": username,
            "email": build_test_email("at135_pw", suffix),
            "password": old_pw,
            "display_name": "pw",
            "role": "user",
        },
    )
    store.save_operation(
        "create_user",
        {"username": username},
        {
            "status_code": resp.status_code,
            "body": resp.json() if resp.status_code in (200, 201) else resp.text,
        },
    )
    store.save_validation(
        "create_user_200", {"status": resp.status_code}, passed=(resp.status_code in (200, 201))
    )
    user_id = resp.json()["id"]

    # Login as user
    user = APIClient(base_url)
    user.session.headers.pop("X-API-Key", None)
    login = user.post(
        "/auth/login", json={"username": username, "password": old_pw, "expires_in_seconds": 300}
    )
    store.save_operation(
        "user_login_old",
        {"username": username},
        {
            "status_code": login.status_code,
            "body": login.json() if login.status_code == 200 else login.text,
        },
    )
    store.save_validation(
        "user_login_old_200", {"status": login.status_code}, passed=(login.status_code == 200)
    )
    token = login.json()["token"]
    user.session.headers.update({"Authorization": f"Bearer {token}"})

    # Change password (requires current password)
    cp = user.post(
        "/auth/change-password", json={"current_password": old_pw, "new_password": new_pw}
    )
    store.save_operation(
        "change_password",
        {"user": username},
        {"status_code": cp.status_code, "body": cp.json() if cp.status_code == 200 else cp.text},
    )
    store.save_validation(
        "change_password_200", {"status": cp.status_code}, passed=(cp.status_code == 200)
    )

    # Old password should fail
    bad = user.post("/auth/login", json={"username": username, "password": old_pw})
    store.save_operation(
        "login_old_after_change",
        {"username": username},
        {"status_code": bad.status_code, "body": bad.text},
    )
    store.save_validation(
        "old_password_401", {"status": bad.status_code}, passed=(bad.status_code == 401)
    )

    # New password should succeed
    ok = user.post("/auth/login", json={"username": username, "password": new_pw})
    store.save_operation(
        "login_new_after_change",
        {"username": username},
        {"status_code": ok.status_code, "body": ok.json() if ok.status_code == 200 else ok.text},
    )
    store.save_validation(
        "new_password_200", {"status": ok.status_code}, passed=(ok.status_code == 200)
    )

    # Admin reset password
    reset_pw = get_config("test.user.password_reset")
    if not reset_pw:
        pytest.fail("Missing test.user.password_reset in --env file")
    rr = admin.post(
        "/auth/admin-reset-password", json={"user_id": user_id, "new_password": reset_pw}
    )
    store.save_operation(
        "admin_reset_password",
        {"user_id": user_id},
        {"status_code": rr.status_code, "body": rr.json() if rr.status_code == 200 else rr.text},
    )
    store.save_validation(
        "admin_reset_200", {"status": rr.status_code}, passed=(rr.status_code == 200)
    )

    # New password (after reset) works
    ok2 = user.post("/auth/login", json={"username": username, "password": reset_pw})
    store.save_operation(
        "login_after_admin_reset",
        {"username": username},
        {
            "status_code": ok2.status_code,
            "body": ok2.json() if ok2.status_code == 200 else ok2.text,
        },
    )
    store.save_validation(
        "reset_password_200", {"status": ok2.status_code}, passed=(ok2.status_code == 200)
    )

    print_summary_table(store)
    assert_all_validations_passed(store)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_35_token_refresh_and_disable_and_lockout(request: pytest.FixtureRequest):
    env_file = _require_env_file(request)
    store = TestOutputStorage(
        "AT1.35_LocalAuthentication", "test_AT1_35_token_refresh_and_disable_and_lockout"
    )

    cfg = get_config()
    base_url = f"http://{cfg['api_server']['host']}:{int(cfg['api_server']['port'])}"

    # Start server with lockout enabled (tight settings for test)
    overrides = {
        "CLOUD_DOG__EXPERT__AUTH__LOCKOUT_ENABLED": "true",
        "CLOUD_DOG__EXPERT__AUTH__LOCKOUT_MAX_ATTEMPTS": "3",
        "CLOUD_DOG__EXPERT__AUTH__LOCKOUT_WINDOW_SECONDS": "30",
        "CLOUD_DOG__EXPERT__AUTH__LOCKOUT_SECONDS": "2",
    }
    _run_server_control(env_file, ["stop", "api"], timeout_s=180)
    start = _run_server_control(env_file, ["start", "api"], env_overrides=overrides, timeout_s=240)
    store.save_operation(
        "start_api_lockout_enabled",
        {"overrides": overrides},
        {"returncode": start.returncode, "stdout": start.stdout, "stderr": start.stderr},
    )
    store.save_validation(
        "start_exitcode_0", {"rc": start.returncode}, passed=(start.returncode == 0)
    )

    admin = _admin_client(base_url, store)

    suffix = uuid.uuid4().hex[:8]
    username = f"at135_lock_{suffix}"
    password = get_config("test.user.password")
    if not password:
        pytest.fail("Missing test.user.password in --env file")
    resp = admin.post(
        "/users",
        json={
            "username": username,
            "email": build_test_email("at135_lock", suffix),
            "password": password,
            "display_name": "lock",
            "role": "user",
        },
    )
    store.save_operation(
        "create_user",
        {"username": username},
        {
            "status_code": resp.status_code,
            "body": resp.json() if resp.status_code in (200, 201) else resp.text,
        },
    )
    store.save_validation(
        "create_user_200", {"status": resp.status_code}, passed=(resp.status_code in (200, 201))
    )
    user_id = resp.json()["id"]

    # Token refresh
    user = APIClient(base_url)
    user.session.headers.pop("X-API-Key", None)
    login = user.post(
        "/auth/login", json={"username": username, "password": password, "expires_in_seconds": 60}
    )
    store.save_operation(
        "user_login",
        {"username": username},
        {
            "status_code": login.status_code,
            "body": login.json() if login.status_code == 200 else login.text,
        },
    )
    store.save_validation(
        "user_login_200", {"status": login.status_code}, passed=(login.status_code == 200)
    )
    token = login.json()["token"]
    refresh = user.post("/auth/refresh", json={"token": token})
    store.save_operation(
        "token_refresh",
        {},
        {
            "status_code": refresh.status_code,
            "body": refresh.json() if refresh.status_code == 200 else refresh.text,
        },
    )
    store.save_validation(
        "refresh_200", {"status": refresh.status_code}, passed=(refresh.status_code == 200)
    )
    new_token = refresh.json().get("token")
    store.save_validation("new_token_present", {"has": bool(new_token)}, passed=bool(new_token))

    # Disable account -> subsequent Bearer use should fail (401)
    user.session.headers.update({"Authorization": f"Bearer {new_token}"})
    ok = user.get(f"/users/{user_id}")
    store.save_operation(
        "bearer_access_before_disable",
        {"path": f"/users/{user_id}"},
        {"status_code": ok.status_code, "body": ok.json() if ok.status_code == 200 else ok.text},
    )
    store.save_validation(
        "bearer_before_disable_200", {"status": ok.status_code}, passed=(ok.status_code == 200)
    )

    dis = admin.put(f"/users/{user_id}", json={"enabled": False})
    store.save_operation(
        "admin_disable_user",
        {"user_id": user_id},
        {
            "status_code": dis.status_code,
            "body": dis.json() if dis.status_code == 200 else dis.text,
        },
    )
    store.save_validation(
        "disable_200", {"status": dis.status_code}, passed=(dis.status_code == 200)
    )

    denied = user.get(f"/users/{user_id}")
    store.save_operation(
        "bearer_access_after_disable",
        {"path": f"/users/{user_id}"},
        {"status_code": denied.status_code, "body": denied.text},
    )
    store.save_validation(
        "bearer_after_disable_401",
        {"status": denied.status_code},
        passed=(denied.status_code == 401),
    )

    # Lockout behaviour (re-enable first so login attempts happen on enabled user)
    ren = admin.put(f"/users/{user_id}", json={"enabled": True})
    store.save_operation(
        "admin_reenable_user",
        {"user_id": user_id},
        {
            "status_code": ren.status_code,
            "body": ren.json() if ren.status_code == 200 else ren.text,
        },
    )
    store.save_validation(
        "reenable_200", {"status": ren.status_code}, passed=(ren.status_code == 200)
    )

    wrong_password = get_config("test.user.password_weak")
    if not wrong_password:
        pytest.fail("test.user.password_weak must be configured for invalid login tests")

    for i in range(3):
        bad = user.post("/auth/login", json={"username": username, "password": wrong_password})
        store.save_operation(
            f"bad_login_{i + 1}",
            {"username": username},
            {"status_code": bad.status_code, "body": bad.text},
        )
        store.save_validation(
            f"bad_login_{i + 1}_401", {"status": bad.status_code}, passed=(bad.status_code == 401)
        )

    locked = user.post("/auth/login", json={"username": username, "password": wrong_password})
    store.save_operation(
        "login_while_locked",
        {"username": username},
        {"status_code": locked.status_code, "body": locked.text},
    )
    store.save_validation(
        "lockout_429", {"status": locked.status_code}, passed=(locked.status_code == 429)
    )

    # Wait for lockout to expire and login succeeds
    time.sleep(2.5)
    ok2 = user.post("/auth/login", json={"username": username, "password": password})
    store.save_operation(
        "login_after_lockout_expires",
        {"username": username},
        {
            "status_code": ok2.status_code,
            "body": ok2.json() if ok2.status_code == 200 else ok2.text,
        },
    )
    store.save_validation(
        "login_after_lockout_200", {"status": ok2.status_code}, passed=(ok2.status_code == 200)
    )

    # Restore baseline server
    _run_server_control(env_file, ["restart", "api"], timeout_s=240)

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

