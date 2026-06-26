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
Description: REAL Application Test AT1.25 - Configuration hierarchy enforcement.

Validates that OS environment variables override the env file/default config
by starting the API server on an overridden port via server_control.sh and
verifying the API is reachable at that port.

This test uses ONLY:
- server_control.sh for server management (RULES.md)
- real HTTP requests for validation (requests-based APIClient)

Related Requirements: NF1.5, FR1.9
Related Tasks: T110
Related Architecture: CM1.1, DO1.1
Related Tests: AT1.25
**************************************************
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
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


def _require_env_file(request: pytest.FixtureRequest) -> str:
    env_file = request.config.getoption("--env")
    if not env_file:
        pytest.fail("--env is REQUIRED (see RULES.md)")
    return env_file


def _run_server_control(
    env_file: str,
    args: list[str],
    env_overrides: dict[str, str] | None = None,
    timeout_s: int = 180,
) -> subprocess.CompletedProcess:
    cmd = ["./server_control.sh", "--env", env_file, *args]
    env = os.environ.copy()
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_s, env=env)


def _pick_free_tcp_port(host: str = "127.0.0.1") -> int:
    """Ask OS for an available TCP port on a local bindable host, then release it."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((host, 0))
        return int(s.getsockname()[1])
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-033")


def test_AT1_25_env_overrides_env_file_for_api_port(request: pytest.FixtureRequest):
    """
    AT1.25: Prove config precedence (os.environ > --env file/default).

    Steps:
    - Stop API (baseline)
    - Start API with CLOUD_DOG__EXPERT__API_SERVER__PORT overridden to a free port
    - Verify /health is reachable on overridden port
    - Stop API, then restore by starting using default port from config
    """
    env_file = _require_env_file(request)
    store = TestOutputStorage(
        "AT1.25_ConfigHierarchyEnforcement", "test_AT1_25_env_overrides_env_file_for_api_port"
    )

    cfg = get_config()
    base_scheme = str(cfg.get("api_server", {}).get("scheme") or "http").strip().lower()
    base_host = cfg.get("api_server", {}).get("host")
    base_port = cfg.get("api_server", {}).get("port")
    if not base_host or not base_port:
        pytest.fail("api_server.host/port not configured")
    if base_scheme not in {"http", "https"}:
        pytest.fail(f"Unsupported api_server.scheme: {base_scheme}")
    base_port_int = int(base_port) if isinstance(base_port, str) else int(base_port)

    # This test starts a local process via server_control.sh. When --env points to a
    # remote host profile (preprod), force local bind host for the override run.
    runtime_host = str(base_host)
    if runtime_host not in {"127.0.0.1", "localhost", "0.0.0.0"}:
        runtime_host = "127.0.0.1"
    runtime_scheme = base_scheme
    if runtime_host == "127.0.0.1" and base_scheme == "https":
        runtime_scheme = "http"

    override_port = _pick_free_tcp_port()
    # Avoid picking the configured port to make the proof strong
    if override_port == base_port_int:
        override_port = _pick_free_tcp_port()

    overrides = {
        "CLOUD_DOG__EXPERT__API_SERVER__SCHEME": runtime_scheme,
        "CLOUD_DOG__EXPERT__API_SERVER__HOST": runtime_host,
        "CLOUD_DOG__EXPERT__API_SERVER__PORT": str(override_port),
    }

    # Ensure stopped baseline first
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

    try:
        # Start with overridden port
        start_res = _run_server_control(
            env_file, ["start", "api"], env_overrides=overrides, timeout_s=240
        )
        store.save_operation(
            "server_control_start_api_with_env_override",
            {
                "env_file": env_file,
                "args": ["start", "api"],
                "overrides": {"API_SERVER__PORT": str(override_port)},
            },
            {
                "returncode": start_res.returncode,
                "stdout": start_res.stdout,
                "stderr": start_res.stderr,
            },
        )
        store.save_validation(
            "start_api_exitcode_ok",
            {"returncode": start_res.returncode},
            passed=(start_res.returncode == 0),
        )

        # Verify reachable on override port (real HTTP)
        client = APIClient(f"{runtime_scheme}://{runtime_host}:{override_port}")
        ok = False
        last_status = None
        last_text = None
        for _ in range(30):
            try:
                r = client.get("/health")
                last_status = r.status_code
                last_text = r.text
                if r.status_code == 200:
                    ok = True
                    store.save_operation(
                        "api_get_health_on_override_port",
                        {"base_url": client.base_url, "path": "/health"},
                        {"status_code": r.status_code, "json": r.json()},
                    )
                    break
            except Exception as e:
                last_text = str(e)
            time.sleep(1)

        store.save_validation(
            "health_200_on_override_port",
            {
                "override_port": override_port,
                "ok": ok,
                "last_status": last_status,
                "last_text": last_text,
            },
            passed=ok,
        )

        # Negative check: the default port should NOT respond while overridden instance is running
        default_client = APIClient(f"{runtime_scheme}://{runtime_host}:{base_port_int}")
        default_ok = False
        try:
            rr = default_client.get("/health")
            default_ok = rr.status_code == 200
        except Exception:
            default_ok = False
        store.save_validation(
            "default_port_not_serving_while_override_running",
            {"default_port": base_port_int, "served_200": default_ok},
            passed=(default_ok is False),
        )

    finally:
        # Always stop overridden instance
        stop2_res = _run_server_control(
            env_file, ["stop", "api"], env_overrides=overrides, timeout_s=180
        )
        store.save_operation(
            "server_control_stop_api_override_instance",
            {
                "env_file": env_file,
                "args": ["stop", "api"],
                "overrides": {"API_SERVER__PORT": str(override_port)},
            },
            {
                "returncode": stop2_res.returncode,
                "stdout": stop2_res.stdout,
                "stderr": stop2_res.stderr,
            },
        )
        store.save_validation(
            "stop_override_exitcode_ok",
            {"returncode": stop2_res.returncode},
            passed=(stop2_res.returncode == 0),
        )

        # Restore baseline on configured port
        restore_res = _run_server_control(env_file, ["start", "api"], timeout_s=240)
        store.save_operation(
            "server_control_restore_start_api_default_port",
            {"env_file": env_file, "args": ["start", "api"], "default_port": base_port_int},
            {
                "returncode": restore_res.returncode,
                "stdout": restore_res.stdout,
                "stderr": restore_res.stderr,
            },
        )
        is_remote_profile = str(base_host) not in {"127.0.0.1", "localhost", "0.0.0.0"}
        restore_ok = (
            (restore_res.returncode == 0)
            or ("already running" in (restore_res.stdout or "").lower())
            or is_remote_profile
        )
        store.save_validation(
            "restore_start_ok_or_already_running",
            {
                "returncode": restore_res.returncode,
                "stdout_tail": (restore_res.stdout or "")[-400:],
                "is_remote_profile": is_remote_profile,
            },
            passed=restore_ok,
        )

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]

