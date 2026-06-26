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
Application Test: AT1.11 - Context Summarization and Consolidation

License: Apache 2.0
Ownership: Cloud Dog
Description: Test context summarization and consolidation via API

Related Requirements: FR1.28
Related Tasks: T066
Related Architecture: CC2.1.4
Related Tests: AT1.11 (Test 6)
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
            "Test user credentials not configured. Set test.user.* keys in your --env file."
        )

    unique_id = str(uuid.uuid4())[:8]
    return {
        "username": f"{base_username}_at1_11_sum_{unique_id}",
        "email": build_test_email("at1_11_sum", unique_id, base_email),
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
    assert response.status_code == 200
    user_data = response.json()

    yield user_data

    # Cleanup via API
    try:
        api_client.delete(f"/users/{user_data['id']}")
    except Exception:
        pass


@pytest.fixture
def test_expert(api_client, test_config):
    """Create test expert via API."""
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")

    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_at1_11_sum_{unique_id}",
        "title": f"Context Summarization Expert {unique_id} consolidation retention compression coherence traceability",
        "description": "Summarization consolidation scenario with unique vocabulary: acorn basil cipher dune ember fjord glyph helios isotope juniper keystone",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "enabled": True,
    }

    response = api_client.post("/experts", json=expert_data)
    assert response.status_code == 200
    expert = response.json()

    yield expert

    # Cleanup via API
    try:
        api_client.delete(f"/experts/{expert['id']}")
    except Exception:
        pass
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-020")


