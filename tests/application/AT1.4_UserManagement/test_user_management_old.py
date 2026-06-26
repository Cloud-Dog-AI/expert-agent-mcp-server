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
Application Test: AT1.4 - User Management (create, update, delete)

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for user management workflows via API

Related Requirements: FR1.5
Related Tasks: T005
Related Architecture: CC5.1.1
Related Tests: AT1.4

Recent Changes:
- Refactored to use API endpoints only (no direct UserManager calls)
- Added user cleanup fixtures (remove at start/end)
- Removed all hard-coded values (all from config system)
- Added deletion test
- All outputs validated via API responses
"""

import sys
from pathlib import Path

# Add parent directory to path for shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import build_test_email, create_api_client_fixture, validate_config_loaded


import pytest
import uuid
from src.config.loader import get_config


@pytest.fixture(scope="module")
def api_client():
    """Create API client that connects to real running API server."""
    validate_config_loaded()
    return create_api_client_fixture(check_health=True)()


@pytest.fixture
def unique_test_user_credentials(test_config):
    """Generate unique test user credentials from configuration system."""
    # Use config system to get values (respects hierarchy: os.environ -> env-file -> config.yaml -> defaults.yaml)
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    base_password = get_config("test.user.password")
    base_display_name = get_config("test.user.display_name")

    if not base_username or not base_email or not base_password:
        pytest.fail("Test user credentials not configured. Set test.user.* via --env file.")

    if not base_display_name:
        base_display_name = base_username

    unique_id = str(uuid.uuid4())[:8]
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    return {
        "username": f"{base_username}_at1_4_{unique_id}",
        "email": build_test_email("at1_4", unique_id, base_email),
        "password": base_password,
        "display_name": f"{base_display_name} {unique_id}",
    }


@pytest.fixture(autouse=True)
def cleanup_test_user(api_client, unique_test_user_credentials):
    """Cleanup: Remove test user at start (if exists) and end of test."""
    creds = unique_test_user_credentials
    username = creds["username"]
    email = creds["email"]

    # Cleanup before test via API
    list_response = api_client.get("/users")
    if list_response.status_code != 200:
        pytest.fail(
            f"Failed to list users for cleanup: {list_response.status_code} {list_response.text}"
        )
    users = list_response.json().get("users", [])
    for user in users:
        if user.get("username") == username or user.get("email") == email:
            delete_response = api_client.delete(f"/users/{user['id']}")
            if delete_response.status_code not in (200, 204):
                pytest.fail(
                    f"Failed to delete user via API: {delete_response.status_code} {delete_response.text}"
                )

    yield

    # Cleanup after test via API
    list_response = api_client.get("/users")
    if list_response.status_code != 200:
        pytest.fail(
            f"Failed to list users for cleanup: {list_response.status_code} {list_response.text}"
        )
    users = list_response.json().get("users", [])
    for user in users:
        if user.get("username") == username or user.get("email") == email:
            delete_response = api_client.delete(f"/users/{user['id']}")
            if delete_response.status_code not in (200, 204):
                pytest.fail(
                    f"Failed to delete user via API: {delete_response.status_code} {delete_response.text}"
                )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_creation_workflow(api_client, unique_test_user_credentials):
    """Test complete user creation workflow via API."""
    creds = unique_test_user_credentials

    # Show settings being used
    print(f"\n[SETTINGS] User username: {creds['username']}")
    print(f"[SETTINGS] User email: {creds['email']}")
    print(f"[SETTINGS] User display_name: {creds['display_name']}")

    # Create user via API
    response = api_client.post(
        "/users",
        json={
            "username": creds["username"],
            "email": creds["email"],
            "password": creds["password"],
            "display_name": creds["display_name"],
            "role": "user",
        },
    )

    assert response.status_code == 200, f"Creation failed: {response.text}"
    data = response.json()

    # Validate all outputs
    assert "id" in data
    assert data["username"] == creds["username"]
    assert data["email"] == creds["email"]
    assert data.get("display_name") == creds["display_name"]
    assert data.get("role") == "user"

    # Verify user exists via API
    get_response = api_client.get(f"/users/{data['id']}")
    assert get_response.status_code == 200
    user_data = get_response.json()
    assert user_data["username"] == creds["username"]
    assert user_data["email"] == creds["email"]
    assert user_data["enabled"] is True
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_update_workflow(api_client, unique_test_user_credentials):
    """Test user update workflow via API."""
    creds = unique_test_user_credentials

    # Create user via API
    create_response = api_client.post(
        "/users",
        json={
            "username": creds["username"],
            "email": creds["email"],
            "password": creds["password"],
            "display_name": creds["display_name"],
        },
    )
    assert create_response.status_code == 200
    user_id = create_response.json()["id"]

    # Update user via PUT endpoint (if exists)
    unique_id = str(uuid.uuid4())[:8]
    update_response = api_client.put(
        f"/users/{user_id}",
        json={
            "display_name": f"Updated Name {unique_id}",
            "email": build_test_email("updated", unique_id, creds["email"]),
            "role": "admin",
        },
    )

    if update_response.status_code == 200:
        # PUT endpoint exists - validate outputs
        data = update_response.json()
        assert data["id"] == user_id
        assert data["display_name"] == f"Updated Name {unique_id}"
        assert data["role"] == "admin"

        # Verify via GET
        get_response = api_client.get(f"/users/{user_id}")
        assert get_response.status_code == 200
        user_data = get_response.json()
        assert user_data["display_name"] == f"Updated Name {unique_id}"
        assert user_data["role"] == "admin"
    elif update_response.status_code == 404:
        pytest.fail("PUT endpoint for updating users not implemented")
    else:
        pytest.fail(
            f"Update endpoint returned {update_response.status_code}: {update_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_retrieval_workflow(api_client, unique_test_user_credentials):
    """Test user retrieval workflow via API."""
    creds = unique_test_user_credentials

    # Create user via API
    create_response = api_client.post(
        "/users",
        json={
            "username": creds["username"],
            "email": creds["email"],
            "password": creds["password"],
            "display_name": creds["display_name"],
        },
    )
    assert create_response.status_code == 200
    user_id = create_response.json()["id"]

    # Retrieve by ID via API
    get_response = api_client.get(f"/users/{user_id}")
    assert get_response.status_code == 200
    user_data = get_response.json()

    # Validate all outputs
    assert user_data["id"] == user_id
    assert user_data["username"] == creds["username"]
    assert user_data["email"] == creds["email"]
    assert user_data.get("display_name") == creds["display_name"]
    assert "enabled" in user_data
    assert "role" in user_data
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_deletion_workflow(api_client, unique_test_user_credentials):
    """Test user deletion workflow via API."""
    creds = unique_test_user_credentials

    # Create user via API
    create_response = api_client.post(
        "/users",
        json={
            "username": creds["username"],
            "email": creds["email"],
            "password": creds["password"],
            "display_name": creds["display_name"],
        },
    )
    assert create_response.status_code == 200
    user_id = create_response.json()["id"]

    # Verify user exists
    get_response = api_client.get(f"/users/{user_id}")
    assert get_response.status_code == 200

    # Delete user via DELETE endpoint (if exists)
    delete_response = api_client.delete(f"/users/{user_id}")

    if delete_response.status_code in [200, 204]:
        # DELETE endpoint exists - verify deletion
        # Try to get deleted user - should return 404
        get_response2 = api_client.get(f"/users/{user_id}")
        assert get_response2.status_code == 404
    elif delete_response.status_code == 404:
        pytest.fail("DELETE endpoint for users not implemented")
    else:
        pytest.fail(
            f"Delete endpoint returned {delete_response.status_code}: {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_creation_duplicate_username(api_client, unique_test_user_credentials):
    """Test that duplicate usernames are rejected via API."""
    creds = unique_test_user_credentials

    # Create first user
    create_response1 = api_client.post(
        "/users",
        json={
            "username": creds["username"],
            "email": creds["email"],
            "password": creds["password"],
        },
    )
    assert create_response1.status_code == 200

    # Try to create another user with same username
    unique_id = str(uuid.uuid4())[:8]
    create_response2 = api_client.post(
        "/users",
        json={
            "username": creds["username"],  # Same username
            "email": build_test_email("different", unique_id, creds["email"]),
            "password": creds["password"],
        },
    )

    assert create_response2.status_code == 400
    assert (
        "already exists" in create_response2.json()["detail"].lower()
        or "duplicate" in create_response2.json()["detail"].lower()
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_creation_duplicate_email(api_client, unique_test_user_credentials):
    """Test that duplicate emails are rejected via API."""
    creds = unique_test_user_credentials

    # Create first user
    create_response1 = api_client.post(
        "/users",
        json={
            "username": creds["username"],
            "email": creds["email"],
            "password": creds["password"],
        },
    )
    assert create_response1.status_code == 200

    # Try to create another user with same email
    unique_id = str(uuid.uuid4())[:8]
    create_response2 = api_client.post(
        "/users",
        json={
            "username": f"{creds['username']}_2_{unique_id}",
            "email": creds["email"],  # Same email
            "password": creds["password"],
        },
    )

    assert create_response2.status_code == 400
    assert (
        "already exists" in create_response2.json()["detail"].lower()
        or "duplicate" in create_response2.json()["detail"].lower()
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_not_found(api_client):
    """Test user not found error via API."""
    # Try to get non-existent user
    response = api_client.get("/users/99999")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_creation_validation(api_client, unique_test_user_credentials):
    """Test user creation validation via API."""
    creds = unique_test_user_credentials

    # Test missing required fields - username required
    response1 = api_client.post(
        "/users",
        json={
            "email": creds["email"],
            "password": creds["password"],
            # Missing username
        },
    )
    assert response1.status_code == 422  # Validation error

    # Test missing email
    response2 = api_client.post(
        "/users",
        json={
            "username": creds["username"],
            "password": creds["password"],
            # Missing email
        },
    )
    assert response2.status_code == 422  # Validation error

    # Test valid creation
    response3 = api_client.post(
        "/users",
        json={
            "username": creds["username"],
            "email": creds["email"],
            "password": creds["password"],
        },
    )
    assert response3.status_code == 200

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

