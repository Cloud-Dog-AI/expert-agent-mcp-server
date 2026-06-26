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
Description: REAL Application Test AT1.23 - server_control.sh status command.

Validates `./server_control.sh status api` output and exit code.

Related Requirements: NF1.2, FR1.9
Related Tasks: T054
Related Architecture: DO1.1, MO1.1
Related Tests: AT1.23
**************************************************
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from src.config.loader import get_config

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from test_helpers_common import (
    TestOutputStorage,
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
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-033")


def test_AT1_23_status_api_server(request: pytest.FixtureRequest):
    """
    AT1.23: Status of API server via server_control.sh.

    Validations:
    - Exit code 0
    - Output includes "API Server" line and configured port
    - Output indicates Running when API is enabled and up
    """
    env_file = _require_env_file(request)
    store = TestOutputStorage("AT1.23_ServerControlStatus", "test_AT1_23_status_api_server")

    # Ensure running (idempotent)
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
        "status_exitcode_ok",
        {"returncode": status_res.returncode},
        passed=(status_res.returncode == 0),
    )

    cfg = get_config()
    port = cfg.get("api_server", {}).get("port")
    port_str = str(int(port)) if isinstance(port, str) else str(port)

    out = status_res.stdout or ""
    store.save_validation(
        "status_mentions_api_server", {"stdout_snippet": out[:4000]}, passed=("API Server" in out)
    )
    store.save_validation(
        "status_mentions_port",
        {"expected_port": port_str},
        passed=(f"Port: {port_str}" in out or f"Port: {port_str})" in out),
    )

    # Loose "Running" detection (script colour codes may be present)
    running = bool(re.search(r"API Server:.*Running", out))
    store.save_validation("status_indicates_running", {"matched": running}, passed=running)

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]

