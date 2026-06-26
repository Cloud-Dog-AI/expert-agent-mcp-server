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
Description: REAL Application Test AT1.47 - Session creation within user/group limits.
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
    build_test_email,
    print_summary_table,
)


def _run_server_control(
    env_file: str,
    args: list[str],
    env_overrides: dict[str, str] | None = None,
    timeout_s: int = 240,
) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        ["./server_control.sh", "--env", env_file, *args],
        text=True,
        capture_output=True,
        timeout=timeout_s,
        env=env,
    )


def _admin_client(base_url: str, store: TestOutputStorage) -> APIClient:
    username = get_config("test.user.username")
    password = get_config("test.user.password")
    if not username or not password:
        pytest.fail("test.user.username and test.user.password must be configured")
    c = APIClient(base_url)
    r = c.post(
        "/auth/login", json={"username": username, "password": password, "expires_in_seconds": 300}
    )
    store.save_validation(
        "admin_login_200", {"status": r.status_code}, passed=(r.status_code == 200)
    )
    token = r.json().get("token") if r.status_code == 200 else None
    store.save_validation("admin_token_present", {"has": bool(token)}, passed=bool(token))
    c.session.headers.update({"Authorization": f"Bearer {token}"})
    return c
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_47_session_limit_enforced_no_queue(request: pytest.FixtureRequest):
    env_file = request.config.getoption("--env")
    if not env_file:
        pytest.fail("--env is REQUIRED")
    store = TestOutputStorage("AT1.47_SessionLimits", "test_AT1_47_session_limit_enforced_no_queue")

    # Start API with very low session limit and queue disabled
    overrides = {
        "CLOUD_DOG__EXPERT__SESSION__MAX_SESSIONS_PER_USER": "1",
        "CLOUD_DOG__EXPERT__SESSION__QUEUE_ENABLED": "false",
    }
    _run_server_control(env_file, ["stop", "api"], timeout_s=180)
    start = _run_server_control(env_file, ["start", "api"], env_overrides=overrides, timeout_s=240)
    store.save_operation(
        "start_api_limit1_noqueue",
        {"overrides": overrides},
        {"returncode": start.returncode, "stdout": start.stdout, "stderr": start.stderr},
    )
    store.save_validation(
        "start_exitcode_0", {"rc": start.returncode}, passed=(start.returncode == 0)
    )

    cfg = get_config()
    base_url = f"http://{cfg['api_server']['host']}:{int(cfg['api_server']['port'])}"
    admin = _admin_client(base_url, store)

    # Create expert
    suffix = uuid.uuid4().hex[:8]
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    ex = admin.post(
        "/experts",
        json={
            "name": f"at147_ex_{suffix}",
            "title": "AT1.47",
            "description": (
                "AT1.47 session limit expert description with unique vocabulary: "
                "amber basil cipher dune ember fjord glyph."
            ),
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_base_url": llm_base_url,
            "enabled": True,
        },
    )
    store.save_validation("expert_200", {"status": ex.status_code}, passed=(ex.status_code == 200))
    expert_id = ex.json()["id"]

    # Create a fresh user to avoid pre-existing sessions impacting limits
    user_name = f"at147_user_{suffix}"
    user_password = get_config("test.user.password")
    if not user_password:
        pytest.fail("test.user.password not configured (set in --env file)")
    user_resp = admin.post(
        "/users",
        json={
            "username": user_name,
            "email": build_test_email("at1_47", suffix),
            "password": user_password,
            "display_name": "AT1.47 user",
            "role": "user",
        },
    )
    store.save_operation(
        "create_user",
        {"username": user_name},
        {
            "status_code": user_resp.status_code,
            "body": user_resp.json() if user_resp.status_code in (200, 201) else user_resp.text,
        },
    )
    store.save_validation(
        "create_user_200",
        {"status": user_resp.status_code},
        passed=(user_resp.status_code in (200, 201)),
    )
    user_id = user_resp.json().get("id") if user_resp.status_code in (200, 201) else None
    store.save_validation("user_id_present", {"id": user_id}, passed=bool(user_id))

    # Create first session (allowed)
    s1 = admin.post(
        "/sessions?queue_if_full=false",
        json={"user_id": user_id, "expert_config_id": expert_id, "title": "s1"},
    )
    store.save_operation(
        "create_session_1",
        {},
        {"status_code": s1.status_code, "body": s1.json() if s1.status_code == 200 else s1.text},
    )
    store.save_validation("s1_200", {"status": s1.status_code}, passed=(s1.status_code == 200))

    # Create second session (should be rejected since queue disabled and queue_if_full=false)
    s2 = admin.post(
        "/sessions?queue_if_full=false",
        json={"user_id": user_id, "expert_config_id": expert_id, "title": "s2"},
    )
    store.save_operation("create_session_2", {}, {"status_code": s2.status_code, "body": s2.text})
    store.save_validation("s2_400", {"status": s2.status_code}, passed=(s2.status_code == 400))

    # Restore baseline
    _run_server_control(env_file, ["restart", "api"], timeout_s=240)

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

