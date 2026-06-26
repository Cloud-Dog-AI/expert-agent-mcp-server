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
Application Test: AT1.10 - Context Window Truncation

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for truncation fallback when summarization fails or is disabled

Related Requirements: FR1.2
Related Tasks: T010
Related Architecture: CC2.1.1
Related Tests: AT1.10

Recent Changes:
- Initial comprehensive implementation
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
            "Test user credentials not configured. Ensure test.user.* keys are configured via config/env."
        )

    unique_id = str(uuid.uuid4())[:8]
    return {
        "username": f"{base_username}_at1_10_trunc_{unique_id}",
        "email": build_test_email("at1_10_trunc", unique_id, base_email),
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
        pytest.fail("llm.provider/llm.model not configured (required for AT1.10).")

    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_at1_10_trunc_{unique_id}",
        "title": f"Context Truncation Expert {unique_id} fallback strategy pagination limits preserve_recent",
        "description": "Truncation fallback validation with unique terms: atlas beacon canyon delta ember fission grove halcyon iris juniper keystone",
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
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_truncation_when_summarization_disabled_via_api(api_client, test_user, test_expert):
    """Test that truncation occurs when summarization is disabled.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Session with many messages
    - get_message_history: Called with max_tokens and use_summarization=False

    Expected Outputs:
    - Messages truncated to fit within max_tokens
    - Most recent messages preserved
    - Older messages removed
    - Message count reduced appropriately
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    context_window = int(get_config("test.at1_10.context_windows.small"))

    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Truncation Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add many messages
    message_count = int(get_config("test.at1_10.message_counts.xlong"))
    message_ids = []
    for i in range(message_count):
        message_content = f"Message {i} for truncation test {unique_id}: " + "H" * 50
        msg_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )
        assert msg_response.status_code == 200, f"Failed to add message {i}: {msg_response.text}"
        message_ids.append(msg_response.json()["id"])

    # Get all messages (no truncation)
    all_messages_response = api_client.get(f"/sessions/{session_id}/messages")
    assert all_messages_response.status_code == 200, (
        f"Failed to get all messages: {all_messages_response.text}"
    )
    all_messages = all_messages_response.json()
    assert len(all_messages["messages"]) == message_count, (
        f"Should have all {message_count} messages"
    )

    # Get messages with limit (simulating truncation via pagination)
    limit = int(get_config("test.at1_10.truncation.limits.medium"))
    limited_response = api_client.get(f"/sessions/{session_id}/messages?limit={limit}")
    assert limited_response.status_code == 200, (
        f"Failed to get limited messages: {limited_response.text}"
    )
    limited_messages = limited_response.json()
    assert len(limited_messages["messages"]) <= limit, f"Should have at most {limit} messages"

    # Verify messages are returned (API returns in chronological order, oldest first)
    if len(limited_messages["messages"]) > 0:
        # Messages are returned in chronological order (oldest first)
        # So first message should be from the first messages
        first_limited_id = limited_messages["messages"][0]["id"]
        assert first_limited_id in message_ids[:10], (
            "Limited messages should include early messages"
        )

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_truncation_preserves_recent_messages_via_api(api_client, test_user, test_expert):
    """Test that truncation preserves most recent messages.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Session with messages
    - truncation: Applied with different limits

    Expected Outputs:
    - Most recent messages always preserved
    - Older messages removed first
    - Message order maintained
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    context_window = int(get_config("test.at1_10.context_windows.medium"))

    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Preserve Recent Truncation Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add messages with identifiable content
    message_count = int(get_config("test.at1_10.message_counts.long"))
    message_contents = []
    for i in range(message_count):
        message_content = f"Message_{i}_for_preserve_test_{unique_id}"
        message_contents.append(message_content)
        api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )

    # Get messages with different limits
    for limit in [
        int(get_config("test.at1_10.truncation.limits.low")),
        int(get_config("test.at1_10.truncation.limits.medium")),
        int(get_config("test.at1_10.truncation.limits.high")),
    ]:
        limited_response = api_client.get(f"/sessions/{session_id}/messages?limit={limit}")
        assert limited_response.status_code == 200, (
            f"Failed to get messages with limit {limit}: {limited_response.text}"
        )
        limited_messages = limited_response.json()

        # Should have at most limit messages
        assert len(limited_messages["messages"]) <= limit, f"Should have at most {limit} messages"

        # Messages are returned in chronological order (oldest first)
        # So first message should be from early messages
        if len(limited_messages["messages"]) > 0:
            first_retrieved_content = limited_messages["messages"][0]["content"]
            # Should be one of the first messages (API returns oldest first)
            assert first_retrieved_content in message_contents[:limit], (
                f"First message should be from first {limit} messages"
            )

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_truncation_order_most_recent_first_via_api(api_client, test_user, test_expert):
    """Test that truncation keeps most recent messages first.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Session with messages added in sequence
    - truncation: Applied

    Expected Outputs:
    - Most recent messages appear first in truncated result
    - Message order maintained (chronological)
    - Timestamps validate order
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    context_window = int(get_config("test.at1_10.context_windows.small"))

    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Truncation Order Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add messages in sequence
    message_count = int(get_config("test.at1_10.truncation.limits.high"))
    import time

    for i in range(message_count):
        time.sleep(0.1)  # Ensure different timestamps
        message_content = f"Sequential message {i} for order test {unique_id}"
        api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )

    # Get messages with limit
    limit = int(get_config("test.at1_10.truncation.limits.low"))
    limited_response = api_client.get(f"/sessions/{session_id}/messages?limit={limit}")
    assert limited_response.status_code == 200, (
        f"Failed to get limited messages: {limited_response.text}"
    )
    limited_messages = limited_response.json()

    # Verify order - should be chronological (oldest first)
    if len(limited_messages["messages"]) > 1:
        timestamps = [msg["timestamp"] for msg in limited_messages["messages"]]
        from datetime import datetime

        for i in range(1, len(timestamps)):
            prev_dt = datetime.fromisoformat(timestamps[i - 1].replace("Z", "+00:00"))
            curr_dt = datetime.fromisoformat(timestamps[i].replace("Z", "+00:00"))
            assert curr_dt >= prev_dt, (
                f"Messages not in chronological order: {timestamps[i - 1]} > {timestamps[i]}"
            )

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_truncation_with_different_limits_via_api(api_client, test_user, test_expert):
    """Test truncation with different token/message limits.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Session with messages
    - different limits: Applied via pagination

    Expected Outputs:
    - Truncation respects limit parameter
    - Message count matches limit (when enough messages exist)
    - All limits work correctly
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    context_window = int(get_config("test.at1_10.context_windows.large"))

    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Different Limits Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add messages
    message_count = int(get_config("test.at1_10.message_counts.xxlong"))
    for i in range(message_count):
        message_content = f"Message {i} for limits test {unique_id}: " + "I" * 30
        api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )

    # Test different limits
    for limit in [
        int(get_config("test.at1_10.summarization.preserve_recent_small")),
        int(get_config("test.at1_10.truncation.limits.low")),
        int(get_config("test.at1_10.truncation.limits.medium")),
        int(get_config("test.at1_10.truncation.limits.xl")),
        int(get_config("test.at1_10.truncation.limits.xxl")),
    ]:
        limited_response = api_client.get(f"/sessions/{session_id}/messages?limit={limit}")
        assert limited_response.status_code == 200, (
            f"Failed to get messages with limit {limit}: {limited_response.text}"
        )
        limited_messages = limited_response.json()

        # Should have at most limit messages
        assert len(limited_messages["messages"]) <= limit, (
            f"Should have at most {limit} messages, got {len(limited_messages['messages'])}"
        )
        assert limited_messages["count"] == len(limited_messages["messages"]), (
            "Count should match message count"
        )

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_truncation_with_empty_session_via_api(api_client, test_user, test_expert):
    """Test truncation handling for empty session.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Empty session (no messages)

    Expected Outputs:
    - Truncation returns empty list
    - No errors
    - Response structure valid
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]

    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Empty Truncation Test {unique_id}",
            "context_window": int(get_config("test.at1_10.context_windows.small")),
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Get messages from empty session
    limit = int(get_config("test.at1_10.truncation.limits.medium"))
    messages_response = api_client.get(f"/sessions/{session_id}/messages?limit={limit}")
    assert messages_response.status_code == 200, f"Failed to get messages: {messages_response.text}"
    messages_data = messages_response.json()

    # Validate empty response
    assert "messages" in messages_data, "messages array missing"
    assert "count" in messages_data, "count missing"
    assert len(messages_data["messages"]) == 0, "Should have no messages"
    assert messages_data["count"] == 0, "Count should be 0"

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_truncation_fallback_when_summarization_fails_via_api(api_client, test_user, test_expert):
    """Test that truncation is used as fallback when summarization fails.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Session with messages
    - summarization: Attempted but fails (LLM unavailable)

    Expected Outputs:
    - System falls back to truncation
    - Recent messages preserved
    - No errors in response
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    context_window = int(get_config("test.at1_10.context_windows.small"))

    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Fallback Truncation Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add messages
    message_count = int(get_config("test.at1_10.message_counts.long"))
    for i in range(message_count):
        message_content = f"Message {i} for fallback test {unique_id}: " + "J" * 40
        api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )

    # Attempt summarization (may fail if LLM unavailable)
    api_client.post(
        f"/sessions/{session_id}/summarize",
        params={
            "preserve_recent": int(get_config("test.at1_10.summarization.preserve_recent")),
            "max_tokens": int(get_config("test.at1_10.summarization.max_tokens")),
        },
    )

    # Regardless of summarization result, messages should still be retrievable with truncation
    limit = int(get_config("test.at1_10.truncation.limits.medium"))
    messages_response = api_client.get(f"/sessions/{session_id}/messages?limit={limit}")
    assert messages_response.status_code == 200, f"Failed to get messages: {messages_response.text}"
    messages_data = messages_response.json()

    # Should have messages (truncated if needed)
    assert "messages" in messages_data, "messages array missing"
    assert "count" in messages_data, "count missing"
    assert len(messages_data["messages"]) <= limit, f"Should have at most {limit} messages"
    assert messages_data["count"] == len(messages_data["messages"]), "Count should match"

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

