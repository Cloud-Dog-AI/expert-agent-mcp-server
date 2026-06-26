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
Description: REAL Application Test AT1.35 - Local database authentication.

Covers:
- Admin login (local user/pass) and Bearer token use
- Admin creates a local user with a valid password
- New user can login/validate/logout; logout revokes token
- Password policy is enforced on user creation (min length + complexity)

Related Requirements: CS1.1
Related Tasks: T005, T006
Related Architecture: SE1.1
Related Tests: AT1.35
**************************************************
"""

from __future__ import annotations

import subprocess
import sys
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
    env_file: str, args: list[str], timeout_s: int = 240
) -> subprocess.CompletedProcess:
    cmd = ["./server_control.sh", "--env", env_file, *args]
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_s)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-001")


def test_AT1_35_local_auth_end_to_end(request: pytest.FixtureRequest):
    env_file = _require_env_file(request)
    store = TestOutputStorage("AT1.35_LocalAuthentication", "test_AT1_35_local_auth_end_to_end")

    restart = _run_server_control(env_file, ["restart", "api"], timeout_s=240)
    store.save_operation(
        "server_restart_api",
        {"args": ["restart", "api"]},
        {"returncode": restart.returncode, "stdout": restart.stdout, "stderr": restart.stderr},
    )
    store.save_validation(
        "restart_exitcode_0", {"rc": restart.returncode}, passed=(restart.returncode == 0)
    )

    cfg = get_config()
    host = cfg.get("api_server", {}).get("host")
    port = int(cfg.get("api_server", {}).get("port"))
    base_url = f"http://{host}:{port}"

    admin_username = get_config("test.user.username")
    admin_password = get_config("test.user.password")
    if not admin_username or not admin_password:
        pytest.fail(
            "test.user.username and test.user.password must be configured for local auth tests"
        )

    admin = APIClient(base_url)
    login = admin.post("/auth/login", json={"username": admin_username, "password": admin_password})
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
    admin_token = login.json().get("token") if login.status_code == 200 else None
    store.save_validation(
        "admin_token_present", {"has_token": bool(admin_token)}, passed=bool(admin_token)
    )
    admin.session.headers.update({"Authorization": f"Bearer {admin_token}"})

    # Password policy negative case (intentionally weak)
    suffix = uuid.uuid4().hex[:8]
    weak_password = get_config("test.user.password_weak")
    if not weak_password:
        pytest.fail("test.user.password_weak must be configured for weak-password test")
    weak_user_payload = {
        "username": f"at135_weak_{suffix}",
        "email": build_test_email("at135_weak", suffix),
        "password": weak_password,
        "display_name": "weak",
        "role": "user",
    }
    resp = admin.post("/users", json=weak_user_payload)
    store.save_operation(
        "create_user_weak_password",
        weak_user_payload,
        {"status_code": resp.status_code, "body": resp.text},
    )
    store.save_validation(
        "weak_password_rejected_400",
        {"actual": resp.status_code, "expected": 400},
        passed=(resp.status_code == 400),
    )

    # Create a normal local user
    good_password = get_config("test.user.password")
    if not good_password:
        pytest.fail("test.user.password must be configured for good-password test")
    user_payload = {
        "username": f"at135_user_{suffix}",
        "email": build_test_email("at135_user", suffix),
        "password": good_password,
        "display_name": "AT1.35 user",
        "role": "user",
    }
    resp = admin.post("/users", json=user_payload)
    store.save_operation(
        "create_user_good_password",
        user_payload,
        {
            "status_code": resp.status_code,
            "body": resp.json() if resp.status_code in (200, 201) else resp.text,
        },
    )
    store.save_validation(
        "create_user_200", {"actual": resp.status_code}, passed=(resp.status_code in (200, 201))
    )
    user_id = resp.json().get("id") if resp.status_code in (200, 201) else None
    store.save_validation("user_id_present", {"id": user_id}, passed=bool(user_id))

    # Login as the new user
    user_client = APIClient(base_url)
    ulogin = user_client.post(
        "/auth/login",
        json={
            "username": user_payload["username"],
            "password": good_password,
            "expires_in_seconds": 120,
        },
    )
    store.save_operation(
        "user_login",
        {"username": user_payload["username"]},
        {
            "status_code": ulogin.status_code,
            "body": ulogin.json() if ulogin.status_code == 200 else ulogin.text,
        },
    )
    store.save_validation(
        "user_login_200", {"actual": ulogin.status_code}, passed=(ulogin.status_code == 200)
    )
    user_token = ulogin.json().get("token") if ulogin.status_code == 200 else None
    store.save_validation(
        "user_token_present", {"has_token": bool(user_token)}, passed=bool(user_token)
    )

    # Validate token
    v = user_client.get("/auth/validate", params={"token": user_token})
    store.save_operation(
        "user_validate",
        {"token": user_token},
        {"status_code": v.status_code, "body": v.json() if v.status_code == 200 else v.text},
    )
    store.save_validation("validate_200", {"actual": v.status_code}, passed=(v.status_code == 200))
    store.save_validation(
        "validate_true", {"valid": v.json().get("valid")}, passed=(v.json().get("valid") is True)
    )

    # Use Bearer token to access protected endpoint (self access)
    user_client.session.headers.update({"Authorization": f"Bearer {user_token}"})
    r = user_client.get(f"/users/{user_id}")
    store.save_operation(
        "user_get_self",
        {"path": f"/users/{user_id}"},
        {"status_code": r.status_code, "body": r.json() if r.status_code == 200 else r.text},
    )
    store.save_validation(
        "user_get_self_200", {"actual": r.status_code}, passed=(r.status_code == 200)
    )

    # Wrong password rejected
    wrong_password = get_config("test.user.password_weak")
    if not wrong_password:
        pytest.fail("test.user.password_weak must be configured for invalid login tests")
    bad = user_client.post(
        "/auth/login", json={"username": user_payload["username"], "password": wrong_password}
    )
    store.save_operation(
        "user_login_wrong_password",
        {"username": user_payload["username"]},
        {"status_code": bad.status_code, "body": bad.text},
    )
    store.save_validation(
        "wrong_password_401",
        {"actual": bad.status_code, "expected": 401},
        passed=(bad.status_code == 401),
    )

    # Logout revokes token
    out = user_client.post("/auth/logout", json={"token": user_token})
    store.save_operation(
        "user_logout",
        {"token": user_token},
        {
            "status_code": out.status_code,
            "body": out.json() if out.status_code == 200 else out.text,
        },
    )
    store.save_validation(
        "logout_200", {"actual": out.status_code}, passed=(out.status_code == 200)
    )

    v2 = user_client.get("/auth/validate", params={"token": user_token})
    store.save_operation(
        "validate_after_logout",
        {"token": user_token},
        {"status_code": v2.status_code, "body": v2.json() if v2.status_code == 200 else v2.text},
    )
    store.save_validation(
        "validate_false_after_logout",
        {"valid": v2.json().get("valid")},
        passed=(v2.json().get("valid") is False),
    )

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.db, pytest.mark.smtp, pytest.mark.heavy]

