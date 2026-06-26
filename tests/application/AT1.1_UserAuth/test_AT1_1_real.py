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
Description: Comprehensive Application Test for User Registration and Authentication.
Tests user registration, login, logout, token validation, password management, and
authentication workflows via real API server. 100% RULES.md compliant with comprehensive
logging, validation tracking, and summary table generation.

Related Requirements: CS1.1, FR1.5, UC1.1, UC1.2
Related Tasks: T005, T006
Related Architecture: SE1.1, CC5.1.1, AI1.1
Related Tests: AT1.1

Recent Changes (max 10):
- Initial comprehensive implementation with TestOutputManager
- Full RULES.md compliance (API-only, zero hardcoded values, comprehensive logging)
- Added 12 comprehensive test scenarios covering all auth workflows
- Validation tracking with file output for all assertions
- Summary table generation with clickable file:// URIs
**************************************************
"""

import pytest
import time
import uuid
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any

from src.config.loader import get_config

# Shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import build_test_email, create_api_client_fixture, validate_config_loaded


class TestOutputManager:
    """
    Manages comprehensive test output logging for AT1.1.
    Saves all inputs, outputs, validations, and generates summary tables.
    100% RULES.md compliant output management.
    """

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.base_dir = Path("working") / "AT1.1_TEST_OUTPUTS" / test_name
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

    def save_output(self, operation: str, data: Any) -> Path:
        """Save output data with sequential numbering."""
        self.output_counter += 1
        filename = f"{self.output_counter:02d}_{operation}_output.json"
        filepath = self.outputs_dir / filename

        # Handle different response types
        if hasattr(data, "json"):
            try:
                output_data = data.json()
            except Exception:
                output_data = {"status_code": data.status_code, "text": data.text}
        elif isinstance(data, dict):
            output_data = data
        else:
            output_data = {"value": str(data)}

        with open(filepath, "w") as f:
            json.dump(output_data, f, indent=2, default=str)

        self.log_console(f"Output saved: {operation} -> {filepath.name}")
        return filepath

    def validate(
        self, name: str, condition: bool, actual: Any, expected: Any, context: str = ""
    ) -> bool:
        """
        Record validation result with full details.
        Saves to file and tracks in memory.
        """
        self.validation_counter += 1

        validation_result = {
            "number": self.validation_counter,
            "name": name,
            "passed": condition,
            "actual": str(actual),
            "expected": str(expected),
            "context": context,
            "timestamp": datetime.now().isoformat(),
        }

        self.validations.append(validation_result)

        # Save to file
        filename = f"{self.validation_counter:02d}_{name}.json"
        filepath = self.validations_dir / filename

        with open(filepath, "w") as f:
            json.dump(validation_result, f, indent=2)

        # Log result
        status = "✅ PASS" if condition else "❌ FAIL"
        self.log_console(f"[VALIDATION {self.validation_counter:02d}] {status}: {name}")
        if not condition:
            self.log_console(f"  Expected: {expected}")
            self.log_console(f"  Actual: {actual}")
            if context:
                self.log_console(f"  Context: {context}")

        return condition

    def generate_summary_table(self) -> str:
        """Generate comprehensive markdown summary table with clickable file:// URIs."""
        duration = (datetime.now() - self.start_time).total_seconds()

        table = "\n" + "=" * 80 + "\n"
        table += f"TEST SUMMARY: {self.test_name}\n"
        table += "=" * 80 + "\n\n"

        # Console log
        table += "## CONSOLE LOG\n"
        console_file = self.base_dir / "console.log"
        with open(console_file, "w") as f:
            f.write("\n".join(self.console_log))
        table += f"- [{console_file.name}]({console_file.resolve().as_uri()})\n\n"

        # Inputs
        table += "## INPUTS\n"
        input_files = sorted(self.inputs_dir.glob("*.json"))
        if input_files:
            for f in input_files:
                table += f"- [{f.name}]({f.resolve().as_uri()})\n"
        else:
            table += "- No inputs recorded\n"
        table += "\n"

        # Outputs
        table += "## OUTPUTS\n"
        output_files = sorted(self.outputs_dir.glob("*.json"))
        if output_files:
            for f in output_files:
                table += f"- [{f.name}]({f.resolve().as_uri()})\n"
        else:
            table += "- No outputs recorded\n"
        table += "\n"

        # Validations
        table += "## VALIDATIONS\n"
        validation_files = sorted(self.validations_dir.glob("*.json"))
        if validation_files:
            for f in validation_files:
                table += f"- [{f.name}]({f.resolve().as_uri()})\n"
        else:
            table += "- No validations recorded\n"
        table += "\n"

        # Results summary
        table += "## RESULTS\n"
        passed = sum(1 for v in self.validations if v["passed"])
        total = len(self.validations)
        pass_rate = (passed / total * 100) if total > 0 else 0

        table += f"- **Total Validations**: {total}\n"
        table += f"- **Passed**: {passed}\n"
        table += f"- **Failed**: {total - passed}\n"
        table += f"- **Pass Rate**: {pass_rate:.1f}%\n"
        table += f"- **Duration**: {duration:.2f}s\n\n"

        table += "=" * 80 + "\n"

        return table


@pytest.fixture(scope="module")
def api_client():
    """Create API client that connects to real running API server."""
    validate_config_loaded()
    return create_api_client_fixture(check_health=True)()


@pytest.fixture
def base_user_credentials():
    """Base test user credentials from config hierarchy (RULES.md compliant)."""
    username = get_config("test.user.username")
    email = get_config("test.user.email")
    password = get_config("test.user.password")
    display_name = get_config("test.user.display_name")

    if not username or not email or not password:
        pytest.fail(
            "Missing required test user configuration. "
            "Set test.user.username, test.user.email, test.user.password in --env file. "
            "RULES.md violation: Zero hardcoded values required."
        )

    return {
        "username": username,
        "email": email,
        "password": password,
        "display_name": display_name or username,
    }


