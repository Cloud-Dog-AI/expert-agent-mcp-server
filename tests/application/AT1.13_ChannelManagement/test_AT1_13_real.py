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
Description: Comprehensive Application Test for Channel Creation and Configuration.
Tests channel CRUD operations, LLM configuration, enable/disable, and channel management via real API server.
100% RULES.md compliant with comprehensive logging, validation tracking, and summary table generation.

Related Requirements: FR1.12, UC1.6
Related Tasks: T050
Related Architecture: CC3.1.3, CC1.1.1
Related Tests: AT1.13

Recent Changes (max 10):
- Initial comprehensive implementation with TestOutputManager
- Full RULES.md compliance (API-only, zero hardcoded values, comprehensive logging)
- Added comprehensive test scenarios covering all channel management workflows
- Validation tracking with file output for all assertions
- Summary table generation with clickable file:// URIs
**************************************************
"""

import pytest
import uuid
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from src.config.loader import get_config

# Shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import create_api_client_fixture, validate_config_loaded


class TestOutputManager:
    """
    Manages comprehensive test output logging for AT1.13.
    Saves all inputs, outputs, validations, and generates summary tables.
    100% RULES.md compliant output management.
    """

    __test__ = False  # Prevent pytest from collecting this as a test class

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.base_dir = Path("working") / "AT1.13_TEST_OUTPUTS" / test_name
        self.inputs_dir = self.base_dir / "inputs"
        self.outputs_dir = self.base_dir / "outputs"
        self.validations_dir = self.base_dir / "validations"
        self.console_log = []

        # Create directories
        for d in [self.inputs_dir, self.outputs_dir, self.validations_dir]:
            d.mkdir(parents=True, exist_ok=True)

        # Counters for sequential numbering
        self.input_counter = 0
        self.output_counter = 0
        self.validation_counter = 0

        # Track all validations
        self.validations = []

        # Track test start time
        self.start_time = datetime.now()

    def log_console(self, message: str):
        """Log message to console and internal log."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        log_entry = f"[{timestamp}] {message}"
        self.console_log.append(log_entry)
        print(log_entry)

    def save_input(self, operation: str, data: Dict[str, Any]) -> Path:
        """Save input data with sequential numbering."""
        self.input_counter += 1
        filename = f"{self.input_counter:02d}_{operation}_input.json"
        filepath = self.inputs_dir / filename

        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)

        self.log_console(f"Input saved: {operation} -> {filepath.name}")
        return filepath

    def save_output(self, operation: str, response: Any) -> Path:
        """Save output data with sequential numbering."""
        self.output_counter += 1
        filename = f"{self.output_counter:02d}_{operation}_output.json"
        filepath = self.outputs_dir / filename

        # Handle response object
        output_data = {
            "status_code": getattr(response, "status_code", None),
            "headers": dict(getattr(response, "headers", {})),
            "body": None,
        }

        try:
            output_data["body"] = response.json() if hasattr(response, "json") else str(response)
        except Exception:
            output_data["body"] = str(response)

        with open(filepath, "w") as f:
            json.dump(output_data, f, indent=2, default=str)

        self.log_console(f"Output saved: {operation} -> {filepath.name}")
        return filepath

    def validate(self, name: str, condition: bool, actual: Any, expected: Any, context: str = ""):
        """Track a validation with detailed logging."""
        self.validation_counter += 1

        validation = {
            "id": self.validation_counter,
            "name": name,
            "passed": bool(condition),
            "actual": str(actual),
            "expected": str(expected),
            "context": context,
            "timestamp": datetime.now().isoformat(),
        }

        self.validations.append(validation)

        # Save individual validation file
        filename = f"{self.validation_counter:02d}_{name}.json"
        filepath = self.validations_dir / filename

        with open(filepath, "w") as f:
            json.dump(validation, f, indent=2)

        status = "✅ PASS" if condition else "❌ FAIL"
        self.log_console(f"[VALIDATION {self.validation_counter:02d}] {status}: {name}")

        return condition

    def generate_summary_table(self) -> str:
        """Generate markdown summary table with statistics."""
        duration = (datetime.now() - self.start_time).total_seconds()

        # Save console log
        console_log_path = self.base_dir / "console.log"
        with open(console_log_path, "w") as f:
            f.write("\n".join(self.console_log))

        # Calculate statistics
        total = len(self.validations)
        passed = sum(1 for v in self.validations if v["passed"])
        pass_rate = (passed / total * 100) if total > 0 else 0

        # Generate summary
        table = "\n" + "=" * 80 + "\n"
        table += f"TEST SUMMARY: {self.test_name}\n"
        table += "=" * 80 + "\n\n"

        # Console log link
        table += "## CONSOLE LOG\n"
        table += f"- [console.log](file://{console_log_path.absolute()})\n\n"

        # Input files
        table += "## INPUTS\n"
        for f in sorted(self.inputs_dir.glob("*.json")):
            table += f"- [{f.name}](file://{f.absolute()})\n"
        table += "\n"

        # Output files
        table += "## OUTPUTS\n"
        for f in sorted(self.outputs_dir.glob("*.json")):
            table += f"- [{f.name}](file://{f.absolute()})\n"
        table += "\n"

        # Validation files
        table += "## VALIDATIONS\n"
        for f in sorted(self.validations_dir.glob("*.json")):
            table += f"- [{f.name}](file://{f.absolute()})\n"
        table += "\n"

        # Results
        table += "## RESULTS\n"
        table += f"- **Total Validations**: {total}\n"
        table += f"- **Passed**: {passed}\n"
        table += f"- **Failed**: {total - passed}\n"
        table += f"- **Pass Rate**: {pass_rate:.1f}%\n"
        table += f"- **Duration**: {duration:.2f}s\n\n"

        table += "=" * 80 + "\n"

        print(table)
        return table


