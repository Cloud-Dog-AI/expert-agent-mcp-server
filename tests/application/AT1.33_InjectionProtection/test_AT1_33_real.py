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
Description: REAL Application Test AT1.33 - Protection against injection attacks.

Validates that typical SQL injection strings do not cause server errors and do not
result in unintended access.

Related Requirements: CS1.4, CS1.1
Related Tasks: T006
Related Architecture: SE1.1
Related Tests: AT1.33
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
@pytest.mark.req("FR-003")


def test_AT1_33_injection_strings_do_not_break_or_escalate(request: pytest.FixtureRequest):
    env_file = _require_env_file(request)
    store = TestOutputStorage(
        "AT1.33_InjectionProtection", "test_AT1_33_injection_strings_do_not_break_or_escalate"
    )

    _run_server_control(env_file, ["restart", "api"], timeout_s=240)

    cfg = get_config()
    host = cfg.get("api_server", {}).get("host")
    port = int(cfg.get("api_server", {}).get("port"))
    base_url = f"http://{host}:{port}"
    client = APIClient(base_url)
    username = get_config("test.user.username")
    password = get_config("test.user.password")
    if not username or not password:
        pytest.fail("test.user.username and test.user.password must be configured")
    login = client.post("/auth/login", json={"username": username, "password": password})
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
    token = login.json().get("token") if login.status_code == 200 else None
    store.save_validation("admin_token_present", {"has_token": bool(token)}, passed=bool(token))
    client.session.headers.update({"Authorization": f"Bearer {token}"})

    inj = "' OR '1'='1';--"
    suffix = uuid.uuid4().hex[:8]

    # Create a user with injection-like username; should not 500
    user_payload = {
        "username": f"at133_{suffix}{inj}",
        "email": build_test_email("at133", suffix),
        "password": password,
        "display_name": "inj test",
        "role": "user",
    }
    resp = client.post("/users", json=user_payload)
    store.save_operation(
        "create_user_injection_like",
        user_payload,
        {
            "status_code": resp.status_code,
            "body": resp.json() if resp.status_code in (200, 201) else resp.text,
        },
    )
    store.save_validation(
        "create_user_not_500", {"status_code": resp.status_code}, passed=(resp.status_code != 500)
    )
    store.save_validation(
        "create_user_success",
        {"status_code": resp.status_code},
        passed=(resp.status_code in (200, 201)),
    )
    user_id = resp.json().get("id")

    # Fetch that user by id - should succeed and not leak others
    resp = client.get(f"/users/{user_id}")
    store.save_operation(
        "get_user_by_id",
        {"user_id": user_id},
        {
            "status_code": resp.status_code,
            "body": resp.json() if resp.status_code == 200 else resp.text,
        },
    )
    store.save_validation(
        "get_user_200", {"actual": resp.status_code}, passed=(resp.status_code == 200)
    )

    # Query audit with injection-like event_type - should not 500
    resp = client.get("/audit", params={"event_type": inj, "limit": 5})
    store.save_operation(
        "audit_list_injection_like",
        {"event_type": inj},
        {
            "status_code": resp.status_code,
            "body": resp.json() if resp.status_code == 200 else resp.text,
        },
    )
    store.save_validation(
        "audit_list_not_500", {"status_code": resp.status_code}, passed=(resp.status_code != 500)
    )

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

