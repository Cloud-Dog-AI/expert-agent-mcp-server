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
Description: REAL Application Test AT1.27 - Log file management.

Validates that:
- `server_control.sh` creates/uses the expected `logs/` files
- The API server writes to `logs/api_server.log` during normal operation

This test is intentionally conservative: it only checks for existence and
non-empty size to avoid coupling to specific log formats.

Related Requirements: FR1.9, NF1.2
Related Tasks: T054
Related Architecture: MO1.1, DO1.1
Related Tests: AT1.27
**************************************************
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
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
    env_file: str, args: list[str], timeout_s: int = 120
) -> subprocess.CompletedProcess:
    cmd = ["./server_control.sh", "--env", env_file, *args]
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_s)


api_client = create_api_client_fixture(check_health=True)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-033")


def test_AT1_27_api_log_file_written(request: pytest.FixtureRequest):
    env_file = _require_env_file(request)
    store = TestOutputStorage("AT1.27_LogFileManagement", "test_AT1_27_api_log_file_written")

    logs_dir = Path("logs")
    api_log = logs_dir / "api_server.log"

    # Ensure API started
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

    # Trigger a simple request to generate some log activity
    client = api_client()
    resp = client.get("/health")
    store.save_operation(
        "api_get_health",
        {"path": "/health"},
        {
            "status_code": resp.status_code,
            "body": (resp.json() if resp.status_code == 200 else resp.text),
        },
    )
    store.save_validation(
        "health_status_200",
        {"actual": resp.status_code, "expected": 200},
        passed=(resp.status_code == 200),
    )

    # Give log writer time
    time.sleep(1)

    store.save_validation(
        "logs_dir_exists", {"path": str(logs_dir.resolve())}, passed=logs_dir.exists()
    )
    store.save_validation(
        "api_log_exists", {"path": str(api_log.resolve())}, passed=api_log.exists()
    )
    size = api_log.stat().st_size if api_log.exists() else 0
    store.save_validation("api_log_non_empty", {"size_bytes": size}, passed=(size > 0))

    # Record a small tail for debugging (avoid large reads)
    tail = ""
    if api_log.exists():
        with open(api_log, "rb") as f:
            f.seek(0, os.SEEK_END)
            end = f.tell()
            f.seek(max(0, end - 2048))
            tail = f.read().decode("utf-8", errors="replace")
    store.save_operation("api_log_tail", {"bytes": 2048}, {"tail": tail})

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]

