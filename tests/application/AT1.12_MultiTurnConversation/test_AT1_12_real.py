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
Description: Comprehensive Application Test for Multi-turn Conversation with Context Retention.
Tests multi-turn conversations, context retention, message ordering, and conversation flow via real API server.
100% RULES.md compliant with comprehensive logging, validation tracking, and summary table generation.

Related Requirements: FR1.2, FR1.3
Related Tasks: T022, T010, T024
Related Architecture: CC2.1.1, CC2.1.2
Related Tests: AT1.12

Recent Changes (max 10):
- Initial comprehensive implementation with TestOutputManager
- Full RULES.md compliance (API-only, zero hardcoded values, comprehensive logging)
- Multi-turn conversation tests with context retention
- Message ordering and conversation flow validation
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
from test_helpers_common import create_api_client_fixture, get_admin_api_key, validate_config_loaded


class TestOutputManager:
    """
    Manages comprehensive test output logging for AT1.12.
    Saves all inputs, outputs, validations, and generates summary tables.
    100% RULES.md compliant output management.
    """

    __test__ = False  # Prevent pytest from collecting this as a test class

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.base_dir = Path("working") / "AT1.12_TEST_OUTPUTS" / test_name
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


@pytest.fixture
def test_user(api_client):
    """Create a test user for multi-turn conversation tests."""
    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    unique_id = str(uuid.uuid4())[:8]
    username = get_config("test.user.username")
    email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not username or not email or not password:
        pytest.fail(
            "Missing required test user configuration: test.user.username, test.user.email, test.user.password"
        )

    user_data = {
        "username": f"{username}_at1_12_{unique_id}",
        "email": f"at1_12_{unique_id}_{email}",
        "password": password,
        "display_name": f"AT1.12 Test User {unique_id}",
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
    if not llm_provider or not llm_model:
        pytest.fail("Missing required LLM configuration: llm.provider and llm.model")

    expert_data = {
        "name": f"AT1.12 Test Expert {unique_id}",
        "title": f"AT1.12 Multi Turn Expert {unique_id} context retention ordering recall consistency grounding",
        "description": f"Comprehensive test expert configuration for AT1.12 multi-turn conversation testing with context retention and message ordering validation - {unique_id}",
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
def test_session(api_client, test_user, test_expert):
    """Create a test session and activate it."""
    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    session_data = {
        "user_id": test_user["id"],
        "expert_config_id": test_expert["id"],
        "title": f"AT1.12 Multi-turn Test {uuid.uuid4()}",
        "context_window": 4096,
        "history_retention_days": 30,
    }

    response = api_client.post("/sessions", json=session_data)
    assert response.status_code == 200, f"Failed to create test session: {response.text}"
    session = response.json()

    yield session

    # Cleanup
    api_client.delete(f"/sessions/{session['id']}")
    api_client.session.headers.pop("X-API-Key", None)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_AT1_12a_multi_turn_conversation_basic(api_client, test_session):
    """AT1.12a: Basic multi-turn conversation with 3 messages"""
    mgr = TestOutputManager("AT1_12a_multi_turn_conversation_basic")
    mgr.log_console("TEST START: AT1.12a - Basic Multi-turn Conversation")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    session_id = test_session["id"]

    # Message 1
    msg1_data = {"role": "user", "content": "Hello, what is your name?"}
    mgr.save_input("message_1", msg1_data)
    response1 = api_client.post(f"/sessions/{session_id}/messages", json=msg1_data)
    mgr.save_output("message_1", response1)
    mgr.validate(
        "msg1_status", response1.status_code == 200, response1.status_code, 200, "Message 1 added"
    )

    # Message 2
    msg2_data = {"role": "user", "content": "What was my first question?"}
    mgr.save_input("message_2", msg2_data)
    response2 = api_client.post(f"/sessions/{session_id}/messages", json=msg2_data)
    mgr.save_output("message_2", response2)
    mgr.validate(
        "msg2_status", response2.status_code == 200, response2.status_code, 200, "Message 2 added"
    )

    # Message 3
    msg3_data = {"role": "user", "content": "Can you remember our conversation?"}
    mgr.save_input("message_3", msg3_data)
    response3 = api_client.post(f"/sessions/{session_id}/messages", json=msg3_data)
    mgr.save_output("message_3", response3)
    mgr.validate(
        "msg3_status", response3.status_code == 200, response3.status_code, 200, "Message 3 added"
    )

    # Get all messages
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    mgr.save_output("get_messages", get_response)
    mgr.validate(
        "get_status", get_response.status_code == 200, get_response.status_code, 200, "GET messages"
    )

    if get_response.status_code == 200:
        data = get_response.json()
        mgr.validate("has_messages", "messages" in data, "messages" in data, True, "Has messages")
        messages = data.get("messages", [])
        mgr.validate(
            "message_count", len(messages) >= 3, len(messages), ">=3", "At least 3 messages"
        )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_AT1_12b_message_ordering(api_client, test_session):
    """AT1.12b: Verify message ordering is preserved"""
    mgr = TestOutputManager("AT1_12b_message_ordering")
    mgr.log_console("TEST START: AT1.12b - Message Ordering")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    session_id = test_session["id"]

    # Add 5 messages in sequence
    messages_content = [
        "First message",
        "Second message",
        "Third message",
        "Fourth message",
        "Fifth message",
    ]

    for i, content in enumerate(messages_content, 1):
        msg_data = {"role": "user", "content": content}
        mgr.save_input(f"message_{i}", msg_data)
        response = api_client.post(f"/sessions/{session_id}/messages", json=msg_data)
        mgr.save_output(f"message_{i}", response)
        mgr.validate(
            f"msg{i}_status",
            response.status_code == 200,
            response.status_code,
            200,
            f"Message {i} added",
        )

    # Get messages and verify order
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    mgr.save_output("get_messages", get_response)
    mgr.validate(
        "get_status", get_response.status_code == 200, get_response.status_code, 200, "GET messages"
    )

    if get_response.status_code == 200:
        data = get_response.json()
        messages = data.get("messages", [])
        mgr.validate(
            "has_5_messages", len(messages) >= 5, len(messages), ">=5", "At least 5 messages"
        )

        # Verify ordering (messages should be in chronological order)
        if len(messages) >= 2:
            for i in range(max(0, len(messages) - 1)):
                msg_i = messages[i]
                msg_next = messages[i + 1]
                # Compare timestamps
                time_i = msg_i.get("timestamp", "")
                time_next = msg_next.get("timestamp", "")
                mgr.validate(
                    f"order_{i}",
                    time_i <= time_next,
                    f"{time_i} <= {time_next}",
                    True,
                    f"Message {i} before {i + 1}",
                )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_AT1_12c_context_retention(api_client, test_session):
    """AT1.12c: Verify context is retained across messages"""
    mgr = TestOutputManager("AT1_12c_context_retention")
    mgr.log_console("TEST START: AT1.12c - Context Retention")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    session_id = test_session["id"]

    # Add contextual messages
    msg1 = {"role": "user", "content": "My favorite color is blue"}
    response1 = api_client.post(f"/sessions/{session_id}/messages", json=msg1)
    mgr.save_output("context_message", response1)
    mgr.validate(
        "context_added",
        response1.status_code == 200,
        response1.status_code,
        200,
        "Context message added",
    )

    # Add more messages
    msg2 = {"role": "user", "content": "I like programming in Python"}
    response2 = api_client.post(f"/sessions/{session_id}/messages", json=msg2)
    mgr.validate(
        "msg2_added", response2.status_code == 200, response2.status_code, 200, "Message 2 added"
    )

    msg3 = {"role": "user", "content": "What is my favorite color?"}
    response3 = api_client.post(f"/sessions/{session_id}/messages", json=msg3)
    mgr.validate(
        "msg3_added", response3.status_code == 200, response3.status_code, 200, "Message 3 added"
    )

    # Retrieve all messages
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    mgr.save_output("all_messages", get_response)
    mgr.validate(
        "get_status", get_response.status_code == 200, get_response.status_code, 200, "GET messages"
    )

    if get_response.status_code == 200:
        data = get_response.json()
        messages = data.get("messages", [])
        mgr.validate("has_messages", len(messages) >= 3, len(messages), ">=3", "Has all messages")

        # Verify first message content is preserved
        if messages:
            first_msg = messages[0]
            mgr.validate(
                "first_msg_content",
                "blue" in first_msg.get("content", "").lower(),
                True,
                True,
                "First message preserved",
            )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_AT1_12d_pagination(api_client, test_session):
    """AT1.12d: Test message pagination with limit and offset"""
    mgr = TestOutputManager("AT1_12d_pagination")
    mgr.log_console("TEST START: AT1.12d - Message Pagination")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    session_id = test_session["id"]

    # Add 10 messages
    message_count = int(get_config("test.at1_12.message_counts.short"))
    for i in range(message_count):
        msg_data = {"role": "user", "content": f"Message number {i + 1}"}
        response = api_client.post(f"/sessions/{session_id}/messages", json=msg_data)
        mgr.validate(
            f"msg{i + 1}_added",
            response.status_code == 200,
            response.status_code,
            200,
            f"Message {i + 1} added",
        )

    # Test pagination - first 5
    limit = int(get_config("test.at1_10.truncation.limits.low"))
    response1 = api_client.get(f"/sessions/{session_id}/messages?limit={limit}&offset=0")
    mgr.save_output("first_page", response1)
    mgr.validate(
        "page1_status", response1.status_code == 200, response1.status_code, 200, "First page"
    )

    if response1.status_code == 200:
        data1 = response1.json()
        messages1 = data1.get("messages", [])
        mgr.validate(
            "page1_count",
            len(messages1) <= limit,
            len(messages1),
            f"<={limit}",
            "First page has <=limit messages",
        )

    # Test pagination - next 5
    response2 = api_client.get(f"/sessions/{session_id}/messages?limit={limit}&offset={limit}")
    mgr.save_output("second_page", response2)
    mgr.validate(
        "page2_status", response2.status_code == 200, response2.status_code, 200, "Second page"
    )

    if response2.status_code == 200:
        data2 = response2.json()
        messages2 = data2.get("messages", [])
        mgr.validate(
            "page2_count",
            len(messages2) <= limit,
            len(messages2),
            f"<={limit}",
            "Second page has <=limit messages",
        )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_AT1_12e_empty_session_messages(api_client, test_session):
    """AT1.12e: Get messages from empty session"""
    mgr = TestOutputManager("AT1_12e_empty_session_messages")
    mgr.log_console("TEST START: AT1.12e - Empty Session Messages")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    session_id = test_session["id"]

    # Get messages from empty session
    response = api_client.get(f"/sessions/{session_id}/messages")
    mgr.save_output("empty_messages", response)

    mgr.validate(
        "status_code", response.status_code == 200, response.status_code, 200, "GET empty messages"
    )

    if response.status_code == 200:
        data = response.json()
        mgr.validate(
            "has_messages_key", "messages" in data, "messages" in data, True, "Has messages key"
        )
        messages = data.get("messages", [])
        mgr.validate("empty_list", len(messages) == 0, len(messages), 0, "Empty message list")

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

