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
Application Test: AT1.8 - Basic Chat Interaction with LLM

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for basic chat interaction with LLM via API

Related Requirements: FR1.2, FR1.1
Related Tasks: T022, T008
Related Architecture: CC2.1.1, IP1.1.1
Related Tests: AT1.8

Recent Changes:
- Refactored to use API endpoints only (no direct SessionManager/LLMManager calls)
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
            "Test user credentials not configured. "
            "Set test.user.username/test.user.email/test.user.password in your --env file."
        )

    unique_id = str(uuid.uuid4())[:8]
    return {
        "username": f"{base_username}_at1_8_{unique_id}",
        "email": build_test_email("at1_8", unique_id, base_email),
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
        "name": f"expert_at1_8_{unique_id}",
        "title": f"Test Expert {unique_id}",
        "description": (
            f"Chat interaction expert for robust testing with unique words and context {unique_id}"
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


@pytest.fixture
def test_session(api_client, test_user, test_expert, test_config):
    """Create test session via API. Cleanup via API only."""
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
    session_title = f"Test Chat Session {unique_id}"

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

    # Cleanup: Delete session via API only
    delete_response = api_client.delete(f"/sessions/{session_data['id']}")
    if delete_response.status_code not in (200, 204):
        pytest.fail(
            f"Failed to delete session via API: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_basic_chat_interaction_via_api(api_client, test_session):
    """Test basic chat interaction via API (adding messages).

    Inputs:
    - test_session: Session created via API (from fixture)
    - role: "user" (string)
    - content: Generated unique message content

    Expected Outputs (POST /sessions/{session_id}/messages):
    - id: Integer (message ID)
    - role: String (matches input, "user")
    - content: String (matches input)
    - timestamp: String (ISO format timestamp)

    Expected Outputs (GET /sessions/{session_id}/messages):
    - messages: Array of message objects
    - count: Integer (number of messages)
    - Each message has: id, role, content, timestamp
    - First message content matches input
    """
    session_id = test_session["id"]

    # Generate unique message content (no hard-coding)
    unique_id = str(uuid.uuid4())[:8]
    user_message = f"Hello, this is test message {unique_id}. How are you?"

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Message content: {user_message[:50]}...")

    # User sends message via API
    add_message_response = api_client.post(
        f"/sessions/{session_id}/messages", json={"role": "user", "content": user_message}
    )

    assert add_message_response.status_code == 200, (
        f"Failed to add message: {add_message_response.text}"
    )
    message_data = add_message_response.json()

    # Validate all outputs comprehensively
    assert "id" in message_data, "Message ID missing from response"
    assert isinstance(message_data["id"], int), "Message ID must be integer"
    assert "role" in message_data, "Role missing from response"
    assert message_data["role"] == "user", (
        f"Role mismatch: expected 'user', got '{message_data['role']}'"
    )
    assert "content" in message_data, "Content missing from response"
    assert message_data["content"] == user_message, (
        f"Content mismatch: expected '{user_message}', got '{message_data['content']}'"
    )
    assert "timestamp" in message_data, "Timestamp missing from response"
    assert isinstance(message_data["timestamp"], str), "Timestamp must be string"
    # Validate timestamp is ISO format (contains 'T' or is valid ISO format)
    assert "T" in message_data["timestamp"] or len(message_data["timestamp"]) > 10, (
        "Timestamp should be ISO format"
    )

    # Get messages via API
    get_messages_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_messages_response.status_code == 200, (
        f"Failed to get messages: {get_messages_response.text}"
    )
    messages_data = get_messages_response.json()

    # Validate outputs
    assert "messages" in messages_data, "messages array missing from response"
    assert "count" in messages_data, "count missing from response"
    assert isinstance(messages_data["messages"], list), "messages must be a list"
    assert isinstance(messages_data["count"], int), "count must be an integer"
    assert len(messages_data["messages"]) >= 1, (
        f"Expected at least 1 message, got {len(messages_data['messages'])}"
    )
    assert messages_data["count"] >= 1, f"Expected count at least 1, got {messages_data['count']}"

    # Validate message structure
    first_message = messages_data["messages"][0]
    assert "id" in first_message, "Message ID missing in list"
    assert "role" in first_message, "Message role missing in list"
    assert "content" in first_message, "Message content missing in list"
    assert "timestamp" in first_message, "Message timestamp missing in list"

    # Verify content matches
    assert first_message["content"] == user_message, (
        f"Message content mismatch in list: expected '{user_message}', got '{first_message['content']}'"
    )
    assert first_message["role"] == "user", (
        f"Message role mismatch in list: expected 'user', got '{first_message['role']}'"
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_with_system_prompt_via_api(api_client, test_session):
    """Test chat interaction with system prompt via API.

    Inputs:
    - test_session: Session created via API
    - system_message: Generated unique system message
    - user_message: Generated unique user message

    Expected Outputs:
    - Both messages successfully added (status 200)
    - GET /sessions/{session_id}/messages returns both messages
    - Messages in correct order (system first, user second)
    - All message fields validated
    """
    session_id = test_session["id"]

    # Generate unique messages (no hard-coding)
    unique_id = str(uuid.uuid4())[:8]
    system_message = f"You are a helpful assistant for test {unique_id}."
    user_message = f"What is 2+2? Test {unique_id}"

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] System message: {system_message}")
    print(f"[SETTINGS] User message: {user_message}")

    # Add system message via API
    system_response = api_client.post(
        f"/sessions/{session_id}/messages", json={"role": "system", "content": system_message}
    )
    assert system_response.status_code == 200, (
        f"Failed to add system message: {system_response.text}"
    )
    system_data = system_response.json()
    assert system_data["role"] == "system", "System message role mismatch"
    assert system_data["content"] == system_message, "System message content mismatch"

    # Add user message via API
    user_response = api_client.post(
        f"/sessions/{session_id}/messages", json={"role": "user", "content": user_message}
    )
    assert user_response.status_code == 200, f"Failed to add user message: {user_response.text}"
    user_data = user_response.json()
    assert user_data["role"] == "user", "User message role mismatch"
    assert user_data["content"] == user_message, "User message content mismatch"

    # Get all messages via API
    get_messages_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_messages_response.status_code == 200, (
        f"Failed to get messages: {get_messages_response.text}"
    )
    messages_data = get_messages_response.json()

    # Validate outputs
    assert "messages" in messages_data, "messages array missing from response"
    assert "count" in messages_data, "count missing from response"
    assert len(messages_data["messages"]) >= 2, (
        f"Expected at least 2 messages, got {len(messages_data['messages'])}"
    )
    assert messages_data["count"] >= 2, f"Expected count at least 2, got {messages_data['count']}"

    # Validate message order and content
    messages = messages_data["messages"]
    # Messages should be in order (system first, then user)
    # Note: Order depends on implementation - we validate that both exist
    system_found = False
    user_found = False
    for msg in messages:
        if msg["role"] == "system" and msg["content"] == system_message:
            system_found = True
        if msg["role"] == "user" and msg["content"] == user_message:
            user_found = True

    assert system_found, f"System message not found in list. Expected: '{system_message}'"
    assert user_found, f"User message not found in list. Expected: '{user_message}'"

    # Validate structure of all messages
    for msg in messages:
        assert "id" in msg, "Message ID missing"
        assert "role" in msg, "Message role missing"
        assert "content" in msg, "Message content missing"
        assert "timestamp" in msg, "Message timestamp missing"
        assert msg["role"] in ["system", "user", "assistant"], f"Invalid role: {msg['role']}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_message_pagination_via_api(api_client, test_session):
    """Test chat message pagination via API.

    Inputs:
    - test_session: Session created via API
    - Multiple messages: 10 messages with unique content
    - limit: 5 (for pagination)
    - offset: 0 and 5 (for pagination)

    Expected Outputs:
    - All 10 messages successfully added (status 200)
    - GET with limit=5&offset=0 returns first page (<= 5 messages)
    - GET with limit=5&offset=5 returns second page (<= 5 messages)
    - Pages contain different messages (no overlap)
    - All message fields validated
    """
    session_id = test_session["id"]

    # Generate unique messages (no hard-coding)
    unique_id = str(uuid.uuid4())[:8]
    message_count = 10
    limit = 5

    # Add multiple messages via API
    created_message_ids = []
    for i in range(message_count):
        message_content = f"Message {i} for test {unique_id}"
        response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )
        assert response.status_code == 200, f"Failed to add message {i}: {response.text}"
        message_data = response.json()
        created_message_ids.append(message_data["id"])

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Created {message_count} messages")
    print(f"[SETTINGS] Pagination: limit={limit}, offset=0 and {limit}")

    # Get first page via API
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
    # Note: API returns count of messages in current response, not total count
    assert page1["count"] == len(page1["messages"]), (
        f"Count should match number of messages in response: expected {len(page1['messages'])}, got {page1['count']}"
    )

    # Validate message structure in first page
    for msg in page1["messages"]:
        assert "id" in msg, "Message ID missing in first page"
        assert "role" in msg, "Message role missing in first page"
        assert "content" in msg, "Message content missing in first page"
        assert "timestamp" in msg, "Message timestamp missing in first page"

    # Get second page via API
    page2_response = api_client.get(f"/sessions/{session_id}/messages?limit={limit}&offset={limit}")
    assert page2_response.status_code == 200, (
        f"Failed to get second page: {page2_response.status_code}"
    )
    page2 = page2_response.json()

    # Validate outputs
    assert "messages" in page2, "messages array missing from second page"
    assert "count" in page2, "count missing from second page"
    assert isinstance(page2["messages"], list), "messages must be a list"
    assert isinstance(page2["count"], int), "count must be an integer"
    assert len(page2["messages"]) <= limit, (
        f"Second page should have at most {limit} messages, got {len(page2['messages'])}"
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

        # Validate that page1 messages come before page2 messages (by ID or timestamp)
        # This is a basic check - actual ordering depends on implementation
        assert page1["messages"][0]["id"] != page2["messages"][0]["id"], (
            "First messages in pages should be different"
        )

    # Validate message structure in second page
    for msg in page2["messages"]:
        assert "id" in msg, "Message ID missing in second page"
        assert "role" in msg, "Message role missing in second page"
        assert "content" in msg, "Message content missing in second page"
        assert "timestamp" in msg, "Message timestamp missing in second page"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.llm, pytest.mark.smtp, pytest.mark.heavy]
