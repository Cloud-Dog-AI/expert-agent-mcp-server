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
Description: REAL Application Test AT1.30 - Session timeout and cleanup.

Validates that sessions expire based on `auth.session_timeout_minutes` and are
reported as ended via the API.

Related Requirements: CS1.1, FR1.7
Related Tasks: T022
Related Architecture: RR1.4, SE1.1
Related Tests: AT1.30
**************************************************
"""

from __future__ import annotations

import os
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
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_AT1_30_session_expires_and_is_reported_ended(request: pytest.FixtureRequest):
    env_file = _require_env_file(request)
    store = TestOutputStorage(
        "AT1.30_SessionTimeoutCleanup", "test_AT1_30_session_expires_and_is_reported_ended"
    )

    cfg = get_config()
    host = cfg.get("api_server", {}).get("host")
    port = int(cfg.get("api_server", {}).get("port"))
    base_url = f"http://{host}:{port}"

    # Start API with immediate session timeout
    overrides = {"CLOUD_DOG__EXPERT__AUTH__SESSION_TIMEOUT_MINUTES": "0"}
    _run_server_control(env_file, ["stop", "api"], timeout_s=180)
    start_res = _run_server_control(
        env_file, ["start", "api"], env_overrides=overrides, timeout_s=240
    )
    store.save_operation(
        "server_start_api_timeout0",
        {"args": ["start", "api"], "overrides": overrides},
        {
            "returncode": start_res.returncode,
            "stdout": start_res.stdout,
            "stderr": start_res.stderr,
        },
    )
    store.save_validation(
        "start_exitcode_0", {"rc": start_res.returncode}, passed=(start_res.returncode == 0)
    )

    client = APIClient(base_url)
    username = get_config("test.user.username")
    password = get_config("test.user.password")
    if not username or not password:
        pytest.fail("test.user.username and test.user.password must be configured")
    # When auth.session_timeout_minutes=0, default token expiry is immediate; request an explicit token TTL.
    login = client.post(
        "/auth/login", json={"username": username, "password": password, "expires_in_seconds": 120}
    )
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

    # Find admin user id (bootstrap user)
    users = client.get("/users").json().get("users", [])
    admin_username = get_config("test.user.username")
    admin_user = next((u for u in users if u.get("username") == admin_username), None)
    store.save_validation(
        "admin_user_found",
        {"username": admin_username, "found": bool(admin_user)},
        passed=bool(admin_user),
    )
    admin_user_id = admin_user["id"]

    # Create an expert (config-driven)
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("llm.provider/llm.model/llm.base_url must be configured")

    suffix = uuid.uuid4().hex[:8]
    expert_payload = {
        "name": f"at130_expert_{suffix}",
        "title": f"AT1.30 Expert {suffix}",
        "description": (
            "Session timeout test expert with unique vocabulary: "
            "amber basil cipher dune ember fjord glyph."
        ),
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "enabled": True,
    }
    resp = client.post("/experts", json=expert_payload)
    store.save_operation(
        "create_expert",
        expert_payload,
        {
            "status_code": resp.status_code,
            "body": resp.json() if resp.status_code == 200 else resp.text,
        },
    )
    store.save_validation(
        "create_expert_200", {"actual": resp.status_code}, passed=(resp.status_code == 200)
    )
    expert_id = resp.json().get("id")
    store.save_validation("expert_id_present", {"id": expert_id}, passed=bool(expert_id))

    # Create a session
    session_payload = {
        "user_id": admin_user_id,
        "expert_config_id": expert_id,
        "title": "AT1.30 timeout session",
        "context_window": 256,
        "history_retention_days": 1,
    }
    resp = client.post("/sessions", json=session_payload)
    store.save_operation(
        "create_session",
        session_payload,
        {
            "status_code": resp.status_code,
            "body": resp.json() if resp.status_code == 200 else resp.text,
        },
    )
    store.save_validation(
        "create_session_200", {"actual": resp.status_code}, passed=(resp.status_code == 200)
    )
    session_id = resp.json().get("id")
    store.save_validation("session_id_present", {"id": session_id}, passed=bool(session_id))

    # Get session should mark it ended due to timeout=0
    resp = client.get(f"/sessions/{session_id}")
    store.save_operation(
        "get_session_after_timeout",
        {"path": f"/sessions/{session_id}"},
        {
            "status_code": resp.status_code,
            "body": resp.json() if resp.status_code == 200 else resp.text,
        },
    )
    store.save_validation(
        "get_session_200", {"actual": resp.status_code}, passed=(resp.status_code == 200)
    )
    status = resp.json().get("status")
    store.save_validation("session_status_ended", {"status": status}, passed=(status == "ended"))

    # Restore baseline
    _run_server_control(env_file, ["restart", "api"], timeout_s=240)

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]

