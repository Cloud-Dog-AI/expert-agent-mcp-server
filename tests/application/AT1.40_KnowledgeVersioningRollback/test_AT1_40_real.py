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
Description: REAL Application Test AT1.40 - Knowledge versioning and rollback.
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


def _run_server_control(
    env_file: str, args: list[str], timeout_s: int = 240
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["./server_control.sh", "--env", env_file, *args],
        text=True,
        capture_output=True,
        timeout=timeout_s,
    )


def _login(base_url: str, username: str, password: str, store: TestOutputStorage) -> APIClient:
    c = APIClient(base_url)
    r = c.post(
        "/auth/login", json={"username": username, "password": password, "expires_in_seconds": 300}
    )
    store.save_validation("login_200", {"status": r.status_code}, passed=(r.status_code == 200))
    token = r.json().get("token") if r.status_code == 200 else None
    store.save_validation("token_present", {"has": bool(token)}, passed=bool(token))
    c.session.headers.update({"Authorization": f"Bearer {token}"})
    return c
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_40_versions_and_rollback_for_user_knowledge(request: pytest.FixtureRequest):
    env_file = request.config.getoption("--env")
    if not env_file:
        pytest.fail("--env is REQUIRED")
    store = TestOutputStorage(
        "AT1.40_KnowledgeVersioningRollback", "test_AT1_40_versions_and_rollback_for_user_knowledge"
    )

    _run_server_control(env_file, ["restart", "api"], timeout_s=240)
    cfg = get_config()
    base_url = f"http://{cfg['api_server']['host']}:{int(cfg['api_server']['port'])}"

    # Admin client (create user)
    admin = _login(
        base_url, get_config("test.user.username"), get_config("test.user.password"), store
    )

    suffix = uuid.uuid4().hex[:8]
    uname = f"at140_{suffix}"
    upw = get_config("test.user.password")
    if not upw:
        pytest.fail("test.user.password not configured (set in --env file)")
    u = admin.post(
        "/users",
        json={
            "username": uname,
            "email": build_test_email("at140", suffix),
            "password": upw,
            "display_name": "AT1.40",
            "role": "user",
        },
    )
    store.save_validation(
        "create_user_200", {"status": u.status_code}, passed=(u.status_code in (200, 201))
    )
    user_id = u.json().get("id")
    store.save_validation("user_id_present", {"id": user_id}, passed=bool(user_id))

    user = _login(base_url, uname, upw, store)

    # Add two knowledge entries -> should create versions
    k1 = user.post(
        "/knowledge",
        json={
            "knowledge_type": "user",
            "knowledge_id": user_id,
            "content": "First fact",
            "metadata": {"source": "test"},
        },
    )
    store.save_operation(
        "add_k1",
        {},
        {"status_code": k1.status_code, "body": k1.json() if k1.status_code == 200 else k1.text},
    )
    store.save_validation("add_k1_200", {"status": k1.status_code}, passed=(k1.status_code == 200))

    k2 = user.post(
        "/knowledge",
        json={
            "knowledge_type": "user",
            "knowledge_id": user_id,
            "content": "Second fact",
            "metadata": {"source": "test"},
        },
    )
    store.save_operation(
        "add_k2",
        {},
        {"status_code": k2.status_code, "body": k2.json() if k2.status_code == 200 else k2.text},
    )
    store.save_validation("add_k2_200", {"status": k2.status_code}, passed=(k2.status_code == 200))

    versions = user.get(f"/knowledge/user/{user_id}/versions")
    vbody = versions.json() if versions.status_code == 200 else {"text": versions.text}
    store.save_operation("list_versions", {}, {"status_code": versions.status_code, "body": vbody})
    store.save_validation(
        "versions_200", {"status": versions.status_code}, passed=(versions.status_code == 200)
    )
    store.save_validation(
        "has_multiple_versions",
        {"count": len(vbody.get("versions", []))},
        passed=(len(vbody.get("versions", [])) >= 3),
    )

    # Rollback to version 2 (should contain only the first fact)
    rb = user.post(f"/knowledge/user/{user_id}/rollback", json={"version": 2})
    store.save_operation(
        "rollback_v2",
        {},
        {"status_code": rb.status_code, "body": rb.json() if rb.status_code == 200 else rb.text},
    )
    store.save_validation(
        "rollback_200", {"status": rb.status_code}, passed=(rb.status_code == 200)
    )

    hist = user.get(f"/knowledge/user/{user_id}")
    hbody = hist.json() if hist.status_code == 200 else {"text": hist.text}
    store.save_operation(
        "history_after_rollback", {}, {"status_code": hist.status_code, "body": hbody}
    )
    store.save_validation(
        "history_200", {"status": hist.status_code}, passed=(hist.status_code == 200)
    )
    contents = [e.get("content") for e in hbody.get("entries", [])]
    store.save_validation(
        "rollback_removed_second",
        {"contents": contents},
        passed=("Second fact" not in contents and "First fact" in contents),
    )

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

