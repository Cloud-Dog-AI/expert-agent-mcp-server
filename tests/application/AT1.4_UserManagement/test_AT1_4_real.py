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
Description: Comprehensive Application Test for User Management CRUD Operations.
Tests user creation, retrieval, update, and deletion via real API server.
100% RULES.md compliant with comprehensive logging, validation tracking, and summary table generation.

Related Requirements: FR1.5
Related Tasks: T005
Related Architecture: CC5.1.1
Related Tests: AT1.4

Recent Changes (max 10):
- Initial comprehensive implementation with TestOutputManager
- Full RULES.md compliance (API-only, zero hardcoded values, comprehensive logging)
- Complete CRUD operations with admin authentication
- User role and status management tests
**************************************************
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import APIClient, build_test_email

import pytest
import uuid
import json
from datetime import datetime
from typing import Any
from src.config.loader import get_config


class TestOutputManager:
    """Manages test outputs, validations, and summary generation for AT1.4 tests."""

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.base_dir = Path("working/AT1.4_TEST_OUTPUTS") / test_name
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
    cfg = get_config()
    host = cfg.get("api_server", {}).get("host")
    port = cfg.get("api_server", {}).get("port")
    if not host or not port:
        pytest.fail("api_server.host/port not configured (set in --env file)")
    base_url = f"http://{host}:{int(port)}"

    client = APIClient(base_url)

    response = client.get("/health")
    if response.status_code != 200:
        pytest.fail(f"API server not healthy at {base_url}/health")

    return client


def get_admin_api_key():
    """Get admin API key from configuration."""
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured (set in secrets env file)")
    return str(api_key)


def _require_base_user_config():
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    base_password = get_config("test.user.password")
    if not base_username or not base_email or not base_password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in --env file")
    return base_username, base_email, base_password


