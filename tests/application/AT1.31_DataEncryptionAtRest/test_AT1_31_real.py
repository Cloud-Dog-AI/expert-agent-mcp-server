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
Description: REAL Application Test AT1.31 - Data encryption at rest.

Validates that audit event "data" is encrypted at rest when
privacy.data_encryption_at_rest is enabled:
- API returns decrypted JSON details
- Admin raw endpoint shows stored ciphertext does not contain plaintext marker

Related Requirements: CS1.3, NF1.5
Related Tasks: T041
Related Architecture: SE1.3
Related Tests: AT1.31
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
@pytest.mark.req("FR-002")


def test_AT1_31_audit_data_encrypted_at_rest(request: pytest.FixtureRequest):
    env_file = _require_env_file(request)
    store = TestOutputStorage(
        "AT1.31_DataEncryptionAtRest", "test_AT1_31_audit_data_encrypted_at_rest"
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

    # Create group with a unique marker (produces an audit event)
    marker = f"ENC_MARKER_{uuid.uuid4().hex}"
    group_payload = {"name": f"at131_{marker}", "description": f"desc {marker}", "enabled": True}
    resp = client.post("/groups", json=group_payload)
    store.save_operation(
        "create_group",
        group_payload,
        {
            "status_code": resp.status_code,
            "body": resp.json() if resp.status_code == 200 else resp.text,
        },
    )
    store.save_validation(
        "create_group_200", {"actual": resp.status_code}, passed=(resp.status_code == 200)
    )

    # Find the matching audit event (group.created with details.name containing marker)
    resp = client.get("/audit", params={"event_type": "group.created", "limit": 100})
    store.save_operation(
        "list_audit_group_created",
        {"event_type": "group.created"},
        {
            "status_code": resp.status_code,
            "body": resp.json() if resp.status_code == 200 else resp.text,
        },
    )
    store.save_validation(
        "audit_list_200", {"actual": resp.status_code}, passed=(resp.status_code == 200)
    )
    events = resp.json().get("events", []) if resp.status_code == 200 else []
    match = next((e for e in events if marker in (e.get("details", {}).get("name") or "")), None)
    store.save_validation("audit_event_found", {"found": bool(match)}, passed=bool(match))
    event_id = match["id"]

    # Decrypted view contains marker
    resp = client.get(f"/audit/{event_id}")
    body = resp.json() if resp.status_code == 200 else {"text": resp.text}
    store.save_operation(
        "get_audit_event", {"id": event_id}, {"status_code": resp.status_code, "body": body}
    )
    store.save_validation(
        "audit_get_200", {"actual": resp.status_code}, passed=(resp.status_code == 200)
    )
    store.save_validation(
        "audit_details_contains_marker",
        {"marker": marker, "details": body.get("details")},
        passed=(marker in str(body.get("details"))),
    )

    # Raw stored data does NOT contain marker
    resp = client.get(f"/audit/{event_id}/raw")
    raw = resp.json() if resp.status_code == 200 else {"text": resp.text}
    store.save_operation(
        "get_audit_event_raw", {"id": event_id}, {"status_code": resp.status_code, "body": raw}
    )
    store.save_validation(
        "audit_raw_200", {"actual": resp.status_code}, passed=(resp.status_code == 200)
    )
    data_raw = raw.get("data_raw") or ""
    store.save_validation(
        "raw_data_does_not_contain_marker",
        {"contains": marker in data_raw},
        passed=(marker not in data_raw),
    )

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]