@pytest.fixture(scope="module")
def api_client():
    """Create API client that connects to real running API server."""
    validate_config_loaded()
    return create_api_client_fixture(check_health=True)()


def get_admin_api_key():
    """Get admin API key from config (RULES.md compliant - no hardcoded values)."""
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured (set via --env: TEST_API_KEY)")
    return str(api_key)


@pytest.fixture
def test_expert(api_client):
    """Create a test expert configuration for channel tests."""
    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    unique_id = str(uuid.uuid4())[:8]
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")

    expert_data = {
        "name": f"AT1.13 Test Expert {unique_id}",
        "title": f"AT1.13 Test Expert {unique_id}",
        "description": f"Test expert configuration for AT1.13 channel management tests - {unique_id}",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "enabled": True,
    }

    response = api_client.post("/experts", json=expert_data)
    assert response.status_code == 200, f"Failed to create test expert: {response.text}"
    expert = response.json()

    yield expert

    # Cleanup
    api_client.delete(f"/experts/{expert['id']}")
    api_client.session.headers.pop("X-API-Key", None)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-007")


def test_AT1_13a_channel_creation_success(api_client, test_expert):
    """AT1.13a: Channel creation with expert configuration"""
    mgr = TestOutputManager("AT1_13a_channel_creation_success")
    mgr.log_console("TEST START: AT1.13a - Channel Creation Success")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    unique_id = str(uuid.uuid4())[:8]
    channel_data = {
        "name": f"AT1.13 Test Channel {unique_id}",
        "expert_config_id": test_expert["id"],
        "description": f"Test channel for AT1.13 - {unique_id}",
        "context_type": "general",
        "expected_outcomes": "Test outcomes",
        "history_scope": "session",
        "enabled": True,
    }
    mgr.save_input("create_channel", channel_data)

    response = api_client.post("/channels", json=channel_data)
    mgr.save_output("create_channel", response)

    mgr.validate(
        "status_code", response.status_code == 200, response.status_code, 200, "POST /channels"
    )

    if response.status_code == 200:
        channel = response.json()
        mgr.validate("has_id", "id" in channel, "id" in channel, True, "Has id field")
        mgr.validate("has_name", "name" in channel, "name" in channel, True, "Has name field")
        mgr.validate(
            "has_expert_config_id",
            "expert_config_id" in channel,
            "expert_config_id" in channel,
            True,
            "Has expert_config_id",
        )
        mgr.validate(
            "has_enabled", "enabled" in channel, "enabled" in channel, True, "Has enabled field"
        )
        mgr.validate(
            "expert_id_match",
            channel.get("expert_config_id") == test_expert["id"],
            channel.get("expert_config_id"),
            test_expert["id"],
            "Expert ID matches",
        )
        mgr.validate(
            "enabled_true",
            channel.get("enabled"),
            channel.get("enabled"),
            True,
            "Channel enabled",
        )

        # Cleanup
        api_client.delete(f"/channels/{channel['id']}")

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-007")