@pytest.fixture
def unique_user_credentials(base_user_credentials):
    """Generate unique user credentials for test isolation."""
    unique_id = str(uuid.uuid4())[:8]
    base = base_user_credentials
    return {
        "username": f"{base['username']}_at1_1_{unique_id}",
        "email": build_test_email("at1_1", unique_id, base["email"]),
        "password": base["password"],
        "display_name": f"{base['display_name']} AT1.1 {unique_id}",
    }


def get_auth_token(api_client, username: str, password: str) -> str:
    """
    Helper function to get authentication token via login.
    Used for token-based authentication in tests (Option B).

    Args:
        api_client: API client instance
        username: Username for login
        password: Password for login

    Returns:
        JWT token string
    """
    login_response = api_client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    if login_response.status_code != 200:
        raise ValueError(f"Login failed: {login_response.status_code} - {login_response.text}")
    return login_response.json()["token"]
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_1a_user_registration_success(api_client, unique_user_credentials):
    """
    AT1.1a: User registration with valid credentials.
    Tests successful user creation via POST /auth/register endpoint.
    Validates response structure, status codes, and data persistence.
    """
    mgr = TestOutputManager("AT1_1a_user_registration_success")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.1a - User Registration Success")
    mgr.log_console("=" * 80)

    creds = unique_user_credentials

    # Create user payload
    create_payload = {
        "username": creds["username"],
        "email": creds["email"],
        "password": creds["password"],
        "display_name": creds["display_name"],
    }

    mgr.save_input("create_user", create_payload)

    # Execute: Create user via API
    mgr.log_console(f"Creating user: {creds['username']}")
    response = api_client.post("/auth/register", json=create_payload)

    mgr.save_output("create_user", response)

    # Validate: Response status
    mgr.validate(
        "create_status_200",
        response.status_code == 200,
        response.status_code,
        200,
        "User creation should return 200 OK",
    )

    data = response.json()

    # Validate: Response structure
    mgr.validate("id_present", "id" in data, "id" in data, True, "Response must contain user ID")
    mgr.validate(
        "username_matches",
        data.get("username") == creds["username"],
        data.get("username"),
        creds["username"],
        "Username in response must match request",
    )
    mgr.validate(
        "email_matches",
        data.get("email") == creds["email"],
        data.get("email"),
        creds["email"],
        "Email in response must match request",
    )
    mgr.validate(
        "display_name_matches",
        data.get("display_name") == creds["display_name"],
        data.get("display_name"),
        creds["display_name"],
        "Display name in response must match request",
    )
    mgr.validate(
        "role_is_user",
        data.get("role") == "user",
        data.get("role"),
        "user",
        "Role should be set to 'user'",
    )
    mgr.validate(
        "enabled_is_true",
        data.get("enabled") is True,
        data.get("enabled"),
        True,
        "User should be enabled by default",
    )
    mgr.validate(
        "created_at_present",
        "created_at" in data,
        "created_at" in data,
        True,
        "Response must contain created_at timestamp",
    )

    user_id = data.get("id")

    # Login to get authentication token for subsequent operations
    mgr.log_console(f"Logging in as {creds['username']} to get auth token")
    token = get_auth_token(api_client, creds["username"], creds["password"])

    # Verify: User persists in database (using token auth)
    # Note: Remove X-API-Key header temporarily to use Bearer token
    mgr.log_console(f"Retrieving user {user_id} to verify persistence")
    saved_api_key = api_client.session.headers.pop("X-API-Key", None)
    get_response = api_client.get(f"/users/{user_id}", headers={"Authorization": f"Bearer {token}"})
    if saved_api_key:
        api_client.session.headers["X-API-Key"] = saved_api_key
    mgr.save_output("get_user", get_response)

    mgr.validate(
        "get_status_200",
        get_response.status_code == 200,
        get_response.status_code,
        200,
        "User retrieval should return 200 OK",
    )

    get_data = get_response.json()
    mgr.validate(
        "persisted_username_matches",
        get_data.get("username") == creds["username"],
        get_data.get("username"),
        creds["username"],
        "Persisted username must match original",
    )
    mgr.validate(
        "persisted_email_matches",
        get_data.get("email") == creds["email"],
        get_data.get("email"),
        creds["email"],
        "Persisted email must match original",
    )

    # Cleanup: Delete user (using admin API key - DELETE requires admin)
    mgr.log_console(f"Cleaning up: Deleting user {user_id}")
    delete_response = api_client.delete(f"/users/{user_id}")
    mgr.save_output("delete_user", delete_response)
    mgr.validate(
        "cleanup_delete_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
        "User deletion should succeed",
    )

    # Print summary
    summary = mgr.generate_summary_table()
    print(summary)

    # Assert all validations passed
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_1b_user_registration_duplicate_username(api_client, unique_user_credentials):
    """
    AT1.1b: User registration with duplicate username.
    Tests that system rejects duplicate usernames with appropriate error.
    """
    mgr = TestOutputManager("AT1_1b_duplicate_username_rejection")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.1b - Duplicate Username Rejection")
    mgr.log_console("=" * 80)

    creds = unique_user_credentials

    # Create first user
    create_payload1 = {
        "username": creds["username"],
        "email": creds["email"],
        "password": creds["password"],
        "display_name": creds["display_name"],
    }

    mgr.save_input("create_user_first", create_payload1)
    response1 = api_client.post("/auth/register", json=create_payload1)
    mgr.save_output("create_user_first", response1)

    mgr.validate(
        "first_user_created",
        response1.status_code == 200,
        response1.status_code,
        200,
        "First user creation should succeed",
    )

    user_id = response1.json().get("id")

    # Attempt to create duplicate username with different email
    dup_email = f"dup_{uuid.uuid4().hex[:8]}@{creds['email'].split('@')[1]}"
    create_payload2 = {
        "username": creds["username"],  # Same username
        "email": dup_email,  # Different email
        "password": creds["password"],
        "display_name": f"{creds['display_name']} Duplicate",
    }

    mgr.save_input("create_user_duplicate", create_payload2)
    response2 = api_client.post("/auth/register", json=create_payload2)
    mgr.save_output("create_user_duplicate", response2)

    # Validate: Duplicate should be rejected
    mgr.validate(
        "duplicate_rejected",
        response2.status_code == 400,
        response2.status_code,
        400,
        "Duplicate username should return 400 Bad Request",
    )

    # Cleanup
    delete_response = api_client.delete(f"/users/{user_id}")
    mgr.validate(
        "cleanup_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_1c_user_registration_duplicate_email(api_client, unique_user_credentials):
    """
    AT1.1c: User registration with duplicate email.
    Tests that system rejects duplicate emails with appropriate error.
    """
    mgr = TestOutputManager("AT1_1c_duplicate_email_rejection")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.1c - Duplicate Email Rejection")
    mgr.log_console("=" * 80)

    creds = unique_user_credentials

    # Create first user
    create_payload1 = {
        "username": creds["username"],
        "email": creds["email"],
        "password": creds["password"],
        "display_name": creds["display_name"],
    }

    mgr.save_input("create_user_first", create_payload1)
    response1 = api_client.post("/auth/register", json=create_payload1)
    mgr.save_output("create_user_first", response1)

    mgr.validate("first_user_created", response1.status_code == 200, response1.status_code, 200)

    user_id = response1.json().get("id")

    # Attempt to create duplicate email with different username
    dup_username = f"dup_{uuid.uuid4().hex[:8]}"
    create_payload2 = {
        "username": dup_username,  # Different username
        "email": creds["email"],  # Same email
        "password": creds["password"],
        "display_name": f"{creds['display_name']} Duplicate",
    }

    mgr.save_input("create_user_duplicate", create_payload2)
    response2 = api_client.post("/auth/register", json=create_payload2)
    mgr.save_output("create_user_duplicate", response2)

    # Validate: Duplicate should be rejected
    mgr.validate(
        "duplicate_rejected",
        response2.status_code == 400,
        response2.status_code,
        400,
        "Duplicate email should return 400 Bad Request",
    )

    # Cleanup
    delete_response = api_client.delete(f"/users/{user_id}")
    mgr.validate(
        "cleanup_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_1d_user_login_success(api_client, unique_user_credentials):
    """
    AT1.1d: User login with valid credentials.
    Tests successful authentication via POST /auth/login endpoint.
    Validates token generation and structure.
    """
    mgr = TestOutputManager("AT1_1d_user_login_success")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.1d - User Login Success")
    mgr.log_console("=" * 80)

    creds = unique_user_credentials

    # Create user first
    create_payload = {
        "username": creds["username"],
        "email": creds["email"],
        "password": creds["password"],
        "display_name": creds["display_name"],
    }

    mgr.save_input("create_user", create_payload)
    create_response = api_client.post("/auth/register", json=create_payload)
    mgr.save_output("create_user", create_response)

    mgr.validate(
        "user_created", create_response.status_code == 200, create_response.status_code, 200
    )

    user_id = create_response.json().get("id")

    # Login with valid credentials
    login_payload = {"username": creds["username"], "password": creds["password"]}

    mgr.save_input("login", login_payload)
    login_response = api_client.post("/auth/login", json=login_payload)
    mgr.save_output("login", login_response)

    # Validate: Login success
    mgr.validate(
        "login_status_200",
        login_response.status_code == 200,
        login_response.status_code,
        200,
        "Login should return 200 OK",
    )

    login_data = login_response.json()

    mgr.validate(
        "token_present",
        "token" in login_data,
        "token" in login_data,
        True,
        "Login response must contain token",
    )
    mgr.validate(
        "token_not_empty",
        len(login_data.get("token", "")) > 0,
        len(login_data.get("token", "")),
        "> 0",
        "Token must not be empty",
    )
    mgr.validate(
        "user_id_present",
        "user_id" in login_data,
        "user_id" in login_data,
        True,
        "Login response should contain user_id",
    )
    mgr.validate(
        "user_id_matches",
        login_data.get("user_id") == user_id,
        login_data.get("user_id"),
        user_id,
        "User ID in token should match created user",
    )

    # Cleanup
    delete_response = api_client.delete(f"/users/{user_id}")
    mgr.validate(
        "cleanup_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_1e_user_login_invalid_username(api_client):
    """
    AT1.1e: User login with invalid username.
    Tests that system rejects login with non-existent username.
    """
    mgr = TestOutputManager("AT1_1e_login_invalid_username")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.1e - Login Invalid Username")
    mgr.log_console("=" * 80)

    # Attempt login with non-existent user
    base_password = get_config("test.user.password")
    if not base_password:
        pytest.fail("Missing test.user.password in --env (required for login tests)")
    login_payload = {"username": f"nonexistent_{uuid.uuid4().hex[:8]}", "password": base_password}

    mgr.save_input("login_invalid", login_payload)
    login_response = api_client.post("/auth/login", json=login_payload)
    mgr.save_output("login_invalid", login_response)

    # Validate: Login should fail with 401
    mgr.validate(
        "login_rejected",
        login_response.status_code == 401,
        login_response.status_code,
        401,
        "Login with invalid username should return 401 Unauthorized",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_1f_user_login_invalid_password(api_client, unique_user_credentials):
    """
    AT1.1f: User login with invalid password.
    Tests that system rejects login with incorrect password.
    """
    mgr = TestOutputManager("AT1_1f_login_invalid_password")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.1f - Login Invalid Password")
    mgr.log_console("=" * 80)

    creds = unique_user_credentials

    # Create user
    create_payload = {
        "username": creds["username"],
        "email": creds["email"],
        "password": creds["password"],
        "display_name": creds["display_name"],
    }

    mgr.save_input("create_user", create_payload)
    create_response = api_client.post("/auth/register", json=create_payload)
    mgr.save_output("create_user", create_response)

    mgr.validate(
        "user_created", create_response.status_code == 200, create_response.status_code, 200
    )

    user_id = create_response.json().get("id")

    # Attempt login with wrong password
    wrong_password = get_config("test.user.password_weak")
    if not wrong_password:
        pytest.fail(
            "Missing test.user.password_weak in --env (required for invalid password tests)"
        )
    if wrong_password == creds["password"]:
        pytest.fail("test.user.password_weak must differ from test.user.password")
    login_payload = {"username": creds["username"], "password": wrong_password}

    mgr.save_input("login_wrong_password", login_payload)
    login_response = api_client.post("/auth/login", json=login_payload)
    mgr.save_output("login_wrong_password", login_response)

    # Validate: Login should fail
    mgr.validate(
        "login_rejected",
        login_response.status_code == 401,
        login_response.status_code,
        401,
        "Login with wrong password should return 401 Unauthorized",
    )

    # Cleanup
    delete_response = api_client.delete(f"/users/{user_id}")
    mgr.validate(
        "cleanup_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_1g_user_login_disabled_user(api_client, unique_user_credentials):
    """
    AT1.1g: User login with disabled account.
    Tests that system rejects login for disabled users.
    """
    mgr = TestOutputManager("AT1_1g_login_disabled_user")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.1g - Login Disabled User")
    mgr.log_console("=" * 80)

    creds = unique_user_credentials

    # Create user
    create_payload = {
        "username": creds["username"],
        "email": creds["email"],
        "password": creds["password"],
        "display_name": creds["display_name"],
    }

    mgr.save_input("create_user", create_payload)
    create_response = api_client.post("/auth/register", json=create_payload)
    mgr.save_output("create_user", create_response)

    mgr.validate(
        "user_created", create_response.status_code == 200, create_response.status_code, 200
    )

    user_id = create_response.json().get("id")

    # Disable user
    disable_payload = {"enabled": False}
    mgr.save_input("disable_user", disable_payload)
    disable_response = api_client.put(f"/users/{user_id}", json=disable_payload)
    mgr.save_output("disable_user", disable_response)

    mgr.validate(
        "user_disabled",
        disable_response.status_code == 200,
        disable_response.status_code,
        200,
        "User should be successfully disabled",
    )

    # Attempt login with disabled user
    login_payload = {"username": creds["username"], "password": creds["password"]}

    mgr.save_input("login_disabled", login_payload)
    login_response = api_client.post("/auth/login", json=login_payload)
    mgr.save_output("login_disabled", login_response)

    # Validate: Login should fail
    mgr.validate(
        "login_rejected",
        login_response.status_code == 401,
        login_response.status_code,
        401,
        "Login with disabled user should return 401 Unauthorized",
    )

    # Cleanup
    delete_response = api_client.delete(f"/users/{user_id}")
    mgr.validate(
        "cleanup_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_1h_user_logout_token_revocation(api_client, unique_user_credentials):
    """
    AT1.1h: User logout and token revocation.
    Tests that logout properly revokes authentication token.
    """
    mgr = TestOutputManager("AT1_1h_logout_token_revocation")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.1h - Logout Token Revocation")
    mgr.log_console("=" * 80)

    creds = unique_user_credentials

    # Create user
    create_payload = {
        "username": creds["username"],
        "email": creds["email"],
        "password": creds["password"],
        "display_name": creds["display_name"],
    }

    mgr.save_input("create_user", create_payload)
    create_response = api_client.post("/auth/register", json=create_payload)
    mgr.save_output("create_user", create_response)

    mgr.validate(
        "user_created", create_response.status_code == 200, create_response.status_code, 200
    )

    user_id = create_response.json().get("id")

    # Login
    login_payload = {"username": creds["username"], "password": creds["password"]}
    mgr.save_input("login", login_payload)
    login_response = api_client.post("/auth/login", json=login_payload)
    mgr.save_output("login", login_response)

    mgr.validate(
        "login_success", login_response.status_code == 200, login_response.status_code, 200
    )

    token = login_response.json().get("token")
    mgr.validate(
        "token_received",
        token is not None and len(token) > 0,
        bool(token),
        True,
        "Token should be received from login",
    )

    # Logout
    logout_payload = {"token": token}
    mgr.save_input("logout", logout_payload)
    logout_response = api_client.post("/auth/logout", json=logout_payload)
    mgr.save_output("logout", logout_response)

    mgr.validate(
        "logout_success",
        logout_response.status_code == 200,
        logout_response.status_code,
        200,
        "Logout should return 200 OK",
    )

    # Validate token is revoked
    validate_response = api_client.get(f"/auth/validate?token={token}")
    mgr.save_output("validate_after_logout", validate_response)

    mgr.validate(
        "validate_status_200",
        validate_response.status_code == 200,
        validate_response.status_code,
        200,
        "Validate endpoint should return 200",
    )

    validate_data = validate_response.json()
    mgr.validate(
        "token_invalid_after_logout",
        validate_data.get("valid") is False,
        validate_data.get("valid"),
        False,
        "Token should be invalid after logout",
    )

    # Cleanup
    delete_response = api_client.delete(f"/users/{user_id}")
    mgr.validate(
        "cleanup_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_1i_token_expiration(api_client, unique_user_credentials):
    """
    AT1.1i: Token expiration handling.
    Tests that tokens expire after specified duration.
    """
    mgr = TestOutputManager("AT1_1i_token_expiration")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.1i - Token Expiration")
    mgr.log_console("=" * 80)

    creds = unique_user_credentials

    # Create user
    create_payload = {
        "username": creds["username"],
        "email": creds["email"],
        "password": creds["password"],
        "display_name": creds["display_name"],
    }

    mgr.save_input("create_user", create_payload)
    create_response = api_client.post("/auth/register", json=create_payload)
    mgr.save_output("create_user", create_response)

    mgr.validate(
        "user_created", create_response.status_code == 200, create_response.status_code, 200
    )

    user_id = create_response.json().get("id")

    # Login with short expiration (1 second)
    login_payload = {
        "username": creds["username"],
        "password": creds["password"],
        "expires_in_seconds": 1,
    }

    mgr.save_input("login_short_expiry", login_payload)
    login_response = api_client.post("/auth/login", json=login_payload)
    mgr.save_output("login_short_expiry", login_response)

    mgr.validate(
        "login_success", login_response.status_code == 200, login_response.status_code, 200
    )

    token = login_response.json().get("token")

    # Wait for token to expire
    mgr.log_console("Waiting 2 seconds for token to expire...")
    time.sleep(2)

    # Validate token is expired
    validate_response = api_client.get(f"/auth/validate?token={token}")
    mgr.save_output("validate_after_expiry", validate_response)

    mgr.validate(
        "validate_status_200",
        validate_response.status_code == 200,
        validate_response.status_code,
        200,
    )

    validate_data = validate_response.json()
    mgr.validate(
        "token_expired",
        validate_data.get("valid") is False,
        validate_data.get("valid"),
        False,
        "Token should be invalid after expiration",
    )

    # Cleanup
    delete_response = api_client.delete(f"/users/{user_id}")
    mgr.validate(
        "cleanup_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_1j_external_user_registration(api_client, base_user_credentials):
    """
    AT1.1j: External user registration (no password).
    Tests creation of users managed by external auth providers.
    """
    mgr = TestOutputManager("AT1_1j_external_user_registration")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.1j - External User Registration")
    mgr.log_console("=" * 80)

    uid = uuid.uuid4().hex[:8]

    # Create external user (password=null)
    create_payload = {
        "username": f"external_{uid}",
        "email": build_test_email("external", uid, base_user_credentials["email"]),
        "password": None,  # External user - no password
        "display_name": f"External User {uid}",
    }

    mgr.save_input("create_external_user", create_payload)
    create_response = api_client.post("/auth/register", json=create_payload)
    mgr.save_output("create_external_user", create_response)

    # Validate: User created successfully
    mgr.validate(
        "user_created",
        create_response.status_code == 200,
        create_response.status_code,
        200,
        "External user should be created successfully",
    )

    user_id = create_response.json().get("id")

    # Attempt login with external user (should fail)
    wrong_password = get_config("test.user.password_weak")
    if not wrong_password:
        pytest.fail("Missing test.user.password_weak in --env (required for external login tests)")
    login_payload = {"username": f"external_{uid}", "password": wrong_password}

    mgr.save_input("login_external_user", login_payload)
    login_response = api_client.post("/auth/login", json=login_payload)
    mgr.save_output("login_external_user", login_response)

    # Validate: Login should fail (external users can't use password auth)
    mgr.validate(
        "login_rejected",
        login_response.status_code == 401,
        login_response.status_code,
        401,
        "External user login should fail with 401",
    )

    # Cleanup
    delete_response = api_client.delete(f"/users/{user_id}")
    mgr.validate(
        "cleanup_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_1k_user_password_change(api_client, unique_user_credentials):
    """
    AT1.1k: User password change.
    Tests password update functionality and validation.
    """
    mgr = TestOutputManager("AT1_1k_password_change")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.1k - Password Change")
    mgr.log_console("=" * 80)

    creds = unique_user_credentials

    # Create user
    create_payload = {
        "username": creds["username"],
        "email": creds["email"],
        "password": creds["password"],
        "display_name": creds["display_name"],
    }

    mgr.save_input("create_user", create_payload)
    create_response = api_client.post("/auth/register", json=create_payload)
    mgr.save_output("create_user", create_response)

    mgr.validate(
        "user_created", create_response.status_code == 200, create_response.status_code, 200
    )

    user_id = create_response.json().get("id")

    # Login to get authentication token
    token = get_auth_token(api_client, creds["username"], creds["password"])

    # Change password
    new_password = f"{creds['password']}_new"
    update_payload = {"password": new_password}

    mgr.save_input("update_password", update_payload)
    saved_api_key = api_client.session.headers.pop("X-API-Key", None)

    update_response = api_client.put(
        f"/users/{user_id}", json=update_payload, headers={"Authorization": f"Bearer {token}"}
    )

    if saved_api_key:
        api_client.session.headers["X-API-Key"] = saved_api_key
    mgr.save_output("update_password", update_response)

    mgr.validate(
        "password_updated",
        update_response.status_code == 200,
        update_response.status_code,
        200,
        "Password update should return 200 OK",
    )

    # Attempt login with old password (should fail)
    old_login_payload = {"username": creds["username"], "password": creds["password"]}
    mgr.save_input("login_old_password", old_login_payload)
    old_login_response = api_client.post("/auth/login", json=old_login_payload)
    mgr.save_output("login_old_password", old_login_response)

    mgr.validate(
        "old_password_rejected",
        old_login_response.status_code == 401,
        old_login_response.status_code,
        401,
        "Login with old password should fail",
    )

    # Login with new password (should succeed)
    new_login_payload = {"username": creds["username"], "password": new_password}
    mgr.save_input("login_new_password", new_login_payload)
    new_login_response = api_client.post("/auth/login", json=new_login_payload)
    mgr.save_output("login_new_password", new_login_response)

    mgr.validate(
        "new_password_accepted",
        new_login_response.status_code == 200,
        new_login_response.status_code,
        200,
        "Login with new password should succeed",
    )

    mgr.validate(
        "token_received",
        "token" in new_login_response.json(),
        "token" in new_login_response.json(),
        True,
        "New login should return token",
    )

    # Cleanup
    delete_response = api_client.delete(f"/users/{user_id}")
    mgr.validate(
        "cleanup_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_1l_token_validation(api_client, unique_user_credentials):
    """
    AT1.1l: Token validation endpoint.
    Tests GET /auth/validate endpoint for token verification.
    """
    mgr = TestOutputManager("AT1_1l_token_validation")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.1l - Token Validation")
    mgr.log_console("=" * 80)

    creds = unique_user_credentials

    # Create user
    create_payload = {
        "username": creds["username"],
        "email": creds["email"],
        "password": creds["password"],
        "display_name": creds["display_name"],
    }

    mgr.save_input("create_user", create_payload)
    create_response = api_client.post("/auth/register", json=create_payload)
    mgr.save_output("create_user", create_response)

    mgr.validate(
        "user_created", create_response.status_code == 200, create_response.status_code, 200
    )

    user_id = create_response.json().get("id")

    # Login to get valid token
    login_payload = {"username": creds["username"], "password": creds["password"]}
    mgr.save_input("login", login_payload)
    login_response = api_client.post("/auth/login", json=login_payload)
    mgr.save_output("login", login_response)

    mgr.validate(
        "login_success", login_response.status_code == 200, login_response.status_code, 200
    )

    token = login_response.json().get("token")

    # Validate valid token
    validate_response = api_client.get(f"/auth/validate?token={token}")
    mgr.save_output("validate_valid_token", validate_response)

    mgr.validate(
        "validate_status_200",
        validate_response.status_code == 200,
        validate_response.status_code,
        200,
        "Validate endpoint should return 200",
    )

    validate_data = validate_response.json()
    mgr.validate(
        "token_is_valid",
        validate_data.get("valid") is True,
        validate_data.get("valid"),
        True,
        "Valid token should return valid=true",
    )
    mgr.validate(
        "user_id_in_validation",
        "user_id" in validate_data,
        "user_id" in validate_data,
        True,
        "Validation should include user_id",
    )

    # Validate invalid token
    invalid_token = "invalid_token_12345"
    invalid_validate_response = api_client.get(f"/auth/validate?token={invalid_token}")
    mgr.save_output("validate_invalid_token", invalid_validate_response)

    mgr.validate(
        "invalid_validate_status_200",
        invalid_validate_response.status_code == 200,
        invalid_validate_response.status_code,
        200,
    )

    invalid_data = invalid_validate_response.json()
    mgr.validate(
        "invalid_token_rejected",
        invalid_data.get("valid") is False,
        invalid_data.get("valid"),
        False,
        "Invalid token should return valid=false",
    )

    # Cleanup
    delete_response = api_client.delete(f"/users/{user_id}")
    mgr.validate(
        "cleanup_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_1m_user_update_username(api_client, unique_user_credentials):
    """
    AT1.1m: Update user username.
    Tests username update functionality via PUT /users/{id}.
    """
    mgr = TestOutputManager("AT1_1m_update_username")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.1m - Update Username")
    mgr.log_console("=" * 80)

    creds = unique_user_credentials

    # Create user
    create_payload = {
        "username": creds["username"],
        "email": creds["email"],
        "password": creds["password"],
        "display_name": creds["display_name"],
    }

    mgr.save_input("create_user", create_payload)
    create_response = api_client.post("/auth/register", json=create_payload)
    mgr.save_output("create_user", create_response)

    mgr.validate(
        "user_created", create_response.status_code == 200, create_response.status_code, 200
    )

    user_id = create_response.json().get("id")

    # Login to get authentication token for update operations
    token = get_auth_token(api_client, creds["username"], creds["password"])

    # Update username
    new_username = f"{creds['username']}_updated"
    update_payload = {"username": new_username}

    mgr.save_input("update_username", update_payload)
    saved_api_key = api_client.session.headers.pop("X-API-Key", None)

    update_response = api_client.put(
        f"/users/{user_id}", json=update_payload, headers={"Authorization": f"Bearer {token}"}
    )

    if saved_api_key:
        api_client.session.headers["X-API-Key"] = saved_api_key
    mgr.save_output("update_username", update_response)

    mgr.validate(
        "update_success",
        update_response.status_code == 200,
        update_response.status_code,
        200,
        "Username update should return 200 OK",
    )

    # Verify update persisted
    saved_api_key = api_client.session.headers.pop("X-API-Key", None)

    get_response = api_client.get(f"/users/{user_id}", headers={"Authorization": f"Bearer {token}"})

    if saved_api_key:
        api_client.session.headers["X-API-Key"] = saved_api_key
    mgr.save_output("get_updated_user", get_response)

    mgr.validate("get_success", get_response.status_code == 200, get_response.status_code, 200)

    get_data = get_response.json()
    mgr.validate(
        "username_updated",
        get_data.get("username") == new_username,
        get_data.get("username"),
        new_username,
        "Username should be updated in database",
    )

    # Cleanup
    delete_response = api_client.delete(f"/users/{user_id}")
    mgr.validate(
        "cleanup_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_1n_user_update_email(api_client, unique_user_credentials):
    """
    AT1.1n: Update user email.
    Tests email update functionality via PUT /users/{id}.
    """
    mgr = TestOutputManager("AT1_1n_update_email")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.1n - Update Email")
    mgr.log_console("=" * 80)

    creds = unique_user_credentials

    # Create user
    create_payload = {
        "username": creds["username"],
        "email": creds["email"],
        "password": creds["password"],
        "display_name": creds["display_name"],
    }

    mgr.save_input("create_user", create_payload)
    create_response = api_client.post("/auth/register", json=create_payload)
    mgr.save_output("create_user", create_response)

    mgr.validate(
        "user_created", create_response.status_code == 200, create_response.status_code, 200
    )

    user_id = create_response.json().get("id")

    # Login to get authentication token for update operations
    token = get_auth_token(api_client, creds["username"], creds["password"])

    # Update email
    domain = creds["email"].split("@")[1]
    new_email = f"updated_{uuid.uuid4().hex[:8]}@{domain}"
    update_payload = {"email": new_email}

    mgr.save_input("update_email", update_payload)
    saved_api_key = api_client.session.headers.pop("X-API-Key", None)

    update_response = api_client.put(
        f"/users/{user_id}", json=update_payload, headers={"Authorization": f"Bearer {token}"}
    )

    if saved_api_key:
        api_client.session.headers["X-API-Key"] = saved_api_key
    mgr.save_output("update_email", update_response)

    mgr.validate(
        "update_success",
        update_response.status_code == 200,
        update_response.status_code,
        200,
        "Email update should return 200 OK",
    )

    # Verify update persisted
    saved_api_key = api_client.session.headers.pop("X-API-Key", None)

    get_response = api_client.get(f"/users/{user_id}", headers={"Authorization": f"Bearer {token}"})

    if saved_api_key:
        api_client.session.headers["X-API-Key"] = saved_api_key
    mgr.save_output("get_updated_user", get_response)

    mgr.validate("get_success", get_response.status_code == 200, get_response.status_code, 200)

    get_data = get_response.json()
    mgr.validate(
        "email_updated",
        get_data.get("email") == new_email,
        get_data.get("email"),
        new_email,
        "Email should be updated in database",
    )

    # Cleanup
    delete_response = api_client.delete(f"/users/{user_id}")
    mgr.validate(
        "cleanup_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_1o_user_update_display_name(api_client, unique_user_credentials):
    """
    AT1.1o: Update user display name.
    Tests display_name update functionality via PUT /users/{id}.
    """
    mgr = TestOutputManager("AT1_1o_update_display_name")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.1o - Update Display Name")
    mgr.log_console("=" * 80)

    creds = unique_user_credentials

    # Create user
    create_payload = {
        "username": creds["username"],
        "email": creds["email"],
        "password": creds["password"],
        "display_name": creds["display_name"],
    }

    mgr.save_input("create_user", create_payload)
    create_response = api_client.post("/auth/register", json=create_payload)
    mgr.save_output("create_user", create_response)

    mgr.validate(
        "user_created", create_response.status_code == 200, create_response.status_code, 200
    )

    user_id = create_response.json().get("id")

    # Login to get authentication token for update operations
    token = get_auth_token(api_client, creds["username"], creds["password"])

    # Update display name
    new_display_name = f"{creds['display_name']} - Updated"
    update_payload = {"display_name": new_display_name}

    mgr.save_input("update_display_name", update_payload)
    saved_api_key = api_client.session.headers.pop("X-API-Key", None)

    update_response = api_client.put(
        f"/users/{user_id}", json=update_payload, headers={"Authorization": f"Bearer {token}"}
    )

    if saved_api_key:
        api_client.session.headers["X-API-Key"] = saved_api_key
    mgr.save_output("update_display_name", update_response)

    mgr.validate(
        "update_success",
        update_response.status_code == 200,
        update_response.status_code,
        200,
        "Display name update should return 200 OK",
    )

    # Verify update persisted
    saved_api_key = api_client.session.headers.pop("X-API-Key", None)

    get_response = api_client.get(f"/users/{user_id}", headers={"Authorization": f"Bearer {token}"})

    if saved_api_key:
        api_client.session.headers["X-API-Key"] = saved_api_key
    mgr.save_output("get_updated_user", get_response)

    mgr.validate("get_success", get_response.status_code == 200, get_response.status_code, 200)

    get_data = get_response.json()
    mgr.validate(
        "display_name_updated",
        get_data.get("display_name") == new_display_name,
        get_data.get("display_name"),
        new_display_name,
        "Display name should be updated in database",
    )

    # Cleanup
    delete_response = api_client.delete(f"/users/{user_id}")
    mgr.validate(
        "cleanup_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_1p_user_update_role(api_client, unique_user_credentials):
    """
    AT1.1p: Update user role.
    Tests role update functionality via PUT /users/{id}.
    """
    mgr = TestOutputManager("AT1_1p_update_role")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.1p - Update Role")
    mgr.log_console("=" * 80)

    creds = unique_user_credentials

    # Create user with 'user' role
    create_payload = {
        "username": creds["username"],
        "email": creds["email"],
        "password": creds["password"],
        "display_name": creds["display_name"],
    }

    mgr.save_input("create_user", create_payload)
    create_response = api_client.post("/auth/register", json=create_payload)
    mgr.save_output("create_user", create_response)

    mgr.validate(
        "user_created", create_response.status_code == 200, create_response.status_code, 200
    )

    user_id = create_response.json().get("id")

    # Login to get authentication token for update operations
    token = get_auth_token(api_client, creds["username"], creds["password"])
    mgr.validate(
        "initial_role_user",
        create_response.json().get("role") == "user",
        create_response.json().get("role"),
        "user",
        "Initial role should be 'user'",
    )

    # Update role to admin (requires admin privileges - use admin API key)
    update_payload = {"role": "admin"}

    mgr.save_input("update_role", update_payload)
    # Role changes require admin - use admin API key instead of user token
    update_response = api_client.put(f"/users/{user_id}", json=update_payload)
    mgr.save_output("update_role", update_response)

    mgr.validate(
        "update_success",
        update_response.status_code == 200,
        update_response.status_code,
        200,
        "Role update should return 200 OK",
    )

    # Verify update persisted
    saved_api_key = api_client.session.headers.pop("X-API-Key", None)

    get_response = api_client.get(f"/users/{user_id}", headers={"Authorization": f"Bearer {token}"})

    if saved_api_key:
        api_client.session.headers["X-API-Key"] = saved_api_key
    mgr.save_output("get_updated_user", get_response)

    mgr.validate("get_success", get_response.status_code == 200, get_response.status_code, 200)

    get_data = get_response.json()
    mgr.validate(
        "role_updated",
        get_data.get("role") == "admin",
        get_data.get("role"),
        "admin",
        "Role should be updated to 'admin' in database",
    )

    # Cleanup
    delete_response = api_client.delete(f"/users/{user_id}")
    mgr.validate(
        "cleanup_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_1q_user_update_multiple_fields(api_client, unique_user_credentials):
    """
    AT1.1q: Update multiple user fields simultaneously.
    Tests updating username, email, and display_name in single request.
    """
    mgr = TestOutputManager("AT1_1q_update_multiple_fields")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.1q - Update Multiple Fields")
    mgr.log_console("=" * 80)

    creds = unique_user_credentials

    # Create user
    create_payload = {
        "username": creds["username"],
        "email": creds["email"],
        "password": creds["password"],
        "display_name": creds["display_name"],
    }

    mgr.save_input("create_user", create_payload)
    create_response = api_client.post("/auth/register", json=create_payload)
    mgr.save_output("create_user", create_response)

    mgr.validate(
        "user_created", create_response.status_code == 200, create_response.status_code, 200
    )

    user_id = create_response.json().get("id")

    # Login to get authentication token for update operations
    token = get_auth_token(api_client, creds["username"], creds["password"])

    # Update multiple fields
    new_username = f"{creds['username']}_multi"
    domain = creds["email"].split("@")[1]
    new_email = f"multi_{uuid.uuid4().hex[:8]}@{domain}"
    new_display_name = f"{creds['display_name']} - Multi Update"

    update_payload = {
        "username": new_username,
        "email": new_email,
        "display_name": new_display_name,
    }

    mgr.save_input("update_multiple", update_payload)
    saved_api_key = api_client.session.headers.pop("X-API-Key", None)

    update_response = api_client.put(
        f"/users/{user_id}", json=update_payload, headers={"Authorization": f"Bearer {token}"}
    )

    if saved_api_key:
        api_client.session.headers["X-API-Key"] = saved_api_key
    mgr.save_output("update_multiple", update_response)

    mgr.validate(
        "update_success",
        update_response.status_code == 200,
        update_response.status_code,
        200,
        "Multiple field update should return 200 OK",
    )

    # Verify all updates persisted
    saved_api_key = api_client.session.headers.pop("X-API-Key", None)

    get_response = api_client.get(f"/users/{user_id}", headers={"Authorization": f"Bearer {token}"})

    if saved_api_key:
        api_client.session.headers["X-API-Key"] = saved_api_key
    mgr.save_output("get_updated_user", get_response)

    mgr.validate("get_success", get_response.status_code == 200, get_response.status_code, 200)

    get_data = get_response.json()
    mgr.validate(
        "username_updated",
        get_data.get("username") == new_username,
        get_data.get("username"),
        new_username,
        "Username should be updated",
    )
    mgr.validate(
        "email_updated",
        get_data.get("email") == new_email,
        get_data.get("email"),
        new_email,
        "Email should be updated",
    )
    mgr.validate(
        "display_name_updated",
        get_data.get("display_name") == new_display_name,
        get_data.get("display_name"),
        new_display_name,
        "Display name should be updated",
    )

    # Cleanup
    delete_response = api_client.delete(f"/users/{user_id}")
    mgr.validate(
        "cleanup_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_1r_user_update_validation(api_client, unique_user_credentials):
    """
    AT1.1r: Update validation - invalid data rejection.
    Tests that system rejects invalid update data with appropriate errors.
    """
    mgr = TestOutputManager("AT1_1r_update_validation")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.1r - Update Validation")
    mgr.log_console("=" * 80)

    creds = unique_user_credentials

    # Create user
    create_payload = {
        "username": creds["username"],
        "email": creds["email"],
        "password": creds["password"],
        "display_name": creds["display_name"],
    }

    mgr.save_input("create_user", create_payload)
    create_response = api_client.post("/auth/register", json=create_payload)
    mgr.save_output("create_user", create_response)

    mgr.validate(
        "user_created", create_response.status_code == 200, create_response.status_code, 200
    )

    user_id = create_response.json().get("id")

    # Login to get authentication token for update operations
    token = get_auth_token(api_client, creds["username"], creds["password"])

    # Test 1: Invalid email format
    invalid_email_payload = {"email": "not-an-email"}
    mgr.save_input("update_invalid_email", invalid_email_payload)
    invalid_email_response = api_client.put(f"/users/{user_id}", json=invalid_email_payload)
    mgr.save_output("update_invalid_email", invalid_email_response)

    mgr.validate(
        "invalid_email_rejected",
        invalid_email_response.status_code in (400, 422),
        invalid_email_response.status_code,
        "400 or 422",
        "Invalid email format should be rejected",
    )

    # Test 2: Empty username
    empty_username_payload = {"username": ""}
    mgr.save_input("update_empty_username", empty_username_payload)
    empty_username_response = api_client.put(f"/users/{user_id}", json=empty_username_payload)
    mgr.save_output("update_empty_username", empty_username_response)

    mgr.validate(
        "empty_username_rejected",
        empty_username_response.status_code in (400, 422),
        empty_username_response.status_code,
        "400 or 422",
        "Empty username should be rejected",
    )

    # Verify user data unchanged after invalid updates
    saved_api_key = api_client.session.headers.pop("X-API-Key", None)

    get_response = api_client.get(f"/users/{user_id}", headers={"Authorization": f"Bearer {token}"})

    if saved_api_key:
        api_client.session.headers["X-API-Key"] = saved_api_key
    mgr.save_output("get_user_after_invalid_updates", get_response)

    mgr.validate("get_success", get_response.status_code == 200, get_response.status_code, 200)

    get_data = get_response.json()
    mgr.validate(
        "username_unchanged",
        get_data.get("username") == creds["username"],
        get_data.get("username"),
        creds["username"],
        "Username should remain unchanged after invalid updates",
    )
    mgr.validate(
        "email_unchanged",
        get_data.get("email") == creds["email"],
        get_data.get("email"),
        creds["email"],
        "Email should remain unchanged after invalid updates",
    )

    # Cleanup
    delete_response = api_client.delete(f"/users/{user_id}")
    mgr.validate(
        "cleanup_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.db, pytest.mark.smtp, pytest.mark.heavy]

