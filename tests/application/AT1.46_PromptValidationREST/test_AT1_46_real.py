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
Description: REAL Application Test AT1.46 - Prompt validation REST endpoint behaviour.

Validates:
- Missing prompt rejected (400)
- Bad/insufficient prompt returns structured failure (is_valid == False) OR low score
**************************************************
"""

from __future__ import annotations

import subprocess
import sys
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


def test_AT1_46_prompt_validation_rest_contract(request: pytest.FixtureRequest):
    env_file = request.config.getoption("--env")
    if not env_file:
        pytest.fail("--env is REQUIRED")
    store = TestOutputStorage(
        "AT1.46_PromptValidationREST", "test_AT1_46_prompt_validation_rest_contract"
    )

    _run_server_control(env_file, ["restart", "api"], timeout_s=240)
    cfg = get_config()
    base_url = f"http://{cfg['api_server']['host']}:{int(cfg['api_server']['port'])}"
    client = _admin_client(base_url, store)

    # Missing prompt -> 400
    resp = client.post("/validation/prompt", json={"prompt": ""})
    store.save_operation("missing_prompt", {}, {"status_code": resp.status_code, "body": resp.text})
    store.save_validation(
        "missing_prompt_400", {"status": resp.status_code}, passed=(resp.status_code == 400)
    )

    # Bad prompt -> should produce structured response (likely invalid)
    bad_prompt = "do stuff"
    resp = client.post(
        "/validation/prompt",
        json={
            "prompt": bad_prompt,
            "requirements": ["Must include detailed rules and safety constraints"],
        },
    )
    body = resp.json() if resp.status_code == 200 else {"text": resp.text}
    store.save_operation(
        "bad_prompt_validate",
        {"prompt": bad_prompt},
        {"status_code": resp.status_code, "body": body},
    )
    store.save_validation(
        "bad_prompt_200", {"status": resp.status_code}, passed=(resp.status_code == 200)
    )
    store.save_validation(
        "has_is_valid",
        {"is_valid": body.get("is_valid")},
        passed=isinstance(body.get("is_valid"), bool),
    )
    store.save_validation(
        "bad_prompt_is_invalid_or_low_score",
        {"is_valid": body.get("is_valid"), "score": body.get("score")},
        passed=(
            body.get("is_valid") is False
            or (isinstance(body.get("score"), (int, float)) and body.get("score") < 60)
        ),
    )

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]

