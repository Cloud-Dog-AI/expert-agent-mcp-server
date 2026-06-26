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
Description: REAL Application Test AT1.28 - Authentication with various providers.

Covers:
- API key authentication (X-API-Key) required for protected endpoints
- JWT login/validate/logout flow (local provider)

Related Requirements: CS1.1, FR1.11
Related Tasks: T055
Related Architecture: SE1.1
Related Tests: AT1.28
**************************************************
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.config.loader import get_config

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_helpers_common import (
    TestOutputStorage,
    APIClient,
    assert_all_validations_passed,
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
@pytest.mark.req("FR-006")


def test_AT1_28_api_key_and_jwt_auth(request: pytest.FixtureRequest):
    env_file = _require_env_file(request)
    store = TestOutputStorage("AT1.28_AuthenticationProviders", "test_AT1_28_api_key_and_jwt_auth")

    # Ensure API running
    start_res = _run_server_control(env_file, ["restart", "api"], timeout_s=240)
    store.save_operation(
        "server_control_restart_api",
        {"env_file": env_file, "args": ["restart", "api"]},
        {
            "returncode": start_res.returncode,
            "stdout": start_res.stdout,
            "stderr": start_res.stderr,
        },
    )
    store.save_validation(
        "restart_api_exitcode_ok",
        {"returncode": start_res.returncode},
        passed=(start_res.returncode == 0),
    )

    cfg = get_config()
    host = cfg.get("api_server", {}).get("host")
    port = int(cfg.get("api_server", {}).get("port"))
    base_url = f"http://{host}:{port}"

    # Protected endpoint without key should 401
    no_key_client = APIClient(base_url)
    no_key_client.session.headers.pop("X-API-Key", None)
    no_key_client.session.headers.pop("Authorization", None)
    resp = no_key_client.get("/users")
    store.save_operation(
        "users_list_no_api_key",
        {"path": "/users"},
        {"status_code": resp.status_code, "body": resp.text},
    )
    store.save_validation(
        "users_list_401_without_key",
        {"actual": resp.status_code, "expected": 401},
        passed=(resp.status_code == 401),
    )

    # JWT login/validate/logout (local) and use token for auth
    admin_client = APIClient(base_url)
    username = get_config("test.user.username")
    password = get_config("test.user.password")
    if not username or not password:
        pytest.fail(
            "test.user.username and test.user.password must be configured for JWT login test"
        )

    login_payload = {"username": username, "password": password, "expires_in_seconds": 2}
    resp = admin_client.post("/auth/login", json=login_payload)
    store.save_operation(
        "auth_login",
        login_payload,
        {
            "status_code": resp.status_code,
            "body": resp.json() if resp.status_code == 200 else resp.text,
        },
    )
    store.save_validation(
        "login_status_200",
        {"actual": resp.status_code, "expected": 200},
        passed=(resp.status_code == 200),
    )
    token = resp.json().get("token") if resp.status_code == 200 else None
    store.save_validation("login_returns_token", {"has_token": bool(token)}, passed=bool(token))

    # With valid Bearer token, protected endpoint should succeed (admin user)
    admin_client.session.headers.update({"Authorization": f"Bearer {token}"})
    resp = admin_client.get("/users")
    store.save_operation(
        "users_list_with_bearer_token",
        {"path": "/users"},
        {
            "status_code": resp.status_code,
            "body": resp.json() if resp.status_code == 200 else resp.text,
        },
    )
    store.save_validation(
        "users_list_200_with_valid_token",
        {"actual": resp.status_code, "expected": 200},
        passed=(resp.status_code == 200),
    )

    resp = admin_client.get("/auth/validate", params={"token": token})
    store.save_operation(
        "auth_validate",
        {"token": token},
        {
            "status_code": resp.status_code,
            "body": resp.json() if resp.status_code == 200 else resp.text,
        },
    )
    store.save_validation(
        "validate_status_200",
        {"actual": resp.status_code, "expected": 200},
        passed=(resp.status_code == 200),
    )
    store.save_validation(
        "validate_valid_true",
        {"valid": resp.json().get("valid")},
        passed=(resp.json().get("valid") is True),
    )

    # Wait for token to expire
    time.sleep(3)
    resp = admin_client.get("/auth/validate", params={"token": token})
    store.save_operation(
        "auth_validate_after_expiry",
        {"token": token},
        {
            "status_code": resp.status_code,
            "body": resp.json() if resp.status_code == 200 else resp.text,
        },
    )
    store.save_validation(
        "validate_after_expiry_returns_false",
        {"valid": resp.json().get("valid")},
        passed=(resp.json().get("valid") is False),
    )

    # Logout (revocation)
    resp = admin_client.post("/auth/logout", json={"token": token})
    store.save_operation(
        "auth_logout",
        {"token": token},
        {
            "status_code": resp.status_code,
            "body": resp.json() if resp.status_code == 200 else resp.text,
        },
    )
    store.save_validation(
        "logout_status_200",
        {"actual": resp.status_code, "expected": 200},
        passed=(resp.status_code == 200),
    )

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]

