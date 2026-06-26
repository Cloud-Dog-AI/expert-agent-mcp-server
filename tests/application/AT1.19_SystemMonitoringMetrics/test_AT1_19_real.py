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
Description: REAL Application Test AT1.19 - System monitoring and metrics viewing.

Validates monitoring endpoints via the public API using real HTTP requests:
- GET /health
- GET /health/status
- GET /metrics (Prometheus exposition)

Also verifies the API server is managed via server_control.sh (RULES.md).

Related Requirements: FR1.9, NF1.2
Related Tasks: T040, T100
Related Architecture: MO1.1, MO1.2, DO1.1
Related Tests: AT1.19
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
    env_file: str, args: list[str], timeout_s: int = 120
) -> subprocess.CompletedProcess:
    cmd = ["./server_control.sh", "--env", env_file, *args]
    return subprocess.run(cmd, text=True, capture_output=True, timeout=timeout_s)


api_client = create_api_client_fixture(check_health=True)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-033")


def test_AT1_19_monitoring_and_metrics_endpoints(request: pytest.FixtureRequest):
    """
    AT1.19: Verify core monitoring endpoints.

    Validations:
    - /health returns 200 and expected keys
    - /health/status returns 200 and expected keys
    - /metrics returns 200, text/plain, and contains expected metric names
    """
    env_file = _require_env_file(request)
    store = TestOutputStorage(
        "AT1.19_SystemMonitoringMetrics", "test_AT1_19_monitoring_and_metrics_endpoints"
    )

    # Ensure API running (idempotent)
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

    # /health
    resp = client.get("/health")
    body = (
        resp.json()
        if resp.status_code == 200
        else {"status_code": resp.status_code, "text": resp.text}
    )
    store.save_operation(
        "api_get_health", {"path": "/health"}, {"status_code": resp.status_code, "body": body}
    )
    store.save_validation(
        "health_status_200",
        {"actual": resp.status_code, "expected": 200},
        passed=(resp.status_code == 200),
    )
    if resp.status_code == 200:
        store.save_validation(
            "health_has_status", {"keys": list(body.keys())}, passed=("status" in body)
        )
        store.save_validation(
            "health_status_healthy",
            {"status": body.get("status")},
            passed=(body.get("status") == "healthy"),
        )

    # /health/status
    resp2 = client.get("/health/status")
    body2 = (
        resp2.json()
        if resp2.status_code == 200
        else {"status_code": resp2.status_code, "text": resp2.text}
    )
    store.save_operation(
        "api_get_health_status",
        {"path": "/health/status"},
        {"status_code": resp2.status_code, "body": body2},
    )
    store.save_validation(
        "health_status_endpoint_200",
        {"actual": resp2.status_code, "expected": 200},
        passed=(resp2.status_code == 200),
    )
    if resp2.status_code == 200:
        store.save_validation(
            "health_status_has_status", {"keys": list(body2.keys())}, passed=("status" in body2)
        )
        store.save_validation(
            "health_status_running",
            {"status": body2.get("status")},
            passed=(body2.get("status") == "running"),
        )

    # /metrics (Prometheus)
    resp3 = client.get("/metrics")
    content_type = resp3.headers.get("content-type") if hasattr(resp3, "headers") else None
    text = resp3.text if hasattr(resp3, "text") else ""
    store.save_operation(
        "api_get_metrics",
        {"path": "/metrics"},
        {"status_code": resp3.status_code, "content_type": content_type, "body_head": text[:2000]},
    )
    store.save_validation(
        "metrics_status_200",
        {"actual": resp3.status_code, "expected": 200},
        passed=(resp3.status_code == 200),
    )
    store.save_validation(
        "metrics_content_type_text_plain",
        {"content_type": content_type},
        passed=(content_type is not None and "text/plain" in content_type),
    )
    # Strict checks for expected metric names created by setup_metrics()
    store.save_validation(
        "metrics_contains_sessions_total",
        {"expected": "expert_agent_sessions_total"},
        passed=("expert_agent_sessions_total" in text),
    )
    store.save_validation(
        "metrics_contains_queue_depth",
        {"expected": "expert_agent_queue_depth"},
        passed=("expert_agent_queue_depth" in text),
    )

    print_summary_table(store)
    assert_all_validations_passed(store)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]

