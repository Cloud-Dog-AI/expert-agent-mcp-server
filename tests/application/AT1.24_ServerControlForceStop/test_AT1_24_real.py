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
Description: REAL Application Test AT1.24 - server_control.sh force-stop command.

Validates `./server_control.sh force-stop api` behaviour using ONLY server_control.sh.

Related Requirements: NF1.2, FR1.9
Related Tasks: T054
Related Architecture: DO1.1, MO1.1
Related Tests: AT1.24
**************************************************
"""

from __future__ import annotations

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


api_client = create_api_client_fixture(check_health=False)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-033")


def test_AT1_24_force_stop_api_server(request: pytest.FixtureRequest):
    """
    AT1.24: Force-stop API server and verify it stops, then restore baseline by starting it.
    """
    env_file = _require_env_file(request)
    store = TestOutputStorage("AT1.24_ServerControlForceStop", "test_AT1_24_force_stop_api_server")

    # Ensure running first
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

    force_res = _run_server_control(env_file, ["force-stop", "api"], timeout_s=120)
    store.save_operation(
        "server_control_force_stop_api",
        {"env_file": env_file, "args": ["force-stop", "api"]},
        {
            "returncode": force_res.returncode,
            "stdout": force_res.stdout,
            "stderr": force_res.stderr,
        },
    )
    store.save_validation(
        "force_stop_exitcode_ok",
        {"returncode": force_res.returncode},
        passed=(force_res.returncode == 0),
    )

    client = api_client()
    stopped = False
    for _ in range(10):
        try:
            resp = client.get("/health")
            if resp.status_code != 200:
                stopped = True
                break
        except Exception:
            stopped = True
            break
        time.sleep(1)
    store.save_validation(
        "health_unreachable_after_force_stop", {"stopped": stopped}, passed=stopped
    )

    # Restore baseline
    restore_res = _run_server_control(env_file, ["start", "api"], timeout_s=180)
    store.save_operation(
        "server_control_restore_start_api",
        {"env_file": env_file, "args": ["start", "api"]},
        {
            "returncode": restore_res.returncode,
            "stdout": restore_res.stdout,
            "stderr": restore_res.stderr,
        },
    )
    store.save_validation(
        "restore_start_exitcode_ok",
        {"returncode": restore_res.returncode},
        passed=(restore_res.returncode == 0),
    )

    ok = False
    for _ in range(30):
        try:
            resp = client.get("/health")
            if resp.status_code == 200:
                ok = True
                store.save_operation(
                    "api_get_health_after_restore",
                    {"path": "/health"},
                    {"status_code": resp.status_code, "json": resp.json()},
                )
                break
        except Exception:
            pass
        time.sleep(1)
    store.save_validation("health_200_after_restore", {"ok": ok}, passed=ok)

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]

