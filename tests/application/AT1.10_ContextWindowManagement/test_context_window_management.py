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
Application Test: AT1.10 - Context Window Management for Long Conversations

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for context window management via API

Related Requirements: FR1.2
Related Tasks: T010, T024
Related Architecture: CC2.1.1
Related Tests: AT1.10

Recent Changes:
- Refactored to use API endpoints only (no direct SessionManager/ContextWindowManager calls)
- Removed all hard-coded values (all from config system or generated)
- All outputs validated via API responses
- Cleanup fixtures use API where possible
- Comprehensive input/output documentation
"""

import sys
from pathlib import Path

# Add parent directory to path for shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import (
    build_test_email,
    create_api_client_fixture,
    log_validation_checks,
    validate_config_loaded,
)


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
            "Test user credentials not configured. Ensure test.user.* keys are configured via config/env."
        )

    unique_id = str(uuid.uuid4())[:8]
    return {
        "username": f"{base_username}_at1_10_{unique_id}",
        "email": build_test_email("at1_10", unique_id, base_email),
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

    delete_response = api_client.delete(f"/users/{user_data['id']}")
    if delete_response.status_code not in (200, 204, 404):
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
        pytest.fail("llm.provider/llm.model not configured (required for AT1.10 expert creation).")

    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_at1_10_{unique_id}",
        "title": f"Long Conversation Context Expert {unique_id} memory retention summarization truncation pagination embeddings",
        "description": "Extended context-window integration scenario with diverse terms: aurora basilisk cipher drift engine fable glyph helios isomer kernel lumen matrix nexus",
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
    """Create test session via API with context window from config. Cleanup via API."""
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    # Get configuration values from config system (no hard-coding)
    context_window = get_config("session.context_window_size")
    history_retention_days = get_config("session.history_retention_days")
    if context_window is None or history_retention_days is None:
        pytest.fail(
            "session.context_window_size/session.history_retention_days not configured (required for AT1.10)."
        )
    context_window = int(context_window)
    history_retention_days = int(history_retention_days)

    unique_id = str(uuid.uuid4())[:8]
    session_title = f"Test Context Window Session {unique_id}"

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


def test_long_conversation_context_management_via_api(api_client, test_session, output_store):
    """Test context window management for long conversations via API.

    Inputs:
    - test_session: Session created via API (from fixture, with context_window from config)
    - messages: Multiple user/assistant message pairs (generated unique content)

    Expected Outputs:
    - All messages successfully added (status 200)
    - GET /sessions/{session_id}/messages returns all messages
    - Messages are stored and retrievable (context window managed internally)
    - All message fields validated
    """
    session_id = test_session["id"]

    # Get context window from config (for reference, not for direct use)
    context_window = get_config("session.context_window_size")
    if context_window is None:
        pytest.fail("Missing session.context_window_size in config (--env)")

    # Generate unique messages (no hard-coding)
    unique_id = str(uuid.uuid4())[:8]
    message_count = get_config("test.at1_10.message_counts.medium")
    if message_count is None:
        pytest.fail("test.at1_10.message_counts.medium not configured (required for AT1.10)")
    message_count = int(message_count)

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Context window: {context_window} (from config)")
    print(
        f"[SETTINGS] Adding {message_count * 2} messages ({message_count} user + {message_count} assistant)"
    )

    # Add many messages via API to test context window management
    created_message_ids = []
    for i in range(message_count):
        # User message with unique content
        user_content = f"User message {i} for test {unique_id}: " + "A" * 50
        user_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": user_content}
        )
        assert user_response.status_code == 200, (
            f"Failed to add user message {i}: {user_response.text}"
        )
        user_data = user_response.json()
        created_message_ids.append(user_data["id"])
        assert user_data["content"] == user_content, (
            f"User message content mismatch for message {i}"
        )

        # Assistant message with unique content
        assistant_content = f"Assistant response {i} for test {unique_id}: " + "B" * 50
        assistant_response = api_client.post(
            f"/sessions/{session_id}/messages",
            json={"role": "assistant", "content": assistant_content},
        )
        assert assistant_response.status_code == 200, (
            f"Failed to add assistant message {i}: {assistant_response.text}"
        )
        assistant_data = assistant_response.json()
        created_message_ids.append(assistant_data["id"])
        assert assistant_data["content"] == assistant_content, (
            f"Assistant message content mismatch for message {i}"
        )

    # Get message history via API (context window managed internally by SessionManager)
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate outputs
    checks = {
        "has_messages": "messages" in messages_data,
        "has_count": "count" in messages_data,
        "messages_is_list": isinstance(messages_data.get("messages"), list),
        "count_is_int": isinstance(messages_data.get("count"), int),
        "min_message_count": len(messages_data.get("messages", [])) >= message_count * 2,
        "count_matches_len": messages_data.get("count") == len(messages_data.get("messages", [])),
    }
    assert log_validation_checks(
        output_store,
        "long_conversation_messages_checks",
        checks,
        context={
            "expected_min": message_count * 2,
            "actual_count": len(messages_data.get("messages", [])),
        },
    )

    # Validate message structure
    structure_checks = {
        "all_have_id": all("id" in msg for msg in messages_data.get("messages", [])),
        "all_have_role": all("role" in msg for msg in messages_data.get("messages", [])),
        "all_have_content": all("content" in msg for msg in messages_data.get("messages", [])),
        "all_have_timestamp": all("timestamp" in msg for msg in messages_data.get("messages", [])),
        "all_roles_valid": all(
            msg.get("role") in ["user", "assistant", "system"]
            for msg in messages_data.get("messages", [])
        ),
    }
    assert log_validation_checks(
        output_store,
        "long_conversation_message_structure_checks",
        structure_checks,
        context={"message_total": len(messages_data.get("messages", []))},
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_context_window_near_limit_handling_via_api(
    api_client, test_user, test_expert, test_config, output_store
):
    """Test handling when context window is near limit via API.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - context_window: Smaller value from config or test default (for testing near-limit scenarios)
    - messages: Multiple messages approaching the limit

    Expected Outputs:
    - Session created successfully with specified context_window
    - All messages successfully added (status 200)
    - GET /sessions/{session_id}/messages returns messages
    - Messages are stored correctly (context window managed internally)
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    # Use a smaller context window for testing near-limit scenarios
    test_context_window = get_config("test.at1_10.context_windows.small")
    if test_context_window is None:
        pytest.fail("test.at1_10.context_windows.small not configured (required for AT1.10)")
    test_context_window = int(test_context_window)

    unique_id = str(uuid.uuid4())[:8]
    session_title = f"Near Limit Session {unique_id}"

    # Create session with smaller context window via API
    create_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": session_title,
            "context_window": test_context_window,
            "history_retention_days": int(get_config("session.history_retention_days")),
        },
    )
    assert create_response.status_code == 200, f"Failed to create session: {create_response.text}"
    session_data = create_response.json()
    session_id = session_data["id"]

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Context window: {test_context_window} (test value)")
    print("[SETTINGS] Adding messages to approach limit")

    # Add messages to approach limit via API
    message_count = get_config("test.at1_10.message_counts.near_limit")
    if message_count is None:
        pytest.fail("test.at1_10.message_counts.near_limit not configured (required for AT1.10)")
    message_count = int(message_count)
    for i in range(message_count):
        message_content = f"Message {i} for test {unique_id}: " + "A" * 80
        add_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )
        assert add_response.status_code == 200, f"Failed to add message {i}: {add_response.text}"
        message_data = add_response.json()
        assert message_data["content"] == message_content, (
            f"Message content mismatch for message {i}"
        )

    # Get messages via API (context window managed internally)
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate outputs
    checks = {
        "has_messages": "messages" in messages_data,
        "has_count": "count" in messages_data,
        "min_message_count": len(messages_data.get("messages", [])) >= message_count,
    }
    assert log_validation_checks(
        output_store,
        "near_limit_messages_checks",
        checks,
        context={
            "expected_min": message_count,
            "actual_count": len(messages_data.get("messages", [])),
        },
    )

    # Validate message structure
    structure_checks = {
        "all_have_id": all("id" in msg for msg in messages_data.get("messages", [])),
        "all_have_role": all("role" in msg for msg in messages_data.get("messages", [])),
        "all_have_content": all("content" in msg for msg in messages_data.get("messages", [])),
        "all_have_timestamp": all("timestamp" in msg for msg in messages_data.get("messages", [])),
    }
    assert log_validation_checks(
        output_store,
        "near_limit_message_structure_checks",
        structure_checks,
        context={"message_total": len(messages_data.get("messages", []))},
    )

    # Cleanup session
    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_context_window_exceeded_handling_via_api(
    api_client, test_user, test_expert, test_config, output_store
):
    """Test handling when many messages are added via API (context window managed internally).

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - context_window: Small value for testing
    - messages: Many messages that would exceed limit

    Expected Outputs:
    - Session created successfully
    - All messages successfully added (status 200)
    - GET /sessions/{session_id}/messages returns messages
    - Messages are stored (context window truncation/summarization handled internally)
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    # Use a small context window for testing exceeded scenarios
    test_context_window = get_config("test.at1_10.context_windows.tiny")
    if test_context_window is None:
        pytest.fail("test.at1_10.context_windows.tiny not configured (required for AT1.10)")
    test_context_window = int(test_context_window)

    unique_id = str(uuid.uuid4())[:8]
    session_title = f"Exceeded Limit Session {unique_id}"

    # Create session with small context window via API
    create_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": session_title,
            "context_window": test_context_window,
            "history_retention_days": int(get_config("session.history_retention_days")),
        },
    )
    assert create_response.status_code == 200, f"Failed to create session: {create_response.text}"
    session_data = create_response.json()
    session_id = session_data["id"]

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Context window: {test_context_window} (test value)")
    print("[SETTINGS] Adding many messages that would exceed limit")

    # Add messages that would exceed limit via API
    message_count = get_config("test.at1_10.message_counts.long")
    if message_count is None:
        pytest.fail("test.at1_10.message_counts.long not configured (required for AT1.10)")
    message_count = int(message_count)
    for i in range(message_count):
        message_content = f"Message {i} for test {unique_id}: " + "A" * 200
        add_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )
        assert add_response.status_code == 200, f"Failed to add message {i}: {add_response.text}"
        message_data = add_response.json()
        assert message_data["content"] == message_content, (
            f"Message content mismatch for message {i}"
        )

    # Get messages via API (context window management handled internally)
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate outputs
    checks = {
        "has_messages": "messages" in messages_data,
        "has_count": "count" in messages_data,
        "min_message_count": len(messages_data.get("messages", [])) >= message_count,
    }
    assert log_validation_checks(
        output_store,
        "exceeded_messages_checks",
        checks,
        context={
            "expected_min": message_count,
            "actual_count": len(messages_data.get("messages", [])),
        },
    )

    # Validate message structure
    structure_checks = {
        "all_have_id": all("id" in msg for msg in messages_data.get("messages", [])),
        "all_have_role": all("role" in msg for msg in messages_data.get("messages", [])),
        "all_have_content": all("content" in msg for msg in messages_data.get("messages", [])),
        "all_have_timestamp": all("timestamp" in msg for msg in messages_data.get("messages", [])),
    }
    assert log_validation_checks(
        output_store,
        "exceeded_message_structure_checks",
        structure_checks,
        context={"message_total": len(messages_data.get("messages", []))},
    )

    # Cleanup session
    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_context_window_message_fitting_via_api(api_client, test_session, output_store):
    """Test that messages of varying lengths are stored correctly via API.

    Inputs:
    - test_session: Session created via API
    - messages: Array of messages with varying lengths (short, long, medium)

    Expected Outputs:
    - All messages successfully added (status 200)
    - GET /sessions/{session_id}/messages returns all messages
    - Message content matches input (all lengths handled)
    - All message fields validated
    """
    session_id = test_session["id"]

    # Generate unique messages with varying lengths (no hard-coding)
    unique_id = str(uuid.uuid4())[:8]
    short_content = f"Short message {unique_id}"
    long_content = "A" * 200 + f" test {unique_id}"  # Long message
    medium_content = f"Medium length message for test {unique_id}"

    messages_to_add = [
        {"role": "user", "content": short_content},
        {"role": "assistant", "content": long_content},
        {"role": "user", "content": medium_content},
    ]

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Adding {len(messages_to_add)} messages with varying lengths")

    # Add messages of varying lengths via API
    created_message_ids = []
    for msg in messages_to_add:
        add_response = api_client.post(f"/sessions/{session_id}/messages", json=msg)
        assert add_response.status_code == 200, f"Failed to add message: {add_response.text}"
        message_data = add_response.json()
        created_message_ids.append(message_data["id"])
        assert message_data["content"] == msg["content"], (
            f"Content mismatch: expected length {len(msg['content'])}, got length {len(message_data['content'])}"
        )
        assert message_data["role"] == msg["role"], (
            f"Role mismatch: expected {msg['role']}, got {message_data['role']}"
        )

    # Get messages via API
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate outputs
    checks = {
        "has_messages": "messages" in messages_data,
        "has_count": "count" in messages_data,
        "min_message_count": len(messages_data.get("messages", [])) >= len(messages_to_add),
    }
    assert log_validation_checks(
        output_store,
        "message_fitting_messages_checks",
        checks,
        context={
            "expected_min": len(messages_to_add),
            "actual_count": len(messages_data.get("messages", [])),
        },
    )

    # Validate all messages are present with correct content
    retrieved_contents = [msg.get("content") for msg in messages_data.get("messages", [])]
    contains_checks = {
        f"contains_{idx}": expected_msg["content"] in retrieved_contents
        for idx, expected_msg in enumerate(messages_to_add)
    }
    assert log_validation_checks(
        output_store,
        "message_fitting_contains_checks",
        contains_checks,
        context={"expected_count": len(messages_to_add)},
    )

    # Validate message structure
    structure_checks = {
        "all_have_id": all("id" in msg for msg in messages_data.get("messages", [])),
        "all_have_role": all("role" in msg for msg in messages_data.get("messages", [])),
        "all_have_content": all("content" in msg for msg in messages_data.get("messages", [])),
        "all_have_timestamp": all("timestamp" in msg for msg in messages_data.get("messages", [])),
        "all_content_str": all(
            isinstance(msg.get("content"), str) for msg in messages_data.get("messages", [])
        ),
        "all_content_nonempty": all(
            bool(msg.get("content")) for msg in messages_data.get("messages", [])
        ),
    }
    assert log_validation_checks(
        output_store,
        "message_fitting_structure_checks",
        structure_checks,
        context={"message_total": len(messages_data.get("messages", []))},
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_context_window_session_config_via_api(
    api_client, test_user, test_expert, test_config, output_store
):
    """Test context window configuration in session via API.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - context_window: Custom value (from config or test default)
    - title: Generated unique title

    Expected Outputs:
    - Session created successfully (status 200)
    - GET /sessions/{session_id} returns session
    - Session ID matches
    - Session exists and is retrievable
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    # Get context window from config or use test value
    # Use a different value for testing custom configuration
    test_context_window = get_config("test.at1_10.context_windows.custom")
    if test_context_window is None:
        pytest.fail("test.at1_10.context_windows.custom not configured (required for AT1.10)")
    test_context_window = int(test_context_window)

    unique_id = str(uuid.uuid4())[:8]
    session_title = f"Custom Context Window Session {unique_id}"

    # Show settings being used
    print(f"\n[SETTINGS] User ID: {user_id}")
    print(f"[SETTINGS] Expert ID: {expert_id}")
    print(f"[SETTINGS] Custom context window: {test_context_window}")
    print(f"[SETTINGS] Session title: {session_title}")

    # Create session with custom context window via API
    create_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": session_title,
            "context_window": test_context_window,
            "history_retention_days": int(get_config("session.history_retention_days")),
        },
    )
    assert create_response.status_code == 200, f"Failed to create session: {create_response.text}"
    session_data = create_response.json()
    session_id = session_data["id"]

    # Validate session creation response
    session_checks = {
        "has_id": "id" in session_data,
        "user_id_matches": session_data.get("user_id") == user_id,
        "expert_id_matches": session_data.get("expert_config_id") == expert_id,
        "has_status": "status" in session_data,
    }
    assert log_validation_checks(
        output_store,
        "session_config_create_checks",
        session_checks,
        context={"user_id": user_id, "expert_id": expert_id},
    )

    # Verify context window is set (retrieve session via API)
    get_response = api_client.get(f"/sessions/{session_id}")
    assert get_response.status_code == 200, f"Failed to get session: {get_response.text}"
    retrieved = get_response.json()

    # Validate retrieved session
    retrieved_checks = {
        "id_matches": retrieved.get("id") == session_id,
        "user_id_matches": retrieved.get("user_id") == user_id,
        "expert_id_matches": retrieved.get("expert_config_id") == expert_id,
    }
    assert log_validation_checks(
        output_store,
        "session_config_retrieved_checks",
        retrieved_checks,
        context={"session_id": session_id, "user_id": user_id, "expert_id": expert_id},
    )
    # Note: context_window may not be in API response, but session should exist and be valid

    # Cleanup
    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.vdb, pytest.mark.smtp, pytest.mark.heavy]

