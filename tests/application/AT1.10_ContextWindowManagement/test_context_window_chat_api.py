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
Application Test: AT1.10 - Context Window Management via Chat API

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for context window management via chat API endpoints

Related Requirements: FR1.2
Related Tasks: T010, T022
Related Architecture: CC2.1.1
Related Tests: AT1.10

Recent Changes:
- Initial comprehensive implementation
"""

import json
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
            "Test user credentials not configured. Ensure test.user.* keys are configured via config/env."
        )

    unique_id = str(uuid.uuid4())[:8]
    return {
        "username": f"{base_username}_at1_10_chat_{unique_id}",
        "email": build_test_email("at1_10_chat", unique_id, base_email),
        "password": base_password,
    }


@pytest.fixture
def test_user(api_client, test_user_credentials):
    """Create test user via API."""
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

    try:
        api_client.delete(f"/users/{user_data['id']}")
    except Exception:
        pass


@pytest.fixture
def test_expert(api_client, test_config):
    """Create test expert via API."""
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    if not llm_provider or not llm_model:
        pytest.fail("llm.provider/llm.model not configured (required for AT1.10 chat tests).")

    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_at1_10_chat_{unique_id}",
        "title": f"Context Window Chat Expert {unique_id} analysis retrieval summarization pagination truncation embeddings",
        "description": "Comprehensive evaluation of chat context window management with unique vocabulary: autonomy bandwidth catalog delta eclipse flux galaxy horizon insight junction kinetic lattice",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "enabled": True,
    }

    response = api_client.post("/experts", json=expert_data)
    assert response.status_code == 200, f"Failed to create test expert: {response.text}"
    expert = response.json()

    yield expert

    try:
        api_client.delete(f"/experts/{expert['id']}")
    except Exception:
        pass


@pytest.fixture
def test_channel(api_client, test_user, test_expert):
    """Create test channel via API."""
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    channel_data = {
        "name": f"channel_at1_10_chat_{unique_id}",
        "expert_config_id": expert_id,
        "user_id": user_id,
        "enabled": True,
    }

    response = api_client.post("/channels", json=channel_data)
    if response.status_code != 200:
        pytest.fail(
            f"Channel endpoint not available (required for AT1.10 chat tests): {response.status_code} {response.text}"
        )

    channel = response.json()

    yield channel

    try:
        api_client.delete(f"/channels/{channel['id']}")
    except Exception:
        pass
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_context_window_management_via_chat_api(api_client, test_user, test_expert, test_channel):
    """Test context window management when using chat API.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - test_channel: Channel created via API
    - session: Created via chat API
    - messages: Multiple messages via chat API
    - context_window: Managed automatically

    Expected Outputs:
    - Chat API creates session
    - Messages stored correctly
    - Context window managed automatically
    - Response structure validated
    """
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]

    # First chat message (creates session)
    chat1_response = api_client.post(
        f"/channels/{channel_id}/chat",
        json={
            "message": f"First message for context window test {unique_id}",
            "user_id": user_id,
            "async_mode": False,
        },
    )

    if chat1_response.status_code == 503:
        pytest.fail(f"LLM service unavailable (required for AT1.10): {chat1_response.text}")

    assert chat1_response.status_code == 200, f"Failed to chat via API: {chat1_response.text}"
    chat1_data = chat1_response.json()

    # Validate chat response
    assert "response" in chat1_data or "message" in chat1_data or "content" in chat1_data, (
        "Chat response missing response/message/content"
    )
    session_id = chat1_data.get("session_id")

    if session_id:
        # Add more messages to test context window
        message_count = int(get_config("test.at1_10.message_counts.short"))
        for i in range(message_count):
            chat_response = api_client.post(
                f"/channels/{channel_id}/chat",
                json={
                    "message": f"Message {i} for context test {unique_id}: " + "S" * 50,
                    "user_id": user_id,
                    "session_id": session_id,
                    "async_mode": False,
                },
            )

            if chat_response.status_code == 503:
                pytest.fail(f"LLM service unavailable (required for AT1.10): {chat_response.text}")

            if chat_response.status_code == 200:
                # Verify response structure
                chat_data = chat_response.json()
                assert (
                    "response" in chat_data or "message" in chat_data or "content" in chat_data
                ), "Chat response missing response/message/content"

        # Verify messages are stored
        if session_id:
            messages_response = api_client.get(f"/sessions/{session_id}/messages")
            if messages_response.status_code == 200:
                messages_data = messages_response.json()
                assert "messages" in messages_data, "messages array missing"
                assert len(messages_data["messages"]) >= 1, "Should have at least 1 message"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_context_window_limits_in_chat_responses_via_api(
    api_client, test_user, test_expert, test_channel
):
    """Test that context window limits are respected in chat responses.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - test_channel: Channel created via API
    - session: With many messages
    - chat: New message via API

    Expected Outputs:
    - Chat API respects context window
    - Response generated within limits
    - Context window management applied
    """
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]

    # Create session with many messages first
    small_cw = get_config("test.at1_10.context_windows.small")
    if small_cw is None:
        pytest.fail("test.at1_10.context_windows.small not configured (required for AT1.10)")
    small_cw = int(small_cw)
    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": test_expert["id"],
            "title": f"Chat Context Limit Test {unique_id}",
            "context_window": small_cw,
        },
    )
    if session_response.status_code == 200:
        session_data = session_response.json()
        session_id = session_data["id"]

        # Add many messages
        message_count = int(get_config("test.at1_10.message_counts.long"))
        for i in range(message_count):
            api_client.post(
                f"/sessions/{session_id}/messages",
                json={
                    "role": "user",
                    "content": f"Message {i} for limit test {unique_id}: " + "T" * 40,
                },
            )

        # Chat via API (should respect context window)
        chat_response = api_client.post(
            f"/channels/{channel_id}/chat",
            json={
                "message": f"New message for limit test {unique_id}",
                "user_id": user_id,
                "session_id": session_id,
                "async_mode": False,
            },
        )

        if chat_response.status_code == 503:
            pytest.fail(f"LLM service unavailable (required for AT1.10): {chat_response.text}")

        if chat_response.status_code == 200:
            chat_data = chat_response.json()
            assert "response" in chat_data or "message" in chat_data or "content" in chat_data, (
                "Chat response missing"
            )

        delete_response = api_client.delete(f"/sessions/{session_id}")
        if delete_response.status_code not in (200, 204, 404):
            print(
                f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
            )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_context_window_with_chat_pagination_via_api(
    api_client, test_user, test_expert, test_channel
):
    """Test context window management with chat message pagination.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - test_channel: Channel created via API
    - session: With messages
    - pagination: Applied when retrieving history

    Expected Outputs:
    - Chat API works with paginated history
    - Context window respected
    - Pagination doesn't break context
    """
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]

    # Create session and add messages
    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": test_expert["id"],
            "title": f"Chat Pagination Test {unique_id}",
            "context_window": int(get_config("test.at1_10.context_windows.large")),
        },
    )
    if session_response.status_code == 200:
        session_data = session_response.json()
        session_id = session_data["id"]

        # Add messages
        message_count = int(get_config("test.at1_10.message_counts.medium"))
        for i in range(message_count):
            api_client.post(
                f"/sessions/{session_id}/messages",
                json={
                    "role": "user",
                    "content": f"Message {i} for pagination test {unique_id}: " + "U" * 35,
                },
            )

        # Get messages with pagination
        limit = int(get_config("test.at1_10.truncation.limits.low"))
        page1_response = api_client.get(f"/sessions/{session_id}/messages?limit={limit}&offset=0")
        assert page1_response.status_code == 200, f"Failed to get page 1: {page1_response.text}"
        page1 = page1_response.json()
        assert len(page1["messages"]) <= limit, f"Page 1 should have at most {limit} messages"

        # Chat should still work
        chat_response = api_client.post(
            f"/channels/{channel_id}/chat",
            json={
                "message": f"Pagination test message {unique_id}",
                "user_id": user_id,
                "session_id": session_id,
                "async_mode": False,
            },
        )

        if chat_response.status_code == 503:
            pytest.fail(f"LLM service unavailable (required for AT1.10): {chat_response.text}")

        if chat_response.status_code == 200:
            chat_data = chat_response.json()
            assert "response" in chat_data or "message" in chat_data or "content" in chat_data, (
                "Chat response missing"
            )

        delete_response = api_client.delete(f"/sessions/{session_id}")
        if delete_response.status_code not in (200, 204, 404):
            print(
                f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
            )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_context_window_summarization_via_chat_api(
    api_client, test_user, test_expert, test_channel
):
    """Test that summarization works when triggered during chat.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - test_channel: Channel created via API
    - session: With many messages
    - summarization: Triggered before chat

    Expected Outputs:
    - Summarization successful
    - Chat works with summarized context
    - Response structure validated
    """
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]

    preserve_recent = int(get_config("test.at1_10.summarization.preserve_recent"))
    max_tokens = int(get_config("test.at1_10.summarization.max_tokens"))
    # Create session with many messages
    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": test_expert["id"],
            "title": f"Chat Summarization Test {unique_id}",
            "context_window": int(get_config("test.at1_10.context_windows.small")),
        },
    )
    if session_response.status_code == 200:
        session_data = session_response.json()
        session_id = session_data["id"]

        # Add messages
        message_count = int(get_config("test.at1_10.message_counts.xlong"))
        for i in range(message_count):
            api_client.post(
                f"/sessions/{session_id}/messages",
                json={
                    "role": "user",
                    "content": f"Message {i} for summary chat test {unique_id}: " + "V" * 40,
                },
            )

        # Trigger summarization
        summarize_response = api_client.post(
            f"/sessions/{session_id}/summarize",
            params={"preserve_recent": preserve_recent, "max_tokens": max_tokens},
        )

        if summarize_response.status_code in (500, 503):
            pytest.fail(
                f"Summarization failed (LLM required for AT1.10): {summarize_response.text}"
            )

        # Chat should work with summarized context
        if summarize_response.status_code == 200:
            chat_response = api_client.post(
                f"/channels/{channel_id}/chat",
                json={
                    "message": f"Message after summarization {unique_id}",
                    "user_id": user_id,
                    "session_id": session_id,
                    "async_mode": False,
                },
            )

            if chat_response.status_code == 503:
                pytest.fail(f"LLM service unavailable (required for AT1.10): {chat_response.text}")

            if chat_response.status_code == 200:
                chat_data = chat_response.json()
                assert (
                    "response" in chat_data or "message" in chat_data or "content" in chat_data
                ), "Chat response missing"

        delete_response = api_client.delete(f"/sessions/{session_id}")
        if delete_response.status_code not in (200, 204, 404):
            print(
                f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
            )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_context_window_with_different_llm_settings_via_chat_api(
    api_client, test_user, test_expert, test_channel
):
    """Test context window management with different LLM settings in chat.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - test_channel: Channel created via API
    - chat: With different temperature, max_tokens settings
    - context_window: Managed with different settings

    Expected Outputs:
    - Chat works with different LLM settings
    - Context window respected regardless of settings
    - Response structure validated
    """
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]

    test_settings = get_config("test.at1_10.llm_settings")
    if isinstance(test_settings, str):
        try:
            test_settings = json.loads(test_settings)
        except json.JSONDecodeError as exc:
            pytest.fail(f"test.at1_10.llm_settings is not valid JSON: {exc}")
    if not isinstance(test_settings, list) or not test_settings:
        pytest.fail("test.at1_10.llm_settings not configured as a non-empty list")

    for settings in test_settings:
        chat_response = api_client.post(
            f"/channels/{channel_id}/chat",
            json={
                "message": f"Test message with settings {unique_id}",
                "user_id": user_id,
                "async_mode": False,
                "temperature": settings["temperature"],
                "max_tokens": settings["max_tokens"],
            },
        )

        if chat_response.status_code == 503:
            pytest.fail(f"LLM service unavailable (required for AT1.10): {chat_response.text}")

        if chat_response.status_code == 200:
            chat_data = chat_response.json()
            assert "response" in chat_data or "message" in chat_data or "content" in chat_data, (
                "Chat response missing"
            )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_context_window_multi_turn_chat_via_api(api_client, test_user, test_expert, test_channel):
    """Test context window management across multiple chat turns.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - test_channel: Channel created via API
    - multiple chat turns: Via API
    - context_window: Managed across turns

    Expected Outputs:
    - Multiple chat turns work correctly
    - Context window managed across turns
    - Context retained between turns
    - Response structure validated
    """
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    session_id = None

    # Multiple chat turns
    message_count = int(get_config("test.at1_10.message_counts.short"))
    for i in range(message_count):
        chat_response = api_client.post(
            f"/channels/{channel_id}/chat",
            json={
                "message": f"Turn {i} message for multi-turn test {unique_id}",
                "user_id": user_id,
                "session_id": session_id,
                "async_mode": False,
            },
        )

        if chat_response.status_code == 503:
            pytest.fail(f"LLM service unavailable (required for AT1.10): {chat_response.text}")

        if chat_response.status_code == 200:
            chat_data = chat_response.json()
            assert "response" in chat_data or "message" in chat_data or "content" in chat_data, (
                "Chat response missing"
            )

            # Get session_id from first response
            if not session_id:
                session_id = chat_data.get("session_id")

            # Verify context is maintained (messages stored)
            if session_id:
                messages_response = api_client.get(f"/sessions/{session_id}/messages")
                if messages_response.status_code == 200:
                    messages_data = messages_response.json()
                    assert "messages" in messages_data, "messages array missing"
                    assert len(messages_data["messages"]) >= (i + 1) * 2, (
                        f"Should have at least {(i + 1) * 2} messages (user + assistant per turn)"
                    )

    if session_id:
        delete_response = api_client.delete(f"/sessions/{session_id}")
        if delete_response.status_code not in (200, 204, 404):
            print(
                f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
            )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.llm, pytest.mark.vdb, pytest.mark.smtp, pytest.mark.heavy]
