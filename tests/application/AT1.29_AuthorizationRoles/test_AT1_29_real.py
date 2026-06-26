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
Description: REAL Application Test AT1.29 - Authorization for different user roles.

Validates admin-only protections and self-access rules using API keys.

Related Requirements: CS1.1, FR1.6, FR1.11
Related Tasks: T006, T055
Related Architecture: SE1.1
Related Tests: AT1.29
**************************************************
"""

from __future__ import annotations

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
    env_file: str, args: list[str], timeout_s: int = 180
) -> subprocess.CompletedProcess:
    cmd = ["./server_control.sh", "--env", env_file, *args]
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_s)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-030")


def test_AT1_29_admin_vs_user_permissions(request: pytest.FixtureRequest):
    env_file = _require_env_file(request)
    store = TestOutputStorage("AT1.29_AuthorizationRoles", "test_AT1_29_admin_vs_user_permissions")

    restart_res = _run_server_control(env_file, ["restart", "api"], timeout_s=240)
    store.save_operation(
        "server_control_restart_api",
        {"env_file": env_file, "args": ["restart", "api"]},
        {
            "returncode": restart_res.returncode,
            "stdout": restart_res.stdout,
            "stderr": restart_res.stderr,
        },
    )
    store.save_validation(
        "restart_api_exitcode_ok",
        {"returncode": restart_res.returncode},
        passed=(restart_res.returncode == 0),
    )

    cfg = get_config()
    host = cfg.get("api_server", {}).get("host")
    port = int(cfg.get("api_server", {}).get("port"))
    base_url = f"http://{host}:{port}"
    admin = APIClient(base_url)

    health_ok = False
    health_status = None
    health_body = None
    for _ in range(30):
        try:
            resp = admin.get("/health")
            health_status = resp.status_code
            health_body = resp.text
            if resp.status_code == 200:
                health_ok = True
                store.save_operation(
                    "api_get_health_after_restart",
                    {"path": "/health"},
                    {"status_code": resp.status_code, "body": resp.json()},
                )
                break
        except Exception as exc:
            health_body = str(exc)
        time.sleep(1)
    store.save_validation(
        "health_200_after_restart",
        {"status_code": health_status, "body": health_body},
        passed=health_ok,
    )

    # Admin auth via JWT
    username = get_config("test.user.username")
    password = get_config("test.user.password")
    if not username or not password:
        pytest.fail("test.user.username and test.user.password must be configured")
    login = admin.post("/auth/login", json={"username": username, "password": password})
    store.save_operation(
        "auth_login_admin",
        {"username": username},
        {
            "status_code": login.status_code,
            "body": login.json() if login.status_code == 200 else login.text,
        },
    )
    store.save_validation(
        "auth_login_200", {"actual": login.status_code}, passed=(login.status_code == 200)
    )
    token = login.json().get("token")
    store.save_validation("admin_token_present", {"has_token": bool(token)}, passed=bool(token))
    admin.session.headers.update({"Authorization": f"Bearer {token}"})

    # Create a normal user
    suffix = uuid.uuid4().hex[:8]
    user_payload = {
        "username": f"at129_user_{suffix}",
        "email": build_test_email("at129_user", suffix),
        "password": password,
        "display_name": f"AT1.29 User {suffix}",
        "role": "user",
    }
    resp = admin.post("/users", json=user_payload)
    store.save_operation(
        "admin_create_user",
        user_payload,
        {
            "status_code": resp.status_code,
            "body": resp.json() if resp.status_code in (200, 201) else resp.text,
        },
    )
    store.save_validation(
        "admin_create_user_200",
        {"actual": resp.status_code},
        passed=(resp.status_code in (200, 201)),
    )
    created_user_id = resp.json().get("id") if resp.status_code in (200, 201) else None
    store.save_validation(
        "created_user_id_present", {"id": created_user_id}, passed=bool(created_user_id)
    )

    # Create an API key for that user
    key_req = {"user_id": created_user_id, "name": "at129_user_key", "expires_days": None}
    resp = admin.post("/api-keys", json=key_req)
    store.save_operation(
        "admin_create_api_key_for_user",
        key_req,
        {
            "status_code": resp.status_code,
            "body": resp.json() if resp.status_code == 200 else resp.text,
        },
    )
    store.save_validation(
        "admin_create_api_key_200", {"actual": resp.status_code}, passed=(resp.status_code == 200)
    )
    user_key = resp.json().get("key") if resp.status_code == 200 else None
    store.save_validation(
        "user_api_key_present", {"has_key": bool(user_key)}, passed=bool(user_key)
    )

    user_client = APIClient(base_url)
    user_client.session.headers.update({"X-API-Key": str(user_key)})

    # Non-admin cannot list users
    resp = user_client.get("/users")
    store.save_operation(
        "user_list_users_forbidden",
        {"path": "/users"},
        {"status_code": resp.status_code, "body": resp.text},
    )
    store.save_validation(
        "user_list_users_403",
        {"actual": resp.status_code, "expected": 403},
        passed=(resp.status_code == 403),
    )

    # Non-admin can get themselves
    resp = user_client.get(f"/users/{created_user_id}")
    store.save_operation(
        "user_get_self",
        {"path": f"/users/{created_user_id}"},
        {
            "status_code": resp.status_code,
            "body": resp.json() if resp.status_code == 200 else resp.text,
        },
    )
    store.save_validation(
        "user_get_self_200",
        {"actual": resp.status_code, "expected": 200},
        passed=(resp.status_code == 200),
    )

    # Non-admin cannot create groups (admin-only)
    group_payload = {"name": f"at129_group_{suffix}", "description": "test", "enabled": True}
    resp = user_client.post("/groups", json=group_payload)
    store.save_operation(
        "user_create_group_forbidden",
        group_payload,
        {"status_code": resp.status_code, "body": resp.text},
    )
    store.save_validation(
        "user_create_group_403",
        {"actual": resp.status_code, "expected": 403},
        passed=(resp.status_code == 403),
    )

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]
