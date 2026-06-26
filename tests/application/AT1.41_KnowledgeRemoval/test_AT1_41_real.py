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
Description: REAL Application Test AT1.41 - Removal of unwanted knowledge.
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


def test_AT1_41_remove_by_keyword_and_channel_filter(request: pytest.FixtureRequest):
    env_file = request.config.getoption("--env")
    if not env_file:
        pytest.fail("--env is REQUIRED")
    store = TestOutputStorage(
        "AT1.41_KnowledgeRemoval", "test_AT1_41_remove_by_keyword_and_channel_filter"
    )

    _run_server_control(env_file, ["restart", "api"], timeout_s=240)
    cfg = get_config()
    base_url = f"http://{cfg['api_server']['host']}:{int(cfg['api_server']['port'])}"

    admin = _login(
        base_url, get_config("test.user.username"), get_config("test.user.password"), store
    )

    suffix = uuid.uuid4().hex[:8]
    uname = f"at141_{suffix}"
    upw = get_config("test.user.password")
    if not upw:
        pytest.fail("test.user.password not configured (set in --env file)")
    u = admin.post(
        "/users",
        json={
            "username": uname,
            "email": build_test_email("at141", suffix),
            "password": upw,
            "display_name": "AT1.41",
            "role": "user",
        },
    )
    store.save_validation(
        "create_user_200", {"status": u.status_code}, passed=(u.status_code in (200, 201))
    )
    user_id = u.json().get("id")
    store.save_validation("user_id_present", {"id": user_id}, passed=bool(user_id))

    user = _login(base_url, uname, upw, store)

    user.post(
        "/knowledge",
        json={
            "knowledge_type": "user",
            "knowledge_id": user_id,
            "content": "Keep this entry",
            "metadata": {"channel_id": 1},
        },
    )
    user.post(
        "/knowledge",
        json={
            "knowledge_type": "user",
            "knowledge_id": user_id,
            "content": "BAD entry should go",
            "metadata": {"channel_id": 2},
        },
    )
    user.post(
        "/knowledge",
        json={
            "knowledge_type": "user",
            "knowledge_id": user_id,
            "content": "Another entry",
            "metadata": {"channel_id": 999},
        },
    )

    # Remove by keyword
    rem = user.delete(f"/knowledge/user/{user_id}", params={"keyword": "BAD"})
    store.save_operation(
        "remove_keyword",
        {},
        {
            "status_code": rem.status_code,
            "body": rem.json() if rem.status_code == 200 else rem.text,
        },
    )
    store.save_validation(
        "remove_keyword_200", {"status": rem.status_code}, passed=(rem.status_code == 200)
    )
    removed_count = rem.json().get("removed", 0) if rem.status_code == 200 else 0
    store.save_validation(
        "removed_at_least_1", {"removed": removed_count}, passed=(removed_count >= 1)
    )

    hist = user.get(f"/knowledge/user/{user_id}")
    hbody = hist.json() if hist.status_code == 200 else {"text": hist.text}
    store.save_validation(
        "history_200", {"status": hist.status_code}, passed=(hist.status_code == 200)
    )
    contents = [e.get("content") for e in hbody.get("entries", [])]
    store.save_validation(
        "keyword_removed",
        {"contents": contents},
        passed=(all("BAD" not in (c or "") for c in contents)),
    )

    # Remove by channel_id
    rem2 = user.delete(f"/knowledge/user/{user_id}", params={"channel_id": 999})
    store.save_operation(
        "remove_channel",
        {},
        {
            "status_code": rem2.status_code,
            "body": rem2.json() if rem2.status_code == 200 else rem2.text,
        },
    )
    store.save_validation(
        "remove_channel_200", {"status": rem2.status_code}, passed=(rem2.status_code == 200)
    )

    hist2 = user.get(f"/knowledge/user/{user_id}")
    hbody2 = hist2.json() if hist2.status_code == 200 else {"text": hist2.text}
    contents2 = [e.get("content") for e in hbody2.get("entries", [])]
    store.save_validation(
        "channel_removed",
        {"contents": contents2},
        passed=(all("Another entry" != (c or "") for c in contents2)),
    )

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

