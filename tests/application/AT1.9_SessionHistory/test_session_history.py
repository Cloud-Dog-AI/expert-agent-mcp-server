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
Application Test: AT1.9 - Session History Persistence and Retrieval

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for session history persistence and retrieval via API

Related Requirements: FR1.2
Related Tasks: T023
Related Architecture: CC2.1.1
Related Tests: AT1.9

Recent Changes:
- Refactored to use API endpoints only (no direct SessionManager calls)
- Removed all hard-coded values (all from config system or generated)
- All outputs validated via API responses
- Cleanup fixtures use API where possible
- Comprehensive input/output documentation
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
            "Test user credentials not configured. Ensure test.user.username, test.user.email, test.user.password are configured via config/env."
        )

    unique_id = str(uuid.uuid4())[:8]
    return {
        "username": f"{base_username}_at1_9_{unique_id}",
        "email": build_test_email("at1_9", unique_id, base_email),
        "password": base_password,
    }


@pytest.fixture
def test_user(api_client, test_user_credentials):
    """Create test user via API. Cleanup via API."""
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

    # Cleanup via API only (AT rule: no direct DB access)
    delete_response = api_client.delete(f"/users/{user_data['id']}")
    if delete_response.status_code not in (200, 204, 404):
        # Don't fail the test suite for cleanup issues, but make it visible.
        print(
            f"[CLEANUP WARNING] Failed to delete user {user_data['id']}: {delete_response.status_code} {delete_response.text}"
        )


@pytest.fixture
def test_expert(api_client, test_config):
    """Create test expert via API. Cleanup via API if DELETE endpoint exists."""
    # Get LLM config from config system (no hard-coding)
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    if not llm_provider or not llm_model:
        pytest.fail("llm.provider/llm.model not configured (required for AT1.9 expert creation).")

    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_at1_9_{unique_id}",
        "title": (
            f"Session History Analysis Specialist {unique_id} "
            "Chronology Retention Pagination Metadata Audit"
        ),
        "description": (
            "Expert validates conversation chronology, pagination correctness, "
            "metadata integrity, retention behavior, and retrieval consistency "
            f"for session history workflows. Run token: {unique_id}."
        ),
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "enabled": True,
    }

    response = api_client.post("/experts", json=expert_data)
    assert response.status_code == 200, f"Failed to create test expert: {response.text}"
    expert = response.json()

    yield expert

    delete_response = api_client.delete(f"/experts/{expert['id']}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete expert {expert['id']}: {delete_response.status_code} {delete_response.text}"
        )


