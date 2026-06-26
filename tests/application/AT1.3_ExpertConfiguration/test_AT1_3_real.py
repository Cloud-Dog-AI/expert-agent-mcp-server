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
Description: Comprehensive Application Test for Expert Configuration Management.
Tests expert CRUD operations, validation, and configuration management via real API server.
100% RULES.md compliant with comprehensive logging, validation tracking, and summary table generation.

Related Requirements: FR1.1, FR1.12
Related Tasks: T007, T008, T009
Related Architecture: CC3.1.1
Related Tests: AT1.3

Recent Changes (max 10):
- Initial comprehensive implementation with TestOutputManager
- Full RULES.md compliance (API-only, zero hardcoded values, comprehensive logging)
- Expert CRUD operations with admin authentication
- LLM configuration validation tests
**************************************************
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import APIClient

import pytest
import uuid
import json
from datetime import datetime
from typing import Any
from src.config.loader import get_config


class TestOutputManager:
    """Manages test outputs, validations, and summary generation for AT1.3 tests."""

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.base_dir = Path("working/AT1.3_TEST_OUTPUTS") / test_name
        self.inputs_dir = self.base_dir / "inputs"
        self.outputs_dir = self.base_dir / "outputs"
        self.validations_dir = self.base_dir / "validations"
        self.console_log = []
        self.validations = []
        self.start_time = datetime.now()

        for d in [self.inputs_dir, self.outputs_dir, self.validations_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def log_console(self, message: str):
        timestamp = datetime.now().strftime("[%Y-%m-%d %H:%M:%S.%f]")[:-3]
        log_entry = f"{timestamp} {message}"
        self.console_log.append(log_entry)
        print(log_entry)

    def save_input(self, name: str, data: Any):
        counter = len([f for f in self.inputs_dir.glob("*.json")]) + 1
        filename = f"{counter:02d}_{name}_input.json"
        filepath = self.inputs_dir / filename
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)
        self.log_console(f"Input saved: {name} -> {filename}")

    def save_output(self, name: str, response):
        counter = len([f for f in self.outputs_dir.glob("*.json")]) + 1
        filename = f"{counter:02d}_{name}_output.json"
        filepath = self.outputs_dir / filename

        output_data = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": response.json()
            if response.headers.get("content-type", "").startswith("application/json")
            else response.text,
        }

        with open(filepath, "w") as f:
            json.dump(output_data, f, indent=2, default=str)
        self.log_console(f"Output saved: {name} -> {filename}")

    def validate(self, name: str, condition: bool, actual: Any, expected: Any, context: str = ""):
        validation_num = len(self.validations) + 1
        passed = bool(condition)

        validation = {
            "number": validation_num,
            "name": name,
            "passed": passed,
            "actual": str(actual),
            "expected": str(expected),
            "context": context,
            "timestamp": datetime.now().isoformat(),
        }

        self.validations.append(validation)

        filename = f"{validation_num:02d}_{name}.json"
        filepath = self.validations_dir / filename
        with open(filepath, "w") as f:
            json.dump(validation, f, indent=2)

        status = "✅ PASS" if passed else "❌ FAIL"
        self.log_console(f"[VALIDATION {validation_num:02d}] {status}: {name}")
        if not passed:
            self.log_console(f"  Expected: {expected}")
            self.log_console(f"  Actual: {actual}")
            if context:
                self.log_console(f"  Context: {context}")

    def generate_summary_table(self) -> str:
        duration = (datetime.now() - self.start_time).total_seconds()
        passed_count = sum(1 for v in self.validations if v["passed"])
        failed_count = len(self.validations) - passed_count
        pass_rate = (passed_count / len(self.validations) * 100) if self.validations else 0

        console_path = self.base_dir / "console.log"
        with open(console_path, "w") as f:
            f.write("\n".join(self.console_log))

        summary = [
            "\n" + "=" * 80,
            f"TEST SUMMARY: {self.test_name}",
            "=" * 80,
            "",
            "## CONSOLE LOG",
            f"- [console.log](file://{console_path.absolute()})",
            "",
            "## INPUTS",
        ]

        for input_file in sorted(self.inputs_dir.glob("*.json")):
            summary.append(f"- [{input_file.name}](file://{input_file.absolute()})")

        summary.extend(["", "## OUTPUTS"])
        for output_file in sorted(self.outputs_dir.glob("*.json")):
            summary.append(f"- [{output_file.name}](file://{output_file.absolute()})")

        summary.extend(["", "## VALIDATIONS"])
        for val_file in sorted(self.validations_dir.glob("*.json")):
            summary.append(f"- [{val_file.name}](file://{val_file.absolute()})")

        summary.extend(
            [
                "",
                "## RESULTS",
                f"- **Total Validations**: {len(self.validations)}",
                f"- **Passed**: {passed_count}",
                f"- **Failed**: {failed_count}",
                f"- **Pass Rate**: {pass_rate:.1f}%",
                f"- **Duration**: {duration:.2f}s",
                "",
                "=" * 80,
            ]
        )

        return "\n".join(summary)


