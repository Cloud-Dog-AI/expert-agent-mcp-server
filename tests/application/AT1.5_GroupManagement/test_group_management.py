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
Application Test: AT1.5 - Group Management (create, update, delete, membership)

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for group management workflows via API

Related Requirements: FR1.5, FR1.27
Related Tasks: T005, T006, T114
Related Architecture: CC5.1.1, CC5.1.2
Related Tests: AT1.5

Recent Changes:
- Refactored to use API endpoints only (no direct GroupManager calls)
- Added group cleanup fixtures (remove at start/end)
- Removed all hard-coded values (all from config system)
- Added deletion and update tests
- All outputs validated via API responses
"""

import sys
from pathlib import Path

# Add parent directory to path for shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import build_test_email, create_api_client_fixture, validate_config_loaded


import pytest
import uuid

# Note: GroupManager and UserManager removed - all operations via API
from src.config.loader import get_config


@pytest.fixture(scope="module")
def api_client():
    """Create API client that connects to real running API server."""
    validate_config_loaded()
    return create_api_client_fixture(check_health=True)()


@pytest.fixture
def unique_test_user_credentials(test_config):
    """Generate unique test user credentials from configuration system."""
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    base_password = get_config("test.user.password")

    if not base_username or not base_email or not base_password:
        pytest.fail("Test user credentials not configured. Set test.user.* via --env file.")

    unique_id = str(uuid.uuid4())[:8]
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    return {
        "username": f"{base_username}_at1_5_{unique_id}",
        "email": build_test_email("at1_5", unique_id, base_email),
        "password": base_password,
    }


@pytest.fixture
def test_users(api_client, test_env_file, test_secrets_file):
    """Create test users via API.

    Dependencies:
    - test_env_file: Session-scoped fixture that loads env-test
    - test_secrets_file: Session-scoped fixture that loads env-test-secrets
    """
    # Ensure config cache is cleared after env files are loaded
    from src.config.loader import load_config

    load_config.cache_clear()

    # Try get_config first (from loaded env files)
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    base_password = get_config("test.user.password")

    # Final validation - fail if still missing
    if not base_username or not base_email or not base_password:
        pytest.fail(
            "Test user credentials not configured. "
            "Set test.user.username/test.user.email/test.user.password in your --env file."
        )

    users = []

    for i in range(3):
        unique_id = str(uuid.uuid4())[:8]
        create_response = api_client.post(
            "/users",
            json={
                "username": f"{base_username}_at1_5_user{i + 1}_{unique_id}",
                "email": build_test_email(f"user{i + 1}", unique_id, base_email),
                "password": base_password,
            },
        )
        assert create_response.status_code == 200, (
            f"Failed to create test user {i + 1}: {create_response.text}"
        )
        users.append(create_response.json())

    yield users

    # Cleanup users via API
    for user_data in users:
        try:
            api_client.delete(f"/users/{user_data['id']}")
        except Exception:
            pass


@pytest.fixture
def unique_group_name():
    """Generate unique group name for each test."""
    return f"group_at1_5_{str(uuid.uuid4())[:8]}"


@pytest.fixture(autouse=True)
def cleanup_test_group(api_client, unique_group_name):
    """Cleanup: Remove test group at start (if exists) and end of test."""
    group_name = unique_group_name

    # Cleanup: Remove group at start if exists (via API)
    # List groups and find by name
    try:
        groups_response = api_client.get("/groups")
        if groups_response.status_code == 200:
            groups_data = groups_response.json()
            for group in groups_data.get("groups", []):
                if group.get("name") == group_name:
                    api_client.delete(f"/groups/{group['id']}")
    except Exception:
        pass

    yield

    # Cleanup after test: Remove group if created (via API)
    try:
        groups_response = api_client.get("/groups")
        if groups_response.status_code == 200:
            groups_data = groups_response.json()
            for group in groups_data.get("groups", []):
                if group.get("name") == group_name:
                    api_client.delete(f"/groups/{group['id']}")
    except Exception:
        pass
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_group_creation_workflow(api_client, unique_group_name):
    """Test complete group creation workflow via API with comprehensive output validation."""
    group_name = unique_group_name
    group_description = "Test group description"

    # Show settings being used
    print("\n[TEST START] test_group_creation_workflow")
    print(f"[SETTINGS] Group name: {group_name}")
    print(f"[SETTINGS] Group description: {group_description}")

    # Create group via API
    response = api_client.post(
        "/groups", json={"name": group_name, "description": group_description, "enabled": True}
    )

    assert response.status_code == 200, f"Creation failed: {response.text}"
    data = response.json()

    # Validate all outputs - Format, Content, Structure
    # Format validation
    assert isinstance(data, dict), "Response should be a dictionary"
    assert "id" in data, "Response must contain 'id' field"
    assert "name" in data, "Response must contain 'name' field"
    assert "description" in data, "Response must contain 'description' field"
    assert "enabled" in data, "Response must contain 'enabled' field"
    assert "created_at" in data, "Response must contain 'created_at' field"

    # Content validation
    assert isinstance(data["id"], int), "id must be an integer"
    assert data["id"] > 0, "id must be positive"
    assert isinstance(data["name"], str), "name must be a string"
    assert data["name"] == group_name, (
        f"name must match request: expected '{group_name}', got '{data['name']}'"
    )
    assert isinstance(data["description"], str), "description must be a string"
    assert data["description"] == group_description, (
        f"description must match request: expected '{group_description}', got '{data['description']}'"
    )
    assert isinstance(data["enabled"], bool), "enabled must be a boolean"
    assert data["enabled"] is True, f"enabled must be True, got {data['enabled']}"
    assert isinstance(data["created_at"], str), "created_at must be a string (ISO format)"

    # Structure validation - ISO datetime format
    from datetime import datetime

    try:
        datetime.fromisoformat(data["created_at"].replace("Z", "+00:00"))
    except ValueError:
        pytest.fail(f"created_at must be valid ISO format datetime, got: {data['created_at']}")

    # Verify group exists via API (cross-validation)
    get_response = api_client.get(f"/groups/{data['id']}")
    assert get_response.status_code == 200, f"Failed to retrieve created group: {get_response.text}"
    group_data = get_response.json()

    # Cross-validate all fields match
    assert group_data["id"] == data["id"], "Retrieved group ID must match created group ID"
    assert group_data["name"] == group_name, "Retrieved group name must match"
    assert group_data["description"] == group_description, "Retrieved group description must match"
    assert group_data["enabled"] is True, "Retrieved group enabled must match"
    assert group_data["created_at"] == data["created_at"], "Retrieved created_at must match"

    print("[TEST END] test_group_creation_workflow")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_group_update_workflow(api_client, unique_group_name):
    """Test group update workflow via API with comprehensive output validation."""
    group_name = unique_group_name
    original_description = "Original description"
    updated_description = "Updated description"

    print("\n[TEST START] test_group_update_workflow")
    print(f"[SETTINGS] Group name: {group_name}")

    # Create group via API
    create_response = api_client.post(
        "/groups", json={"name": group_name, "description": original_description, "enabled": True}
    )
    assert create_response.status_code == 200, f"Failed to create group: {create_response.text}"
    group_id = create_response.json()["id"]
    original_created_at = create_response.json()["created_at"]

    # Update group via PUT endpoint
    update_response = api_client.put(
        f"/groups/{group_id}", json={"description": updated_description, "enabled": False}
    )

    assert update_response.status_code == 200, f"Update failed: {update_response.text}"
    data = update_response.json()

    # Validate outputs - Format, Content, Structure
    # Format validation
    assert isinstance(data, dict), "Response should be a dictionary"
    assert "id" in data, "Response must contain 'id' field"
    assert "name" in data, "Response must contain 'name' field"
    assert "description" in data, "Response must contain 'description' field"
    assert "enabled" in data, "Response must contain 'enabled' field"
    assert "updated_at" in data, "Response must contain 'updated_at' field"

    # Content validation
    assert data["id"] == group_id, f"id must match group_id: expected {group_id}, got {data['id']}"
    assert data["name"] == group_name, (
        f"name must remain unchanged: expected '{group_name}', got '{data['name']}'"
    )
    assert data["description"] == updated_description, (
        f"description must be updated: expected '{updated_description}', got '{data['description']}'"
    )
    assert data["enabled"] is False, f"enabled must be False, got {data['enabled']}"

    # Structure validation - updated_at must be present and valid ISO format
    assert isinstance(data["updated_at"], str), "updated_at must be a string (ISO format)"
    from datetime import datetime

    try:
        updated_time = datetime.fromisoformat(data["updated_at"].replace("Z", "+00:00"))
        created_time = datetime.fromisoformat(original_created_at.replace("Z", "+00:00"))
        assert updated_time >= created_time, "updated_at must be >= created_at"
    except ValueError:
        pytest.fail(f"updated_at must be valid ISO format datetime, got: {data['updated_at']}")

    # Verify via GET (cross-validation)
    get_response = api_client.get(f"/groups/{group_id}")
    assert get_response.status_code == 200, f"Failed to retrieve updated group: {get_response.text}"
    group_data = get_response.json()

    # Cross-validate all fields
    assert group_data["id"] == group_id, "Retrieved group ID must match"
    assert group_data["name"] == group_name, "Retrieved group name must match"
    assert group_data["description"] == updated_description, (
        "Retrieved description must match updated value"
    )
    assert group_data["enabled"] is False, "Retrieved enabled must match updated value"
    assert group_data["updated_at"] == data["updated_at"], "Retrieved updated_at must match"
    assert group_data["created_at"] == original_created_at, "created_at must remain unchanged"

    print("[TEST END] test_group_update_workflow")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_group_retrieval_workflow(api_client, unique_group_name):
    """Test group retrieval workflow via API with comprehensive output validation."""
    group_name = unique_group_name
    group_description = "Test group"

    print("\n[TEST START] test_group_retrieval_workflow")
    print(f"[SETTINGS] Group name: {group_name}")

    # Create group via API
    create_response = api_client.post(
        "/groups", json={"name": group_name, "description": group_description, "enabled": True}
    )
    assert create_response.status_code == 200, f"Failed to create group: {create_response.text}"
    group_id = create_response.json()["id"]

    # Retrieve by ID via API
    get_response = api_client.get(f"/groups/{group_id}")
    assert get_response.status_code == 200, f"Failed to retrieve group: {get_response.text}"
    group_data = get_response.json()

    # Validate all outputs - Format, Content, Structure
    # Format validation
    assert isinstance(group_data, dict), "Response should be a dictionary"
    assert "id" in group_data, "Response must contain 'id' field"
    assert "name" in group_data, "Response must contain 'name' field"
    assert "description" in group_data, "Response must contain 'description' field"
    assert "enabled" in group_data, "Response must contain 'enabled' field"
    assert "created_at" in group_data, "Response must contain 'created_at' field"

    # Content validation
    assert group_data["id"] == group_id, (
        f"id must match: expected {group_id}, got {group_data['id']}"
    )
    assert group_data["name"] == group_name, (
        f"name must match: expected '{group_name}', got '{group_data['name']}'"
    )
    assert group_data["description"] == group_description, (
        f"description must match: expected '{group_description}', got '{group_data['description']}'"
    )
    assert group_data["enabled"] is True, f"enabled must be True, got {group_data['enabled']}"

    # Structure validation
    assert isinstance(group_data["id"], int), "id must be an integer"
    assert isinstance(group_data["name"], str), "name must be a string"
    assert isinstance(group_data["description"], str), "description must be a string"
    assert isinstance(group_data["enabled"], bool), "enabled must be a boolean"
    assert isinstance(group_data["created_at"], str), "created_at must be a string (ISO format)"

    # Validate ISO datetime format
    from datetime import datetime

    try:
        datetime.fromisoformat(group_data["created_at"].replace("Z", "+00:00"))
    except ValueError:
        pytest.fail(
            f"created_at must be valid ISO format datetime, got: {group_data['created_at']}"
        )

    # Optional fields validation
    if "updated_at" in group_data:
        assert isinstance(group_data["updated_at"], str), "updated_at must be a string if present"

    print("[TEST END] test_group_retrieval_workflow")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_group_deletion_workflow(api_client, unique_group_name):
    """Test group deletion workflow via API with comprehensive output validation."""
    group_name = unique_group_name

    print("\n[TEST START] test_group_deletion_workflow")
    print(f"[SETTINGS] Group name: {group_name}")

    # Create group via API
    create_response = api_client.post(
        "/groups", json={"name": group_name, "description": "Test group to delete", "enabled": True}
    )
    assert create_response.status_code == 200, f"Failed to create group: {create_response.text}"
    group_id = create_response.json()["id"]

    # Verify group exists
    get_response = api_client.get(f"/groups/{group_id}")
    assert get_response.status_code == 200, (
        f"Group should exist before deletion: {get_response.text}"
    )

    # Delete group via DELETE endpoint
    delete_response = api_client.delete(f"/groups/{group_id}")

    if delete_response.status_code in [200, 204]:
        # DELETE endpoint exists - validate response format
        if delete_response.status_code == 200:
            delete_data = delete_response.json()
            assert isinstance(delete_data, dict), "Delete response should be a dictionary"
            assert "message" in delete_data or "id" in delete_data, (
                "Delete response should contain 'message' or 'id'"
            )
            if "id" in delete_data:
                assert delete_data["id"] == group_id, (
                    f"Response id must match group_id: expected {group_id}, got {delete_data.get('id')}"
                )

        # Verify deletion via GET
        get_response2 = api_client.get(f"/groups/{group_id}")
        assert get_response2.status_code == 404, (
            f"Group should not exist after deletion, but got status {get_response2.status_code}"
        )

        # Validate 404 error response format
        error_data = get_response2.json()
        assert isinstance(error_data, dict), "404 error response should be a dictionary"
        assert "detail" in error_data, "404 error response must contain 'detail' field"
        assert isinstance(error_data["detail"], str), "detail must be a string"
        assert "not found" in error_data["detail"].lower(), (
            f"Error message should indicate not found: {error_data['detail']}"
        )

        print("[TEST END] test_group_deletion_workflow")
    elif delete_response.status_code == 404:
        pytest.fail("DELETE endpoint for groups not implemented")
    else:
        pytest.fail(
            f"Delete endpoint returned {delete_response.status_code}: {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_group_membership_workflow(api_client, unique_group_name, test_users):
    """Test group membership workflow via API with comprehensive output validation."""
    group_name = unique_group_name

    print("\n[TEST START] test_group_membership_workflow")
    print(f"[SETTINGS] Group name: {group_name}")
    print(f"[SETTINGS] Adding {len(test_users)} members")

    # Create group via API
    create_response = api_client.post(
        "/groups", json={"name": group_name, "description": "Test group for membership"}
    )
    assert create_response.status_code == 200, f"Failed to create group: {create_response.text}"
    group_id = create_response.json()["id"]

    # Add members via API
    added_members = []
    for i, user in enumerate(test_users):
        add_response = api_client.post(
            f"/groups/{group_id}/members", json={"user_id": user["id"], "role": "member"}
        )
        assert add_response.status_code in [200, 201], (
            f"Failed to add member {i + 1}: {add_response.text}"
        )
        add_data = add_response.json()

        # Validate add member response format
        assert isinstance(add_data, dict), "Add member response should be a dictionary"
        assert "user_id" in add_data or "success" in add_data, "Response must indicate success"
        if "user_id" in add_data:
            assert add_data["user_id"] == user["id"], (
                f"user_id must match: expected {user['id']}, got {add_data.get('user_id')}"
            )
        added_members.append(user)

    # Get members via API
    members_response = api_client.get(f"/groups/{group_id}/members")
    assert members_response.status_code == 200, f"Failed to get members: {members_response.text}"
    members_data = members_response.json()

    # Validate outputs - Format, Content, Structure
    # Format validation
    assert isinstance(members_data, dict), "Response should be a dictionary"
    assert "members" in members_data or "items" in members_data, (
        "Response must contain 'members' or 'items' field"
    )

    members_list = members_data.get("members", members_data.get("items", []))
    assert isinstance(members_list, list), "members/items must be a list"

    # Content validation
    assert len(members_list) == len(test_users), (
        f"Member count must match: expected {len(test_users)}, got {len(members_list)}"
    )

    # Structure validation - each member must have required fields
    expected_user_ids = {user["id"] for user in test_users}
    found_user_ids = set()

    for member in members_list:
        assert isinstance(member, dict), "Each member must be a dictionary"
        member_id = member.get("id") or member.get("user_id")
        assert member_id is not None, "Member must have 'id' or 'user_id' field"
        assert isinstance(member_id, int), "Member ID must be an integer"
        found_user_ids.add(member_id)

        # Validate member structure
        if "username" in member:
            assert isinstance(member["username"], str), "username must be a string"
        if "email" in member:
            assert isinstance(member["email"], str), "email must be a string"
        if "role" in member:
            assert isinstance(member["role"], str), "role must be a string"
            assert member["role"] in ["admin", "member", "viewer"], (
                f"role must be valid: got '{member['role']}'"
            )

    # Verify all users are members
    assert expected_user_ids == found_user_ids, (
        f"All test users must be members: expected {expected_user_ids}, found {found_user_ids}"
    )

    # Validate count if present
    if "count" in members_data:
        assert members_data["count"] == len(members_list), (
            f"count must match list length: expected {len(members_list)}, got {members_data['count']}"
        )

    print("[TEST END] test_group_membership_workflow")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_group_member_roles(api_client, unique_group_name, test_users):
    """Test group members with different roles via API with comprehensive output validation."""
    group_name = unique_group_name
    roles = ["admin", "member", "viewer"]

    print("\n[TEST START] test_group_member_roles")
    print(f"[SETTINGS] Group name: {group_name}")
    print(f"[SETTINGS] Testing roles: {roles}")

    # Create group via API
    create_response = api_client.post(
        "/groups", json={"name": group_name, "description": "Test group for roles"}
    )
    assert create_response.status_code == 200, f"Failed to create group: {create_response.text}"
    group_id = create_response.json()["id"]

    # Add members with different roles via API
    role_assignments = {}
    for i, role in enumerate(roles):
        user_id = test_users[i]["id"]
        add_response = api_client.post(
            f"/groups/{group_id}/members", json={"user_id": user_id, "role": role}
        )
        assert add_response.status_code in [200, 201], (
            f"Failed to add member with role {role}: {add_response.text}"
        )

        # Validate add response format
        add_data = add_response.json()
        assert isinstance(add_data, dict), "Add member response should be a dictionary"
        if "role" in add_data:
            assert add_data["role"] == role, (
                f"Response role must match: expected '{role}', got '{add_data.get('role')}'"
            )

        role_assignments[user_id] = role

    # Get members via API
    members_response = api_client.get(f"/groups/{group_id}/members")
    assert members_response.status_code == 200, f"Failed to get members: {members_response.text}"
    members_data = members_response.json()

    # Validate outputs - Format, Content, Structure
    # Format validation
    assert isinstance(members_data, dict), "Response should be a dictionary"
    members_list = members_data.get("members", members_data.get("items", []))
    assert isinstance(members_list, list), "members/items must be a list"
    assert len(members_list) == len(roles), (
        f"Member count must match roles: expected {len(roles)}, got {len(members_list)}"
    )

    # Content and structure validation
    found_roles = {}
    for member in members_list:
        assert isinstance(member, dict), "Each member must be a dictionary"
        member_id = member.get("id") or member.get("user_id")
        assert member_id is not None, "Member must have 'id' or 'user_id' field"
        assert isinstance(member_id, int), "Member ID must be an integer"

        # Validate role if present
        if "role" in member:
            assert isinstance(member["role"], str), "role must be a string"
            assert member["role"] in roles, (
                f"role must be valid: got '{member['role']}', expected one of {roles}"
            )
            found_roles[member_id] = member["role"]

    # Verify all roles are assigned correctly
    for user_id, expected_role in role_assignments.items():
        if user_id in found_roles:
            assert found_roles[user_id] == expected_role, (
                f"User {user_id} role must match: expected '{expected_role}', got '{found_roles[user_id]}'"
            )

    print("[TEST END] test_group_member_roles")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_group_creation_duplicate_name(api_client, unique_group_name):
    """Test that duplicate group names are rejected via API with comprehensive error validation."""
    group_name = unique_group_name

    print("\n[TEST START] test_group_creation_duplicate_name")
    print(f"[SETTINGS] Group name: {group_name}")

    # Create first group
    create_response1 = api_client.post(
        "/groups", json={"name": group_name, "description": "First group"}
    )
    assert create_response1.status_code == 200, (
        f"Failed to create first group: {create_response1.text}"
    )
    first_group_id = create_response1.json()["id"]

    # Try to create another group with same name
    create_response2 = api_client.post(
        "/groups",
        json={
            "name": group_name,  # Same name
            "description": "Second group",
        },
    )

    # Validate error response - Format, Content, Structure
    assert create_response2.status_code == 400, (
        f"Duplicate name should return 400, got {create_response2.status_code}: {create_response2.text}"
    )

    error_data = create_response2.json()
    assert isinstance(error_data, dict), "Error response should be a dictionary"
    assert "detail" in error_data, "Error response must contain 'detail' field"
    assert isinstance(error_data["detail"], str), "detail must be a string"

    detail_lower = error_data["detail"].lower()
    assert "already exists" in detail_lower or "duplicate" in detail_lower, (
        f"Error message should indicate duplicate/exists: {error_data['detail']}"
    )

    # Verify first group still exists
    get_response = api_client.get(f"/groups/{first_group_id}")
    assert get_response.status_code == 200, "First group should still exist"

    print("[TEST END] test_group_creation_duplicate_name")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_group_not_found(api_client):
    """Test group not found error via API with comprehensive error validation."""
    non_existent_id = 99999

    print("\n[TEST START] test_group_not_found")
    print(f"[SETTINGS] Non-existent group ID: {non_existent_id}")

    # Try to get non-existent group
    response = api_client.get(f"/groups/{non_existent_id}")

    # Validate error response - Format, Content, Structure
    assert response.status_code == 404, (
        f"Non-existent group should return 404, got {response.status_code}: {response.text}"
    )

    error_data = response.json()
    assert isinstance(error_data, dict), "Error response should be a dictionary"
    assert "detail" in error_data, "Error response must contain 'detail' field"
    assert isinstance(error_data["detail"], str), "detail must be a string"

    detail_lower = error_data["detail"].lower()
    assert "not found" in detail_lower, (
        f"Error message should indicate not found: {error_data['detail']}"
    )

    print("[TEST END] test_group_not_found")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_group_list_all(api_client, unique_group_name):
    """Test listing all groups via API with comprehensive output validation."""
    group_name = unique_group_name
    num_groups = 3

    print("\n[TEST START] test_group_list_all")
    print(f"[SETTINGS] Creating {num_groups} groups")

    # Create multiple groups via API
    group_ids = []
    created_names = []
    for i in range(num_groups):
        unique_id = str(uuid.uuid4())[:8]
        group_name_i = f"{group_name}_list_{i}_{unique_id}"
        create_response = api_client.post(
            "/groups", json={"name": group_name_i, "description": f"Group {i}"}
        )
        assert create_response.status_code == 200, (
            f"Failed to create group {i + 1}: {create_response.text}"
        )
        group_ids.append(create_response.json()["id"])
        created_names.append(group_name_i)

    # List all groups via API
    list_response = api_client.get("/groups")
    assert list_response.status_code == 200, f"Failed to list groups: {list_response.text}"
    data = list_response.json()

    # Validate outputs - Format, Content, Structure
    # Format validation
    assert isinstance(data, dict), "Response should be a dictionary"
    assert "total" in data or "count" in data or "items" in data, (
        "Response must contain 'total', 'count', or 'items' field"
    )

    groups_list = data.get("items", data.get("groups", []))
    assert isinstance(groups_list, list), "groups/items must be a list"
    assert len(groups_list) >= num_groups, (
        f"List must contain at least {num_groups} groups, got {len(groups_list)}"
    )

    # Content validation - verify created groups are in list
    found_ids = {g.get("id") for g in groups_list if g.get("id")}
    for group_id in group_ids:
        assert group_id in found_ids, f"Created group {group_id} must be in list"

    # Structure validation - each group must have required fields
    for group in groups_list:
        assert isinstance(group, dict), "Each group must be a dictionary"
        assert "id" in group, "Each group must have 'id' field"
        assert "name" in group, "Each group must have 'name' field"
        assert isinstance(group["id"], int), "id must be an integer"
        assert isinstance(group["name"], str), "name must be a string"
        if "description" in group:
            assert isinstance(group["description"], (str, type(None))), (
                "description must be a string or null"
            )
        if "enabled" in group:
            assert isinstance(group["enabled"], bool), "enabled must be a boolean"
        if "created_at" in group:
            assert isinstance(group["created_at"], str), "created_at must be a string"

    # Validate count/total if present
    if "count" in data:
        assert isinstance(data["count"], int), "count must be an integer"
        assert data["count"] >= num_groups, f"count must be >= {num_groups}, got {data['count']}"
    if "total" in data:
        assert isinstance(data["total"], int), "total must be an integer"
        assert data["total"] >= num_groups, f"total must be >= {num_groups}, got {data['total']}"

    print("[TEST END] test_group_list_all")

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

