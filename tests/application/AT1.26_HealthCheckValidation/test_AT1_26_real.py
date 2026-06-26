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
Description: REAL Application Test AT1.26 - Health check validation.

Validates:
- `GET /health` returns expected structure
- `GET /health/status` returns expected structure
- `server_control.sh status api` is consistent with the API being reachable

Related Requirements: FR1.9, NF1.2
Related Tasks: T058, T054
Related Architecture: MO1.1, DO1.1
Related Tests: AT1.26
**************************************************
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_helpers_common import (
    TestOutputStorage,
    create_api_client_fixture,
    assert_all_validations_passed,
    print_summary_table,
)


def _require_env_file(request: pytest.FixtureRequest) -> str:
    env_file = request.config.getoption("--env")
    if not env_file:
        pytest.fail("--env is REQUIRED (see RULES.md)")
    return env_file


def _run_server_control(
    env_file: str, args: list[str], timeout_s: int = 60
) -> subprocess.CompletedProcess:
    cmd = ["./server_control.sh", "--env", env_file, *args]
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_s)


api_client = create_api_client_fixture(check_health=True)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-033")


def test_AT1_26_health_endpoints_and_status_consistency(request: pytest.FixtureRequest):
    env_file = _require_env_file(request)
    store = TestOutputStorage(
        "AT1.26_HealthCheckValidation", "test_AT1_26_health_endpoints_and_status_consistency"
    )

    # Ensure API is running for this test
    start_res = _run_server_control(env_file, ["start", "api"], timeout_s=180)
    store.save_operation(
        "server_control_start_api",
        {"env_file": env_file, "args": ["start", "api"]},
        {
            "returncode": start_res.returncode,
            "stdout": start_res.stdout,
            "stderr": start_res.stderr,
        },
    )
    start_ok = (start_res.returncode == 0) or (
        "already running" in (start_res.stdout or "").lower()
    )
    store.save_validation(
        "start_api_ok_or_already_running",
        {"returncode": start_res.returncode, "stdout_tail": (start_res.stdout or "")[-400:]},
        passed=start_ok,
    )

    client = api_client()

    resp = client.get("/health")
    out = (
        resp.json() if resp.status_code == 200 else {"error": resp.text, "status": resp.status_code}
    )
    store.save_operation(
        "api_get_health", {"path": "/health"}, {"status_code": resp.status_code, "body": out}
    )
    store.save_validation(
        "health_status_200",
        {"actual": resp.status_code, "expected": 200},
        passed=(resp.status_code == 200),
    )
    if resp.status_code == 200:
        store.save_validation(
            "health_has_status", {"keys": list(out.keys())}, passed=("status" in out)
        )
        store.save_validation(
            "health_status_healthy",
            {"status": out.get("status")},
            passed=(out.get("status") == "healthy"),
        )

    resp = client.get("/health/status")
    out2 = (
        resp.json() if resp.status_code == 200 else {"error": resp.text, "status": resp.status_code}
    )
    store.save_operation(
        "api_get_health_status",
        {"path": "/health/status"},
        {"status_code": resp.status_code, "body": out2},
    )
    store.save_validation(
        "health_status_endpoint_200",
        {"actual": resp.status_code, "expected": 200},
        passed=(resp.status_code == 200),
    )
    if resp.status_code == 200:
        store.save_validation(
            "health_status_has_status", {"keys": list(out2.keys())}, passed=("status" in out2)
        )
        store.save_validation(
            "health_status_running",
            {"status": out2.get("status")},
            passed=(out2.get("status") == "running"),
        )

    # server_control status api should indicate running
    status_res = _run_server_control(env_file, ["status", "api"], timeout_s=60)
    store.save_operation(
        "server_control_status_api",
        {"env_file": env_file, "args": ["status", "api"]},
        {
            "returncode": status_res.returncode,
            "stdout": status_res.stdout,
            "stderr": status_res.stderr,
        },
    )
    store.save_validation(
        "server_control_status_exitcode_ok",
        {"returncode": status_res.returncode},
        passed=(status_res.returncode == 0),
    )
    store.save_validation(
        "server_control_status_mentions_running",
        {"stdout_snippet": (status_res.stdout or "")[:2000]},
        passed=("Running" in (status_res.stdout or "")),
    )

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]