def test_AT1_13b_channel_list_and_retrieve(api_client, test_expert):
    """AT1.13b: List channels and retrieve by ID"""
    mgr = TestOutputManager("AT1_13b_channel_list_and_retrieve")
    mgr.log_console("TEST START: AT1.13b - Channel List and Retrieve")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create channel
    unique_id = str(uuid.uuid4())[:8]
    channel_data = {
        "name": f"AT1.13 List Test {unique_id}",
        "expert_config_id": test_expert["id"],
        "description": "Channel for list/retrieve test",
        "enabled": True,
    }

    create_response = api_client.post("/channels", json=channel_data)
    assert create_response.status_code == 200
    channel = create_response.json()

    # List channels
    list_response = api_client.get("/channels")
    mgr.save_output("list_channels", list_response)

    mgr.validate(
        "list_status",
        list_response.status_code == 200,
        list_response.status_code,
        200,
        "GET /channels",
    )

    if list_response.status_code == 200:
        data = list_response.json()
        mgr.validate(
            "has_channels", "channels" in data, "channels" in data, True, "Has channels array"
        )
        mgr.validate("has_count", "count" in data, "count" in data, True, "Has count field")

    # Get specific channel
    get_response = api_client.get(f"/channels/{channel['id']}")
    mgr.save_output("get_channel", get_response)

    mgr.validate(
        "get_status",
        get_response.status_code == 200,
        get_response.status_code,
        200,
        "GET /channels/{id}",
    )

    if get_response.status_code == 200:
        retrieved = get_response.json()
        mgr.validate(
            "id_match",
            retrieved.get("id") == channel["id"],
            retrieved.get("id"),
            channel["id"],
            "Channel ID matches",
        )
        mgr.validate(
            "has_description",
            "description" in retrieved,
            "description" in retrieved,
            True,
            "Has description",
        )

    # Cleanup
    api_client.delete(f"/channels/{channel['id']}")
    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-007")


def test_AT1_13c_channel_llm_config(api_client, test_expert):
    """AT1.13c: Get channel LLM configuration"""
    mgr = TestOutputManager("AT1_13c_channel_llm_config")
    mgr.log_console("TEST START: AT1.13c - Channel LLM Configuration")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create channel
    unique_id = str(uuid.uuid4())[:8]
    channel_data = {
        "name": f"AT1.13 LLM Config Test {unique_id}",
        "expert_config_id": test_expert["id"],
        "enabled": True,
    }

    create_response = api_client.post("/channels", json=channel_data)
    assert create_response.status_code == 200
    channel = create_response.json()

    # Get LLM config
    response = api_client.get(f"/channels/{channel['id']}/llm-config")
    mgr.save_output("get_llm_config", response)

    mgr.validate(
        "status_code",
        response.status_code == 200,
        response.status_code,
        200,
        "GET /channels/{id}/llm-config",
    )

    if response.status_code == 200:
        config = response.json()
        mgr.validate(
            "has_provider", "provider" in config, "provider" in config, True, "Has provider field"
        )
        mgr.validate("has_model", "model" in config, "model" in config, True, "Has model field")
        mgr.validate(
            "has_base_url", "base_url" in config, "base_url" in config, True, "Has base_url field"
        )

    # Cleanup
    api_client.delete(f"/channels/{channel['id']}")
    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-007")


