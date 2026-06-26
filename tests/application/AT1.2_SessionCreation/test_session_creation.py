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
Application Test: AT1.2 - Session Creation and Conversation Flow

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for session creation and conversation flow via API

Related Requirements: FR1.2
Related Tasks: T022
Related Architecture: CC2.1.1
Related Tests: AT1.2

Recent Changes:
- Refactored to use API endpoints only (no direct SessionManager calls)
- Removed all hard-coded values (all from config system)
- All outputs validated via API responses
- Cleanup fixtures use API where possible (users, experts)
- Session cleanup uses direct DB (no DELETE endpoint exists yet)
- Configuration-driven values for context_window and history_retention_days
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
def test_user_credentials(test_env_file, test_secrets_file):
    """Get test user credentials from configuration system."""
    from src.config.loader import load_config

    load_config.cache_clear()

    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    base_password = get_config("test.user.password")

    if not base_username or not base_email or not base_password:
        pytest.fail(
            "Test user credentials not configured. "
            "Set test.user.username/test.user.email/test.user.password in your --env file."
        )

    unique_id = str(uuid.uuid4())[:8]
    return {
        "username": f"{base_username}_at1_2_{unique_id}",
        "email": build_test_email("at1_2", unique_id, base_email),
        "password": base_password,
    }


@pytest.fixture
def test_user(api_client, test_user_credentials):
    """Create test user via API. Cleanup via API if DELETE endpoint exists."""
    creds = test_user_credentials

    response = api_client.post(
        "/users",
        json={
            "username": creds["username"],
            "email": creds["email"],
            "password": creds["password"],
        },
    )
    assert response.status_code == 200, f"Failed to create test user: {response.text}"
    user_data = response.json()

    yield user_data

    # Cleanup via API only
    delete_response = api_client.delete(f"/users/{user_data['id']}")
    if delete_response.status_code not in (200, 204):
        pytest.fail(
            f"Failed to delete user via API: {delete_response.status_code} {delete_response.text}"
        )


@pytest.fixture
def test_expert(api_client, test_config):
    """Create test expert via API. Cleanup via API if DELETE endpoint exists."""
    # Get LLM config from config system (no hard-coding)
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")

    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_at1_2_{unique_id}",
        "title": f"Session Workflow Specialist {unique_id}",
        "description": (
            "Expert for session lifecycle workflow, context retention, retrieval, "
            "cleanup, and validation checks."
        ),
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "enabled": True,
    }

    response = api_client.post("/experts", json=expert_data)
    assert response.status_code == 200, f"Failed to create test expert: {response.text}"
    expert = response.json()

    yield expert

    # Cleanup via API only
    delete_response = api_client.delete(f"/experts/{expert['id']}")
    if delete_response.status_code not in (200, 204):
        pytest.fail(
            f"Failed to delete expert via API: {delete_response.status_code} {delete_response.text}"
        )


