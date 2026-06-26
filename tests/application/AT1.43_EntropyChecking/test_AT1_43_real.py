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
Description: REAL Application Test AT1.43 - Entropy checking for expert prompts/descriptions.
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


def _run_server_control(
    env_file: str, args: list[str], timeout_s: int = 240
) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["./server_control.sh", "--env", env_file, *args],
        text=True,
        capture_output=True,
        timeout=timeout_s,
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


def test_AT1_43_low_entropy_description_rejected(request: pytest.FixtureRequest):
    env_file = request.config.getoption("--env")
    if not env_file:
        pytest.fail("--env is REQUIRED")
    store = TestOutputStorage(
        "AT1.43_EntropyChecking", "test_AT1_43_low_entropy_description_rejected"
    )

    _run_server_control(env_file, ["restart", "api"], timeout_s=240)
    cfg = get_config()
    base_url = f"http://{cfg['api_server']['host']}:{int(cfg['api_server']['port'])}"
    client = _admin_client(base_url, store)

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    suffix = uuid.uuid4().hex[:8]

    low_entropy = "a a a a a a a a a a a a a a a"
    resp = client.post(
        "/experts",
        json={
            "name": f"at143_{suffix}",
            "title": "A",
            "description": low_entropy,
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_base_url": llm_base_url,
        },
    )
    store.save_operation(
        "create_expert_low_entropy",
        {"description": low_entropy},
        {"status_code": resp.status_code, "body": resp.text},
    )
    store.save_validation(
        "low_entropy_400", {"status": resp.status_code}, passed=(resp.status_code == 400)
    )

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]