def test_AT1_13d_channel_enable_disable(api_client, test_expert):
    """AT1.13d: Channel enable/disable functionality"""
    mgr = TestOutputManager("AT1_13d_channel_enable_disable")
    mgr.log_console("TEST START: AT1.13d - Channel Enable/Disable")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create enabled channel
    unique_id = str(uuid.uuid4())[:8]
    channel_data = {
        "name": f"AT1.13 Enable Test {unique_id}",
        "expert_config_id": test_expert["id"],
        "enabled": True,
    }

    create_response = api_client.post("/channels", json=channel_data)
    assert create_response.status_code == 200
    channel = create_response.json()

    mgr.validate(
        "initially_enabled",
        channel.get("enabled"),
        channel.get("enabled"),
        True,
        "Channel initially enabled",
    )

    # Create disabled channel
    disabled_data = {
        "name": f"AT1.13 Disabled Test {unique_id}",
        "expert_config_id": test_expert["id"],
        "enabled": False,
    }

    disabled_response = api_client.post("/channels", json=disabled_data)
    mgr.save_output("create_disabled", disabled_response)

    mgr.validate(
        "disabled_status",
        disabled_response.status_code == 200,
        disabled_response.status_code,
        200,
        "Create disabled channel",
    )

    if disabled_response.status_code == 200:
        disabled_channel = disabled_response.json()
        mgr.validate(
            "disabled_false",
            not disabled_channel.get("enabled"),
            disabled_channel.get("enabled"),
            False,
            "Channel disabled",
        )
        api_client.delete(f"/channels/{disabled_channel['id']}")

    # Cleanup
    api_client.delete(f"/channels/{channel['id']}")
    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-007")


def test_AT1_13e_channel_delete(api_client, test_expert):
    """AT1.13e: Channel deletion"""
    mgr = TestOutputManager("AT1_13e_channel_delete")
    mgr.log_console("TEST START: AT1.13e - Channel Delete")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create channel
    unique_id = str(uuid.uuid4())[:8]
    channel_data = {
        "name": f"AT1.13 Delete Test {unique_id}",
        "expert_config_id": test_expert["id"],
        "enabled": True,
    }

    create_response = api_client.post("/channels", json=channel_data)
    assert create_response.status_code == 200
    channel = create_response.json()

    # Delete channel
    delete_response = api_client.delete(f"/channels/{channel['id']}")
    mgr.save_output("delete_channel", delete_response)

    mgr.validate(
        "delete_status",
        delete_response.status_code == 200,
        delete_response.status_code,
        200,
        "DELETE /channels/{id}",
    )

    # Verify deletion
    get_response = api_client.get(f"/channels/{channel['id']}")
    mgr.save_output("verify_deleted", get_response)

    mgr.validate(
        "not_found",
        get_response.status_code == 404,
        get_response.status_code,
        404,
        "Channel not found after delete",
    )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-007")


def test_AT1_13f_channel_validation_missing_name(api_client, test_expert):
    """AT1.13f: Channel validation - missing name"""
    mgr = TestOutputManager("AT1_13f_channel_validation_missing_name")
    mgr.log_console("TEST START: AT1.13f - Channel Validation Missing Name")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Try to create channel without name
    invalid_data = {"expert_config_id": test_expert["id"], "enabled": True}
    mgr.save_input("create_invalid", invalid_data)

    response = api_client.post("/channels", json=invalid_data)
    mgr.save_output("create_invalid", response)

    mgr.validate(
        "validation_failed",
        response.status_code in [400, 422],
        response.status_code,
        "400 or 422",
        "Missing name rejected",
    )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-007")


def test_AT1_13g_channel_invalid_expert_404(api_client):
    """AT1.13g: Channel with invalid expert ID returns 404"""
    mgr = TestOutputManager("AT1_13g_channel_invalid_expert_404")
    mgr.log_console("TEST START: AT1.13g - Invalid Expert ID")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Try to create channel with non-existent expert
    invalid_data = {"name": "Invalid Expert Test", "expert_config_id": 999999, "enabled": True}
    mgr.save_input("create_invalid_expert", invalid_data)

    response = api_client.post("/channels", json=invalid_data)
    mgr.save_output("create_invalid_expert", response)

    mgr.validate(
        "invalid_expert",
        response.status_code in [400, 404],
        response.status_code,
        "400 or 404",
        "Invalid expert rejected",
    )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.pure, pytest.mark.heavy]
