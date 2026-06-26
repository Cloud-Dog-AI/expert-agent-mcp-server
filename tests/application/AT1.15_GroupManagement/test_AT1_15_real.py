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
AT1.15 - Group Management REAL Tests
License: Apache 2.0
Ownership: Cloud Dog

These are REAL tests that validate actual business logic, not just API status codes.
Each test saves ALL inputs, outputs, and validations.
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

import pytest

# Add parent directory to path for shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import create_api_client_fixture, validate_config_loaded

from src.config.loader import get_config, load_config


def _get_test_user_basics() -> tuple[str, str, str]:
    """Return (base_username, email_domain, base_password) from config."""
    load_config.cache_clear()

    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    base_password = get_config("test.user.password")

    if not base_username or not base_email or not base_password:
        pytest.fail(
            "Missing test.user.username/test.user.email/test.user.password in config (--env)"
        )
    if "@" not in base_email:
        pytest.fail("test.user.email must include an '@' to derive a domain")

    domain = base_email.split("@", 1)[1]
    return base_username, domain, base_password


class TestOutputManager:
    __test__ = False  # Prevent pytest from collecting this helper as a test class
    """Manages saving ALL test inputs, outputs, and validations."""

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.base_dir = Path(f"working/AT1.15_TEST_OUTPUTS/{test_name}")
        self.inputs_dir = self.base_dir / "inputs"
        self.outputs_dir = self.base_dir / "outputs"
        self.validations_dir = self.base_dir / "validations"

        # Create directories
        for dir in [self.inputs_dir, self.outputs_dir, self.validations_dir]:
            dir.mkdir(parents=True, exist_ok=True)

        self.operation_count = 0
        self.validation_count = 0
        self.validations_passed = 0
        self.validations_failed = 0
        self.operations = []
        self.validations = []

    def save_request(self, operation_name: str, request_data: dict) -> int:
        """Save request input to file."""
        self.operation_count += 1
        filename = f"{self.operation_count:02d}_{operation_name}_request.json"
        filepath = self.inputs_dir / filename

        with open(filepath, "w") as f:
            json.dump(
                {
                    "operation": operation_name,
                    "timestamp": datetime.utcnow().isoformat(),
                    "data": request_data,
                },
                f,
                indent=2,
            )

        self.operations.append(
            {
                "number": self.operation_count,
                "name": operation_name,
                "input_file": str(filepath.absolute()),
            }
        )

        return self.operation_count

    def save_response(
        self, operation_number: int, operation_name: str, response_data: dict, status_code: int
    ):
        """Save response output to file."""
        filename = f"{operation_number:02d}_{operation_name}_response.json"
        filepath = self.outputs_dir / filename

        with open(filepath, "w") as f:
            json.dump(
                {
                    "operation": operation_name,
                    "timestamp": datetime.utcnow().isoformat(),
                    "status_code": status_code,
                    "data": response_data,
                },
                f,
                indent=2,
            )

        # Update operation record
        for op in self.operations:
            if op["number"] == operation_number:
                op["output_file"] = str(filepath.absolute())
                op["status_code"] = status_code
                break

    def save_validation(
        self, validation_name: str, expected: any, actual: any, passed: bool, reason: str = ""
    ):
        """Save validation check to file."""
        self.validation_count += 1
        if passed:
            self.validations_passed += 1
        else:
            self.validations_failed += 1

        filename = f"{self.validation_count:02d}_{validation_name}.json"
        filepath = self.validations_dir / filename

        with open(filepath, "w") as f:
            json.dump(
                {
                    "validation": validation_name,
                    "timestamp": datetime.utcnow().isoformat(),
                    "expected": expected,
                    "actual": actual,
                    "passed": passed,
                    "reason": reason,
                },
                f,
                indent=2,
            )

        self.validations.append(
            {
                "number": self.validation_count,
                "name": validation_name,
                "passed": passed,
                "file": str(filepath.absolute()),
            }
        )

    def generate_summary_table(self, scope: str):
        """Generate summary table in markdown with clickable file:// URIs."""
        summary_file = self.base_dir / "test_summary_table.md"

        with open(summary_file, "w") as f:
            f.write(f"# {self.test_name} - Test Summary\n\n")
            f.write(f"**Scope**: {scope}\n\n")
            f.write(f"**Test Executed**: {datetime.utcnow().isoformat()}\n\n")

            # Statistics
            f.write("## Statistics\n\n")
            f.write(f"- **Total API Operations**: {self.operation_count}\n")
            f.write(f"- **Total Validations**: {self.validation_count}\n")
            f.write(
                f"- **Validations Passed**: {self.validations_passed} ({100 * self.validations_passed // self.validation_count if self.validation_count > 0 else 0}%)\n"
            )
            f.write(f"- **Validations Failed**: {self.validations_failed}\n\n")

            # Operations Table
            f.write("## API Operations\n\n")
            f.write("| # | Operation | Status | Input File | Output File |\n")
            f.write("|---|-----------|--------|------------|-------------|\n")
            for op in self.operations:
                status = (
                    f"✅ {op.get('status_code', 'N/A')}"
                    if op.get("status_code", 0) < 400
                    else f"❌ {op.get('status_code', 'N/A')}"
                )
                input_uri = f"file://{op['input_file']}"
                output_uri = (
                    f"file://{op.get('output_file', '')}" if op.get("output_file") else "N/A"
                )
                f.write(
                    f"| {op['number']} | {op['name']} | {status} | [{Path(op['input_file']).name}]({input_uri}) | [{Path(op.get('output_file', '')).name}]({output_uri}) |\n"
                )

            f.write("\n## Validations\n\n")
            f.write("| # | Validation | Result | File |\n")
            f.write("|---|------------|--------|------|\n")
            for val in self.validations:
                result = "✅ PASS" if val["passed"] else "❌ FAIL"
                val_uri = f"file://{val['file']}"
                f.write(
                    f"| {val['number']} | {val['name']} | {result} | [{Path(val['file']).name}]({val_uri}) |\n"
                )

            f.write("\n## Overall Result\n\n")
            if self.validations_failed == 0 and self.validation_count > 0:
                f.write("### ✅ ALL VALIDATIONS PASSED\n")
            elif self.validations_failed > 0:
                f.write(f"### ❌ {self.validations_failed} VALIDATION(S) FAILED\n")
            else:
                f.write("### ⚠️  NO VALIDATIONS RUN\n")

        # Also save JSON version
        results_file = self.base_dir / "test_results.json"
        with open(results_file, "w") as f:
            json.dump(
                {
                    "test_name": self.test_name,
                    "scope": scope,
                    "timestamp": datetime.utcnow().isoformat(),
                    "statistics": {
                        "operations": self.operation_count,
                        "validations": self.validation_count,
                        "passed": self.validations_passed,
                        "failed": self.validations_failed,
                    },
                    "operations": self.operations,
                    "validations": self.validations,
                    "summary_table": str(summary_file.absolute()),
                },
                f,
                indent=2,
            )

        return str(summary_file)