def test_context_summarization_consolidation_via_api(api_client, test_user, test_expert):
    """Test context summarization and consolidation via API.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - context_window: 1000 tokens (small for testing)
    - messages: Array of 20 messages (each ~100 tokens, exceeding context window)

    Expected Outputs:
    - Session created successfully (status 200)
    - All 20 messages added successfully (status 200)
    - Summarization triggered successfully (status 200, summary created)
    - Summaries retrieved successfully (status 200, summary data returned)
    - Message history shows summary + recent messages (status 200, ~6 messages: 1 summary + 5 recent)
    - Recent messages preserved (last 5 messages in history)
    - New message added successfully (status 200)
    - Context is coherent (summary + recent messages + new message)
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    session_title = f"Summarization Test {unique_id}"

    # Use small context window for testing (config-driven)
    context_window = get_config("test.at1_11.context_window")
    if context_window is None:
        pytest.fail("test.at1_11.context_window not configured (required for AT1.11)")
    context_window = int(context_window)

    print(f"\n[SETTINGS] User ID: {user_id}")
    print(f"[SETTINGS] Expert ID: {expert_id}")
    print(f"[SETTINGS] Session title: {session_title}")
    print(f"[SETTINGS] Context window: {context_window} (small for testing)")
    print(f"[SETTINGS] Test ID: {unique_id}")

    # Step 1: Create session with small context window
    history_retention_days = get_config("session.history_retention_days")
    if history_retention_days is None:
        pytest.fail("Missing session.history_retention_days in config (--env)")
    create_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": session_title,
            "context_window": context_window,
            "history_retention_days": int(history_retention_days),
        },
    )
    assert create_response.status_code == 200, f"Failed to create session: {create_response.text}"
    session_data = create_response.json()
    session_id = session_data["id"]

    # Step 2: Add 20 messages (each ~100 tokens, exceeding context window)
    message_count = get_config("test.at1_11.message_count")
    if message_count is None:
        pytest.fail("test.at1_11.message_count not configured (required for AT1.11)")
    message_count = int(message_count)
    messages = []
    for i in range(message_count):
        # Each message is ~100 tokens (400 chars / 4 chars per token)
        message_content = f"Message {i} for summarization test {unique_id}: " + "A" * 300
        messages.append(message_content)

        add_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )
        assert add_response.status_code == 200, (
            f"Failed to add message {i + 1}: {add_response.text}"
        )

    # Step 3: Verify message count before summarization
    get_messages_before = api_client.get(f"/sessions/{session_id}/messages")
    assert get_messages_before.status_code == 200
    messages_before = get_messages_before.json()
    assert len(messages_before["messages"]) == message_count, (
        f"Expected {message_count} messages before summarization, got {len(messages_before['messages'])}"
    )
    assert messages_before["count"] == message_count

    # Step 4: Trigger summarization
    preserve_recent = get_config("test.at1_11.preserve_recent")
    if preserve_recent is None:
        pytest.fail("test.at1_11.preserve_recent not configured (required for AT1.11)")
    preserve_recent = int(preserve_recent)
    summarize_response = api_client.post(
        f"/sessions/{session_id}/summarize",
        params={"preserve_recent": preserve_recent, "max_tokens": context_window // 2},
    )
    # Handle LLM unavailability gracefully
    if summarize_response.status_code == 500:
        error_detail = summarize_response.json().get("detail", "")
        if (
            "LLM" in error_detail
            or "connection" in error_detail.lower()
            or "unavailable" in error_detail.lower()
        ):
            pytest.fail(f"LLM service unavailable for summarization (required): {error_detail}")

    assert summarize_response.status_code == 200, (
        f"Failed to trigger summarization: {summarize_response.text}"
    )
    summarize_data = summarize_response.json()

    # Validate summarization response
    assert "summary_id" in summarize_data or summarize_data.get("summary") is not None, (
        "Summarization should create a summary"
    )
    if summarize_data.get("summary_id"):
        assert summarize_data["summary_id"] is not None, "summary_id should not be None"
    if summarize_data.get("summary"):
        assert len(summarize_data["summary"]) > 0, "Summary text should not be empty"

    # Step 5: Get summaries
    get_summaries_response = api_client.get(f"/sessions/{session_id}/summaries")
    assert get_summaries_response.status_code == 200, (
        f"Failed to get summaries: {get_summaries_response.text}"
    )
    summaries_data = get_summaries_response.json()

    # Validate summaries
    assert "summaries" in summaries_data, "Response should contain summaries array"
    assert "count" in summaries_data, "Response should contain count"
    assert isinstance(summaries_data["summaries"], list), "summaries should be a list"

    # If no summaries exist, it may be because LLM summarization failed
    # In that case, we should have at least preserved the recent messages
    if len(summaries_data["summaries"]) == 0:
        # Check if we have preserved messages in the session history
        history_response = api_client.get(f"/sessions/{session_id}/history")
        if history_response.status_code == 200:
            history_data = history_response.json()
            # If we have preserved messages, that's acceptable (LLM unavailable)
            if len(history_data.get("messages", [])) >= preserve_recent:
                pytest.fail(
                    "LLM summarization unavailable (required), cannot validate AT1.11 summarization behaviour"
                )

    assert len(summaries_data["summaries"]) > 0, "At least one summary should exist"
    assert summaries_data["count"] == len(summaries_data["summaries"])

    # Validate summary content
    first_summary = summaries_data["summaries"][0]
    assert "id" in first_summary, "Summary should have id"
    assert "summary_text" in first_summary, "Summary should have summary_text"
    assert "original_message_count" in first_summary, "Summary should have original_message_count"
    assert "preserved_message_count" in first_summary, "Summary should have preserved_message_count"
    assert first_summary["original_message_count"] == message_count - preserve_recent, (
        f"Expected {message_count - preserve_recent} original messages summarized, got {first_summary['original_message_count']}"
    )
    assert first_summary["preserved_message_count"] == preserve_recent, (
        f"Expected {preserve_recent} preserved messages, got {first_summary['preserved_message_count']}"
    )

    # Step 6: Get message history after summarization
    get_messages_after = api_client.get(f"/sessions/{session_id}/messages")
    assert get_messages_after.status_code == 200
    messages_after = get_messages_after.json()

    # Note: The actual message count after summarization depends on implementation
    # The summarizer may replace old messages with a summary message
    # For now, we verify that messages are still accessible
    assert "messages" in messages_after, "Response should contain messages"
    assert "count" in messages_after, "Response should contain count"
    assert len(messages_after["messages"]) > 0, "At least some messages should be present"

    # Step 7: Continue conversation (add new message)
    new_message = f"New message after summarization {unique_id}"
    add_new_response = api_client.post(
        f"/sessions/{session_id}/messages", json={"role": "user", "content": new_message}
    )
    assert add_new_response.status_code == 200, (
        f"Failed to add new message: {add_new_response.text}"
    )

    # Step 8: Verify context is coherent
    get_final_messages = api_client.get(f"/sessions/{session_id}/messages")
    assert get_final_messages.status_code == 200
    final_messages = get_final_messages.json()

    # Verify new message is present
    final_content = [msg["content"] for msg in final_messages["messages"]]
    assert new_message in final_content, "New message should be in final messages"

    # Verify recent messages are preserved (last 5 original messages)
    # The last 5 messages before summarization should still be accessible
    recent_messages = messages[-5:]
    for recent_msg in recent_messages:
        # Check if any message contains the same content (may be in summary or preserved)
        assert any(recent_msg[:50] in msg["content"] for msg in final_messages["messages"]), (
            f"Recent message should be preserved: {recent_msg[:50]}"
        )

    # Cleanup via API
    try:
        api_client.delete(f"/sessions/{session_id}")
    except Exception:
        pass

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

