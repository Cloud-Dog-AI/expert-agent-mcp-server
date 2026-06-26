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
Description: REAL Application Test AT1.45 - LLM prompt validation conforms to requirements.

Calls /validation/prompt and validates LLM returns a structured result.
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
    store.save_operation(
        "admin_login",
        {"username": username},
        {"status_code": r.status_code, "body": r.json() if r.status_code == 200 else r.text},
    )
    store.save_validation(
        "admin_login_200", {"status": r.status_code}, passed=(r.status_code == 200)
    )
    token = r.json().get("token")
    store.save_validation("admin_token_present", {"has": bool(token)}, passed=bool(token))
    c.session.headers.update({"Authorization": f"Bearer {token}"})
    return c
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_45_prompt_validation_with_requirements(request: pytest.FixtureRequest):
    env_file = request.config.getoption("--env")
    if not env_file:
        pytest.fail("--env is REQUIRED")
    store = TestOutputStorage(
        "AT1.45_PromptLLMValidation", "test_AT1_45_prompt_validation_with_requirements"
    )

    _run_server_control(env_file, ["restart", "api"], timeout_s=240)
    cfg = get_config()
    base_url = f"http://{cfg['api_server']['host']}:{int(cfg['api_server']['port'])}"
    client = _admin_client(base_url, store)

    prompt = (
        "You are a careful assistant.\n"
        "Rules:\n"
        "- Ask clarifying questions when needed.\n"
        "- Never reveal secrets.\n"
        "- Reply in JSON when asked.\n"
    )
    requirements = [
        "Must instruct the assistant not to reveal secrets",
        "Must mention asking clarifying questions",
    ]

    resp = client.post("/validation/prompt", json={"prompt": prompt, "requirements": requirements})
    body = resp.json() if resp.status_code == 200 else {"text": resp.text}
    store.save_operation(
        "validate_prompt",
        {"prompt": prompt, "requirements": requirements},
        {"status_code": resp.status_code, "body": body},
    )
    store.save_validation(
        "validate_prompt_200", {"status": resp.status_code}, passed=(resp.status_code == 200)
    )
    store.save_validation(
        "has_is_valid",
        {"is_valid": body.get("is_valid")},
        passed=isinstance(body.get("is_valid"), bool),
    )
    store.save_validation(
        "has_score",
        {"score": body.get("score")},
        passed=isinstance(body.get("score"), (int, float)),
    )

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]