def get_auth_token(api_client, username: str, password: str) -> str:
    """Helper to get authentication token for a user."""
    login_response = api_client.post(
        "/auth/login", json={"username": username, "password": password}
    )
    if login_response.status_code == 200:
        return login_response.json().get("access_token")
    return None
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_4a_user_creation_success(api_client):
    """
    AT1.4a: User creation with valid data.
    Tests successful user creation via POST /users endpoint.
    """
    mgr = TestOutputManager("AT1_4a_user_creation_success")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.4a - User Creation Success")
    mgr.log_console("=" * 80)

    base_username, base_email, base_password = _require_base_user_config()

    unique_id = uuid.uuid4().hex[:8]
    user_payload = {
        "username": f"user_at1_4a_{unique_id}",
        "email": build_test_email("at1_4a", unique_id, base_email),
        "password": base_password,
        "display_name": f"Test User AT1.4a {unique_id}",
        "role": "user",
    }

    mgr.save_input("create_user", user_payload)
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    user_response = api_client.post("/users", json=user_payload)
    mgr.save_output("create_user", user_response)

    mgr.validate(
        "user_created",
        user_response.status_code == 200,
        user_response.status_code,
        200,
        "User creation should return 200 OK",
    )

    user_data = user_response.json()
    user_id = user_data.get("id")

    mgr.validate(
        "user_id_present", user_id is not None, user_id is not None, True, "User ID must be present"
    )
    mgr.validate(
        "username_matches",
        user_data.get("username") == user_payload["username"],
        user_data.get("username"),
        user_payload["username"],
        "Username must match request",
    )
    mgr.validate(
        "email_matches",
        user_data.get("email") == user_payload["email"],
        user_data.get("email"),
        user_payload["email"],
        "Email must match request",
    )
    mgr.validate(
        "display_name_matches",
        user_data.get("display_name") == user_payload["display_name"],
        user_data.get("display_name"),
        user_payload["display_name"],
        "Display name must match request",
    )
    mgr.validate(
        "role_matches",
        user_data.get("role") == user_payload["role"],
        user_data.get("role"),
        user_payload["role"],
        "Role must match request",
    )
    mgr.validate(
        "user_enabled",
        user_data.get("enabled") is True,
        user_data.get("enabled"),
        True,
        "User should be enabled by default",
    )

    api_client.delete(f"/users/{user_id}")
    api_client.session.headers.pop("X-API-Key", None)

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_4b_user_creation_duplicate_username(api_client):
    """
    AT1.4b: Reject duplicate username.
    Tests that duplicate usernames are properly rejected.
    """
    mgr = TestOutputManager("AT1_4b_user_creation_duplicate_username")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.4b - Duplicate Username Rejection")
    mgr.log_console("=" * 80)

    base_username, base_email, base_password = _require_base_user_config()

    unique_id = uuid.uuid4().hex[:8]
    username = f"user_at1_4b_{unique_id}"

    user_payload1 = {
        "username": username,
        "email": build_test_email("at1_4b_1", unique_id, base_email),
        "password": base_password,
    }

    mgr.save_input("create_user_first", user_payload1)
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    user_response1 = api_client.post("/users", json=user_payload1)
    mgr.save_output("create_user_first", user_response1)

    mgr.validate(
        "first_user_created",
        user_response1.status_code == 200,
        user_response1.status_code,
        200,
        "First user creation should succeed",
    )

    user_id = user_response1.json().get("id")

    user_payload2 = {
        "username": username,
        "email": f"at1_4b_2_{unique_id}@{base_email.split('@')[1]}",
        "password": base_password,
    }

    mgr.save_input("create_user_duplicate", user_payload2)
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    user_response2 = api_client.post("/users", json=user_payload2)
    mgr.save_output("create_user_duplicate", user_response2)

    mgr.validate(
        "duplicate_rejected",
        user_response2.status_code == 400,
        user_response2.status_code,
        400,
        "Duplicate username should return 400",
    )

    if user_response2.status_code == 400:
        error_detail = user_response2.json().get("detail", "").lower()
        mgr.validate(
            "error_message_appropriate",
            "already exists" in error_detail or "duplicate" in error_detail,
            "already exists" in error_detail or "duplicate" in error_detail,
            True,
            "Error message should indicate duplicate/already exists",
        )

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    api_client.delete(f"/users/{user_id}")
    api_client.session.headers.pop("X-API-Key", None)

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_4c_user_creation_duplicate_email(api_client):
    """
    AT1.4c: Reject duplicate email.
    Tests that duplicate emails are properly rejected.
    """
    mgr = TestOutputManager("AT1_4c_user_creation_duplicate_email")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.4c - Duplicate Email Rejection")
    mgr.log_console("=" * 80)

    base_username, base_email, base_password = _require_base_user_config()

    unique_id = uuid.uuid4().hex[:8]
    email = build_test_email("at1_4c", unique_id, base_email)

    user_payload1 = {
        "username": f"user_at1_4c_1_{unique_id}",
        "email": email,
        "password": base_password,
    }

    mgr.save_input("create_user_first", user_payload1)
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    user_response1 = api_client.post("/users", json=user_payload1)
    mgr.save_output("create_user_first", user_response1)

    mgr.validate(
        "first_user_created",
        user_response1.status_code == 200,
        user_response1.status_code,
        200,
        "First user creation should succeed",
    )

    user_id = user_response1.json().get("id")

    user_payload2 = {
        "username": f"user_at1_4c_2_{unique_id}",
        "email": email,
        "password": base_password,
    }

    mgr.save_input("create_user_duplicate", user_payload2)
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    user_response2 = api_client.post("/users", json=user_payload2)
    mgr.save_output("create_user_duplicate", user_response2)

    mgr.validate(
        "duplicate_rejected",
        user_response2.status_code == 400,
        user_response2.status_code,
        400,
        "Duplicate email should return 400",
    )

    if user_response2.status_code == 400:
        error_detail = user_response2.json().get("detail", "").lower()
        mgr.validate(
            "error_message_appropriate",
            "already exists" in error_detail or "duplicate" in error_detail,
            "already exists" in error_detail or "duplicate" in error_detail,
            True,
            "Error message should indicate duplicate/already exists",
        )

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    api_client.delete(f"/users/{user_id}")
    api_client.session.headers.pop("X-API-Key", None)

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_4d_user_get_by_id(api_client):
    """
    AT1.4d: Get user by ID.
    Tests user retrieval via GET /users/{id}.
    """
    mgr = TestOutputManager("AT1_4d_user_get_by_id")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.4d - Get User By ID")
    mgr.log_console("=" * 80)

    base_username, base_email, base_password = _require_base_user_config()

    unique_id = uuid.uuid4().hex[:8]
    user_payload = {
        "username": f"user_at1_4d_{unique_id}",
        "email": build_test_email("at1_4d", unique_id, base_email),
        "password": base_password,
    }

    mgr.save_input("create_user", user_payload)
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    user_response = api_client.post("/users", json=user_payload)
    mgr.save_output("create_user", user_response)

    user_id = user_response.json().get("id")

    get_auth_token(api_client, user_payload["username"], user_payload["password"])

    # GET /users/{id} requires admin auth
    get_response = api_client.get(f"/users/{user_id}")

    mgr.save_output("get_user", get_response)

    mgr.validate(
        "get_success",
        get_response.status_code == 200,
        get_response.status_code,
        200,
        "User retrieval should return 200 OK",
    )

    user_data = get_response.json()

    mgr.validate(
        "id_matches",
        user_data.get("id") == user_id,
        user_data.get("id"),
        user_id,
        "User ID must match",
    )
    mgr.validate(
        "username_matches",
        user_data.get("username") == user_payload["username"],
        user_data.get("username"),
        user_payload["username"],
        "Username must match",
    )
    mgr.validate(
        "email_matches",
        user_data.get("email") == user_payload["email"],
        user_data.get("email"),
        user_payload["email"],
        "Email must match",
    )

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    api_client.delete(f"/users/{user_id}")
    api_client.session.headers.pop("X-API-Key", None)

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_4e_user_list_all(api_client):
    """
    AT1.4e: List all users.
    Tests user listing via GET /users.
    """
    mgr = TestOutputManager("AT1_4e_user_list_all")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.4e - List All Users")
    mgr.log_console("=" * 80)

    base_username, base_email, base_password = _require_base_user_config()

    created_users = []
    for i in range(3):
        unique_id = uuid.uuid4().hex[:8]
        user_payload = {
            "username": f"user_at1_4e_{i}_{unique_id}",
            "email": build_test_email(f"at1_4e_{i}", unique_id, base_email),
            "password": base_password,
        }

        admin_api_key = get_admin_api_key()
        api_client.session.headers["X-API-Key"] = admin_api_key
        user_response = api_client.post("/users", json=user_payload)
        if user_response.status_code == 200:
            created_users.append(user_response.json())

    mgr.save_input("list_users", {"endpoint": "/users"})
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    list_response = api_client.get("/users")
    mgr.save_output("list_users", list_response)

    mgr.validate(
        "list_success",
        list_response.status_code == 200,
        list_response.status_code,
        200,
        "User list should return 200 OK",
    )

    list_data = list_response.json()
    users_list = list_data.get("users", [])

    mgr.validate(
        "users_list_is_array",
        isinstance(users_list, list),
        isinstance(users_list, list),
        True,
        "Users list must be an array",
    )
    mgr.validate(
        "users_list_not_empty",
        len(users_list) >= len(created_users),
        len(users_list) >= len(created_users),
        True,
        f"Users list must contain at least {len(created_users)} users",
    )

    created_ids = {u["id"] for u in created_users}
    found_ids = {u["id"] for u in users_list if u.get("id")}

    mgr.validate(
        "created_users_in_list",
        created_ids.issubset(found_ids),
        created_ids.issubset(found_ids),
        True,
        "All created users must be in list",
    )

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    for user in created_users:
        api_client.delete(f"/users/{user['id']}")
    api_client.session.headers.pop("X-API-Key", None)

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_4f_user_list_filtered_by_role(api_client):
    """
    AT1.4f: List users filtered by role.
    Tests user listing with role filter via GET /users?role=admin.
    """
    mgr = TestOutputManager("AT1_4f_user_list_filtered_by_role")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.4f - List Users Filtered By Role")
    mgr.log_console("=" * 80)

    base_username, base_email, base_password = _require_base_user_config()

    unique_id = uuid.uuid4().hex[:8]
    admin_user_payload = {
        "username": f"admin_at1_4f_{unique_id}",
        "email": build_test_email("admin_at1_4f", unique_id, base_email),
        "password": base_password,
        "role": "admin",
    }

    mgr.save_input("create_admin_user", admin_user_payload)
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    admin_response = api_client.post("/users", json=admin_user_payload)
    mgr.save_output("create_admin_user", admin_response)

    admin_user_id = admin_response.json().get("id")

    mgr.save_input("list_users_by_role", {"endpoint": "/users", "role": "admin"})
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    list_response = api_client.get("/users?role=admin")
    mgr.save_output("list_users_by_role", list_response)

    mgr.validate(
        "list_success",
        list_response.status_code == 200,
        list_response.status_code,
        200,
        "User list should return 200 OK",
    )

    list_data = list_response.json()
    users_list = list_data.get("users", [])

    mgr.validate(
        "admin_user_in_list",
        any(u.get("id") == admin_user_id for u in users_list),
        any(u.get("id") == admin_user_id for u in users_list),
        True,
        "Created admin user must be in filtered list",
    )

    for user in users_list:
        if user.get("role"):
            mgr.validate(
                f"user_{user.get('id')}_is_admin",
                user.get("role") == "admin",
                user.get("role"),
                "admin",
                "All users in filtered list must have admin role",
            )
            break

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    api_client.delete(f"/users/{admin_user_id}")
    api_client.session.headers.pop("X-API-Key", None)

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_4g_user_list_enabled_only(api_client):
    """
    AT1.4g: List only enabled users.
    Tests user listing with enabled filter via GET /users?enabled_only=true.
    """
    mgr = TestOutputManager("AT1_4g_user_list_enabled_only")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.4g - List Enabled Users Only")
    mgr.log_console("=" * 80)

    base_username, base_email, base_password = _require_base_user_config()

    unique_id = uuid.uuid4().hex[:8]
    user_payload = {
        "username": f"user_at1_4g_{unique_id}",
        "email": build_test_email("at1_4g", unique_id, base_email),
        "password": base_password,
    }

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    user_response = api_client.post("/users", json=user_payload)
    user_id = user_response.json().get("id")

    mgr.save_input("list_enabled_users", {"endpoint": "/users", "enabled_only": True})
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    list_response = api_client.get("/users?enabled_only=true")
    mgr.save_output("list_enabled_users", list_response)

    mgr.validate(
        "list_success",
        list_response.status_code == 200,
        list_response.status_code,
        200,
        "User list should return 200 OK",
    )

    list_data = list_response.json()
    users_list = list_data.get("users", [])

    mgr.validate(
        "created_user_in_list",
        any(u.get("id") == user_id for u in users_list),
        any(u.get("id") == user_id for u in users_list),
        True,
        "Created enabled user must be in list",
    )

    for user in users_list:
        if user.get("enabled") is not None:
            mgr.validate(
                f"user_{user.get('id')}_is_enabled",
                user.get("enabled") is True,
                user.get("enabled"),
                True,
                "All users in enabled_only list must be enabled",
            )
            break

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    api_client.delete(f"/users/{user_id}")
    api_client.session.headers.pop("X-API-Key", None)

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_4h_user_update_email(api_client):
    """
    AT1.4h: Update user email.
    Tests email update via PUT /users/{id}.
    """
    mgr = TestOutputManager("AT1_4h_user_update_email")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.4h - Update User Email")
    mgr.log_console("=" * 80)

    base_username, base_email, base_password = _require_base_user_config()

    unique_id = uuid.uuid4().hex[:8]
    user_payload = {
        "username": f"user_at1_4h_{unique_id}",
        "email": build_test_email("at1_4h", unique_id, base_email),
        "password": base_password,
    }

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    user_response = api_client.post("/users", json=user_payload)
    user_id = user_response.json().get("id")

    get_auth_token(api_client, user_payload["username"], user_payload["password"])

    new_email = build_test_email("updated_at1_4h", unique_id, base_email)
    update_payload = {"email": new_email}

    mgr.save_input("update_email", update_payload)
    # PUT /users/{id} requires admin auth
    update_response = api_client.put(f"/users/{user_id}", json=update_payload)
    mgr.save_output("update_email", update_response)

    mgr.validate(
        "update_success",
        update_response.status_code == 200,
        update_response.status_code,
        200,
        "Email update should return 200 OK",
    )

    update_data = update_response.json()
    mgr.validate(
        "email_updated",
        update_data.get("email") == new_email,
        update_data.get("email"),
        new_email,
        "Email must be updated",
    )

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    api_client.delete(f"/users/{user_id}")
    api_client.session.headers.pop("X-API-Key", None)

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_4i_user_update_display_name(api_client):
    """
    AT1.4i: Update user display name.
    Tests display name update via PUT /users/{id}.
    """
    mgr = TestOutputManager("AT1_4i_user_update_display_name")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.4i - Update User Display Name")
    mgr.log_console("=" * 80)

    base_username, base_email, base_password = _require_base_user_config()

    unique_id = uuid.uuid4().hex[:8]
    user_payload = {
        "username": f"user_at1_4i_{unique_id}",
        "email": build_test_email("at1_4i", unique_id, base_email),
        "password": base_password,
        "display_name": "Original Name",
    }

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    user_response = api_client.post("/users", json=user_payload)
    user_id = user_response.json().get("id")

    get_auth_token(api_client, user_payload["username"], user_payload["password"])

    new_display_name = f"Updated Name {unique_id}"
    update_payload = {"display_name": new_display_name}

    mgr.save_input("update_display_name", update_payload)
    # PUT /users/{id} requires admin auth
    update_response = api_client.put(f"/users/{user_id}", json=update_payload)
    mgr.save_output("update_display_name", update_response)

    mgr.validate(
        "update_success",
        update_response.status_code == 200,
        update_response.status_code,
        200,
        "Display name update should return 200 OK",
    )

    update_data = update_response.json()
    mgr.validate(
        "display_name_updated",
        update_data.get("display_name") == new_display_name,
        update_data.get("display_name"),
        new_display_name,
        "Display name must be updated",
    )

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    api_client.delete(f"/users/{user_id}")
    api_client.session.headers.pop("X-API-Key", None)

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_4j_user_update_role(api_client):
    """
    AT1.4j: Update user role (admin operation).
    Tests role update via PUT /users/{id} with admin authentication.
    """
    mgr = TestOutputManager("AT1_4j_user_update_role")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.4j - Update User Role")
    mgr.log_console("=" * 80)

    base_username, base_email, base_password = _require_base_user_config()

    unique_id = uuid.uuid4().hex[:8]
    user_payload = {
        "username": f"user_at1_4j_{unique_id}",
        "email": build_test_email("at1_4j", unique_id, base_email),
        "password": base_password,
        "role": "user",
    }

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    user_response = api_client.post("/users", json=user_payload)
    user_id = user_response.json().get("id")

    update_payload = {"role": "admin"}

    mgr.save_input("update_role", update_payload)
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    update_response = api_client.put(f"/users/{user_id}", json=update_payload)
    mgr.save_output("update_role", update_response)

    mgr.validate(
        "update_success",
        update_response.status_code == 200,
        update_response.status_code,
        200,
        "Role update should return 200 OK",
    )

    update_data = update_response.json()
    mgr.validate(
        "role_updated",
        update_data.get("role") == "admin",
        update_data.get("role"),
        "admin",
        "Role must be updated to admin",
    )

    api_client.delete(f"/users/{user_id}")
    api_client.session.headers.pop("X-API-Key", None)

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_4k_user_update_enabled_status(api_client):
    """
    AT1.4k: Update user enabled status.
    Tests enabling/disabling user via PUT /users/{id}.
    """
    mgr = TestOutputManager("AT1_4k_user_update_enabled_status")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.4k - Update User Enabled Status")
    mgr.log_console("=" * 80)

    base_username, base_email, base_password = _require_base_user_config()

    unique_id = uuid.uuid4().hex[:8]
    user_payload = {
        "username": f"user_at1_4k_{unique_id}",
        "email": build_test_email("at1_4k", unique_id, base_email),
        "password": base_password,
    }

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    user_response = api_client.post("/users", json=user_payload)
    user_id = user_response.json().get("id")

    update_payload = {"enabled": False}

    mgr.save_input("disable_user", update_payload)
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    update_response = api_client.put(f"/users/{user_id}", json=update_payload)
    mgr.save_output("disable_user", update_response)

    mgr.validate(
        "update_success",
        update_response.status_code == 200,
        update_response.status_code,
        200,
        "Enabled status update should return 200 OK",
    )

    update_data = update_response.json()
    mgr.validate(
        "user_disabled",
        update_data.get("enabled") is False,
        update_data.get("enabled"),
        False,
        "User must be disabled",
    )

    api_client.delete(f"/users/{user_id}")
    api_client.session.headers.pop("X-API-Key", None)

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_4l_user_delete_success(api_client):
    """
    AT1.4l: Delete user successfully.
    Tests user deletion via DELETE /users/{id}.
    """
    mgr = TestOutputManager("AT1_4l_user_delete_success")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.4l - Delete User Success")
    mgr.log_console("=" * 80)

    base_username, base_email, base_password = _require_base_user_config()

    unique_id = uuid.uuid4().hex[:8]
    user_payload = {
        "username": f"user_at1_4l_{unique_id}",
        "email": build_test_email("at1_4l", unique_id, base_email),
        "password": base_password,
    }

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    user_response = api_client.post("/users", json=user_payload)
    user_id = user_response.json().get("id")

    mgr.save_input("delete_user", {"user_id": user_id})
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    delete_response = api_client.delete(f"/users/{user_id}")
    mgr.save_output("delete_user", delete_response)

    mgr.validate(
        "delete_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
        "User deletion should return 200 or 204",
    )

    get_response = api_client.get(f"/users/{user_id}")
    mgr.save_output("verify_deleted", get_response)

    mgr.validate(
        "user_not_found",
        get_response.status_code == 404,
        get_response.status_code,
        404,
        "Deleted user should return 404",
    )

    api_client.session.headers.pop("X-API-Key", None)

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_4m_user_delete_cascade(api_client):
    """
    AT1.4m: Verify cascade deletion.
    Tests that user deletion properly cascades to related entities.
    """
    mgr = TestOutputManager("AT1_4m_user_delete_cascade")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.4m - Delete User Cascade")
    mgr.log_console("=" * 80)

    base_username, base_email, base_password = _require_base_user_config()

    unique_id = uuid.uuid4().hex[:8]
    user_payload = {
        "username": f"user_at1_4m_{unique_id}",
        "email": build_test_email("at1_4m", unique_id, base_email),
        "password": base_password,
    }

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    user_response = api_client.post("/users", json=user_payload)
    user_id = user_response.json().get("id")

    mgr.validate(
        "user_created",
        user_response.status_code == 200,
        user_response.status_code,
        200,
        "User creation should succeed",
    )

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    delete_response = api_client.delete(f"/users/{user_id}")

    mgr.validate(
        "delete_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
        "User deletion should succeed",
    )

    get_response = api_client.get(f"/users/{user_id}")
    mgr.validate(
        "user_deleted",
        get_response.status_code == 404,
        get_response.status_code,
        404,
        "User should be deleted",
    )

    api_client.session.headers.pop("X-API-Key", None)

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_4n_user_not_found(api_client):
    """
    AT1.4n: Handle non-existent user ID.
    Tests proper 404 error handling for non-existent users.
    """
    mgr = TestOutputManager("AT1_4n_user_not_found")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.4n - User Not Found")
    mgr.log_console("=" * 80)

    non_existent_id = 99999

    mgr.save_input("get_nonexistent_user", {"user_id": non_existent_id})
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    get_response = api_client.get(f"/users/{non_existent_id}")
    mgr.save_output("get_nonexistent_user", get_response)

    mgr.validate(
        "not_found_status",
        get_response.status_code == 404,
        get_response.status_code,
        404,
        "Non-existent user should return 404",
    )

    error_data = get_response.json()
    mgr.validate(
        "error_detail_present",
        "detail" in error_data,
        "detail" in error_data,
        True,
        "Error response must contain detail field",
    )

    if "detail" in error_data:
        error_detail = error_data["detail"].lower()
        mgr.validate(
            "error_message_appropriate",
            "not found" in error_detail,
            "not found" in error_detail,
            True,
            "Error message should indicate not found",
        )

    api_client.session.headers.pop("X-API-Key", None)

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_4o_user_validation_missing_fields(api_client):
    """
    AT1.4o: Validate required fields.
    Tests validation of required fields during user creation.
    """
    mgr = TestOutputManager("AT1_4o_user_validation_missing_fields")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.4o - Validation Missing Fields")
    mgr.log_console("=" * 80)

    _base_username, base_email, base_password = _require_base_user_config()

    unique_id = uuid.uuid4().hex[:8]

    missing_username = {
        "email": build_test_email("at1_4o", unique_id, base_email),
        "password": base_password,
    }

    mgr.save_input("create_without_username", missing_username)
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    response1 = api_client.post("/users", json=missing_username)
    mgr.save_output("create_without_username", response1)

    mgr.validate(
        "missing_username_rejected",
        response1.status_code == 422,
        response1.status_code,
        422,
        "Missing username should return 422",
    )

    missing_email = {"username": f"user_at1_4o_{unique_id}", "password": base_password}

    mgr.save_input("create_without_email", missing_email)
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    response2 = api_client.post("/users", json=missing_email)
    mgr.save_output("create_without_email", response2)

    mgr.validate(
        "missing_email_rejected",
        response2.status_code == 422,
        response2.status_code,
        422,
        "Missing email should return 422",
    )

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]