@pytest.fixture(scope="module")
def api_client():
    """Create API client that connects to real running API server."""
    validate_config_loaded()
    return create_api_client_fixture(check_health=True)()
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_15a_create_group_and_verify(api_client):
    """
    AT1.15a - Create Group and Verify It Exists

    SCOPE: Create a group via API, then retrieve it and verify ALL fields match exactly.
    This is a REAL test that validates actual data persistence and retrieval accuracy.
    """
    output = TestOutputManager("AT1.15a_create_and_verify")

    print("\n" + "=" * 80)
    print("AT1.15a - Create Group and Verify It Exists")
    print("=" * 80)

    # Step 1: Create group
    group_data = {
        "name": f"test_group_{uuid.uuid4().hex[:8]}",
        "description": "Test group for AT1.15a validation",
        "enabled": True,
    }

    print(f"\n[1/3] Creating group: {group_data['name']}")
    op_num = output.save_request("create_group", group_data)

    create_response = api_client.post("/groups", json=group_data)
    output.save_response(
        op_num,
        "create_group",
        create_response.json() if create_response.status_code == 200 else {},
        create_response.status_code,
    )

    # Validation 1: Creation succeeded
    output.save_validation(
        "group_creation_succeeded",
        expected=200,
        actual=create_response.status_code,
        passed=create_response.status_code == 200,
        reason=f"Expected HTTP 200, got {create_response.status_code}",
    )

    if create_response.status_code != 200:
        print(f"❌ Group creation failed with status {create_response.status_code}")
        summary = output.generate_summary_table(
            "Create a group via API, then retrieve it and verify ALL fields match"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "Group creation failed"

    created_group = create_response.json()
    group_id = created_group.get("id")
    print(f"✅ Group created with ID: {group_id}")

    # Validation 2: Response contains required fields
    required_fields = ["id", "name", "description", "enabled"]
    has_all_fields = all(field in created_group for field in required_fields)
    output.save_validation(
        "response_has_required_fields",
        expected=required_fields,
        actual=list(created_group.keys()),
        passed=has_all_fields,
        reason="All required fields present"
        if has_all_fields
        else f"Missing fields: {set(required_fields) - set(created_group.keys())}",
    )

    # Step 2: Retrieve the group
    print(f"\n[2/3] Retrieving group {group_id}")
    op_num = output.save_request("get_group", {"group_id": group_id})

    get_response = api_client.get(f"/groups/{group_id}")
    output.save_response(
        op_num,
        "get_group",
        get_response.json() if get_response.status_code == 200 else {},
        get_response.status_code,
    )

    # Validation 3: Retrieval succeeded
    output.save_validation(
        "group_retrieval_succeeded",
        expected=200,
        actual=get_response.status_code,
        passed=get_response.status_code == 200,
        reason=f"Expected HTTP 200, got {get_response.status_code}",
    )

    if get_response.status_code != 200:
        print(f"❌ Group retrieval failed with status {get_response.status_code}")
        summary = output.generate_summary_table(
            "Create a group via API, then retrieve it and verify ALL fields match"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "Group retrieval failed"

    retrieved_group = get_response.json()
    print("✅ Group retrieved")

    # Step 3: Validate all fields match
    print("\n[3/3] Validating field accuracy")

    # Validation 4: Name matches
    name_matches = retrieved_group.get("name") == group_data["name"]
    output.save_validation(
        "name_field_matches",
        expected=group_data["name"],
        actual=retrieved_group.get("name"),
        passed=name_matches,
        reason="Name field matches" if name_matches else "Name field does not match",
    )
    print(f"{'✅' if name_matches else '❌'} Name: {retrieved_group.get('name')}")

    # Validation 5: Description matches
    desc_matches = retrieved_group.get("description") == group_data["description"]
    output.save_validation(
        "description_field_matches",
        expected=group_data["description"],
        actual=retrieved_group.get("description"),
        passed=desc_matches,
        reason="Description field matches" if desc_matches else "Description field does not match",
    )
    print(f"{'✅' if desc_matches else '❌'} Description: {retrieved_group.get('description')}")

    # Validation 6: Enabled matches
    enabled_matches = retrieved_group.get("enabled") == group_data["enabled"]
    output.save_validation(
        "enabled_field_matches",
        expected=group_data["enabled"],
        actual=retrieved_group.get("enabled"),
        passed=enabled_matches,
        reason="Enabled field matches" if enabled_matches else "Enabled field does not match",
    )
    print(f"{'✅' if enabled_matches else '❌'} Enabled: {retrieved_group.get('enabled')}")

    # Validation 7: ID is consistent
    id_matches = retrieved_group.get("id") == created_group.get("id")
    output.save_validation(
        "id_consistency",
        expected=created_group.get("id"),
        actual=retrieved_group.get("id"),
        passed=id_matches,
        reason="ID is consistent" if id_matches else "ID changed between create and retrieve",
    )
    print(f"{'✅' if id_matches else '❌'} ID consistency")

    # Cleanup
    api_client.delete(f"/groups/{group_id}")

    # Generate summary
    summary = output.generate_summary_table(
        "Create a group via API, then retrieve it and verify ALL fields match"
    )

    # Print the actual table to console
    print("\n" + "=" * 80)
    print("TEST SUMMARY TABLE")
    print("=" * 80)
    with open(summary, "r") as f:
        print(f.read())
    print("=" * 80)

    # Final assertion
    assert output.validations_failed == 0, (
        f"{output.validations_failed} validation(s) failed - see {summary}"
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_15b_update_group_and_verify(api_client):
    """
    AT1.15b - Update Group Details and Verify Changes

    Scope: Create group, update name/description/enabled, retrieve and verify changes persisted
    Validates: Group update functionality, field modification persistence

    This is a REAL test with REAL validation.
    """
    output = TestOutputManager("AT1.15b_update_and_verify")

    print("\n" + "=" * 80)
    print("AT1.15b - Update Group Details and Verify Changes")
    print("=" * 80)

    # Step 1: Create initial group
    original_name = f"test_group_{uuid.uuid4().hex[:8]}"
    group_data = {"name": original_name, "description": "Original description", "enabled": True}

    print(f"\n[1/5] Creating group: {group_data['name']}")
    op_num = output.save_request("create_group", group_data)

    create_response = api_client.post("/groups", json=group_data)
    output.save_response(
        op_num,
        "create_group",
        create_response.json() if create_response.status_code == 200 else {},
        create_response.status_code,
    )

    # Validation 1: Creation succeeded
    output.save_validation(
        "group_creation_succeeded",
        expected=200,
        actual=create_response.status_code,
        passed=create_response.status_code == 200,
        reason=f"Expected HTTP 200, got {create_response.status_code}",
    )

    if create_response.status_code != 200:
        print(f"❌ Group creation failed with status {create_response.status_code}")
        summary = output.generate_summary_table(
            "Create group, update details, verify changes persisted"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "Group creation failed"

    created_group = create_response.json()
    group_id = created_group.get("id")
    print(f"✅ Group created with ID: {group_id}")

    # Step 2: Update group details
    updated_name = f"updated_group_{uuid.uuid4().hex[:8]}"
    update_data = {
        "name": updated_name,
        "description": "Updated description after modification",
        "enabled": False,
    }

    print(f"\n[2/5] Updating group {group_id} with new details")
    op_num = output.save_request("update_group", {"group_id": group_id, **update_data})

    update_response = api_client.put(f"/groups/{group_id}", json=update_data)
    output.save_response(
        op_num,
        "update_group",
        update_response.json() if update_response.status_code == 200 else {},
        update_response.status_code,
    )

    # Validation 2: Update succeeded
    output.save_validation(
        "group_update_succeeded",
        expected=200,
        actual=update_response.status_code,
        passed=update_response.status_code == 200,
        reason=f"Expected HTTP 200, got {update_response.status_code}",
    )

    if update_response.status_code != 200:
        print(f"❌ Group update failed with status {update_response.status_code}")
        api_client.delete(f"/groups/{group_id}")
        summary = output.generate_summary_table(
            "Create group, update details, verify changes persisted"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "Group update failed"

    print("✅ Group updated")

    # Step 3: Retrieve the updated group
    print(f"\n[3/5] Retrieving updated group {group_id}")
    op_num = output.save_request("get_updated_group", {"group_id": group_id})

    get_response = api_client.get(f"/groups/{group_id}")
    output.save_response(
        op_num,
        "get_updated_group",
        get_response.json() if get_response.status_code == 200 else {},
        get_response.status_code,
    )

    # Validation 3: Retrieval succeeded
    output.save_validation(
        "group_retrieval_succeeded",
        expected=200,
        actual=get_response.status_code,
        passed=get_response.status_code == 200,
        reason=f"Expected HTTP 200, got {get_response.status_code}",
    )

    if get_response.status_code != 200:
        print(f"❌ Group retrieval failed with status {get_response.status_code}")
        api_client.delete(f"/groups/{group_id}")
        summary = output.generate_summary_table(
            "Create group, update details, verify changes persisted"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "Group retrieval failed"

    retrieved_group = get_response.json()
    print("✅ Group retrieved")

    # Step 4: Validate all updated fields match
    print("\n[4/5] Validating updated field accuracy")

    # Validation 4: Name was updated
    name_updated = retrieved_group.get("name") == updated_name
    output.save_validation(
        "name_was_updated",
        expected=updated_name,
        actual=retrieved_group.get("name"),
        passed=name_updated,
        reason=f"Name changed from '{original_name}' to '{updated_name}'"
        if name_updated
        else f"Name did not update (still '{retrieved_group.get('name')}')",
    )
    print(f"{'✅' if name_updated else '❌'} Name updated: {retrieved_group.get('name')}")

    # Validation 5: Description was updated
    desc_updated = retrieved_group.get("description") == update_data["description"]
    output.save_validation(
        "description_was_updated",
        expected=update_data["description"],
        actual=retrieved_group.get("description"),
        passed=desc_updated,
        reason="Description updated correctly" if desc_updated else "Description did not update",
    )
    print(
        f"{'✅' if desc_updated else '❌'} Description updated: {retrieved_group.get('description')}"
    )

    # Validation 6: Enabled status was updated
    enabled_updated = retrieved_group.get("enabled") == update_data["enabled"]
    output.save_validation(
        "enabled_status_was_updated",
        expected=update_data["enabled"],
        actual=retrieved_group.get("enabled"),
        passed=enabled_updated,
        reason="Enabled changed from True to False"
        if enabled_updated
        else f"Enabled did not update (still {retrieved_group.get('enabled')})",
    )
    print(f"{'✅' if enabled_updated else '❌'} Enabled updated: {retrieved_group.get('enabled')}")

    # Validation 7: ID remained the same
    id_unchanged = retrieved_group.get("id") == group_id
    output.save_validation(
        "id_remained_unchanged",
        expected=group_id,
        actual=retrieved_group.get("id"),
        passed=id_unchanged,
        reason="ID correctly unchanged during update" if id_unchanged else "ID incorrectly changed",
    )
    print(f"{'✅' if id_unchanged else '❌'} ID unchanged: {retrieved_group.get('id')}")

    # Validation 8: Ensure old name is NOT present
    name_is_not_old = retrieved_group.get("name") != original_name
    output.save_validation(
        "old_name_not_present",
        expected="NOT " + original_name,
        actual=retrieved_group.get("name"),
        passed=name_is_not_old,
        reason="Old name correctly replaced" if name_is_not_old else "Old name still present",
    )
    print(f"{'✅' if name_is_not_old else '❌'} Old name replaced")

    # Step 5: Cleanup
    print("\n[5/5] Cleaning up")
    api_client.delete(f"/groups/{group_id}")
    print("✅ Group deleted")

    # Generate summary
    summary = output.generate_summary_table(
        "Create group, update details (name/description/enabled), verify all changes persisted"
    )

    # Print the actual table to console
    print("\n" + "=" * 80)
    print("TEST SUMMARY TABLE")
    print("=" * 80)
    with open(summary, "r") as f:
        print(f.read())
    print("=" * 80)

    # Final assertion
    assert output.validations_failed == 0, (
        f"{output.validations_failed} validation(s) failed - see {summary}"
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_15c_delete_group_and_verify(api_client):
    """
    AT1.15c - Delete Group and Verify Removal

    Scope: Create group, delete it, verify 404 on retrieval
    Validates: Group deletion, proper error handling for non-existent groups

    This is a REAL test with REAL validation.
    """
    output = TestOutputManager("AT1.15c_delete_and_verify")

    print("\n" + "=" * 80)
    print("AT1.15c - Delete Group and Verify Removal")
    print("=" * 80)

    # Step 1: Create group
    group_data = {
        "name": f"test_group_delete_{uuid.uuid4().hex[:8]}",
        "description": "Group to be deleted",
        "enabled": True,
    }

    print(f"\n[1/4] Creating group: {group_data['name']}")
    op_num = output.save_request("create_group", group_data)

    create_response = api_client.post("/groups", json=group_data)
    output.save_response(
        op_num,
        "create_group",
        create_response.json() if create_response.status_code == 200 else {},
        create_response.status_code,
    )

    # Validation 1: Creation succeeded
    output.save_validation(
        "group_creation_succeeded",
        expected=200,
        actual=create_response.status_code,
        passed=create_response.status_code == 200,
        reason=f"Expected HTTP 200, got {create_response.status_code}",
    )

    if create_response.status_code != 200:
        print(f"❌ Group creation failed with status {create_response.status_code}")
        summary = output.generate_summary_table("Create group, delete it, verify 404 on retrieval")
        print(f"\n📄 Summary: {summary}")
        assert False, "Group creation failed"

    created_group = create_response.json()
    group_id = created_group.get("id")
    print(f"✅ Group created with ID: {group_id}")

    # Step 2: Verify group exists before deletion
    print(f"\n[2/4] Verifying group {group_id} exists before deletion")
    op_num = output.save_request("get_group_before_delete", {"group_id": group_id})

    get_before_response = api_client.get(f"/groups/{group_id}")
    output.save_response(
        op_num,
        "get_group_before_delete",
        get_before_response.json() if get_before_response.status_code == 200 else {},
        get_before_response.status_code,
    )

    # Validation 2: Group exists before deletion
    output.save_validation(
        "group_exists_before_deletion",
        expected=200,
        actual=get_before_response.status_code,
        passed=get_before_response.status_code == 200,
        reason="Group should exist before deletion",
    )
    print("✅ Group exists")

    # Step 3: Delete group
    print(f"\n[3/4] Deleting group {group_id}")
    op_num = output.save_request("delete_group", {"group_id": group_id})

    delete_response = api_client.delete(f"/groups/{group_id}")
    output.save_response(
        op_num,
        "delete_group",
        delete_response.json() if delete_response.status_code in [200, 204] else {},
        delete_response.status_code,
    )

    # Validation 3: Deletion succeeded
    deletion_succeeded = delete_response.status_code in [200, 204]
    output.save_validation(
        "group_deletion_succeeded",
        expected="200 or 204",
        actual=delete_response.status_code,
        passed=deletion_succeeded,
        reason=f"Expected HTTP 200 or 204, got {delete_response.status_code}",
    )

    if not deletion_succeeded:
        print(f"❌ Group deletion failed with status {delete_response.status_code}")
        summary = output.generate_summary_table("Create group, delete it, verify 404 on retrieval")
        print(f"\n📄 Summary: {summary}")
        assert False, "Group deletion failed"

    print("✅ Group deleted")

    # Step 4: Verify group no longer exists (404)
    print(f"\n[4/4] Verifying group {group_id} no longer exists")
    op_num = output.save_request("get_group_after_delete", {"group_id": group_id})

    get_after_response = api_client.get(f"/groups/{group_id}")
    output.save_response(
        op_num,
        "get_group_after_delete",
        get_after_response.json()
        if get_after_response.status_code != 404
        else {"error": "not found"},
        get_after_response.status_code,
    )

    # Validation 4: Group returns 404
    returns_404 = get_after_response.status_code == 404
    output.save_validation(
        "group_returns_404_after_deletion",
        expected=404,
        actual=get_after_response.status_code,
        passed=returns_404,
        reason=f"Expected HTTP 404 (not found), got {get_after_response.status_code}",
    )
    print(f"{'✅' if returns_404 else '❌'} Group returns 404: {get_after_response.status_code}")

    # Validation 5: Response indicates not found
    if get_after_response.status_code == 404:
        response_data = get_after_response.json() if get_after_response.text else {}
        has_error_message = (
            "detail" in response_data or "error" in response_data or "message" in response_data
        )
        output.save_validation(
            "error_message_present",
            expected="Error message in response",
            actual=str(response_data),
            passed=has_error_message,
            reason="Error message present in 404 response"
            if has_error_message
            else "No error message in response",
        )
        print(f"{'✅' if has_error_message else '❌'} Error message present")
    else:
        output.save_validation(
            "error_message_present",
            expected="Error message in response",
            actual=f"Non-404 status: {get_after_response.status_code}",
            passed=False,
            reason="Got non-404 status code",
        )
        print(f"❌ Expected 404, got {get_after_response.status_code}")

    # Validation 6: Deletion response contained group_id
    if deletion_succeeded:
        delete_data = delete_response.json()
        contains_id = "id" in delete_data or "group_id" in delete_data
        output.save_validation(
            "deletion_response_contains_id",
            expected="id or group_id in response",
            actual=str(delete_data),
            passed=contains_id,
            reason="Deletion response contains group ID"
            if contains_id
            else "No group ID in deletion response",
        )
        print(f"{'✅' if contains_id else '❌'} Deletion response contains ID")

    # Generate summary
    summary = output.generate_summary_table(
        "Create group, delete it, verify 404 on retrieval and proper error message"
    )

    # Print the actual table to console
    print("\n" + "=" * 80)
    print("TEST SUMMARY TABLE")
    print("=" * 80)
    with open(summary, "r") as f:
        print(f.read())
    print("=" * 80)

    # Final assertion
    assert output.validations_failed == 0, (
        f"{output.validations_failed} validation(s) failed - see {summary}"
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_15d_add_user_to_group_and_verify(api_client):
    """
    AT1.15d - Add User to Group and Verify Membership

    Scope: Create user, create group, add user to group, retrieve membership list and verify user is present
    Validates: User-group relationship creation, membership retrieval, role assignment

    This is a REAL test with REAL validation.
    """
    output = TestOutputManager("AT1.15d_add_user_and_verify")

    print("\n" + "=" * 80)
    print("AT1.15d - Add User to Group and Verify Membership")
    print("=" * 80)

    # Step 1: Create user
    base_username, domain, base_password = _get_test_user_basics()
    unique_id = uuid.uuid4().hex[:8]
    user_data = {
        "username": f"{base_username}_at15d_{unique_id}",
        "email": f"at15d_{unique_id}@{domain}",
        "password": base_password,
        "display_name": f"AT1.15d User {unique_id}",
    }

    print(f"\n[1/5] Creating user: {user_data['username']}")
    op_num = output.save_request("create_user", user_data)

    create_user_response = api_client.post("/users", json=user_data)
    output.save_response(
        op_num,
        "create_user",
        create_user_response.json() if create_user_response.status_code == 200 else {},
        create_user_response.status_code,
    )

    # Validation 1: User creation succeeded
    output.save_validation(
        "user_creation_succeeded",
        expected=200,
        actual=create_user_response.status_code,
        passed=create_user_response.status_code == 200,
        reason=f"Expected HTTP 200, got {create_user_response.status_code}",
    )

    if create_user_response.status_code != 200:
        print(f"❌ User creation failed with status {create_user_response.status_code}")
        summary = output.generate_summary_table(
            "Create user, create group, add user to group, verify membership"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "User creation failed"

    created_user = create_user_response.json()
    user_id = created_user.get("id")
    print(f"✅ User created with ID: {user_id}")

    # Step 2: Create group
    group_data = {
        "name": f"test_group_{uuid.uuid4().hex[:8]}",
        "description": "Group for membership testing",
        "enabled": True,
    }

    print(f"\n[2/5] Creating group: {group_data['name']}")
    op_num = output.save_request("create_group", group_data)

    create_group_response = api_client.post("/groups", json=group_data)
    output.save_response(
        op_num,
        "create_group",
        create_group_response.json() if create_group_response.status_code == 200 else {},
        create_group_response.status_code,
    )

    # Validation 2: Group creation succeeded
    output.save_validation(
        "group_creation_succeeded",
        expected=200,
        actual=create_group_response.status_code,
        passed=create_group_response.status_code == 200,
        reason=f"Expected HTTP 200, got {create_group_response.status_code}",
    )

    if create_group_response.status_code != 200:
        print(f"❌ Group creation failed with status {create_group_response.status_code}")
        api_client.delete(f"/users/{user_id}")
        summary = output.generate_summary_table(
            "Create user, create group, add user to group, verify membership"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "Group creation failed"

    created_group = create_group_response.json()
    group_id = created_group.get("id")
    print(f"✅ Group created with ID: {group_id}")

    # Step 3: Add user to group
    membership_data = {"user_id": user_id, "role": "member"}

    print(f"\n[3/5] Adding user {user_id} to group {group_id}")
    op_num = output.save_request("add_member", {"group_id": group_id, **membership_data})

    add_member_response = api_client.post(f"/groups/{group_id}/members", json=membership_data)
    output.save_response(
        op_num,
        "add_member",
        add_member_response.json() if add_member_response.status_code == 200 else {},
        add_member_response.status_code,
    )

    # Validation 3: Member addition succeeded
    output.save_validation(
        "member_addition_succeeded",
        expected=200,
        actual=add_member_response.status_code,
        passed=add_member_response.status_code == 200,
        reason=f"Expected HTTP 200, got {add_member_response.status_code}",
    )

    if add_member_response.status_code != 200:
        print(f"❌ Member addition failed with status {add_member_response.status_code}")
        api_client.delete(f"/groups/{group_id}")
        api_client.delete(f"/users/{user_id}")
        summary = output.generate_summary_table(
            "Create user, create group, add user to group, verify membership"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "Member addition failed"

    print("✅ User added to group")

    # Step 4: Get group members
    print(f"\n[4/5] Retrieving group members for group {group_id}")
    op_num = output.save_request("get_members", {"group_id": group_id})

    get_members_response = api_client.get(f"/groups/{group_id}/members")
    output.save_response(
        op_num,
        "get_members",
        get_members_response.json() if get_members_response.status_code == 200 else {},
        get_members_response.status_code,
    )

    # Validation 4: Member list retrieval succeeded
    output.save_validation(
        "member_list_retrieval_succeeded",
        expected=200,
        actual=get_members_response.status_code,
        passed=get_members_response.status_code == 200,
        reason=f"Expected HTTP 200, got {get_members_response.status_code}",
    )

    if get_members_response.status_code != 200:
        print(f"❌ Member list retrieval failed with status {get_members_response.status_code}")
        api_client.delete(f"/groups/{group_id}")
        api_client.delete(f"/users/{user_id}")
        summary = output.generate_summary_table(
            "Create user, create group, add user to group, verify membership"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "Member list retrieval failed"

    members_data = get_members_response.json()
    print("✅ Member list retrieved")

    # Step 5: Validate membership
    print("\n[5/5] Validating membership details")

    # Validation 5: Member count is correct (should be 1)
    member_count = members_data.get("total", 0)
    count_is_one = member_count == 1
    output.save_validation(
        "member_count_is_one",
        expected=1,
        actual=member_count,
        passed=count_is_one,
        reason=f"Expected 1 member, got {member_count}",
    )
    print(f"{'✅' if count_is_one else '❌'} Member count: {member_count}")

    # Validation 6: User is in member list
    members_list = members_data.get("members", [])
    user_in_list = any(m.get("id") == user_id for m in members_list)
    output.save_validation(
        "user_in_member_list",
        expected=f"User ID {user_id} in list",
        actual=str([m.get("id") for m in members_list]),
        passed=user_in_list,
        reason=f"User {user_id} found in member list"
        if user_in_list
        else f"User {user_id} NOT in member list",
    )
    print(f"{'✅' if user_in_list else '❌'} User in member list")

    # Validation 7: User has correct role
    if user_in_list:
        user_member = next((m for m in members_list if m.get("id") == user_id), None)
        user_role = user_member.get("role") if user_member else None
        role_is_member = user_role == "member"
        output.save_validation(
            "user_has_correct_role",
            expected="member",
            actual=user_role,
            passed=role_is_member,
            reason=f"User has role '{user_role}'",
        )
        print(f"{'✅' if role_is_member else '❌'} User role: {user_role}")
    else:
        output.save_validation(
            "user_has_correct_role",
            expected="member",
            actual="User not in list",
            passed=False,
            reason="Cannot check role - user not in member list",
        )
        print("❌ Cannot check role - user not in list")

    # Validation 8: User details match in member list
    if user_in_list:
        user_member = next((m for m in members_list if m.get("id") == user_id), None)
        username_matches = user_member.get("username") == user_data["username"]
        output.save_validation(
            "username_matches_in_list",
            expected=user_data["username"],
            actual=user_member.get("username"),
            passed=username_matches,
            reason="Username matches" if username_matches else "Username does not match",
        )
        print(
            f"{'✅' if username_matches else '❌'} Username matches: {user_member.get('username')}"
        )

    # Cleanup
    api_client.delete(f"/groups/{group_id}")
    api_client.delete(f"/users/{user_id}")

    # Generate summary
    summary = output.generate_summary_table(
        "Create user, create group, add user to group, verify user appears in member list with correct role"
    )

    # Print the actual table to console
    print("\n" + "=" * 80)
    print("TEST SUMMARY TABLE")
    print("=" * 80)
    with open(summary, "r") as f:
        print(f.read())
    print("=" * 80)

    # Final assertion
    assert output.validations_failed == 0, (
        f"{output.validations_failed} validation(s) failed - see {summary}"
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_15e_remove_user_from_group_and_verify(api_client):
    """
    AT1.15e - Remove User from Group and Verify Removal

    Scope: Create group with user, remove user, verify user no longer in member list
    Validates: Membership removal, list accuracy after removal, member count decreases

    This is a REAL test with REAL validation.
    """
    output = TestOutputManager("AT1.15e_remove_user_and_verify")

    print("\n" + "=" * 80)
    print("AT1.15e - Remove User from Group and Verify Removal")
    print("=" * 80)

    # Step 1: Create user
    base_username, domain, base_password = _get_test_user_basics()
    unique_id = uuid.uuid4().hex[:8]
    user_data = {
        "username": f"{base_username}_at15e_{unique_id}",
        "email": f"at15e_{unique_id}@{domain}",
        "password": base_password,
        "display_name": f"AT1.15e User {unique_id}",
    }

    print(f"\n[1/7] Creating user: {user_data['username']}")
    op_num = output.save_request("create_user", user_data)

    create_user_response = api_client.post("/users", json=user_data)
    output.save_response(
        op_num,
        "create_user",
        create_user_response.json() if create_user_response.status_code == 200 else {},
        create_user_response.status_code,
    )

    # Validation 1: User creation succeeded
    output.save_validation(
        "user_creation_succeeded",
        expected=200,
        actual=create_user_response.status_code,
        passed=create_user_response.status_code == 200,
        reason=f"Expected HTTP 200, got {create_user_response.status_code}",
    )

    if create_user_response.status_code != 200:
        print("❌ User creation failed")
        summary = output.generate_summary_table(
            "Create group with user, remove user, verify no longer in member list"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "User creation failed"

    created_user = create_user_response.json()
    user_id = created_user.get("id")
    print(f"✅ User created with ID: {user_id}")

    # Step 2: Create group
    group_data = {
        "name": f"test_group_{uuid.uuid4().hex[:8]}",
        "description": "Group for removal testing",
        "enabled": True,
    }

    print(f"\n[2/7] Creating group: {group_data['name']}")
    op_num = output.save_request("create_group", group_data)

    create_group_response = api_client.post("/groups", json=group_data)
    output.save_response(
        op_num,
        "create_group",
        create_group_response.json() if create_group_response.status_code == 200 else {},
        create_group_response.status_code,
    )

    # Validation 2: Group creation succeeded
    output.save_validation(
        "group_creation_succeeded",
        expected=200,
        actual=create_group_response.status_code,
        passed=create_group_response.status_code == 200,
        reason=f"Expected HTTP 200, got {create_group_response.status_code}",
    )

    if create_group_response.status_code != 200:
        print("❌ Group creation failed")
        api_client.delete(f"/users/{user_id}")
        summary = output.generate_summary_table(
            "Create group with user, remove user, verify no longer in member list"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "Group creation failed"

    created_group = create_group_response.json()
    group_id = created_group.get("id")
    print(f"✅ Group created with ID: {group_id}")

    # Step 3: Add user to group
    membership_data = {"user_id": user_id, "role": "member"}

    print(f"\n[3/7] Adding user {user_id} to group {group_id}")
    op_num = output.save_request("add_member", {"group_id": group_id, **membership_data})

    add_member_response = api_client.post(f"/groups/{group_id}/members", json=membership_data)
    output.save_response(
        op_num,
        "add_member",
        add_member_response.json() if add_member_response.status_code == 200 else {},
        add_member_response.status_code,
    )

    # Validation 3: Member addition succeeded
    output.save_validation(
        "member_addition_succeeded",
        expected=200,
        actual=add_member_response.status_code,
        passed=add_member_response.status_code == 200,
        reason=f"Expected HTTP 200, got {add_member_response.status_code}",
    )

    if add_member_response.status_code != 200:
        print("❌ Member addition failed")
        api_client.delete(f"/groups/{group_id}")
        api_client.delete(f"/users/{user_id}")
        summary = output.generate_summary_table(
            "Create group with user, remove user, verify no longer in member list"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "Member addition failed"

    print("✅ User added to group")

    # Step 4: Verify user is in member list before removal
    print(f"\n[4/7] Verifying user {user_id} is in member list before removal")
    op_num = output.save_request("get_members_before_removal", {"group_id": group_id})

    get_members_before = api_client.get(f"/groups/{group_id}/members")
    output.save_response(
        op_num,
        "get_members_before_removal",
        get_members_before.json() if get_members_before.status_code == 200 else {},
        get_members_before.status_code,
    )

    members_before = get_members_before.json()
    count_before = members_before.get("total", 0)

    # Validation 4: User is in list before removal
    user_in_list_before = any(m.get("id") == user_id for m in members_before.get("members", []))
    output.save_validation(
        "user_in_list_before_removal",
        expected=f"User {user_id} in list",
        actual=f"Found: {user_in_list_before}, Count: {count_before}",
        passed=user_in_list_before,
        reason=f"User {user_id} is in member list before removal",
    )
    print(f"✅ User in list before removal (count: {count_before})")

    # Step 5: Remove user from group
    print(f"\n[5/7] Removing user {user_id} from group {group_id}")
    op_num = output.save_request("remove_member", {"group_id": group_id, "user_id": user_id})

    # Check if API has a DELETE endpoint for removing members
    remove_response = api_client.delete(f"/groups/{group_id}/members/{user_id}")
    output.save_response(
        op_num,
        "remove_member",
        remove_response.json() if remove_response.status_code in [200, 204] else {},
        remove_response.status_code,
    )

    # Validation 5: Member removal succeeded
    removal_succeeded = remove_response.status_code in [200, 204]
    output.save_validation(
        "member_removal_succeeded",
        expected="200 or 204",
        actual=remove_response.status_code,
        passed=removal_succeeded,
        reason=f"Expected HTTP 200 or 204, got {remove_response.status_code}",
    )

    if not removal_succeeded:
        print(f"❌ Member removal failed with status {remove_response.status_code}")
        api_client.delete(f"/groups/{group_id}")
        api_client.delete(f"/users/{user_id}")
        summary = output.generate_summary_table(
            "Create group with user, remove user, verify no longer in member list"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "Member removal failed"

    print("✅ User removed from group")

    # Step 6: Verify user is NO LONGER in member list
    print(f"\n[6/7] Verifying user {user_id} is NO LONGER in member list")
    op_num = output.save_request("get_members_after_removal", {"group_id": group_id})

    get_members_after = api_client.get(f"/groups/{group_id}/members")
    output.save_response(
        op_num,
        "get_members_after_removal",
        get_members_after.json() if get_members_after.status_code == 200 else {},
        get_members_after.status_code,
    )

    members_after = get_members_after.json()
    count_after = members_after.get("total", 0)

    # Validation 6: User is NOT in list after removal
    user_in_list_after = any(m.get("id") == user_id for m in members_after.get("members", []))
    output.save_validation(
        "user_not_in_list_after_removal",
        expected=f"User {user_id} NOT in list",
        actual=f"Found: {user_in_list_after}, Count: {count_after}",
        passed=not user_in_list_after,
        reason=f"User {user_id} is NOT in member list after removal"
        if not user_in_list_after
        else f"User {user_id} still in list!",
    )
    print(
        f"{'✅' if not user_in_list_after else '❌'} User NOT in list after removal (count: {count_after})"
    )

    # Step 7: Validate member count decreased
    print("\n[7/7] Validating member count decreased")

    # Validation 7: Member count decreased by 1
    count_decreased = count_after == (count_before - 1)
    output.save_validation(
        "member_count_decreased",
        expected=count_before - 1,
        actual=count_after,
        passed=count_decreased,
        reason=f"Count decreased from {count_before} to {count_after}",
    )
    print(f"{'✅' if count_decreased else '❌'} Member count: {count_before} → {count_after}")

    # Validation 8: Member count is now 0
    count_is_zero = count_after == 0
    output.save_validation(
        "member_count_is_zero",
        expected=0,
        actual=count_after,
        passed=count_is_zero,
        reason="Member count is 0 after removing only member",
    )
    print(f"{'✅' if count_is_zero else '❌'} Final member count: {count_after}")

    # Cleanup
    api_client.delete(f"/groups/{group_id}")
    api_client.delete(f"/users/{user_id}")

    # Generate summary
    summary = output.generate_summary_table(
        "Create group with user, remove user, verify user no longer in member list and count decreased to 0"
    )

    # Print the actual table to console
    print("\n" + "=" * 80)
    print("TEST SUMMARY TABLE")
    print("=" * 80)
    with open(summary, "r") as f:
        print(f.read())
    print("=" * 80)

    # Final assertion
    assert output.validations_failed == 0, (
        f"{output.validations_failed} validation(s) failed - see {summary}"
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_15f_duplicate_group_name_rejection(api_client):
    """
    AT1.15f - Test Duplicate Group Name Rejection

    Scope: Create group, attempt to create another with same name, verify rejection
    Validates: Uniqueness constraints, proper error handling, error message quality

    This is a REAL test with REAL validation.
    """
    output = TestOutputManager("AT1.15f_duplicate_name_rejection")

    print("\n" + "=" * 80)
    print("AT1.15f - Test Duplicate Group Name Rejection")
    print("=" * 80)

    # Step 1: Create first group with unique name
    unique_name = f"test_group_unique_{uuid.uuid4().hex[:8]}"
    group_data = {"name": unique_name, "description": "First group with this name", "enabled": True}

    print(f"\n[1/4] Creating first group: {unique_name}")
    op_num = output.save_request("create_first_group", group_data)

    create_first_response = api_client.post("/groups", json=group_data)
    output.save_response(
        op_num,
        "create_first_group",
        create_first_response.json() if create_first_response.status_code == 200 else {},
        create_first_response.status_code,
    )

    # Validation 1: First group creation succeeded
    output.save_validation(
        "first_group_creation_succeeded",
        expected=200,
        actual=create_first_response.status_code,
        passed=create_first_response.status_code == 200,
        reason=f"Expected HTTP 200, got {create_first_response.status_code}",
    )

    if create_first_response.status_code != 200:
        print("❌ First group creation failed")
        summary = output.generate_summary_table(
            "Create group, attempt duplicate name, verify rejection with proper error"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "First group creation failed"

    first_group = create_first_response.json()
    first_group_id = first_group.get("id")
    print(f"✅ First group created with ID: {first_group_id}")

    # Step 2: Attempt to create second group with SAME name
    duplicate_data = {
        "name": unique_name,  # SAME NAME
        "description": "Duplicate attempt with same name",
        "enabled": True,
    }

    print(f"\n[2/4] Attempting to create duplicate group with same name: {unique_name}")
    op_num = output.save_request("create_duplicate_group", duplicate_data)

    create_duplicate_response = api_client.post("/groups", json=duplicate_data)

    # Save response regardless of status code
    response_data = {}
    if create_duplicate_response.status_code in [200, 201]:
        response_data = create_duplicate_response.json()
    else:
        try:
            response_data = create_duplicate_response.json()
        except Exception:
            response_data = {"error": "Non-JSON response", "text": create_duplicate_response.text}

    output.save_response(
        op_num, "create_duplicate_group", response_data, create_duplicate_response.status_code
    )

    # Validation 2: Duplicate creation should FAIL (not 200/201)
    duplicate_rejected = create_duplicate_response.status_code not in [200, 201]
    output.save_validation(
        "duplicate_creation_rejected",
        expected="NOT 200 or 201 (should be 400/409/422)",
        actual=create_duplicate_response.status_code,
        passed=duplicate_rejected,
        reason=f"Got HTTP {create_duplicate_response.status_code}"
        + (" - correctly rejected" if duplicate_rejected else " - INCORRECTLY ACCEPTED!"),
    )
    print(
        f"{'✅' if duplicate_rejected else '❌'} Duplicate rejected with status: {create_duplicate_response.status_code}"
    )

    # Step 3: Validate error status code is appropriate
    print("\n[3/4] Validating error status code")

    # Validation 3: Status code is a client error (4xx)
    is_client_error = 400 <= create_duplicate_response.status_code < 500
    output.save_validation(
        "status_is_client_error_4xx",
        expected="4xx (400-499)",
        actual=create_duplicate_response.status_code,
        passed=is_client_error and duplicate_rejected,
        reason=f"Status {create_duplicate_response.status_code} is {'a 4xx client error' if is_client_error else 'NOT a 4xx error'}",
    )
    print(
        f"{'✅' if is_client_error else '❌'} Status is 4xx: {create_duplicate_response.status_code}"
    )

    # Validation 4: Status code is appropriate for duplicates (400, 409, or 422)
    appropriate_codes = [400, 409, 422]
    is_appropriate_code = create_duplicate_response.status_code in appropriate_codes
    output.save_validation(
        "status_is_appropriate_for_duplicate",
        expected="400 (Bad Request), 409 (Conflict), or 422 (Unprocessable Entity)",
        actual=create_duplicate_response.status_code,
        passed=is_appropriate_code,
        reason=f"Status {create_duplicate_response.status_code} is {'' if is_appropriate_code else 'NOT '}appropriate for duplicate rejection",
    )
    print(
        f"{'✅' if is_appropriate_code else '❌'} Status is appropriate (400/409/422): {create_duplicate_response.status_code}"
    )

    # Step 4: Validate error message quality
    print("\n[4/4] Validating error message")

    # Validation 5: Response contains error details
    has_error_field = False
    error_message = ""
    if response_data:
        has_error_field = (
            "detail" in response_data or "error" in response_data or "message" in response_data
        )
        error_message = str(
            response_data.get("detail")
            or response_data.get("error")
            or response_data.get("message", "")
        )

    output.save_validation(
        "response_has_error_field",
        expected="'detail', 'error', or 'message' field present",
        actual=f"Fields: {list(response_data.keys())}",
        passed=has_error_field and duplicate_rejected,
        reason=f"Error field present: {has_error_field}",
    )
    print(f"{'✅' if has_error_field else '❌'} Error field present: {has_error_field}")

    # Validation 6: Error message mentions duplicate/exists/unique/name
    error_keywords = ["duplicate", "exists", "unique", "already", "name", "constraint"]
    mentions_duplicate = any(keyword.lower() in error_message.lower() for keyword in error_keywords)

    output.save_validation(
        "error_message_mentions_duplicate_issue",
        expected="Error message contains: duplicate/exists/unique/already/name/constraint",
        actual=f"Message: '{error_message}'",
        passed=mentions_duplicate and has_error_field,
        reason=f"Message {'contains' if mentions_duplicate else 'does NOT contain'} relevant keywords",
    )
    print(f"{'✅' if mentions_duplicate else '❌'} Error message quality: {error_message[:100]}")

    # Validation 7: Verify original group still exists
    get_original_response = api_client.get(f"/groups/{first_group_id}")
    original_still_exists = get_original_response.status_code == 200

    output.save_validation(
        "original_group_still_exists",
        expected="Original group still accessible",
        actual=f"Status: {get_original_response.status_code}",
        passed=original_still_exists,
        reason="Original group still exists after duplicate rejection"
        if original_still_exists
        else "Original group NOT found!",
    )
    print(f"{'✅' if original_still_exists else '❌'} Original group still exists")

    # Cleanup
    api_client.delete(f"/groups/{first_group_id}")

    # Generate summary
    summary = output.generate_summary_table(
        "Create group, attempt duplicate name, verify proper rejection with 4xx error and meaningful error message"
    )

    # Print the actual table to console
    print("\n" + "=" * 80)
    print("TEST SUMMARY TABLE")
    print("=" * 80)
    with open(summary, "r") as f:
        print(f.read())
    print("=" * 80)

    # Final assertion
    assert output.validations_failed == 0, (
        f"{output.validations_failed} validation(s) failed - see {summary}"
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_15g_invalid_user_addition(api_client):
    """
    AT1.15g - Test Invalid User Addition (Non-existent User)

    Scope: Create group, try to add non-existent user ID (999999), verify rejection
    Validates: Foreign key validation, proper error handling, data integrity

    This is a REAL test with REAL validation.
    """
    output = TestOutputManager("AT1.15g_invalid_user_addition")

    print("\n" + "=" * 80)
    print("AT1.15g - Test Invalid User Addition (Non-existent User)")
    print("=" * 80)

    # Step 1: Create group
    group_data = {
        "name": f"test_group_{uuid.uuid4().hex[:8]}",
        "description": "Group for invalid user test",
        "enabled": True,
    }

    print(f"\n[1/4] Creating group: {group_data['name']}")
    op_num = output.save_request("create_group", group_data)

    create_group_response = api_client.post("/groups", json=group_data)
    output.save_response(
        op_num,
        "create_group",
        create_group_response.json() if create_group_response.status_code == 200 else {},
        create_group_response.status_code,
    )

    # Validation 1: Group creation succeeded
    output.save_validation(
        "group_creation_succeeded",
        expected=200,
        actual=create_group_response.status_code,
        passed=create_group_response.status_code == 200,
        reason=f"Expected HTTP 200, got {create_group_response.status_code}",
    )

    if create_group_response.status_code != 200:
        print("❌ Group creation failed")
        summary = output.generate_summary_table(
            "Create group, attempt to add non-existent user, verify rejection"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "Group creation failed"

    created_group = create_group_response.json()
    group_id = created_group.get("id")
    print(f"✅ Group created with ID: {group_id}")

    # Step 2: Attempt to add non-existent user (ID 999999)
    invalid_user_id = 999999
    invalid_member_data = {"user_id": invalid_user_id, "role": "member"}

    print(f"\n[2/4] Attempting to add non-existent user ID: {invalid_user_id}")
    op_num = output.save_request("add_invalid_user", {"group_id": group_id, **invalid_member_data})

    add_invalid_response = api_client.post(f"/groups/{group_id}/members", json=invalid_member_data)

    # Save response regardless of status code
    response_data = {}
    if add_invalid_response.status_code in [200, 201]:
        response_data = add_invalid_response.json()
    else:
        try:
            response_data = add_invalid_response.json()
        except Exception:
            response_data = {"error": "Non-JSON response", "text": add_invalid_response.text}

    output.save_response(
        op_num, "add_invalid_user", response_data, add_invalid_response.status_code
    )

    # Validation 2: Invalid user addition should FAIL
    invalid_user_rejected = add_invalid_response.status_code not in [200, 201]
    output.save_validation(
        "invalid_user_addition_rejected",
        expected="NOT 200 or 201 (should be 400/404)",
        actual=add_invalid_response.status_code,
        passed=invalid_user_rejected,
        reason=f"Got HTTP {add_invalid_response.status_code}"
        + (" - correctly rejected" if invalid_user_rejected else " - INCORRECTLY ACCEPTED!"),
    )
    print(
        f"{'✅' if invalid_user_rejected else '❌'} Invalid user rejected with status: {add_invalid_response.status_code}"
    )

    # Step 3: Validate error status code
    print("\n[3/4] Validating error response")

    # Validation 3: Status code is a client error (4xx)
    is_client_error = 400 <= add_invalid_response.status_code < 500
    output.save_validation(
        "status_is_client_error_4xx",
        expected="4xx (400-499)",
        actual=add_invalid_response.status_code,
        passed=is_client_error and invalid_user_rejected,
        reason=f"Status {add_invalid_response.status_code} is {'a 4xx client error' if is_client_error else 'NOT a 4xx error'}",
    )
    print(f"{'✅' if is_client_error else '❌'} Status is 4xx: {add_invalid_response.status_code}")

    # Validation 4: Status code is appropriate (400 or 404)
    appropriate_codes = [400, 404]
    is_appropriate_code = add_invalid_response.status_code in appropriate_codes
    output.save_validation(
        "status_is_appropriate_for_invalid_user",
        expected="400 (Bad Request) or 404 (Not Found)",
        actual=add_invalid_response.status_code,
        passed=is_appropriate_code,
        reason=f"Status {add_invalid_response.status_code} is {'' if is_appropriate_code else 'NOT '}appropriate for invalid user",
    )
    print(
        f"{'✅' if is_appropriate_code else '❌'} Status is appropriate (400/404): {add_invalid_response.status_code}"
    )

    # Validation 5: Response contains error details
    has_error_field = False
    error_message = ""
    if response_data:
        has_error_field = (
            "detail" in response_data or "error" in response_data or "message" in response_data
        )
        error_message = str(
            response_data.get("detail")
            or response_data.get("error")
            or response_data.get("message", "")
        )

    output.save_validation(
        "response_has_error_field",
        expected="'detail', 'error', or 'message' field present",
        actual=f"Fields: {list(response_data.keys())}",
        passed=has_error_field and invalid_user_rejected,
        reason=f"Error field present: {has_error_field}",
    )
    print(f"{'✅' if has_error_field else '❌'} Error field present: {has_error_field}")

    # Validation 6: Error message mentions user/not found/invalid
    error_keywords = ["user", "not found", "invalid", "does not exist", "unknown", "id"]
    mentions_user_issue = any(
        keyword.lower() in error_message.lower() for keyword in error_keywords
    )

    output.save_validation(
        "error_message_mentions_user_issue",
        expected="Error message contains: user/not found/invalid/does not exist",
        actual=f"Message: '{error_message}'",
        passed=mentions_user_issue and has_error_field,
        reason=f"Message {'contains' if mentions_user_issue else 'does NOT contain'} relevant keywords",
    )
    print(f"{'✅' if mentions_user_issue else '❌'} Error message quality: {error_message[:100]}")

    # Step 4: Verify group member list is still empty (no invalid user added)
    print("\n[4/4] Verifying group member list is still empty")
    op_num = output.save_request("get_members_after_invalid_attempt", {"group_id": group_id})

    get_members_response = api_client.get(f"/groups/{group_id}/members")
    output.save_response(
        op_num,
        "get_members_after_invalid_attempt",
        get_members_response.json() if get_members_response.status_code == 200 else {},
        get_members_response.status_code,
    )

    if get_members_response.status_code == 200:
        members_data = get_members_response.json()
        member_count = members_data.get("total", 0)
        members_list = members_data.get("members", [])

        # Validation 7: Member count is 0 (no invalid user added)
        count_is_zero = member_count == 0
        output.save_validation(
            "member_count_is_zero",
            expected=0,
            actual=member_count,
            passed=count_is_zero,
            reason=f"Member count is {member_count} (should be 0)",
        )
        print(f"{'✅' if count_is_zero else '❌'} Member count is 0: {member_count}")

        # Validation 8: Invalid user ID not in member list
        invalid_user_not_in_list = not any(m.get("id") == invalid_user_id for m in members_list)
        output.save_validation(
            "invalid_user_not_in_list",
            expected=f"User ID {invalid_user_id} NOT in list",
            actual=f"Member IDs: {[m.get('id') for m in members_list]}",
            passed=invalid_user_not_in_list,
            reason="Invalid user not in member list"
            if invalid_user_not_in_list
            else "Invalid user FOUND in list!",
        )
        print(f"{'✅' if invalid_user_not_in_list else '❌'} Invalid user not in list")
    else:
        # If we can't get members, still validate but note the issue
        output.save_validation(
            "member_count_is_zero",
            expected=0,
            actual=f"Could not retrieve (status {get_members_response.status_code})",
            passed=False,
            reason="Could not retrieve member list to verify",
        )
        output.save_validation(
            "invalid_user_not_in_list",
            expected=f"User ID {invalid_user_id} NOT in list",
            actual=f"Could not retrieve (status {get_members_response.status_code})",
            passed=False,
            reason="Could not retrieve member list to verify",
        )
        print("❌ Could not retrieve member list")

    # Cleanup
    api_client.delete(f"/groups/{group_id}")

    # Generate summary
    summary = output.generate_summary_table(
        "Create group, attempt to add non-existent user, verify rejection with proper error and data integrity maintained"
    )

    # Print the actual table to console
    print("\n" + "=" * 80)
    print("TEST SUMMARY TABLE")
    print("=" * 80)
    with open(summary, "r") as f:
        print(f.read())
    print("=" * 80)

    # Final assertion
    assert output.validations_failed == 0, (
        f"{output.validations_failed} validation(s) failed - see {summary}"
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_15h_bulk_user_addition(api_client):
    """
    AT1.15h - Bulk User Addition (5 Users)

    Scope: Create 5 users, add all to group, verify all 5 in member list with correct roles
    Validates: Bulk operations, list accuracy, role assignment for multiple users

    This is a REAL test with REAL validation.
    """
    output = TestOutputManager("AT1.15h_bulk_user_addition")

    print("\n" + "=" * 80)
    print("AT1.15h - Bulk User Addition (5 Users)")
    print("=" * 80)

    # Step 1: Create group
    group_data = {
        "name": f"test_group_{uuid.uuid4().hex[:8]}",
        "description": "Group for bulk user test",
        "enabled": True,
    }

    print(f"\n[1/3] Creating group: {group_data['name']}")
    op_num = output.save_request("create_group", group_data)

    create_group_response = api_client.post("/groups", json=group_data)
    output.save_response(
        op_num,
        "create_group",
        create_group_response.json() if create_group_response.status_code == 200 else {},
        create_group_response.status_code,
    )

    # Validation 1: Group creation succeeded
    output.save_validation(
        "group_creation_succeeded",
        expected=200,
        actual=create_group_response.status_code,
        passed=create_group_response.status_code == 200,
        reason=f"Expected HTTP 200, got {create_group_response.status_code}",
    )

    if create_group_response.status_code != 200:
        print("❌ Group creation failed")
        summary = output.generate_summary_table(
            "Create 5 users, add all to group, verify all in member list"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "Group creation failed"

    created_group = create_group_response.json()
    group_id = created_group.get("id")
    print(f"✅ Group created with ID: {group_id}")

    # Step 2: Create 5 users and add them to the group
    print("\n[2/3] Creating and adding 5 users to group")
    created_users = []
    user_roles = ["member", "member", "admin", "member", "admin"]  # Mix of roles
    base_username, domain, base_password = _get_test_user_basics()

    group_count = int(get_config("test.at1_15.group_bulk_count"))
    for i in range(group_count):
        unique_id = uuid.uuid4().hex[:8]
        # Create user
        user_data = {
            "username": f"{base_username}_at15_bulk_{i + 1}_{unique_id}",
            "email": f"at15_bulk_{i + 1}_{unique_id}@{domain}",
            "password": base_password,
            "display_name": f"AT1.15 Bulk User {i + 1} {unique_id}",
        }

        print(f"  [{i + 1}/5] Creating user: {user_data['username']}")
        op_num = output.save_request(f"create_user_{i + 1}", user_data)

        create_user_response = api_client.post("/users", json=user_data)
        output.save_response(
            op_num,
            f"create_user_{i + 1}",
            create_user_response.json() if create_user_response.status_code == 200 else {},
            create_user_response.status_code,
        )

        # Validation: User creation succeeded
        user_created = create_user_response.status_code == 200
        output.save_validation(
            f"user_{i + 1}_creation_succeeded",
            expected=200,
            actual=create_user_response.status_code,
            passed=user_created,
            reason=f"User {i + 1} creation {'succeeded' if user_created else 'failed'}",
        )

        if not user_created:
            print(f"  ❌ User {i + 1} creation failed")
            # Cleanup
            api_client.delete(f"/groups/{group_id}")
            for prev_user in created_users:
                api_client.delete(f"/users/{prev_user['id']}")
            summary = output.generate_summary_table(
                "Create 5 users, add all to group, verify all in member list"
            )
            print(f"\n📄 Summary: {summary}")
            assert False, f"User {i + 1} creation failed"

        user = create_user_response.json()
        user_id = user.get("id")
        created_users.append(
            {"id": user_id, "username": user_data["username"], "role": user_roles[i]}
        )
        print(f"  ✅ User {i + 1} created with ID: {user_id}")

        # Add user to group with specified role
        membership_data = {"user_id": user_id, "role": user_roles[i]}

        print(f"  [{i + 1}/5] Adding user {user_id} to group with role: {user_roles[i]}")
        op_num = output.save_request(
            f"add_member_{i + 1}", {"group_id": group_id, **membership_data}
        )

        add_member_response = api_client.post(f"/groups/{group_id}/members", json=membership_data)
        output.save_response(
            op_num,
            f"add_member_{i + 1}",
            add_member_response.json() if add_member_response.status_code == 200 else {},
            add_member_response.status_code,
        )

        # Validation: Member addition succeeded
        member_added = add_member_response.status_code == 200
        output.save_validation(
            f"user_{i + 1}_addition_succeeded",
            expected=200,
            actual=add_member_response.status_code,
            passed=member_added,
            reason=f"User {i + 1} addition {'succeeded' if member_added else 'failed'}",
        )

        if not member_added:
            print(f"  ❌ User {i + 1} addition failed")
            # Cleanup
            api_client.delete(f"/groups/{group_id}")
            for prev_user in created_users:
                api_client.delete(f"/users/{prev_user['id']}")
            summary = output.generate_summary_table(
                "Create 5 users, add all to group, verify all in member list"
            )
            print(f"\n📄 Summary: {summary}")
            assert False, f"User {i + 1} addition failed"

        print(f"  ✅ User {i + 1} added to group")

    # Step 3: Verify all 5 users are in the member list
    print("\n[3/3] Verifying all 5 users in member list")
    op_num = output.save_request("get_all_members", {"group_id": group_id})

    get_members_response = api_client.get(f"/groups/{group_id}/members")
    output.save_response(
        op_num,
        "get_all_members",
        get_members_response.json() if get_members_response.status_code == 200 else {},
        get_members_response.status_code,
    )

    # Validation: Member list retrieval succeeded
    output.save_validation(
        "member_list_retrieval_succeeded",
        expected=200,
        actual=get_members_response.status_code,
        passed=get_members_response.status_code == 200,
        reason=f"Expected HTTP 200, got {get_members_response.status_code}",
    )

    if get_members_response.status_code != 200:
        print("❌ Member list retrieval failed")
        # Cleanup
        api_client.delete(f"/groups/{group_id}")
        for user in created_users:
            api_client.delete(f"/users/{user['id']}")
        summary = output.generate_summary_table(
            "Create 5 users, add all to group, verify all in member list"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "Member list retrieval failed"

    members_data = get_members_response.json()
    member_count = members_data.get("total", 0)
    members_list = members_data.get("members", [])

    print(f"✅ Member list retrieved with {member_count} members")

    # Validation: Member count is exactly 5
    count_is_five = member_count == 5
    output.save_validation(
        "member_count_is_five",
        expected=5,
        actual=member_count,
        passed=count_is_five,
        reason=f"Expected 5 members, got {member_count}",
    )
    print(f"{'✅' if count_is_five else '❌'} Member count is 5: {member_count}")

    # Validation: All 5 user IDs are in the member list
    member_ids = [m.get("id") for m in members_list]
    expected_ids = [u["id"] for u in created_users]
    all_users_present = all(uid in member_ids for uid in expected_ids)

    output.save_validation(
        "all_five_users_present",
        expected=f"All user IDs: {expected_ids}",
        actual=f"Found IDs: {member_ids}",
        passed=all_users_present,
        reason="All 5 users present in member list"
        if all_users_present
        else f"Missing users: {set(expected_ids) - set(member_ids)}",
    )
    print(f"{'✅' if all_users_present else '❌'} All 5 users present in list")

    # Validation: Each user has the correct role
    roles_correct = True
    role_mismatches = []

    for created_user in created_users:
        member = next((m for m in members_list if m.get("id") == created_user["id"]), None)
        if member:
            expected_role = created_user["role"]
            actual_role = member.get("role")
            if expected_role != actual_role:
                roles_correct = False
                role_mismatches.append(
                    f"User {created_user['id']}: expected '{expected_role}', got '{actual_role}'"
                )
        else:
            roles_correct = False
            role_mismatches.append(f"User {created_user['id']}: not found in list")

    output.save_validation(
        "all_users_have_correct_roles",
        expected=f"Roles: {[u['role'] for u in created_users]}",
        actual=f"Roles: {[m.get('role') for m in members_list]}",
        passed=roles_correct,
        reason="All roles match" if roles_correct else f"Role mismatches: {role_mismatches}",
    )
    print(f"{'✅' if roles_correct else '❌'} All roles correct: {roles_correct}")

    # Validation: Member role distribution (2 admins, 3 members)
    admin_count = sum(1 for m in members_list if m.get("role") == "admin")
    member_count_role = sum(1 for m in members_list if m.get("role") == "member")

    role_distribution_correct = admin_count == 2 and member_count_role == 3
    output.save_validation(
        "role_distribution_correct",
        expected="2 admins, 3 members",
        actual=f"{admin_count} admins, {member_count_role} members",
        passed=role_distribution_correct,
        reason=f"Role distribution: {admin_count} admins, {member_count_role} members",
    )
    print(
        f"{'✅' if role_distribution_correct else '❌'} Role distribution: {admin_count} admins, {member_count_role} members"
    )

    # Validation: No duplicate entries in member list
    no_duplicates = len(member_ids) == len(set(member_ids))
    output.save_validation(
        "no_duplicate_members",
        expected="No duplicates",
        actual=f"Unique: {len(set(member_ids))}, Total: {len(member_ids)}",
        passed=no_duplicates,
        reason="No duplicate members" if no_duplicates else "Duplicates found!",
    )
    print(f"{'✅' if no_duplicates else '❌'} No duplicate members")

    # Cleanup
    api_client.delete(f"/groups/{group_id}")
    for user in created_users:
        api_client.delete(f"/users/{user['id']}")

    # Generate summary
    summary = output.generate_summary_table(
        "Create 5 users with mixed roles (2 admins, 3 members), add all to group, verify all present with correct roles"
    )

    # Print the actual table to console
    print("\n" + "=" * 80)
    print("TEST SUMMARY TABLE")
    print("=" * 80)
    with open(summary, "r") as f:
        print(f.read())
    print("=" * 80)

    # Final assertion
    assert output.validations_failed == 0, (
        f"{output.validations_failed} validation(s) failed - see {summary}"
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_15i_group_with_expert_access_control(api_client):
    """
    AT1.15i - Group with Access Control (Expert Assignment)

    Scope: Create group, create expert with group access control, verify expert config includes group
    Validates: Access control relationships, expert-group linking, proper configuration storage

    This is a REAL test with REAL validation.
    """
    output = TestOutputManager("AT1.15i_group_expert_access_control")

    print("\n" + "=" * 80)
    print("AT1.15i - Group with Access Control (Expert Assignment)")
    print("=" * 80)

    # Step 1: Create group
    group_data = {
        "name": f"test_group_access_{uuid.uuid4().hex[:8]}",
        "description": "Group for access control testing",
        "enabled": True,
    }

    print(f"\n[1/4] Creating group: {group_data['name']}")
    op_num = output.save_request("create_group", group_data)

    create_group_response = api_client.post("/groups", json=group_data)
    output.save_response(
        op_num,
        "create_group",
        create_group_response.json() if create_group_response.status_code == 200 else {},
        create_group_response.status_code,
    )

    # Validation 1: Group creation succeeded
    output.save_validation(
        "group_creation_succeeded",
        expected=200,
        actual=create_group_response.status_code,
        passed=create_group_response.status_code == 200,
        reason=f"Expected HTTP 200, got {create_group_response.status_code}",
    )

    if create_group_response.status_code != 200:
        print("❌ Group creation failed")
        summary = output.generate_summary_table(
            "Create group, create expert with group access control, verify group in expert config"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "Group creation failed"

    created_group = create_group_response.json()
    group_id = created_group.get("id")
    group_name = created_group.get("name")
    print(f"✅ Group created with ID: {group_id}, Name: {group_name}")

    # Step 2: Create expert with group access control
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")
    expert_data = {
        "name": f"test_expert_access_{uuid.uuid4().hex[:6]}",
        "title": f"Test Expert with Access Control {uuid.uuid4().hex[:6]}",
        "description": "Expert for testing group access control",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "enabled": True,
        "access_control": {"groups": [group_id]},
    }

    print(f"\n[2/4] Creating expert with access control for group {group_id}")
    op_num = output.save_request("create_expert_with_access_control", expert_data)

    create_expert_response = api_client.post("/experts", json=expert_data)
    output.save_response(
        op_num,
        "create_expert_with_access_control",
        create_expert_response.json() if create_expert_response.status_code == 200 else {},
        create_expert_response.status_code,
    )

    # Validation 2: Expert creation succeeded
    output.save_validation(
        "expert_creation_succeeded",
        expected=200,
        actual=create_expert_response.status_code,
        passed=create_expert_response.status_code == 200,
        reason=f"Expected HTTP 200, got {create_expert_response.status_code}",
    )

    if create_expert_response.status_code != 200:
        print(f"❌ Expert creation failed with status {create_expert_response.status_code}")
        api_client.delete(f"/groups/{group_id}")
        summary = output.generate_summary_table(
            "Create group, create expert with group access control, verify group in expert config"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "Expert creation failed"

    created_expert = create_expert_response.json()
    expert_id = created_expert.get("id")
    print(f"✅ Expert created with ID: {expert_id}")

    # Step 3: Retrieve expert and verify access control
    print(f"\n[3/4] Retrieving expert {expert_id} to verify access control")
    op_num = output.save_request("get_expert", {"expert_id": expert_id})

    get_expert_response = api_client.get(f"/experts/{expert_id}")
    output.save_response(
        op_num,
        "get_expert",
        get_expert_response.json() if get_expert_response.status_code == 200 else {},
        get_expert_response.status_code,
    )

    # Validation 3: Expert retrieval succeeded
    output.save_validation(
        "expert_retrieval_succeeded",
        expected=200,
        actual=get_expert_response.status_code,
        passed=get_expert_response.status_code == 200,
        reason=f"Expected HTTP 200, got {get_expert_response.status_code}",
    )

    if get_expert_response.status_code != 200:
        print("❌ Expert retrieval failed")
        api_client.delete(f"/experts/{expert_id}")
        api_client.delete(f"/groups/{group_id}")
        summary = output.generate_summary_table(
            "Create group, create expert with group access control, verify group in expert config"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "Expert retrieval failed"

    retrieved_expert = get_expert_response.json()
    print("✅ Expert retrieved")

    # Step 4: Validate access control configuration
    print("\n[4/4] Validating access control configuration")

    # Validation 4: Expert has access_control field
    has_access_control = "access_control" in retrieved_expert
    output.save_validation(
        "expert_has_access_control_field",
        expected="'access_control' field present",
        actual=f"Fields: {list(retrieved_expert.keys())}",
        passed=has_access_control,
        reason="access_control field present"
        if has_access_control
        else "access_control field MISSING",
    )
    print(
        f"{'✅' if has_access_control else '❌'} access_control field present: {has_access_control}"
    )

    # Validation 5: access_control has groups field
    access_control = retrieved_expert.get("access_control", {})
    has_groups_field = "groups" in access_control if isinstance(access_control, dict) else False

    output.save_validation(
        "access_control_has_groups_field",
        expected="'groups' field in access_control",
        actual=f"access_control: {access_control}",
        passed=has_groups_field,
        reason="groups field present in access_control"
        if has_groups_field
        else "groups field MISSING",
    )
    print(f"{'✅' if has_groups_field else '❌'} groups field present: {has_groups_field}")

    # Validation 6: groups list contains our group ID
    groups_list = access_control.get("groups", []) if isinstance(access_control, dict) else []
    group_id_in_list = group_id in groups_list

    output.save_validation(
        "group_id_in_access_control",
        expected=f"Group ID {group_id} in groups list",
        actual=f"Groups list: {groups_list}",
        passed=group_id_in_list,
        reason=f"Group {group_id} found in access_control"
        if group_id_in_list
        else f"Group {group_id} NOT in list",
    )
    print(f"{'✅' if group_id_in_list else '❌'} Group {group_id} in access control list")

    # Validation 7: groups list contains exactly 1 group
    group_count_correct = len(groups_list) == 1
    output.save_validation(
        "access_control_group_count",
        expected=1,
        actual=len(groups_list),
        passed=group_count_correct,
        reason=f"Access control has {len(groups_list)} group(s)",
    )
    print(
        f"{'✅' if group_count_correct else '❌'} Group count in access control: {len(groups_list)}"
    )

    # Validation 8: Expert title matches what was created
    title_matches = retrieved_expert.get("title") == expert_data["title"]
    output.save_validation(
        "expert_title_matches",
        expected=expert_data["title"],
        actual=retrieved_expert.get("title"),
        passed=title_matches,
        reason="Expert title matches" if title_matches else "Expert title does not match",
    )
    print(
        f"{'✅' if title_matches else '❌'} Expert title matches: {retrieved_expert.get('title')}"
    )

    # Validation 9: Expert is enabled
    is_enabled = retrieved_expert.get("enabled")
    output.save_validation(
        "expert_is_enabled",
        expected=True,
        actual=retrieved_expert.get("enabled"),
        passed=is_enabled,
        reason="Expert is enabled" if is_enabled else "Expert is NOT enabled",
    )
    print(f"{'✅' if is_enabled else '❌'} Expert enabled: {retrieved_expert.get('enabled')}")

    # Cleanup
    api_client.delete(f"/experts/{expert_id}")
    api_client.delete(f"/groups/{group_id}")

    # Generate summary
    summary = output.generate_summary_table(
        "Create group, create expert with group access control, verify group ID correctly stored in expert's access_control configuration"
    )

    # Print the actual table to console
    print("\n" + "=" * 80)
    print("TEST SUMMARY TABLE")
    print("=" * 80)
    with open(summary, "r") as f:
        print(f.read())
    print("=" * 80)

    # Final assertion
    assert output.validations_failed == 0, (
        f"{output.validations_failed} validation(s) failed - see {summary}"
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_AT1_15j_empty_group_lifecycle(api_client):
    """
    AT1.15j - Empty Group Lifecycle

    Scope: Create empty group, verify it has 0 members, delete it
    Validates: Empty group handling, member count accuracy, clean deletion

    This is a REAL test with REAL validation.
    """
    output = TestOutputManager("AT1.15j_empty_group_lifecycle")

    print("\n" + "=" * 80)
    print("AT1.15j - Empty Group Lifecycle")
    print("=" * 80)

    # Step 1: Create empty group
    group_data = {
        "name": f"test_empty_group_{uuid.uuid4().hex[:8]}",
        "description": "Empty group for lifecycle testing",
        "enabled": True,
    }

    print(f"\n[1/4] Creating empty group: {group_data['name']}")
    op_num = output.save_request("create_empty_group", group_data)

    create_group_response = api_client.post("/groups", json=group_data)
    output.save_response(
        op_num,
        "create_empty_group",
        create_group_response.json() if create_group_response.status_code == 200 else {},
        create_group_response.status_code,
    )

    # Validation 1: Group creation succeeded
    output.save_validation(
        "group_creation_succeeded",
        expected=200,
        actual=create_group_response.status_code,
        passed=create_group_response.status_code == 200,
        reason=f"Expected HTTP 200, got {create_group_response.status_code}",
    )

    if create_group_response.status_code != 200:
        print("❌ Group creation failed")
        summary = output.generate_summary_table(
            "Create empty group, verify 0 members, delete group"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "Group creation failed"

    created_group = create_group_response.json()
    group_id = created_group.get("id")
    group_name = created_group.get("name")
    print(f"✅ Group created with ID: {group_id}, Name: {group_name}")

    # Validation 2: Group has required fields
    required_fields = ["id", "name", "description", "enabled"]
    has_all_fields = all(field in created_group for field in required_fields)
    output.save_validation(
        "group_has_required_fields",
        expected=f"All fields present: {required_fields}",
        actual=f"Fields: {list(created_group.keys())}",
        passed=has_all_fields,
        reason="All required fields present" if has_all_fields else "Missing required fields",
    )
    print(f"{'✅' if has_all_fields else '❌'} Group has all required fields")

    # Step 2: Get group members
    print(f"\n[2/4] Retrieving members for group {group_id}")
    op_num = output.save_request("get_group_members", {"group_id": group_id})

    get_members_response = api_client.get(f"/groups/{group_id}/members")
    output.save_response(
        op_num,
        "get_group_members",
        get_members_response.json() if get_members_response.status_code == 200 else {},
        get_members_response.status_code,
    )

    # Validation 3: Member retrieval succeeded
    output.save_validation(
        "member_retrieval_succeeded",
        expected=200,
        actual=get_members_response.status_code,
        passed=get_members_response.status_code == 200,
        reason=f"Expected HTTP 200, got {get_members_response.status_code}",
    )

    if get_members_response.status_code != 200:
        print("❌ Member retrieval failed")
        api_client.delete(f"/groups/{group_id}")
        summary = output.generate_summary_table(
            "Create empty group, verify 0 members, delete group"
        )
        print(f"\n📄 Summary: {summary}")
        assert False, "Member retrieval failed"

    members_data = get_members_response.json()
    print("✅ Member data retrieved")

    # Step 3: Validate empty membership
    print("\n[3/4] Validating empty group membership")

    # Validation 4: Response has members field
    has_members_field = "members" in members_data
    output.save_validation(
        "response_has_members_field",
        expected="'members' field present",
        actual=f"Fields: {list(members_data.keys())}",
        passed=has_members_field,
        reason="members field present" if has_members_field else "members field MISSING",
    )
    print(f"{'✅' if has_members_field else '❌'} Response has members field")

    # Validation 5: Members list is empty
    members_list = members_data.get("members", None)
    is_list = isinstance(members_list, list)
    output.save_validation(
        "members_is_list",
        expected="list type",
        actual=f"{type(members_list).__name__}",
        passed=is_list,
        reason="members is a list" if is_list else f"members is {type(members_list).__name__}",
    )
    print(f"{'✅' if is_list else '❌'} Members field is a list")

    # Validation 6: Member count is 0
    member_count = len(members_list) if is_list else -1
    is_empty = member_count == 0
    output.save_validation(
        "member_count_is_zero",
        expected=0,
        actual=member_count,
        passed=is_empty,
        reason=f"Group has {member_count} members",
    )
    print(f"{'✅' if is_empty else '❌'} Member count is 0: {member_count}")

    # Validation 7: Response has count field matching members length
    response_count = members_data.get("total", -1)
    count_matches = response_count == 0
    output.save_validation(
        "count_field_matches_zero",
        expected=0,
        actual=response_count,
        passed=count_matches,
        reason=f"total field is {response_count}",
    )
    print(f"{'✅' if count_matches else '❌'} total field is 0: {response_count}")

    # Validation 8: total field matches members length
    count_consistent = response_count == member_count
    output.save_validation(
        "count_consistent_with_list",
        expected=f"total={member_count}",
        actual=f"total={response_count}, len(members)={member_count}",
        passed=count_consistent,
        reason="total matches member list length"
        if count_consistent
        else "total does NOT match list length",
    )
    print(f"{'✅' if count_consistent else '❌'} total field consistent with list length")

    # Step 4: Delete the empty group
    print(f"\n[4/4] Deleting empty group {group_id}")
    op_num = output.save_request("delete_empty_group", {"group_id": group_id})

    delete_response = api_client.delete(f"/groups/{group_id}")
    output.save_response(
        op_num,
        "delete_empty_group",
        delete_response.json() if delete_response.status_code in [200, 204] else {},
        delete_response.status_code,
    )

    # Validation 9: Group deletion succeeded
    deletion_success = delete_response.status_code in [200, 204]
    output.save_validation(
        "group_deletion_succeeded",
        expected="200 or 204",
        actual=delete_response.status_code,
        passed=deletion_success,
        reason=f"Delete returned {delete_response.status_code}",
    )
    print(
        f"{'✅' if deletion_success else '❌'} Group deletion succeeded: {delete_response.status_code}"
    )

    # Validation 10: Verify group is gone (should get 404)
    print(f"\n[Verification] Confirming group {group_id} is deleted")
    op_num = output.save_request("verify_group_deleted", {"group_id": group_id})

    verify_response = api_client.get(f"/groups/{group_id}")
    output.save_response(
        op_num,
        "verify_group_deleted",
        verify_response.json() if verify_response.status_code == 404 else {},
        verify_response.status_code,
    )

    group_not_found = verify_response.status_code == 404
    output.save_validation(
        "group_not_found_after_deletion",
        expected=404,
        actual=verify_response.status_code,
        passed=group_not_found,
        reason=f"GET after delete returned {verify_response.status_code}",
    )
    print(f"{'✅' if group_not_found else '❌'} Group correctly returns 404 after deletion")

    # Generate summary
    summary = output.generate_summary_table(
        "Create empty group, verify 0 members via API, delete group, verify deletion"
    )

    # Print the actual table to console
    print("\n" + "=" * 80)
    print("TEST SUMMARY TABLE")
    print("=" * 80)
    with open(summary, "r") as f:
        print(f.read())
    print("=" * 80)

    # Final assertion
    assert output.validations_failed == 0, (
        f"{output.validations_failed} validation(s) failed - see {summary}"
    )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

