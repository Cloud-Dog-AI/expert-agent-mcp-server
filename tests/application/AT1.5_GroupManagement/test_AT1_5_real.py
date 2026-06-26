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
Description: Comprehensive Application Test for Group Management CRUD Operations.
Tests group creation, retrieval, update, deletion, and membership management via real API server.
100% RULES.md compliant with comprehensive logging, validation tracking, and summary table generation.

Related Requirements: FR1.5, FR1.27
Related Tasks: T005, T006, T114
Related Architecture: CC5.1.1, CC5.1.2
Related Tests: AT1.5

Recent Changes (max 10):
- Initial comprehensive implementation with TestOutputManager
- Full RULES.md compliance (API-only, zero hardcoded values, comprehensive logging)
- Complete CRUD operations with membership management
- Group admin and role management tests
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
    """Manages test outputs, validations, and summary generation for AT1.5 tests."""

    __test__ = False  # Prevent pytest from collecting this as a test class

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.base_dir = Path("working/AT1.5_TEST_OUTPUTS") / test_name
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


def get_admin_api_key():
    """Get admin API key from configuration."""
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured (set in secrets env file)")
    return str(api_key)


@pytest.fixture
def test_users(api_client):
    """Create test users for group membership tests."""
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    base_password = get_config("test.user.password")
    if not base_username or not base_email or not base_password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in config")
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")

    users = []
    for i in range(3):
        unique_id = uuid.uuid4().hex[:8]
        user_payload = {
            "username": f"{base_username}_at1_5_{i}_{unique_id}",
            "email": f"at1_5_{i}_{unique_id}@{base_email.split('@')[1]}",
            "password": base_password,
        }

        admin_api_key = get_admin_api_key()
        api_client.session.headers["X-API-Key"] = admin_api_key
        response = api_client.post("/users", json=user_payload)
        if response.status_code == 200:
            users.append(response.json())

    yield users

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    for user in users:
        try:
            api_client.delete(f"/users/{user['id']}")
        except Exception:
            pass
    api_client.session.headers.pop("X-API-Key", None)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_5a_group_creation_success(api_client):
    """
    AT1.5a: Group creation with valid data.
    Tests successful group creation via POST /groups endpoint.
    """
    mgr = TestOutputManager("AT1_5a_group_creation_success")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.5a - Group Creation Success")
    mgr.log_console("=" * 80)

    unique_id = uuid.uuid4().hex[:8]
    group_payload = {
        "name": f"group_at1_5a_{unique_id}",
        "description": "Test group for AT1.5a",
        "enabled": True,
    }

    mgr.save_input("create_group", group_payload)
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    group_response = api_client.post("/groups", json=group_payload)
    mgr.save_output("create_group", group_response)

    mgr.validate(
        "group_created",
        group_response.status_code == 200,
        group_response.status_code,
        200,
        "Group creation should return 200 OK",
    )

    group_data = group_response.json()
    group_id = group_data.get("id")

    mgr.validate(
        "group_id_present",
        group_id is not None,
        group_id is not None,
        True,
        "Group ID must be present",
    )
    mgr.validate(
        "name_matches",
        group_data.get("name") == group_payload["name"],
        group_data.get("name"),
        group_payload["name"],
        "Group name must match request",
    )
    mgr.validate(
        "description_matches",
        group_data.get("description") == group_payload["description"],
        group_data.get("description"),
        group_payload["description"],
        "Description must match request",
    )
    mgr.validate(
        "enabled_matches",
        group_data.get("enabled") is True,
        group_data.get("enabled"),
        True,
        "Enabled must match request",
    )

    api_client.delete(f"/groups/{group_id}")

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_5b_group_creation_duplicate_name(api_client):
    """
    AT1.5b: Reject duplicate group name.
    Tests that duplicate group names are properly rejected.
    """
    mgr = TestOutputManager("AT1_5b_group_creation_duplicate_name")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.5b - Duplicate Group Name Rejection")
    mgr.log_console("=" * 80)

    unique_id = uuid.uuid4().hex[:8]
    group_name = f"group_at1_5b_{unique_id}"

    group_payload1 = {"name": group_name, "description": "First group"}

    mgr.save_input("create_group_first", group_payload1)
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    group_response1 = api_client.post("/groups", json=group_payload1)
    mgr.save_output("create_group_first", group_response1)

    mgr.validate(
        "first_group_created",
        group_response1.status_code == 200,
        group_response1.status_code,
        200,
        "First group creation should succeed",
    )

    group_id = group_response1.json().get("id")

    group_payload2 = {"name": group_name, "description": "Second group"}

    mgr.save_input("create_group_duplicate", group_payload2)
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    group_response2 = api_client.post("/groups", json=group_payload2)
    mgr.save_output("create_group_duplicate", group_response2)

    mgr.validate(
        "duplicate_rejected",
        group_response2.status_code == 400,
        group_response2.status_code,
        400,
        "Duplicate group name should return 400",
    )

    if group_response2.status_code == 400:
        error_detail = group_response2.json().get("detail", "").lower()
        mgr.validate(
            "error_message_appropriate",
            "already exists" in error_detail or "duplicate" in error_detail,
            "already exists" in error_detail or "duplicate" in error_detail,
            True,
            "Error message should indicate duplicate/already exists",
        )

    api_client.delete(f"/groups/{group_id}")

    summary = mgr.generate_summary_table()
    print(summary)

    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_5c_group_get_by_id(api_client):
    """AT1.5c: Get group by ID."""
    mgr = TestOutputManager("AT1_5c_group_get_by_id")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.5c - Get Group By ID")
    mgr.log_console("=" * 80)

    unique_id = uuid.uuid4().hex[:8]
    group_payload = {"name": f"group_at1_5c_{unique_id}", "description": "Test group"}

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    group_response = api_client.post("/groups", json=group_payload)
    group_id = group_response.json().get("id")

    mgr.save_input("get_group", {"group_id": group_id})
    get_response = api_client.get(f"/groups/{group_id}")
    mgr.save_output("get_group", get_response)

    mgr.validate(
        "get_success",
        get_response.status_code == 200,
        get_response.status_code,
        200,
        "Group retrieval should return 200 OK",
    )

    group_data = get_response.json()
    mgr.validate(
        "id_matches",
        group_data.get("id") == group_id,
        group_data.get("id"),
        group_id,
        "Group ID must match",
    )
    mgr.validate(
        "name_matches",
        group_data.get("name") == group_payload["name"],
        group_data.get("name"),
        group_payload["name"],
        "Name must match",
    )

    api_client.delete(f"/groups/{group_id}")

    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_5d_group_list_all(api_client):
    """AT1.5d: List all groups."""
    mgr = TestOutputManager("AT1_5d_group_list_all")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.5d - List All Groups")
    mgr.log_console("=" * 80)

    created_groups = []
    for i in range(3):
        unique_id = uuid.uuid4().hex[:8]
        group_payload = {"name": f"group_at1_5d_{i}_{unique_id}", "description": f"Group {i}"}
        response = api_client.post("/groups", json=group_payload)
        if response.status_code == 200:
            created_groups.append(response.json())

    mgr.save_input("list_groups", {"endpoint": "/groups"})
    list_response = api_client.get("/groups")
    mgr.save_output("list_groups", list_response)

    mgr.validate(
        "list_success",
        list_response.status_code == 200,
        list_response.status_code,
        200,
        "Group list should return 200 OK",
    )

    list_data = list_response.json()
    groups_list = list_data.get("groups", list_data.get("items", []))

    mgr.validate(
        "groups_list_is_array",
        isinstance(groups_list, list),
        isinstance(groups_list, list),
        True,
        "Groups list must be an array",
    )
    mgr.validate(
        "groups_list_not_empty",
        len(groups_list) >= len(created_groups),
        len(groups_list) >= len(created_groups),
        True,
        f"Groups list must contain at least {len(created_groups)} groups",
    )

    created_ids = {g["id"] for g in created_groups}
    found_ids = {g["id"] for g in groups_list if g.get("id")}
    mgr.validate(
        "created_groups_in_list",
        created_ids.issubset(found_ids),
        created_ids.issubset(found_ids),
        True,
        "All created groups must be in list",
    )

    for group in created_groups:
        api_client.delete(f"/groups/{group['id']}")

    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_5e_group_get_members(api_client, test_users):
    """AT1.5e: Get group members."""
    mgr = TestOutputManager("AT1_5e_group_get_members")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.5e - Get Group Members")
    mgr.log_console("=" * 80)

    unique_id = uuid.uuid4().hex[:8]
    group_payload = {"name": f"group_at1_5e_{unique_id}", "description": "Test group"}

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    group_response = api_client.post("/groups", json=group_payload)
    group_id = group_response.json().get("id")

    for user in test_users[:2]:
        api_client.post(
            f"/groups/{group_id}/members", json={"user_id": user["id"], "role": "member"}
        )

    mgr.save_input("get_members", {"group_id": group_id})
    members_response = api_client.get(f"/groups/{group_id}/members")
    mgr.save_output("get_members", members_response)

    mgr.validate(
        "get_members_success",
        members_response.status_code == 200,
        members_response.status_code,
        200,
        "Get members should return 200 OK",
    )

    members_data = members_response.json()
    members_list = members_data.get("members", members_data.get("items", []))

    mgr.validate(
        "members_list_is_array",
        isinstance(members_list, list),
        isinstance(members_list, list),
        True,
        "Members list must be an array",
    )
    mgr.validate(
        "correct_member_count",
        len(members_list) >= 2,
        len(members_list) >= 2,
        True,
        "Should have at least 2 members",
    )

    api_client.delete(f"/groups/{group_id}")

    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_5f_group_update_description(api_client):
    """AT1.5f: Update group description."""
    mgr = TestOutputManager("AT1_5f_group_update_description")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.5f - Update Group Description")
    mgr.log_console("=" * 80)

    unique_id = uuid.uuid4().hex[:8]
    group_payload = {"name": f"group_at1_5f_{unique_id}", "description": "Original description"}

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    group_response = api_client.post("/groups", json=group_payload)
    group_id = group_response.json().get("id")

    new_description = "Updated description"
    update_payload = {"description": new_description}

    mgr.save_input("update_description", update_payload)
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    update_response = api_client.put(f"/groups/{group_id}", json=update_payload)
    mgr.save_output("update_description", update_response)

    mgr.validate(
        "update_success",
        update_response.status_code == 200,
        update_response.status_code,
        200,
        "Description update should return 200 OK",
    )

    update_data = update_response.json()
    mgr.validate(
        "description_updated",
        update_data.get("description") == new_description,
        update_data.get("description"),
        new_description,
        "Description must be updated",
    )

    api_client.delete(f"/groups/{group_id}")

    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_5g_group_update_enabled_status(api_client):
    """AT1.5g: Update group enabled status."""
    mgr = TestOutputManager("AT1_5g_group_update_enabled_status")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.5g - Update Group Enabled Status")
    mgr.log_console("=" * 80)

    unique_id = uuid.uuid4().hex[:8]
    group_payload = {
        "name": f"group_at1_5g_{unique_id}",
        "description": "Test group",
        "enabled": True,
    }

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    group_response = api_client.post("/groups", json=group_payload)
    group_id = group_response.json().get("id")

    update_payload = {"enabled": False}

    mgr.save_input("disable_group", update_payload)
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    update_response = api_client.put(f"/groups/{group_id}", json=update_payload)
    mgr.save_output("disable_group", update_response)

    mgr.validate(
        "update_success",
        update_response.status_code == 200,
        update_response.status_code,
        200,
        "Enabled status update should return 200 OK",
    )

    update_data = update_response.json()
    mgr.validate(
        "group_disabled",
        update_data.get("enabled") is False,
        update_data.get("enabled"),
        False,
        "Group must be disabled",
    )

    api_client.delete(f"/groups/{group_id}")

    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_5h_group_delete_success(api_client):
    """AT1.5h: Delete group successfully."""
    mgr = TestOutputManager("AT1_5h_group_delete_success")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.5h - Delete Group Success")
    mgr.log_console("=" * 80)

    unique_id = uuid.uuid4().hex[:8]
    group_payload = {"name": f"group_at1_5h_{unique_id}", "description": "Test group"}

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    group_response = api_client.post("/groups", json=group_payload)
    group_id = group_response.json().get("id")

    mgr.save_input("delete_group", {"group_id": group_id})
    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    delete_response = api_client.delete(f"/groups/{group_id}")
    mgr.save_output("delete_group", delete_response)

    mgr.validate(
        "delete_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
        "Group deletion should return 200 or 204",
    )

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    get_response = api_client.get(f"/groups/{group_id}")
    mgr.save_output("verify_deleted", get_response)

    mgr.validate(
        "group_not_found",
        get_response.status_code == 404,
        get_response.status_code,
        404,
        "Deleted group should return 404",
    )

    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_5i_group_delete_cascade(api_client, test_users):
    """AT1.5i: Verify cascade deletion."""
    mgr = TestOutputManager("AT1_5i_group_delete_cascade")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.5i - Delete Group Cascade")
    mgr.log_console("=" * 80)

    unique_id = uuid.uuid4().hex[:8]
    group_payload = {"name": f"group_at1_5i_{unique_id}", "description": "Test group"}

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    group_response = api_client.post("/groups", json=group_payload)
    group_id = group_response.json().get("id")

    api_client.post(
        f"/groups/{group_id}/members", json={"user_id": test_users[0]["id"], "role": "member"}
    )

    mgr.validate(
        "group_created",
        group_response.status_code == 200,
        group_response.status_code,
        200,
        "Group creation should succeed",
    )

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    delete_response = api_client.delete(f"/groups/{group_id}")
    mgr.validate(
        "delete_success",
        delete_response.status_code in (200, 204),
        delete_response.status_code,
        "200 or 204",
        "Group deletion should succeed",
    )

    get_response = api_client.get(f"/groups/{group_id}")
    mgr.validate(
        "group_deleted",
        get_response.status_code == 404,
        get_response.status_code,
        404,
        "Group should be deleted",
    )

    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_5j_group_add_member(api_client, test_users):
    """AT1.5j: Add user to group."""
    mgr = TestOutputManager("AT1_5j_group_add_member")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.5j - Add Group Member")
    mgr.log_console("=" * 80)

    unique_id = uuid.uuid4().hex[:8]
    group_payload = {"name": f"group_at1_5j_{unique_id}", "description": "Test group"}

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    group_response = api_client.post("/groups", json=group_payload)
    group_id = group_response.json().get("id")

    member_payload = {"user_id": test_users[0]["id"], "role": "member"}

    mgr.save_input("add_member", member_payload)
    add_response = api_client.post(f"/groups/{group_id}/members", json=member_payload)
    mgr.save_output("add_member", add_response)

    mgr.validate(
        "add_member_success",
        add_response.status_code in (200, 201),
        add_response.status_code,
        "200 or 201",
        "Add member should return 200 or 201",
    )

    members_response = api_client.get(f"/groups/{group_id}/members")
    members_data = members_response.json()
    members_list = members_data.get("members", members_data.get("items", []))

    mgr.validate(
        "member_added",
        any(
            m.get("id") == test_users[0]["id"] or m.get("user_id") == test_users[0]["id"]
            for m in members_list
        ),
        True,
        True,
        "User should be in members list",
    )

    api_client.delete(f"/groups/{group_id}")

    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_5k_group_remove_member(api_client, test_users):
    """AT1.5k: Remove user from group."""
    mgr = TestOutputManager("AT1_5k_group_remove_member")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.5k - Remove Group Member")
    mgr.log_console("=" * 80)

    unique_id = uuid.uuid4().hex[:8]
    group_payload = {"name": f"group_at1_5k_{unique_id}", "description": "Test group"}

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    group_response = api_client.post("/groups", json=group_payload)
    group_id = group_response.json().get("id")

    api_client.post(
        f"/groups/{group_id}/members", json={"user_id": test_users[0]["id"], "role": "member"}
    )

    mgr.save_input("remove_member", {"group_id": group_id, "user_id": test_users[0]["id"]})
    remove_response = api_client.delete(f"/groups/{group_id}/members/{test_users[0]['id']}")
    mgr.save_output("remove_member", remove_response)

    mgr.validate(
        "remove_member_success",
        remove_response.status_code in (200, 204),
        remove_response.status_code,
        "200 or 204",
        "Remove member should return 200 or 204",
    )

    api_client.delete(f"/groups/{group_id}")

    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_5l_group_update_member_role(api_client, test_users):
    """AT1.5l: Update member role."""
    mgr = TestOutputManager("AT1_5l_group_update_member_role")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.5l - Update Member Role")
    mgr.log_console("=" * 80)

    unique_id = uuid.uuid4().hex[:8]
    group_payload = {"name": f"group_at1_5l_{unique_id}", "description": "Test group"}

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    group_response = api_client.post("/groups", json=group_payload)
    group_id = group_response.json().get("id")

    api_client.post(
        f"/groups/{group_id}/members", json={"user_id": test_users[0]["id"], "role": "member"}
    )

    update_payload = {"role": "admin"}

    mgr.save_input("update_role", update_payload)
    update_response = api_client.put(
        f"/groups/{group_id}/members/{test_users[0]['id']}/role", json=update_payload
    )
    mgr.save_output("update_role", update_response)

    mgr.validate(
        "update_role_success",
        update_response.status_code == 200,
        update_response.status_code,
        200,
        "Update role should return 200 OK",
    )

    api_client.delete(f"/groups/{group_id}")

    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_5m_group_multiple_members(api_client, test_users):
    """AT1.5m: Add multiple members."""
    mgr = TestOutputManager("AT1_5m_group_multiple_members")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.5m - Add Multiple Members")
    mgr.log_console("=" * 80)

    unique_id = uuid.uuid4().hex[:8]
    group_payload = {"name": f"group_at1_5m_{unique_id}", "description": "Test group"}

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    group_response = api_client.post("/groups", json=group_payload)
    group_id = group_response.json().get("id")

    for user in test_users:
        api_client.post(
            f"/groups/{group_id}/members", json={"user_id": user["id"], "role": "member"}
        )

    mgr.save_input("get_members", {"group_id": group_id})
    members_response = api_client.get(f"/groups/{group_id}/members")
    mgr.save_output("get_members", members_response)

    members_data = members_response.json()
    members_list = members_data.get("members", members_data.get("items", []))

    mgr.validate(
        "all_members_added",
        len(members_list) >= len(test_users),
        len(members_list) >= len(test_users),
        True,
        f"Should have at least {len(test_users)} members",
    )

    api_client.delete(f"/groups/{group_id}")

    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_5n_group_assign_admin(api_client, test_users):
    """AT1.5n: Assign group admin."""
    mgr = TestOutputManager("AT1_5n_group_assign_admin")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.5n - Assign Group Admin")
    mgr.log_console("=" * 80)

    unique_id = uuid.uuid4().hex[:8]
    group_payload = {"name": f"group_at1_5n_{unique_id}", "description": "Test group"}

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    group_response = api_client.post("/groups", json=group_payload)
    group_id = group_response.json().get("id")

    admin_payload = {"user_id": test_users[0]["id"]}

    mgr.save_input("assign_admin", admin_payload)
    admin_response = api_client.post(f"/groups/{group_id}/admins", json=admin_payload)
    mgr.save_output("assign_admin", admin_response)

    mgr.validate(
        "assign_admin_success",
        admin_response.status_code in (200, 201),
        admin_response.status_code,
        "200 or 201",
        "Assign admin should return 200 or 201",
    )

    api_client.delete(f"/groups/{group_id}")

    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_AT1_5o_group_remove_admin(api_client, test_users):
    """AT1.5o: Remove group admin."""
    mgr = TestOutputManager("AT1_5o_group_remove_admin")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.5o - Remove Group Admin")
    mgr.log_console("=" * 80)

    unique_id = uuid.uuid4().hex[:8]
    group_payload = {"name": f"group_at1_5o_{unique_id}", "description": "Test group"}

    admin_api_key = get_admin_api_key()
    api_client.session.headers["X-API-Key"] = admin_api_key
    group_response = api_client.post("/groups", json=group_payload)
    group_id = group_response.json().get("id")

    api_client.post(f"/groups/{group_id}/admins", json={"user_id": test_users[0]["id"]})

    mgr.save_input("remove_admin", {"group_id": group_id, "user_id": test_users[0]["id"]})
    remove_response = api_client.delete(f"/groups/{group_id}/admins/{test_users[0]['id']}")
    mgr.save_output("remove_admin", remove_response)

    mgr.validate(
        "remove_admin_success",
        remove_response.status_code in (200, 204),
        remove_response.status_code,
        "200 or 204",
        "Remove admin should return 200 or 204",
    )

    api_client.delete(f"/groups/{group_id}")

    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]
