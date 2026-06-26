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
Description: REAL Application Test AT1.34 - User/group-based access controls for logs/history.

Validates:
- Session access is restricted to owner/admin
- Audit log viewing is restricted to owner/admin (non-admin cannot see other users' events)

Related Requirements: CS1.1, CS1.2
Related Tasks: T006, T055
Related Architecture: SE1.1
Related Tests: AT1.34
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


def test_AT1_34_session_and_audit_access_controls(request: pytest.FixtureRequest):
    env_file = _require_env_file(request)
    store = TestOutputStorage(
        "AT1.34_LogHistoryAccessControl", "test_AT1_34_session_and_audit_access_controls"
    )

    _run_server_control(env_file, ["restart", "api"], timeout_s=240)

    cfg = get_config()
    host = cfg.get("api_server", {}).get("host")
    port = int(cfg.get("api_server", {}).get("port"))
    base_url = f"http://{host}:{port}"
    admin = APIClient(base_url)
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
    token = login.json().get("token") if login.status_code == 200 else None
    store.save_validation("admin_token_present", {"has_token": bool(token)}, passed=bool(token))
    admin.session.headers.update({"Authorization": f"Bearer {token}"})

    # Create two users
    suffix = uuid.uuid4().hex[:8]
    user_password = get_config("test.user.password")
    if not user_password:
        pytest.fail("test.user.password not configured (set in --env file)")
    u1 = {
        "username": f"at134_u1_{suffix}",
        "email": build_test_email("at134_u1", suffix),
        "password": user_password,
        "display_name": "u1",
        "role": "user",
    }
    u2 = {
        "username": f"at134_u2_{suffix}",
        "email": build_test_email("at134_u2", suffix),
        "password": user_password,
        "display_name": "u2",
        "role": "user",
    }
    r1 = admin.post("/users", json=u1)
    r2 = admin.post("/users", json=u2)
    store.save_operation(
        "admin_create_user1",
        u1,
        {
            "status_code": r1.status_code,
            "body": r1.json() if r1.status_code in (200, 201) else r1.text,
        },
    )
    store.save_operation(
        "admin_create_user2",
        u2,
        {
            "status_code": r2.status_code,
            "body": r2.json() if r2.status_code in (200, 201) else r2.text,
        },
    )
    store.save_validation(
        "users_created",
        {"u1": r1.status_code, "u2": r2.status_code},
        passed=(r1.status_code in (200, 201) and r2.status_code in (200, 201)),
    )
    u1_id = r1.json()["id"]
    u2_id = r2.json()["id"]

    # Create API keys for each user
    k1 = admin.post("/api-keys", json={"user_id": u1_id, "name": "u1_key"})
    k2 = admin.post("/api-keys", json={"user_id": u2_id, "name": "u2_key"})
    store.save_operation(
        "admin_create_key_u1",
        {"user_id": u1_id},
        {"status_code": k1.status_code, "body": k1.json() if k1.status_code == 200 else k1.text},
    )
    store.save_operation(
        "admin_create_key_u2",
        {"user_id": u2_id},
        {"status_code": k2.status_code, "body": k2.json() if k2.status_code == 200 else k2.text},
    )
    store.save_validation(
        "keys_created",
        {"k1": k1.status_code, "k2": k2.status_code},
        passed=(k1.status_code == 200 and k2.status_code == 200),
    )
    u1_key = k1.json()["key"]
    u2_key = k2.json()["key"]

    c1 = APIClient(base_url)
    c1.session.headers.update({"X-API-Key": str(u1_key)})
    c2 = APIClient(base_url)
    c2.session.headers.update({"X-API-Key": str(u2_key)})

    # Create an expert for sessions
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    ex = admin.post(
        "/experts",
        json={
            "name": f"at134_ex_{suffix}",
            "title": "AT1.34",
            "description": (
                "AT1.34 access control expert description with unique vocabulary: "
                "amber basil cipher dune ember fjord glyph."
            ),
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_base_url": llm_base_url,
            "enabled": True,
        },
    )
    store.save_operation(
        "admin_create_expert",
        {"name": f"at134_ex_{suffix}"},
        {"status_code": ex.status_code, "body": ex.json() if ex.status_code == 200 else ex.text},
    )
    store.save_validation(
        "expert_created", {"status": ex.status_code}, passed=(ex.status_code == 200)
    )
    expert_id = ex.json()["id"]

    # Create a session owned by user1 (created by admin)
    s = admin.post(
        "/sessions",
        json={"user_id": u1_id, "expert_config_id": expert_id, "title": "AT1.34 session"},
    )
    store.save_operation(
        "admin_create_session_for_u1",
        {"user_id": u1_id, "expert_config_id": expert_id},
        {"status_code": s.status_code, "body": s.json() if s.status_code == 200 else s.text},
    )
    store.save_validation(
        "session_created", {"status": s.status_code}, passed=(s.status_code == 200)
    )
    session_id = s.json()["id"]

    # User2 cannot access user1 session
    r = c2.get(f"/sessions/{session_id}")
    store.save_operation(
        "u2_get_u1_session",
        {"session_id": session_id},
        {"status_code": r.status_code, "body": r.text},
    )
    store.save_validation(
        "u2_forbidden_403",
        {"actual": r.status_code, "expected": 403},
        passed=(r.status_code == 403),
    )

    # User1 can access their session
    r = c1.get(f"/sessions/{session_id}")
    store.save_operation(
        "u1_get_own_session",
        {"session_id": session_id},
        {"status_code": r.status_code, "body": r.json() if r.status_code == 200 else r.text},
    )
    store.save_validation(
        "u1_get_200", {"actual": r.status_code, "expected": 200}, passed=(r.status_code == 200)
    )

    # Audit list for user2 should not include user1's session.created events
    r = c2.get("/audit", params={"event_type": "session.created", "limit": 50})
    store.save_operation(
        "u2_list_audit_session_created",
        {"event_type": "session.created"},
        {"status_code": r.status_code, "body": r.json() if r.status_code == 200 else r.text},
    )
    store.save_validation(
        "u2_audit_list_200", {"actual": r.status_code}, passed=(r.status_code == 200)
    )
    events = r.json().get("events", [])
    # Ensure none have actor == user1 id
    has_u1 = any(e.get("user_id") == u1_id for e in events)
    store.save_validation(
        "u2_does_not_see_u1_events",
        {"has_u1": has_u1, "count": len(events)},
        passed=(has_u1 is False),
    )

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