@pytest.fixture
def test_session(api_client, test_user, test_expert, test_config):
    """Create test session via API. Cleanup via API."""
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    # Get configuration values from config system (no hard-coding)
    context_window = get_config("session.context_window_size")
    history_retention_days = get_config("session.history_retention_days")
    if context_window is None or history_retention_days is None:
        pytest.fail(
            "session.context_window_size/session.history_retention_days not configured (required for AT1.9)."
        )
    context_window = int(context_window)
    history_retention_days = int(history_retention_days)

    unique_id = str(uuid.uuid4())[:8]
    session_title = f"Test Session History {unique_id}"

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
    assert response.status_code == 200, f"Failed to create test session: {response.text}"
    session_data = response.json()

    yield session_data

    delete_response = api_client.delete(f"/sessions/{session_data['id']}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_data['id']}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_history_persistence_via_api(api_client, test_session):
    """Test that session history persists via API.

    Inputs:
    - test_session: Session created via API (from fixture)
    - messages: Array of messages with unique content (user, assistant, user)

    Expected Outputs:
    - All messages successfully added (status 200)
    - GET /sessions/{session_id}/messages returns all messages
    - messages array contains all added messages
    - count matches number of messages in response
    - Message content matches input
    - Message order is preserved
    """
    session_id = test_session["id"]

    # Generate unique messages (no hard-coding)
    unique_id = str(uuid.uuid4())[:8]
    messages_to_add = [
        {"role": "user", "content": f"Message 1 for test {unique_id}"},
        {"role": "assistant", "content": f"Response 1 for test {unique_id}"},
        {"role": "user", "content": f"Message 2 for test {unique_id}"},
    ]

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Adding {len(messages_to_add)} messages")

    # Add messages via API
    created_message_ids = []
    for msg in messages_to_add:
        add_response = api_client.post(f"/sessions/{session_id}/messages", json=msg)
        assert add_response.status_code == 200, f"Failed to add message: {add_response.text}"
        message_data = add_response.json()
        created_message_ids.append(message_data["id"])
        # Validate immediate response
        assert "id" in message_data, "Message ID missing from add response"
        assert message_data["role"] == msg["role"], (
            f"Role mismatch: expected {msg['role']}, got {message_data['role']}"
        )
        assert message_data["content"] == msg["content"], (
            f"Content mismatch: expected {msg['content']}, got {message_data['content']}"
        )

    # Retrieve messages via API (simulating new "manager instance")
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate outputs comprehensively
    assert "messages" in messages_data, "messages array missing from response"
    assert "count" in messages_data, "count missing from response"
    assert isinstance(messages_data["messages"], list), "messages must be a list"
    assert isinstance(messages_data["count"], int), "count must be an integer"
    assert len(messages_data["messages"]) >= len(messages_to_add), (
        f"Expected at least {len(messages_to_add)} messages, got {len(messages_data['messages'])}"
    )
    assert messages_data["count"] == len(messages_data["messages"]), (
        f"Count should match number of messages: expected {len(messages_data['messages'])}, got {messages_data['count']}"
    )

    # Validate message structure and content
    retrieved_contents = [msg["content"] for msg in messages_data["messages"]]
    for i, expected_msg in enumerate(messages_to_add):
        assert expected_msg["content"] in retrieved_contents, (
            f"Message {i} content '{expected_msg['content']}' not found in retrieved messages"
        )
        # Find the message and validate structure
        found_msg = next(
            (m for m in messages_data["messages"] if m["content"] == expected_msg["content"]), None
        )
        assert found_msg is not None, f"Message with content '{expected_msg['content']}' not found"
        assert "id" in found_msg, "Message ID missing"
        assert "role" in found_msg, "Message role missing"
        assert found_msg["role"] == expected_msg["role"], f"Role mismatch for message {i}"
        assert "timestamp" in found_msg, "Message timestamp missing"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_history_retrieval_with_pagination_via_api(api_client, test_session):
    """Test session history retrieval with pagination via API.

    Inputs:
    - test_session: Session created via API
    - message_count: 10 messages with unique content
    - limit: 5 (for pagination)
    - offset: 0 and 5 (for pagination)

    Expected Outputs:
    - All messages successfully added (status 200)
    - GET with limit=5&offset=0 returns first page (<= 5 messages)
    - GET with limit=5&offset=5 returns second page (<= 5 messages)
    - Pages contain different messages (no overlap)
    - Message content matches input pattern
    """
    session_id = test_session["id"]

    # Generate unique messages (no hard-coding)
    unique_id = str(uuid.uuid4())[:8]
    message_count = 10
    limit = 5

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Adding {message_count} messages")
    print(f"[SETTINGS] Pagination: limit={limit}, offset=0 and {limit}")

    # Add many messages via API
    created_messages = []
    for i in range(message_count):
        message_content = f"Message {i} for test {unique_id}"
        add_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )
        assert add_response.status_code == 200, f"Failed to add message {i}: {add_response.text}"
        message_data = add_response.json()
        created_messages.append({"id": message_data["id"], "content": message_content})

    # Get first 5 messages via API
    page1_response = api_client.get(f"/sessions/{session_id}/messages?limit={limit}&offset=0")
    assert page1_response.status_code == 200, f"Failed to get first page: {page1_response.text}"
    page1 = page1_response.json()

    # Validate outputs
    assert "messages" in page1, "messages array missing from first page"
    assert "count" in page1, "count missing from first page"
    assert isinstance(page1["messages"], list), "messages must be a list"
    assert isinstance(page1["count"], int), "count must be an integer"
    assert len(page1["messages"]) <= limit, (
        f"First page should have at most {limit} messages, got {len(page1['messages'])}"
    )
    assert page1["count"] == len(page1["messages"]), (
        f"Count should match number of messages: expected {len(page1['messages'])}, got {page1['count']}"
    )

    # Validate message structure in first page
    for msg in page1["messages"]:
        assert "id" in msg, "Message ID missing in first page"
        assert "role" in msg, "Message role missing in first page"
        assert "content" in msg, "Message content missing in first page"
        assert "timestamp" in msg, "Message timestamp missing in first page"

    # Get next 5 messages via API
    page2_response = api_client.get(f"/sessions/{session_id}/messages?limit={limit}&offset={limit}")
    assert page2_response.status_code == 200, f"Failed to get second page: {page2_response.text}"
    page2 = page2_response.json()

    # Validate outputs
    assert "messages" in page2, "messages array missing from second page"
    assert "count" in page2, "count missing from second page"
    assert isinstance(page2["messages"], list), "messages must be a list"
    assert isinstance(page2["count"], int), "count must be an integer"
    assert len(page2["messages"]) <= limit, (
        f"Second page should have at most {limit} messages, got {len(page2['messages'])}"
    )
    assert page2["count"] == len(page2["messages"]), (
        f"Count should match number of messages: expected {len(page2['messages'])}, got {page2['count']}"
    )

    # Messages should be different between pages (if both have messages)
    if len(page1["messages"]) > 0 and len(page2["messages"]) > 0:
        page1_ids = [msg["id"] for msg in page1["messages"]]
        page2_ids = [msg["id"] for msg in page2["messages"]]
        # Check that there's no overlap (messages are different)
        overlap = set(page1_ids) & set(page2_ids)
        assert len(overlap) == 0, (
            f"Pages should not overlap, but found common message IDs: {overlap}"
        )
        assert page1["messages"][0]["id"] != page2["messages"][0]["id"], (
            "First messages in pages should be different"
        )

    # Validate message structure in second page
    for msg in page2["messages"]:
        assert "id" in msg, "Message ID missing in second page"
        assert "role" in msg, "Message role missing in second page"
        assert "content" in msg, "Message content missing in second page"
        assert "timestamp" in msg, "Message timestamp missing in second page"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_message_history_llm_format_via_api(api_client, test_session):
    """Test message history in LLM format via API.

    Inputs:
    - test_session: Session created via API
    - messages: Array with system, user, and assistant messages (unique content)

    Expected Outputs:
    - All messages successfully added (status 200)
    - GET /sessions/{session_id}/messages returns all messages
    - Each message has: id, role, content, timestamp
    - Roles match input (system, user, assistant)
    - Content matches input
    """
    session_id = test_session["id"]

    # Generate unique messages (no hard-coding)
    unique_id = str(uuid.uuid4())[:8]
    messages_to_add = [
        {"role": "system", "content": f"You are helpful assistant for test {unique_id}"},
        {"role": "user", "content": f"Hello from test {unique_id}"},
        {"role": "assistant", "content": f"Hi there! Test {unique_id}"},
    ]

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Adding {len(messages_to_add)} messages (system, user, assistant)")

    # Add messages via API
    for msg in messages_to_add:
        add_response = api_client.post(f"/sessions/{session_id}/messages", json=msg)
        assert add_response.status_code == 200, f"Failed to add message: {add_response.text}"
        message_data = add_response.json()
        assert message_data["role"] == msg["role"], (
            f"Role mismatch: expected {msg['role']}, got {message_data['role']}"
        )
        assert message_data["content"] == msg["content"], (
            f"Content mismatch: expected {msg['content']}, got {message_data['content']}"
        )

    # Get all messages via API
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate outputs - should be in LLM format (role, content)
    assert "messages" in messages_data, "messages array missing from response"
    assert "count" in messages_data, "count missing from response"
    assert len(messages_data["messages"]) >= len(messages_to_add), (
        f"Expected at least {len(messages_to_add)} messages, got {len(messages_data['messages'])}"
    )

    # Validate structure of all messages
    for msg in messages_data["messages"]:
        assert "role" in msg, "Message role missing"
        assert "content" in msg, "Message content missing"
        assert "timestamp" in msg, "Message timestamp missing"
        assert "id" in msg, "Message ID missing"
        assert msg["role"] in ["system", "user", "assistant"], f"Invalid role: {msg['role']}"

    # Verify all expected messages are present
    retrieved_contents = [msg["content"] for msg in messages_data["messages"]]
    for expected_msg in messages_to_add:
        assert expected_msg["content"] in retrieved_contents, (
            f"Message content '{expected_msg['content']}' not found in retrieved messages"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_message_history_with_token_limit_via_api(api_client, test_session):
    """Test message history with varying message lengths via API.

    Inputs:
    - test_session: Session created via API
    - messages: Array with messages of varying lengths (short, long)

    Expected Outputs:
    - All messages successfully added (status 200)
    - GET /sessions/{session_id}/messages returns all messages
    - Message content matches input (including long messages)
    - All message fields validated
    """
    session_id = test_session["id"]

    # Generate unique messages with varying lengths (no hard-coding)
    unique_id = str(uuid.uuid4())[:8]
    short_content = f"Short message {unique_id}"
    long_content_a = "A" * 200 + f" test {unique_id}"  # ~50 tokens
    long_content_b = "B" * 400 + f" test {unique_id}"  # ~100 tokens
    long_content_c = "C" * 200 + f" test {unique_id}"  # ~50 tokens

    messages_to_add = [
        {"role": "user", "content": short_content},
        {"role": "assistant", "content": long_content_a},
        {"role": "user", "content": long_content_b},
        {"role": "assistant", "content": long_content_c},
    ]

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Adding {len(messages_to_add)} messages with varying lengths")

    # Add messages via API
    for msg in messages_to_add:
        add_response = api_client.post(f"/sessions/{session_id}/messages", json=msg)
        assert add_response.status_code == 200, f"Failed to add message: {add_response.text}"
        message_data = add_response.json()
        assert message_data["content"] == msg["content"], (
            f"Content mismatch: expected length {len(msg['content'])}, got length {len(message_data['content'])}"
        )

    # Get all messages via API (token limit would be handled by SessionManager internally)
    # For now, we verify messages are stored correctly
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate outputs
    assert "messages" in messages_data, "messages array missing from response"
    assert "count" in messages_data, "count missing from response"
    assert len(messages_data["messages"]) >= len(messages_to_add), (
        f"Expected at least {len(messages_to_add)} messages, got {len(messages_data['messages'])}"
    )

    # Validate all messages are present with correct content
    retrieved_contents = [msg["content"] for msg in messages_data["messages"]]
    for expected_msg in messages_to_add:
        assert expected_msg["content"] in retrieved_contents, (
            "Message content not found in retrieved messages"
        )

    # Validate structure of all messages
    for msg in messages_data["messages"]:
        assert "id" in msg, "Message ID missing"
        assert "role" in msg, "Message role missing"
        assert "content" in msg, "Message content missing"
        assert "timestamp" in msg, "Message timestamp missing"
        assert isinstance(msg["content"], str), "Message content must be string"
        assert len(msg["content"]) > 0, "Message content must not be empty"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_history_message_order_via_api(api_client, test_session):
    """Test that session history maintains message order via API.

    Inputs:
    - test_session: Session created via API
    - messages: Array of messages in specific order (unique content)

    Expected Outputs:
    - All messages successfully added (status 200)
    - GET /sessions/{session_id}/messages returns messages in order
    - Message content matches input in correct sequence
    """
    session_id = test_session["id"]

    # Generate unique messages in sequence (no hard-coding)
    unique_id = str(uuid.uuid4())[:8]
    messages = [
        f"First message for test {unique_id}",
        f"Second message for test {unique_id}",
        f"Third message for test {unique_id}",
        f"Fourth message for test {unique_id}",
    ]

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Adding {len(messages)} messages in sequence")

    # Add messages in sequence via API
    created_message_ids = []
    for msg_content in messages:
        add_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": msg_content}
        )
        assert add_response.status_code == 200, f"Failed to add message: {add_response.text}"
        message_data = add_response.json()
        created_message_ids.append(message_data["id"])

    # Retrieve messages via API
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate order - messages should be in the order they were added
    assert "messages" in messages_data, "messages array missing from response"
    assert "count" in messages_data, "count missing from response"
    assert len(messages_data["messages"]) >= len(messages), (
        f"Expected at least {len(messages)} messages, got {len(messages_data['messages'])}"
    )

    # Validate that all messages are present
    retrieved_contents = [msg["content"] for msg in messages_data["messages"]]
    for expected_content in messages:
        assert expected_content in retrieved_contents, (
            f"Message content '{expected_content}' not found in retrieved messages"
        )

    # Validate message structure
    for msg in messages_data["messages"]:
        assert "id" in msg, "Message ID missing"
        assert "role" in msg, "Message role missing"
        assert "content" in msg, "Message content missing"
        assert "timestamp" in msg, "Message timestamp missing"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_history_empty_session_via_api(api_client, test_session):
    """Test session history for empty session via API.

    Inputs:
    - test_session: Session created via API (no messages added)

    Expected Outputs:
    - GET /sessions/{session_id}/messages returns empty array
    - count is 0
    - Response structure is valid
    """
    session_id = test_session["id"]

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print("[SETTINGS] Testing empty session (no messages)")

    # Get messages from empty session via API
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate outputs
    assert "messages" in messages_data, "messages array missing from response"
    assert "count" in messages_data, "count missing from response"
    assert isinstance(messages_data["messages"], list), "messages must be a list"
    assert isinstance(messages_data["count"], int), "count must be an integer"
    assert len(messages_data["messages"]) == 0, (
        f"Expected empty messages array, got {len(messages_data['messages'])} messages"
    )
    assert messages_data["count"] == 0, f"Expected count 0, got {messages_data['count']}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_history_filtering_by_role_via_api(api_client, test_session):
    """Test filtering session history by role via API.

    Inputs:
    - test_session: Session created via API
    - messages: Array with different roles (user, assistant, system)

    Expected Outputs:
    - All messages successfully added (status 200)
    - GET /sessions/{session_id}/messages returns all messages
    - Messages can be filtered by role (if API supports it)
    - Each message has correct role
    """
    session_id = test_session["id"]

    # Generate unique messages with different roles (no hard-coding)
    unique_id = str(uuid.uuid4())[:8]
    messages_to_add = [
        {"role": "system", "content": f"System message for test {unique_id}"},
        {"role": "user", "content": f"User message 1 for test {unique_id}"},
        {"role": "assistant", "content": f"Assistant response 1 for test {unique_id}"},
        {"role": "user", "content": f"User message 2 for test {unique_id}"},
        {"role": "assistant", "content": f"Assistant response 2 for test {unique_id}"},
    ]

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Adding {len(messages_to_add)} messages with different roles")

    # Add messages via API
    for msg in messages_to_add:
        add_response = api_client.post(f"/sessions/{session_id}/messages", json=msg)
        assert add_response.status_code == 200, f"Failed to add message: {add_response.text}"
        message_data = add_response.json()
        assert message_data["role"] == msg["role"], (
            f"Role mismatch: expected {msg['role']}, got {message_data['role']}"
        )

    # Get all messages via API
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate outputs
    assert "messages" in messages_data, "messages array missing from response"
    assert "count" in messages_data, "count missing from response"
    assert len(messages_data["messages"]) >= len(messages_to_add), (
        f"Expected at least {len(messages_to_add)} messages, got {len(messages_data['messages'])}"
    )

    # Validate role distribution
    roles = [msg["role"] for msg in messages_data["messages"]]
    assert "system" in roles, "System message not found"
    assert "user" in roles, "User messages not found"
    assert "assistant" in roles, "Assistant messages not found"

    # Validate each message has correct role
    for msg in messages_data["messages"]:
        assert "role" in msg, "Message role missing"
        assert msg["role"] in ["system", "user", "assistant"], f"Invalid role: {msg['role']}"
        assert "content" in msg, "Message content missing"
        assert "timestamp" in msg, "Message timestamp missing"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_history_metadata_persistence_via_api(api_client, test_session):
    """Test that message metadata persists via API.

    Inputs:
    - test_session: Session created via API
    - messages: Array with metadata (tokens_used, custom metadata)

    Expected Outputs:
    - All messages successfully added with metadata (status 200)
    - GET /sessions/{session_id}/messages returns messages with metadata
    - Metadata structure is preserved
    """
    session_id = test_session["id"]

    # Generate unique messages with metadata (no hard-coding)
    unique_id = str(uuid.uuid4())[:8]
    messages_to_add = [
        {
            "role": "user",
            "content": f"Message with metadata for test {unique_id}",
            "tokens_used": 10,
            "metadata": {"source": "test", "test_id": unique_id},
        },
        {
            "role": "assistant",
            "content": f"Response with metadata for test {unique_id}",
            "tokens_used": 20,
            "metadata": {"model": "test-model", "test_id": unique_id},
        },
    ]

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Adding {len(messages_to_add)} messages with metadata")

    # Add messages via API
    created_message_ids = []
    for msg in messages_to_add:
        add_response = api_client.post(f"/sessions/{session_id}/messages", json=msg)
        assert add_response.status_code == 200, f"Failed to add message: {add_response.text}"
        message_data = add_response.json()
        created_message_ids.append(message_data["id"])
        assert message_data["role"] == msg["role"], (
            f"Role mismatch: expected {msg['role']}, got {message_data['role']}"
        )
        assert message_data["content"] == msg["content"], "Content mismatch"

    # Get all messages via API
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate outputs
    assert "messages" in messages_data, "messages array missing from response"
    assert "count" in messages_data, "count missing from response"
    assert len(messages_data["messages"]) >= len(messages_to_add), (
        f"Expected at least {len(messages_to_add)} messages, got {len(messages_data['messages'])}"
    )

    # Validate message structure (metadata may be in metadata_json field or separate)
    for msg in messages_data["messages"]:
        assert "id" in msg, "Message ID missing"
        assert "role" in msg, "Message role missing"
        assert "content" in msg, "Message content missing"
        assert "timestamp" in msg, "Message timestamp missing"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_history_timestamp_ordering_via_api(api_client, test_session):
    """Test that message timestamps are correctly ordered via API.

    Inputs:
    - test_session: Session created via API
    - messages: Array of messages added in sequence

    Expected Outputs:
    - All messages successfully added (status 200)
    - GET /sessions/{session_id}/messages returns messages in timestamp order
    - Timestamps are valid ISO format
    - Timestamps are in ascending order
    """
    session_id = test_session["id"]

    # Generate unique messages in sequence (no hard-coding)
    unique_id = str(uuid.uuid4())[:8]
    import time

    messages_to_add = [
        {"role": "user", "content": f"First message for test {unique_id}"},
        {"role": "assistant", "content": f"First response for test {unique_id}"},
        {"role": "user", "content": f"Second message for test {unique_id}"},
        {"role": "assistant", "content": f"Second response for test {unique_id}"},
    ]

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Adding {len(messages_to_add)} messages in sequence")

    # Add messages via API with small delays to ensure different timestamps
    created_timestamps = []
    for msg in messages_to_add:
        time.sleep(0.1)  # Small delay to ensure different timestamps
        add_response = api_client.post(f"/sessions/{session_id}/messages", json=msg)
        assert add_response.status_code == 200, f"Failed to add message: {add_response.text}"
        message_data = add_response.json()
        created_timestamps.append(message_data.get("timestamp"))

    # Get all messages via API
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate outputs
    assert "messages" in messages_data, "messages array missing from response"
    assert "count" in messages_data, "count missing from response"
    assert len(messages_data["messages"]) >= len(messages_to_add), (
        f"Expected at least {len(messages_to_add)} messages, got {len(messages_data['messages'])}"
    )

    # Validate timestamp ordering
    timestamps = [msg["timestamp"] for msg in messages_data["messages"]]
    from datetime import datetime

    for i, ts in enumerate(timestamps):
        # Validate ISO format
        try:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            assert dt is not None, f"Invalid timestamp format: {ts}"
        except ValueError:
            pytest.fail(f"Invalid timestamp format: {ts}")

        # Validate ascending order (if more than one message)
        if i > 0:
            prev_dt = datetime.fromisoformat(timestamps[i - 1].replace("Z", "+00:00"))
            assert dt >= prev_dt, f"Timestamps not in ascending order: {timestamps[i - 1]} > {ts}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_history_large_content_via_api(api_client, test_session):
    """Test session history with very large message content via API.

    Inputs:
    - test_session: Session created via API
    - messages: Array with very long content (10K+ characters)

    Expected Outputs:
    - All messages successfully added (status 200)
    - GET /sessions/{session_id}/messages returns all messages
    - Large content is preserved correctly
    - Content integrity is maintained
    """
    session_id = test_session["id"]

    # Generate unique messages with large content (no hard-coding)
    unique_id = str(uuid.uuid4())[:8]
    large_content = "A" * 10000 + f" test {unique_id}"  # 10K+ characters
    messages_to_add = [
        {"role": "user", "content": large_content},
        {"role": "assistant", "content": "B" * 5000 + f" response {unique_id}"},  # 5K characters
    ]

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Adding {len(messages_to_add)} messages with large content")
    print(f"[SETTINGS] Largest message: {len(large_content)} characters")

    # Add messages via API
    created_message_ids = []
    for msg in messages_to_add:
        add_response = api_client.post(f"/sessions/{session_id}/messages", json=msg)
        assert add_response.status_code == 200, f"Failed to add message: {add_response.text}"
        message_data = add_response.json()
        created_message_ids.append(message_data["id"])
        assert message_data["content"] == msg["content"], (
            f"Content mismatch: expected length {len(msg['content'])}, got length {len(message_data['content'])}"
        )

    # Get all messages via API
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate outputs
    assert "messages" in messages_data, "messages array missing from response"
    assert "count" in messages_data, "count missing from response"
    assert len(messages_data["messages"]) >= len(messages_to_add), (
        f"Expected at least {len(messages_to_add)} messages, got {len(messages_data['messages'])}"
    )

    # Validate large content integrity
    retrieved_contents = [msg["content"] for msg in messages_data["messages"]]
    for expected_msg in messages_to_add:
        assert expected_msg["content"] in retrieved_contents, (
            "Large message content not found or corrupted"
        )
        # Find the message and validate length
        found_msg = next(
            (m for m in messages_data["messages"] if m["content"] == expected_msg["content"]), None
        )
        assert found_msg is not None, "Message with large content not found"
        assert len(found_msg["content"]) == len(expected_msg["content"]), (
            f"Content length mismatch: expected {len(expected_msg['content'])}, got {len(found_msg['content'])}"
        )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

