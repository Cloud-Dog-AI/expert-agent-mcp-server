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
Description: Comprehensive Application Test for Session Key and History Key Management.
Tests session key access, history key access, key rotation, and session sharing via real API server.
100% RULES.md compliant with comprehensive logging, validation tracking, and summary table generation.

Related Requirements: FR1.2, FR1.3, UC1.2
Related Tasks: T022, T023, T025
Related Architecture: CC2.1.2, CC2.1.1
Related Tests: AT1.11

Recent Changes (max 10):
- Initial comprehensive implementation with TestOutputManager
- Full RULES.md compliance (API-only, zero hardcoded values, comprehensive logging)
- Added comprehensive test scenarios covering all key management workflows
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
    Manages comprehensive test output logging for AT1.11.
    Saves all inputs, outputs, validations, and generates summary tables.
    100% RULES.md compliant output management.
    """

    __test__ = False  # Prevent pytest from collecting this as a test class

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.base_dir = Path("working") / "AT1.11_TEST_OUTPUTS" / test_name
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
        pytest.fail("test.api_key not configured (set in secrets env file)")
    return str(api_key)


@pytest.fixture
def test_user(api_client):
    """Create a test user for session key tests."""
    TestOutputManager("fixture_test_user")
    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    unique_id = str(uuid.uuid4())[:8]
    username = get_config("test.user.username")
    email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not username or not email or not password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in config")
    if "@" not in email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    domain = email.split("@", 1)[1]

    user_data = {
        "username": f"{username}_at1_11_{unique_id}",
        "email": f"at1_11_{unique_id}@{domain}",
        "password": password,
        "display_name": f"AT1.11 Test User {unique_id}",
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
        "name": f"AT1.11 Test Expert {unique_id}",
        "title": f"AT1.11 Test Expert {unique_id}",
        "description": f"Test expert configuration for AT1.11 session key management tests - {unique_id}",
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
    """Create a test session with keys."""
    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    session_data = {
        "user_id": test_user["id"],
        "expert_config_id": test_expert["id"],
        "title": f"AT1.11 Test Session {uuid.uuid4()}",
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


def test_AT1_11a_get_session_by_session_key(api_client, test_session):
    """AT1.11a: Get session by session key"""
    mgr = TestOutputManager("AT1_11a_get_session_by_session_key")
    mgr.log_console("TEST START: AT1.11a - Get Session by Session Key")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    session_key = test_session.get("session_key")
    mgr.validate(
        "has_session_key",
        session_key is not None,
        session_key,
        "not None",
        "Session has session_key",
    )

    if session_key:
        response = api_client.get(f"/sessions/key/{session_key}")
        mgr.save_output("get_by_session_key", response)

        mgr.validate(
            "status_code",
            response.status_code == 200,
            response.status_code,
            200,
            "GET /sessions/key/{key}",
        )

        if response.status_code == 200:
            session = response.json()
            mgr.validate("has_id", "id" in session, "id" in session, True, "Has id field")
            mgr.validate(
                "has_title", "title" in session, "title" in session, True, "Has title field"
            )
            mgr.validate(
                "has_session_key",
                "session_key" in session,
                "session_key" in session,
                True,
                "Has session_key field",
            )
            mgr.validate(
                "session_id_match",
                session.get("id") == test_session["id"],
                session.get("id"),
                test_session["id"],
                "Session ID matches",
            )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_AT1_11b_get_history_by_history_key(api_client, test_session):
    """AT1.11b: Get history by history key"""
    mgr = TestOutputManager("AT1_11b_get_history_by_history_key")
    mgr.log_console("TEST START: AT1.11b - Get History by History Key")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    history_key = test_session.get("history_key")
    mgr.validate(
        "has_history_key",
        history_key is not None,
        history_key,
        "not None",
        "Session has history_key",
    )

    if history_key:
        response = api_client.get(f"/sessions/history/{history_key}")
        mgr.save_output("get_by_history_key", response)

        mgr.validate(
            "status_code",
            response.status_code == 200,
            response.status_code,
            200,
            "GET /sessions/history/{key}",
        )

        if response.status_code == 200:
            history = response.json()
            mgr.validate(
                "has_messages",
                "messages" in history or isinstance(history, list),
                True,
                True,
                "Has messages",
            )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_AT1_11c_rotate_session_key(api_client, test_session):
    """AT1.11c: Rotate session key"""
    mgr = TestOutputManager("AT1_11c_rotate_session_key")
    mgr.log_console("TEST START: AT1.11c - Rotate Session Key")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    original_key = test_session.get("session_key")

    response = api_client.post(f"/sessions/{test_session['id']}/rotate-key")
    mgr.save_output("rotate_key", response)

    mgr.validate(
        "status_code",
        response.status_code == 200,
        response.status_code,
        200,
        "POST /sessions/{id}/rotate-key",
    )

    if response.status_code == 200:
        result = response.json()
        mgr.validate(
            "has_session_key",
            "session_key" in result,
            "session_key" in result,
            True,
            "Has new session_key",
        )
        new_key = result.get("session_key")
        mgr.validate(
            "key_changed",
            new_key != original_key,
            f"{new_key} != {original_key}",
            True,
            "Key changed",
        )

        # Verify new key works
        if new_key:
            verify_response = api_client.get(f"/sessions/key/{new_key}")
            mgr.save_output("verify_new_key", verify_response)
            mgr.validate(
                "new_key_works",
                verify_response.status_code == 200,
                verify_response.status_code,
                200,
                "New key works",
            )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_AT1_11d_share_session(api_client, test_session, test_user):
    """AT1.11d: Share session with users"""
    mgr = TestOutputManager("AT1_11d_share_session")
    mgr.log_console("TEST START: AT1.11d - Share Session")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    share_data = {"user_ids": [test_user["id"]], "group_ids": []}
    mgr.save_input("share_session", share_data)

    response = api_client.post(f"/sessions/{test_session['id']}/share", json=share_data)
    mgr.save_output("share_session", response)

    mgr.validate(
        "status_code",
        response.status_code == 200,
        response.status_code,
        200,
        "POST /sessions/{id}/share",
    )

    if response.status_code == 200:
        result = response.json()
        mgr.validate(
            "has_result", result is not None, result is not None, True, "Share result returned"
        )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_AT1_11e_invalid_session_key_404(api_client):
    """AT1.11e: Invalid session key returns 404"""
    mgr = TestOutputManager("AT1_11e_invalid_session_key_404")
    mgr.log_console("TEST START: AT1.11e - Invalid Session Key 404")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    invalid_key = "invalid-session-key-" + str(uuid.uuid4())

    response = api_client.get(f"/sessions/key/{invalid_key}")
    mgr.save_output("invalid_key", response)

    mgr.validate(
        "status_code",
        response.status_code == 404,
        response.status_code,
        404,
        "Invalid key returns 404",
    )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_AT1_11f_invalid_history_key_404(api_client):
    """AT1.11f: Invalid history key returns 404"""
    mgr = TestOutputManager("AT1_11f_invalid_history_key_404")
    mgr.log_console("TEST START: AT1.11f - Invalid History Key 404")

    admin_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_key

    invalid_key = "invalid-history-key-" + str(uuid.uuid4())

    response = api_client.get(f"/sessions/history/{invalid_key}")
    mgr.save_output("invalid_history_key", response)

    mgr.validate(
        "status_code",
        response.status_code == 404,
        response.status_code,
        404,
        "Invalid history key returns 404",
    )

    api_client.session.headers.pop("X-API-Key", None)
    mgr.generate_summary_table()
    assert all(v["passed"] for v in mgr.validations), f"Validations failed in {mgr.test_name}"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]