@pytest.fixture(scope="module")
def api_client():
    """Create API client for real API server."""
    api_host = get_config("api_server.host")
    api_port = get_config("api_server.port")
    if not api_host or api_port is None:
        pytest.fail("Missing api_server.host/api_server.port in config (--env)")
    base_url = f"http://{api_host}:{int(api_port)}"

    client = APIClient(base_url)

    response = client.get("/health")
    if response.status_code != 200:
        pytest.fail(f"API server not healthy at {base_url}/health")

    return client
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_AT1_3a_expert_creation_success(api_client):
    """
    AT1.3a: Expert creation with valid configuration.
    Tests successful expert creation via POST /experts endpoint.
    """
    mgr = TestOutputManager("AT1_3a_expert_creation_success")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.3a - Expert Creation Success")
    mgr.log_console("=" * 80)

    # Get LLM config from environment
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    if not llm_provider or not llm_model:
        pytest.fail("Missing llm.provider/llm.model in config (--env)")

    expert_payload = {
        "name": f"expert_at1_3a_{uuid.uuid4().hex[:8]}",
        "title": "Advanced Comprehensive Expert System Configuration",
        "description": "This advanced comprehensive expert system configuration provides robust testing capabilities for validating AT1.3a functionality with proper entropy requirements and diverse vocabulary",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "enabled": True,
    }

    mgr.save_input("create_expert", expert_payload)
    expert_response = api_client.post("/experts", json=expert_payload)
    mgr.save_output("create_expert", expert_response)

    mgr.validate(
        "expert_created",
        expert_response.status_code == 200,
        expert_response.status_code,
        200,
        "Expert creation should return 200 OK",
    )

    expert_data = expert_response.json()
    expert_id = expert_data.get("id")

    mgr.validate(
        "expert_id_present",
        expert_id is not None,
        expert_id is not None,
        True,
        "Expert ID must be present",
    )
    mgr.validate(
        "expert_name_matches",
        expert_data.get("name") == expert_payload["name"],
        expert_data.get("name"),
        expert_payload["name"],
        "Expert name must match request",
    )
    mgr.validate(
        "expert_title_matches",
        expert_data.get("title") == expert_payload["title"],
        expert_data.get("title"),
        expert_payload["title"],
        "Expert title must match request",
    )
    mgr.validate(
        "expert_llm_provider_matches",
        expert_data.get("llm_provider") == llm_provider,
        expert_data.get("llm_provider"),
        llm_provider,
        "LLM provider must match request",
    )
    mgr.validate(
        "expert_llm_model_matches",
        expert_data.get("llm_model") == llm_model,
        expert_data.get("llm_model"),
        llm_model,
        "LLM model must match request",
    )
    mgr.validate(
        "expert_enabled",
        expert_data.get("enabled") is True,
        expert_data.get("enabled"),
        True,
        "Expert should be enabled",
    )

    # Cleanup
    api_client.delete(f"/experts/{expert_id}")

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_AT1_3b_expert_get_by_id(api_client):
    """
    AT1.3b: Get expert by ID.
    Tests expert retrieval via GET /experts/{id}.
    """
    mgr = TestOutputManager("AT1_3b_expert_get_by_id")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.3b - Get Expert By ID")
    mgr.log_console("=" * 80)

    # Create expert
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    if not llm_provider or not llm_model:
        pytest.fail("Missing llm.provider/llm.model in config (--env)")

    expert_payload = {
        "name": f"expert_at1_3b_{uuid.uuid4().hex[:8]}",
        "title": "Advanced Retrieval Expert System Configuration",
        "description": "This advanced retrieval expert system configuration provides robust testing capabilities for validating AT1.3b functionality with proper entropy requirements and diverse vocabulary",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "enabled": True,
    }

    expert_response = api_client.post("/experts", json=expert_payload)
    expert_id = expert_response.json().get("id")

    # Get expert by ID
    mgr.save_input("get_expert", {"expert_id": expert_id})
    get_response = api_client.get(f"/experts/{expert_id}")
    mgr.save_output("get_expert", get_response)

    mgr.validate(
        "get_success",
        get_response.status_code == 200,
        get_response.status_code,
        200,
        "Expert retrieval should return 200 OK",
    )

    get_data = get_response.json()
    mgr.validate(
        "expert_id_matches",
        get_data.get("id") == expert_id,
        get_data.get("id"),
        expert_id,
        "Retrieved expert ID must match",
    )
    mgr.validate(
        "expert_name_matches",
        get_data.get("name") == expert_payload["name"],
        get_data.get("name"),
        expert_payload["name"],
        "Retrieved expert name must match",
    )

    # Cleanup
    api_client.delete(f"/experts/{expert_id}")

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_AT1_3c_expert_list(api_client):
    """
    AT1.3c: List experts.
    Tests expert listing via GET /experts.
    """
    mgr = TestOutputManager("AT1_3c_expert_list")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.3c - List Experts")
    mgr.log_console("=" * 80)

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    if not llm_provider or not llm_model:
        pytest.fail("Missing llm.provider/llm.model in config (--env)")

    # Create 2 experts
    expert_ids = []
    for i in range(2):
        expert_payload = {
            "name": f"expert_at1_3c_{i}_{uuid.uuid4().hex[:8]}",
            "title": f"Test Expert AT1.3c {i}",
            "description": f"Test expert {i} for AT1.3c validation",
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "enabled": True,
        }

        expert_response = api_client.post("/experts", json=expert_payload)
        expert_ids.append(expert_response.json().get("id"))

    # List experts
    mgr.save_input("list_experts", {})
    list_response = api_client.get("/experts")
    mgr.save_output("list_experts", list_response)

    mgr.validate(
        "list_success",
        list_response.status_code == 200,
        list_response.status_code,
        200,
        "Expert list should return 200 OK",
    )

    list_data = list_response.json()
    experts = list_data.get("experts", [])

    mgr.validate(
        "experts_present",
        len(experts) >= 2,
        len(experts),
        ">=2",
        "At least 2 experts should be returned",
    )

    # Cleanup
    for expert_id in expert_ids:
        api_client.delete(f"/experts/{expert_id}")

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_AT1_3d_expert_update(api_client):
    """
    AT1.3d: Update expert configuration.
    Tests expert update via PUT /experts/{id}.
    """
    mgr = TestOutputManager("AT1_3d_expert_update")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.3d - Update Expert")
    mgr.log_console("=" * 80)

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    if not llm_provider or not llm_model:
        pytest.fail("Missing llm.provider/llm.model in config (--env)")

    # Create expert
    expert_payload = {
        "name": f"expert_at1_3d_{uuid.uuid4().hex[:8]}",
        "title": "Advanced Original Expert System Configuration",
        "description": "This advanced original expert system configuration provides robust testing capabilities for validating AT1.3d update functionality with proper entropy requirements and diverse vocabulary",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "enabled": True,
    }

    expert_response = api_client.post("/experts", json=expert_payload)
    expert_id = expert_response.json().get("id")

    # Update expert with entropy-compliant descriptions
    update_payload = {
        "title": "Advanced Modified Expert System Configuration",
        "description": "This advanced modified expert system configuration provides enhanced testing capabilities for validating AT1.3d update functionality with proper entropy requirements and diverse vocabulary",
    }

    mgr.save_input("update_expert", update_payload)
    update_response = api_client.put(f"/experts/{expert_id}", json=update_payload)
    mgr.save_output("update_expert", update_response)

    mgr.validate(
        "update_success",
        update_response.status_code == 200,
        update_response.status_code,
        200,
        "Expert update should return 200 OK",
    )

    # Verify update
    get_response = api_client.get(f"/experts/{expert_id}")
    get_data = get_response.json()

    mgr.validate(
        "title_updated",
        get_data.get("title") == update_payload["title"],
        get_data.get("title"),
        update_payload["title"],
        "Expert title should be updated",
    )
    mgr.validate(
        "description_updated",
        get_data.get("description") == update_payload["description"],
        get_data.get("description"),
        update_payload["description"],
        "Expert description should be updated",
    )

    # Cleanup
    api_client.delete(f"/experts/{expert_id}")

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_AT1_3e_expert_delete(api_client):
    """
    AT1.3e: Delete expert configuration.
    Tests expert deletion via DELETE /experts/{id}.
    """
    mgr = TestOutputManager("AT1_3e_expert_delete")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.3e - Delete Expert")
    mgr.log_console("=" * 80)

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    if not llm_provider or not llm_model:
        pytest.fail("Missing llm.provider/llm.model in config (--env)")

    # Create expert
    expert_payload = {
        "name": f"expert_at1_3e_{uuid.uuid4().hex[:8]}",
        "title": "Comprehensive Test Expert Configuration for AT1.3e Deletion Validation",
        "description": "This is a comprehensive test expert configuration designed specifically for validating the AT1.3e expert deletion test suite functionality with sufficient entropy and unique word count to pass validation requirements",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "enabled": True,
    }

    expert_response = api_client.post("/experts", json=expert_payload)
    expert_id = expert_response.json().get("id")

    # Delete expert
    mgr.save_input("delete_expert", {"expert_id": expert_id})
    delete_response = api_client.delete(f"/experts/{expert_id}")
    mgr.save_output("delete_expert", delete_response)

    mgr.validate(
        "delete_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
        "Expert deletion should return 200 or 204",
    )

    # Verify deletion
    get_response = api_client.get(f"/experts/{expert_id}")
    mgr.validate(
        "expert_not_found",
        get_response.status_code == 404,
        get_response.status_code,
        404,
        "Deleted expert should return 404",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-004")


def test_AT1_3f_expert_validation_missing_fields(api_client):
    """
    AT1.3f: Expert validation - missing required fields.
    Tests that expert creation fails with missing required fields.
    """
    mgr = TestOutputManager("AT1_3f_expert_validation_missing_fields")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.3f - Expert Validation Missing Fields")
    mgr.log_console("=" * 80)
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    if not llm_provider or not llm_model:
        pytest.fail("Missing llm.provider/llm.model in config (--env)")

    # Try to create expert with missing title
    invalid_payload = {
        "name": f"expert_at1_3f_{uuid.uuid4().hex[:8]}",
        "description": "Missing title field",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
    }

    mgr.save_input("create_invalid_expert", invalid_payload)
    invalid_response = api_client.post("/experts", json=invalid_payload)
    mgr.save_output("create_invalid_expert", invalid_response)

    mgr.validate(
        "validation_failed",
        invalid_response.status_code in (400, 422),
        invalid_response.status_code,
        "400 or 422",
        "Missing required field should return 400 or 422",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]

