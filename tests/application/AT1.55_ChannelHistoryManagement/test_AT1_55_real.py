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
Description: Comprehensive Application Test for Channel History Management.
Tests channel history retrieval on user/channel/session basis via real API server.
100% RULES.md compliant with comprehensive logging, validation tracking, and summary table generation.

Related Requirements: FR1.12, UC1.6
Related Tasks: T050
Related Architecture: CC3.1.3
Related Tests: AT1.55

Recent Changes (max 10):
- Initial comprehensive implementation with TestOutputManager
- Full RULES.md compliance (API-only, zero hardcoded values, comprehensive logging)
- Channel history management tests (user/channel/session scope)
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
    Manages comprehensive test output logging for AT1.55.
    Saves all inputs, outputs, validations, and generates summary tables.
    100% RULES.md compliant output management.
    """

    __test__ = False  # Prevent pytest from collecting this as a test class

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.base_dir = Path("working") / "AT1.55_TEST_OUTPUTS" / test_name
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
def test_user(api_client):
    """Create a test user for channel history tests."""
    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    unique_id = str(uuid.uuid4())[:8]
    username = get_config("test.user.username")
    email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not username or not email or not password:
        pytest.fail(
            "Missing test.user.username/test.user.email/test.user.password in config (--env)"
        )

    user_data = {
        "username": f"{username}_at1_55_{unique_id}",
        "email": f"at1_55_{unique_id}_{email}",
        "password": password,
        "display_name": f"AT1.55 Test User {unique_id}",
        "role": "user",
    }

    response = api_client.post("/users", json=user_data)
    assert response.status_code == 200, f"Failed to create test user: {response.text}"
    user = response.json()

    yield user

    # Cleanup
    api_client.delete(f"/users/{user['id']}")
    api_client.session.headers.pop("X-API-Key", None)


@pytest.fixture
def test_expert(api_client):
    """Create a test expert configuration."""
    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    unique_id = str(uuid.uuid4())[:8]
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")

    expert_data = {
        "name": f"AT1.55 Test Expert {unique_id}",
        "title": f"AT1.55 Test Expert {unique_id}",
        "description": f"Comprehensive test expert configuration for AT1.55 channel history management testing with user, channel, and session scope validation - {unique_id}",
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


@pytest.fixture
def test_channel(api_client, test_expert):
    """Create a test channel with history scope."""
    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    unique_id = str(uuid.uuid4())[:8]
    channel_data = {
        "name": f"AT1.55 Test Channel {unique_id}",
        "expert_config_id": test_expert["id"],
        "description": f"Test channel for AT1.55 history management - {unique_id}",
        "history_scope": "channel",  # Test channel-scoped history
        "enabled": True,
    }

    response = api_client.post("/channels", json=channel_data)
    assert response.status_code == 200, f"Failed to create test channel: {response.text}"
    channel = response.json()

    yield channel

    # Cleanup
    api_client.delete(f"/channels/{channel['id']}")
    api_client.session.headers.pop("X-API-Key", None)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-007")


def test_AT1_55a_channel_history_scope_user(api_client, test_channel, test_user):
    """AT1.55a: Channel with user-scoped history"""
    mgr = TestOutputManager("AT1_55a_channel_history_scope_user")
    mgr.log_console("TEST START: AT1.55a - Channel History Scope User")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Get channel history with user scope
    params = {"scope": "user", "user_id": test_user["id"]}
    mgr.save_input("get_history_user_scope", params)

    response = api_client.get(f"/channels/{test_channel['id']}/history", params=params)
    mgr.save_output("get_history_user_scope", response)

    mgr.validate(
        "status_code",
        response.status_code == 200,
        response.status_code,
        200,
        "GET channel history user scope",
    )

    if response.status_code == 200:
        data = response.json()
        mgr.validate(
            "has_messages",
            "messages" in data,
            "messages" in data,
            True,
            "Response has messages field",
        )
        mgr.validate(
            "has_scope", data.get("scope") == "user", data.get("scope"), "user", "Scope is user"
        )
        mgr.validate(
            "has_count", "count" in data, "count" in data, True, "Response has count field"
        )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-007")


def test_AT1_55b_channel_history_scope_channel(api_client, test_channel):
    """AT1.55b: Channel with channel-scoped history"""
    mgr = TestOutputManager("AT1_55b_channel_history_scope_channel")
    mgr.log_console("TEST START: AT1.55b - Channel History Scope Channel")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Get channel history with channel scope (default)
    params = {"scope": "channel"}
    mgr.save_input("get_history_channel_scope", params)

    response = api_client.get(f"/channels/{test_channel['id']}/history", params=params)
    mgr.save_output("get_history_channel_scope", response)

    mgr.validate(
        "status_code",
        response.status_code == 200,
        response.status_code,
        200,
        "GET channel history channel scope",
    )

    if response.status_code == 200:
        data = response.json()
        mgr.validate(
            "has_messages",
            "messages" in data,
            "messages" in data,
            True,
            "Response has messages field",
        )
        mgr.validate(
            "has_scope",
            data.get("scope") == "channel",
            data.get("scope"),
            "channel",
            "Scope is channel",
        )
        mgr.validate(
            "has_count", "count" in data, "count" in data, True, "Response has count field"
        )
        mgr.validate(
            "messages_is_list",
            isinstance(data.get("messages"), list),
            type(data.get("messages")),
            list,
            "Messages is a list",
        )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-007")


def test_AT1_55c_channel_history_scope_session(api_client, test_channel, test_user, test_expert):
    """AT1.55c: Channel with session-scoped history"""
    mgr = TestOutputManager("AT1_55c_channel_history_scope_session")
    mgr.log_console("TEST START: AT1.55c - Channel History Scope Session")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Create a test session
    session_data = {
        "user_id": test_user["id"],
        "expert_config_id": test_expert["id"],
        "title": f"AT1.55c Test Session {uuid.uuid4()}",
    }
    session_response = api_client.post("/sessions", json=session_data)
    mgr.validate(
        "session_created",
        session_response.status_code == 200,
        session_response.status_code,
        200,
        "Session created",
    )

    if session_response.status_code == 200:
        session = session_response.json()
        session_id = session["id"]

        # Send a message via channel chat to create history
        chat_data = {
            "message": "Test message for session history",
            "user_id": test_user["id"],
            "session_id": session_id,
        }
        mgr.save_input("channel_chat", chat_data)
        chat_response = api_client.post(f"/channels/{test_channel['id']}/chat", json=chat_data)
        mgr.save_output("channel_chat", chat_response)
        mgr.validate(
            "chat_success",
            chat_response.status_code == 200,
            chat_response.status_code,
            200,
            "Chat message sent",
        )

        # Get channel history with session scope
        params = {"scope": "session", "session_id": session_id}
        mgr.save_input("get_history_session_scope", params)

        response = api_client.get(f"/channels/{test_channel['id']}/history", params=params)
        mgr.save_output("get_history_session_scope", response)

        mgr.validate(
            "status_code",
            response.status_code == 200,
            response.status_code,
            200,
            "GET channel history session scope",
        )

        if response.status_code == 200:
            data = response.json()
            mgr.validate(
                "has_scope",
                data.get("scope") == "session",
                data.get("scope"),
                "session",
                "Scope is session",
            )
            mgr.validate(
                "has_messages",
                "messages" in data,
                "messages" in data,
                True,
                "Response has messages field",
            )
            mgr.validate(
                "message_count",
                data.get("count") >= 1,
                data.get("count"),
                ">=1",
                "At least 1 message in session",
            )
            mgr.validate(
                "messages_not_empty",
                len(data.get("messages", [])) > 0,
                len(data.get("messages", [])),
                ">0",
                "Messages list not empty",
            )

        # Cleanup
        api_client.delete(f"/sessions/{session_id}")

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-007")


def test_AT1_55d_channel_history_retrieval(api_client, test_channel):
    """AT1.55d: Retrieve channel history"""
    mgr = TestOutputManager("AT1_55d_channel_history_retrieval")
    mgr.log_console("TEST START: AT1.55d - Channel History Retrieval")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Get channel history (default scope)
    response = api_client.get(f"/channels/{test_channel['id']}/history")
    mgr.save_output("get_history", response)

    mgr.validate(
        "status_code", response.status_code == 200, response.status_code, 200, "GET channel history"
    )

    if response.status_code == 200:
        data = response.json()
        mgr.validate(
            "has_messages", "messages" in data, "messages" in data, True, "Has messages field"
        )
        mgr.validate("has_count", "count" in data, "count" in data, True, "Has count field")
        mgr.validate("has_limit", "limit" in data, "limit" in data, True, "Has limit field")
        mgr.validate("has_offset", "offset" in data, "offset" in data, True, "Has offset field")

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-007")


def test_AT1_55e_channel_history_pagination(api_client, test_channel):
    """AT1.55e: Channel history pagination"""
    mgr = TestOutputManager("AT1_55e_channel_history_pagination")
    mgr.log_console("TEST START: AT1.55e - Channel History Pagination")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    # Test pagination with limit and offset
    params = {"limit": 10, "offset": 0}
    mgr.save_input("get_history_paginated", params)

    response = api_client.get(f"/channels/{test_channel['id']}/history", params=params)
    mgr.save_output("get_history_paginated", response)

    mgr.validate(
        "status_code",
        response.status_code == 200,
        response.status_code,
        200,
        "GET channel history with pagination",
    )

    if response.status_code == 200:
        data = response.json()
        mgr.validate(
            "limit_respected",
            data.get("limit") == 10,
            data.get("limit"),
            10,
            "Limit parameter respected",
        )
        mgr.validate(
            "offset_respected",
            data.get("offset") == 0,
            data.get("offset"),
            0,
            "Offset parameter respected",
        )
        mgr.validate(
            "has_messages", "messages" in data, "messages" in data, True, "Has messages field"
        )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.llm, pytest.mark.smtp, pytest.mark.heavy]
