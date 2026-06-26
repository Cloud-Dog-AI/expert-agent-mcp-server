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
Description: REAL Application Test AT1.44 - Auto-generation of useful prompts.
# Covers: FR1.15
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
@pytest.mark.req("FR-010")


def test_AT1_44_prompt_template_auto_generated_on_expert_create(request: pytest.FixtureRequest):
    env_file = request.config.getoption("--env")
    if not env_file:
        pytest.fail("--env is REQUIRED")
    store = TestOutputStorage(
        "AT1.44_AutoPromptGeneration", "test_AT1_44_prompt_template_auto_generated_on_expert_create"
    )

    _run_server_control(env_file, ["restart", "api"], timeout_s=240)
    cfg = get_config()
    base_url = f"http://{cfg['api_server']['host']}:{int(cfg['api_server']['port'])}"
    client = _admin_client(base_url, store)

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    suffix = uuid.uuid4().hex[:8]

    title = "AT1.44 Auto Prompt Expert"
    description = (
        "This expert helps with prompt generation and will ask clarifying questions when needed."
    )
    payload = {
        "name": f"at144_{suffix}",
        "title": title,
        "description": description,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        # prompt_template intentionally omitted
        "enabled": True,
    }
    created = client.post("/experts", json=payload)
    store.save_operation(
        "create_expert_no_prompt_template",
        payload,
        {
            "status_code": created.status_code,
            "body": created.json() if created.status_code == 200 else created.text,
        },
    )
    store.save_validation(
        "create_expert_200", {"status": created.status_code}, passed=(created.status_code == 200)
    )
    expert_id = created.json().get("id")
    store.save_validation("expert_id_present", {"id": expert_id}, passed=bool(expert_id))

    got = client.get(f"/experts/{expert_id}")
    body = got.json() if got.status_code == 200 else {"text": got.text}
    store.save_operation(
        "get_expert", {"id": expert_id}, {"status_code": got.status_code, "body": body}
    )
    store.save_validation(
        "get_expert_200", {"status": got.status_code}, passed=(got.status_code == 200)
    )
    pt = body.get("prompt_template") or ""
    store.save_validation(
        "prompt_template_non_empty", {"len": len(pt)}, passed=(len(pt.strip()) > 0)
    )
    store.save_validation("prompt_mentions_title", {"contains": title in pt}, passed=(title in pt))

    # Also validate /prompts/generate is usable (auth required)
    gen = client.post(
        "/prompts/generate",
        json={"title": title, "details": description, "context_type": "general"},
    )
    gen_body = gen.json() if gen.status_code == 200 else {"text": gen.text}
    store.save_operation("prompts_generate", {}, {"status_code": gen.status_code, "body": gen_body})
    store.save_validation(
        "prompts_generate_200", {"status": gen.status_code}, passed=(gen.status_code == 200)
    )
    store.save_validation(
        "generated_prompt_non_empty",
        {"len": len(str(gen_body.get("prompt", "")))},
        passed=(len(str(gen_body.get("prompt", "")).strip()) > 0),
    )

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]
