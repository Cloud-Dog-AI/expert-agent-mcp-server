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
Description: REAL Application Test AT1.21 - server_control.sh stop command.

Validates `./server_control.sh stop api` behaviour using ONLY the approved server control script
and REAL HTTP checks (requests-based).

Related Requirements: NF1.2, FR1.9
Related Tasks: T054
Related Architecture: DO1.1, MO1.1
Related Tests: AT1.21
**************************************************
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest

from src.config.loader import get_config

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
    env_file: str, args: list[str], timeout_s: int = 90
) -> subprocess.CompletedProcess:
    cmd = ["./server_control.sh", "--env", env_file, *args]
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_s)


api_client = create_api_client_fixture(check_health=False)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-033")


def test_AT1_21_stop_api_server(request: pytest.FixtureRequest):
    """
    AT1.21: Validate server_control.sh stop api.

    Steps:
    - Ensure API server is running
    - Stop API server via server_control.sh
    - Confirm /health is unreachable (connection failure or non-200)
    - Start API server again (restore baseline)
    """
    env_file = _require_env_file(request)

    store = TestOutputStorage("AT1.21_ServerControlStop", "test_AT1_21_stop_api_server")
    cfg = get_config()
    api_host = cfg.get("api_server", {}).get("host")
    api_port = cfg.get("api_server", {}).get("port")
    if not api_host or not api_port:
        pytest.fail("api_server.host/port not configured")

    # Ensure running
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

    # Stop
    stop_res = _run_server_control(env_file, ["stop", "api"], timeout_s=180)
    store.save_operation(
        "server_control_stop_api",
        {"env_file": env_file, "args": ["stop", "api"]},
        {"returncode": stop_res.returncode, "stdout": stop_res.stdout, "stderr": stop_res.stderr},
    )
    store.save_validation(
        "stop_api_exitcode_ok",
        {"returncode": stop_res.returncode},
        passed=(stop_res.returncode == 0),
    )

    # Confirm /health unreachable
    client = api_client()
    unreachable = False
    last_status = None
    last_body = None
    for _ in range(10):
        try:
            resp = client.get("/health")
            last_status = resp.status_code
            last_body = resp.text
            if resp.status_code != 200:
                unreachable = True
                break
        except Exception:
            unreachable = True
            break
        time.sleep(1)

    store.save_validation(
        "health_unreachable_after_stop",
        {"unreachable": unreachable, "last_status": last_status, "last_body": last_body},
        passed=unreachable,
    )

    # Restore baseline: start again
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

    # Confirm /health 200
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