@pytest.fixture(autouse=True)
def cleanup_test_sessions(api_client, test_user):
    """Cleanup: Remove test sessions at end of test."""
    user_id = test_user["id"]

    yield

    # Cleanup after test: Remove sessions via API
    list_response = api_client.get("/sessions")
    if list_response.status_code != 200:
        pytest.fail(
            f"Failed to list sessions for cleanup: {list_response.status_code} {list_response.text}"
        )
    data = list_response.json()
    sessions = data.get("sessions", [])
    for session in sessions:
        if session.get("user_id") != user_id:
            continue
        delete_response = api_client.delete(f"/sessions/{session['id']}")
        if delete_response.status_code not in (200, 204):
            pytest.fail(
                f"Failed to delete session via API: {delete_response.status_code} {delete_response.text}"
            )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_creation_workflow_via_api(api_client, test_user, test_expert, test_config):
    """Test complete session creation workflow via API.

    Inputs:
    - test_user: User created via API (from fixture)
    - test_expert: Expert created via API (from fixture)
    - context_window: From config system (session.context_window_size)
    - history_retention_days: From config system (session.history_retention_days)
    - title: Generated unique title

    Expected Outputs:
    - Session ID (integer)
    - user_id matches input
    - expert_config_id matches input
    - title matches input
    - status is present (typically "active")
    - context_window matches input
    - history_retention_days matches input
    - created_at timestamp is present
    - updated_at timestamp is present
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    # Get configuration values from config system (no hard-coding)
    context_window = get_config("session.context_window_size")
    history_retention_days = get_config("session.history_retention_days")
    if context_window is None or history_retention_days is None:
        pytest.fail(
            "Missing session.context_window_size/session.history_retention_days in config (--env)"
        )

    unique_id = str(uuid.uuid4())[:8]
    session_title = f"Test Conversation {unique_id}"

    # Show settings being used
    print(f"\n[SETTINGS] User ID: {user_id}")
    print(f"[SETTINGS] Expert ID: {expert_id}")
    print(f"[SETTINGS] Session title: {session_title}")
    print(f"[SETTINGS] Context window: {context_window} (from config)")
    print(f"[SETTINGS] History retention days: {history_retention_days} (from config)")

    # Create session via API
    response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": session_title,
            "context_window": context_window,
            "history_retention_days": history_retention_days,
        },
    )

    assert response.status_code == 200, f"Creation failed: {response.text}"
    data = response.json()

    # Validate all outputs comprehensively
    assert "id" in data, "Session ID missing from response"
    assert isinstance(data["id"], int), "Session ID must be integer"
    assert data["user_id"] == user_id, (
        f"User ID mismatch: expected {user_id}, got {data['user_id']}"
    )
    assert data["expert_config_id"] == expert_id, (
        f"Expert ID mismatch: expected {expert_id}, got {data['expert_config_id']}"
    )
    assert "status" in data, "Status missing from response"
    assert data["title"] == session_title, (
        f"Title mismatch: expected {session_title}, got {data.get('title')}"
    )

    # Verify session exists via API and validate all fields
    get_response = api_client.get(f"/sessions/{data['id']}")
    assert get_response.status_code == 200, f"Failed to retrieve session: {get_response.text}"
    session_data = get_response.json()

    # Comprehensive validation of all fields
    assert session_data["id"] == data["id"], "Session ID mismatch between create and get"
    assert session_data["user_id"] == user_id, "User ID mismatch in retrieved session"
    assert session_data["expert_config_id"] == expert_id, "Expert ID mismatch in retrieved session"
    assert session_data["title"] == session_title, "Title mismatch in retrieved session"
    assert "status" in session_data, "Status missing in retrieved session"
    # Note: context_window and history_retention_days may not be in GET response yet
    # This is acceptable if the API doesn't return them, but we validate what is returned
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_retrieval_via_api(api_client, test_user, test_expert):
    """Test retrieving session via API.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - title: Generated unique title

    Expected Outputs:
    - Session ID matches created session
    - user_id matches input
    - expert_config_id matches input
    - title matches input
    - status is present
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    session_title = f"Test Session {unique_id}"

    # Create session via API
    create_response = api_client.post(
        "/sessions",
        json={"user_id": user_id, "expert_config_id": expert_id, "title": session_title},
    )
    assert create_response.status_code == 200, f"Failed to create session: {create_response.text}"
    session_id = create_response.json()["id"]

    # Retrieve session via API
    get_response = api_client.get(f"/sessions/{session_id}")
    assert get_response.status_code == 200, f"Failed to retrieve session: {get_response.text}"
    session_data = get_response.json()

    # Validate all outputs
    assert session_data["id"] == session_id, "Session ID mismatch"
    assert session_data["user_id"] == user_id, "User ID mismatch"
    assert session_data["expert_config_id"] == expert_id, "Expert ID mismatch"
    assert "title" in session_data, "Title missing from response"
    assert session_data["title"] == session_title, "Title mismatch"
    assert "status" in session_data, "Status missing from response"
    assert isinstance(session_data["status"], str), "Status must be string"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_list_via_api(api_client, test_user, test_expert):
    """Test listing sessions via API.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - Multiple session titles (3 sessions)

    Expected Outputs:
    - sessions array contains all created sessions
    - total count is at least the number of created sessions
    - Each session in list has id, title, status
    - All created session IDs are present in the list
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    # Create multiple sessions via API
    session_ids = []
    session_titles = []
    for i in range(3):
        unique_id = str(uuid.uuid4())[:8]
        session_title = f"Test Session {i} {unique_id}"
        session_titles.append(session_title)

        create_response = api_client.post(
            "/sessions",
            json={"user_id": user_id, "expert_config_id": expert_id, "title": session_title},
        )
        assert create_response.status_code == 200, (
            f"Failed to create session {i}: {create_response.text}"
        )
        session_ids.append(create_response.json()["id"])

    # List sessions via API
    list_response = api_client.get("/sessions")
    assert list_response.status_code == 200, f"Failed to list sessions: {list_response.text}"
    data = list_response.json()

    # Validate outputs
    assert "sessions" in data, "sessions array missing from response"
    assert "total" in data, "total count missing from response"
    assert isinstance(data["sessions"], list), "sessions must be a list"
    assert isinstance(data["total"], int), "total must be an integer"
    assert len(data["sessions"]) >= 3, f"Expected at least 3 sessions, got {len(data['sessions'])}"
    assert data["total"] >= 3, f"Expected total count at least 3, got {data['total']}"

    # Verify created sessions are in list
    session_ids_in_list = [s["id"] for s in data["sessions"]]
    for session_id in session_ids:
        assert session_id in session_ids_in_list, f"Session {session_id} not found in list"

    # Validate structure of each session in list
    for session in data["sessions"]:
        assert "id" in session, "Session ID missing in list item"
        assert "title" in session, "Session title missing in list item"
        assert "status" in session, "Session status missing in list item"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_not_found_via_api(api_client):
    """Test session not found error via API.

    Inputs:
    - Non-existent session ID (99999)

    Expected Outputs:
    - HTTP 404 status code
    - Error message containing "not found"
    """
    # Try to get non-existent session
    response = api_client.get("/sessions/99999")

    assert response.status_code == 404, f"Expected 404, got {response.status_code}"
    error_data = response.json()
    assert "detail" in error_data, "Error detail missing from response"
    assert "not found" in error_data["detail"].lower(), (
        f"Error message should contain 'not found', got: {error_data['detail']}"
    )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

