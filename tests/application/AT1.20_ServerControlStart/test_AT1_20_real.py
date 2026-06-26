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
Description: REAL Application Test AT1.20 - server_control.sh start command.

Validates `./server_control.sh start api` behaviour using ONLY the approved server control script
and REAL HTTP checks against the running API server (requests-based).

Related Requirements: NF1.2, FR1.9
Related Tasks: T054
Related Architecture: DO1.1, MO1.1
Related Tests: AT1.20
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


def test_AT1_20_start_api_server(request: pytest.FixtureRequest):
    """
    AT1.20: Validate server_control.sh start api.

    Steps:
    - Stop API server (to ensure a known baseline)
    - Start API server via server_control.sh
    - Confirm /health returns 200 and expected fields
    - Leave API running at end
    """
    env_file = _require_env_file(request)

    store = TestOutputStorage("AT1.20_ServerControlStart", "test_AT1_20_start_api_server")
    cfg = get_config()
    api_host = cfg.get("api_server", {}).get("host")
    api_port = cfg.get("api_server", {}).get("port")
    if not api_host or not api_port:
        pytest.fail("api_server.host/port not configured")

    # Ensure stopped first (idempotent)
    stop_res = _run_server_control(env_file, ["stop", "api"], timeout_s=120)
    store.save_operation(
        "server_control_stop_api",
        {"env_file": env_file, "args": ["stop", "api"]},
        {"returncode": stop_res.returncode, "stdout": stop_res.stdout, "stderr": stop_res.stderr},
    )
    store.save_validation(
        "stop_api_exitcode_ok",
        {"returncode": stop_res.returncode, "stdout_tail": stop_res.stdout[-500:]},
        passed=(stop_res.returncode == 0),
    )

    # Start API
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
    store.save_validation(
        "start_api_exitcode_ok",
        {
            "returncode": start_res.returncode,
            "stdout_tail": start_res.stdout[-800:],
            "stderr_tail": start_res.stderr[-800:],
        },
        passed=(start_res.returncode == 0),
    )

    # Poll /health
    client = api_client()
    last_status = None
    last_body = None
    for _ in range(30):
        try:
            resp = client.get("/health")
            last_status = resp.status_code
            last_body = resp.text
            if resp.status_code == 200:
                data = resp.json()
                store.save_operation(
                    "api_get_health",
                    {"path": "/health"},
                    {"status_code": resp.status_code, "json": data},
                )
                store.save_validation(
                    "health_status_200", {"actual": resp.status_code, "expected": 200}, passed=True
                )
                store.save_validation(
                    "health_has_status_field",
                    {"keys": list(data.keys())},
                    passed=("status" in data),
                )
                store.save_validation(
                    "health_status_healthy",
                    {"status": data.get("status")},
                    passed=(data.get("status") == "healthy"),
                )
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        store.save_validation(
            "health_never_became_ready",
            {
                "last_status": last_status,
                "last_body": last_body,
                "host": api_host,
                "port": api_port,
            },
            passed=False,
        )

    # Always leave API running
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
        "status_api_exitcode_ok",
        {"returncode": status_res.returncode},
        passed=(status_res.returncode == 0),
    )

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]

