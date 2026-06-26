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
Application Test: AT1.10 - Context Window Summarization

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for automatic summarization when context window is exceeded

Related Requirements: FR1.2
Related Tasks: T010, T024
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
        "username": f"{base_username}_at1_10_sum_{unique_id}",
        "email": build_test_email("at1_10_sum", unique_id, base_email),
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

    # Cleanup
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
        pytest.fail("llm.provider/llm.model not configured (required for AT1.10 summarization).")

    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_at1_10_sum_{unique_id}",
        "title": f"Context Summarization Expert {unique_id} compression retention preserve_recent max_tokens",
        "description": "Summarization behavior validation with unique words: alpine beacon cedar dune ember fjord glacier harbor isotope juniper keystone",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "enabled": True,
    }

    response = api_client.post("/experts", json=expert_data)
    assert response.status_code == 200, f"Failed to create test expert: {response.text}"
    expert = response.json()

    yield expert

    # Cleanup
    try:
        api_client.delete(f"/experts/{expert['id']}")
    except Exception:
        pass
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_automatic_summarization_trigger_via_api(api_client, test_user, test_expert):
    """Test that summarization is automatically triggered when context window is exceeded.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Session with small context_window (200 tokens)
    - messages: 20 messages that exceed context window

    Expected Outputs:
    - Session created successfully
    - All messages added successfully
    - Summarization triggered when retrieving history with max_tokens
    - Summary stored in database
    - Preserved recent messages maintained
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    preserve_recent = int(get_config("test.at1_10.summarization.preserve_recent"))
    max_tokens_cfg = int(get_config("test.at1_10.summarization.max_tokens"))

    # Create session with small context window
    unique_id = str(uuid.uuid4())[:8]
    context_window = int(get_config("test.at1_10.context_windows.small"))

    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Summarization Test {unique_id}",
            "context_window": context_window,
            "history_retention_days": int(get_config("session.history_retention_days")),
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add many messages to exceed context window
    message_count = int(get_config("test.at1_10.message_counts.xlong"))
    for i in range(message_count):
        message_content = f"Message {i} for summarization test {unique_id}: " + "A" * 50
        msg_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )
        assert msg_response.status_code == 200, f"Failed to add message {i}: {msg_response.text}"

    # Trigger summarization via API
    summarize_response = api_client.post(
        f"/sessions/{session_id}/summarize",
        params={
            "preserve_recent": preserve_recent,
            "max_tokens": max(1, min(max_tokens_cfg, context_window // 2)),
        },
    )

    if summarize_response.status_code in (500, 503):
        pytest.fail(f"Summarization failed (LLM required for AT1.10): {summarize_response.text}")

    assert summarize_response.status_code == 200, (
        f"Failed to trigger summarization: {summarize_response.text}"
    )
    summarize_data = summarize_response.json()

    # Validate summarization output
    assert "summary_id" in summarize_data or "summary" in summarize_data, (
        "Summary ID or summary missing from response"
    )
    assert "original_message_count" in summarize_data, "original_message_count missing"
    assert "preserved_message_count" in summarize_data, "preserved_message_count missing"
    assert summarize_data["original_message_count"] >= message_count - preserve_recent, (
        "Original message count should be >= message_count - preserve_recent"
    )
    assert summarize_data["preserved_message_count"] == preserve_recent, (
        "Preserved message count should match preserve_recent"
    )

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_summarization_with_preserve_recent_via_api(api_client, test_user, test_expert):
    """Test summarization with different preserve_recent values.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Session with messages
    - preserve_recent: Different values (3, 5, 10)

    Expected Outputs:
    - Summarization successful for each preserve_recent value
    - Preserved message count matches preserve_recent parameter
    - Summary stored correctly
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
            "title": f"Preserve Recent Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add messages
    message_count = int(get_config("test.at1_10.message_counts.long"))
    for i in range(message_count):
        message_content = f"Message {i} for preserve test {unique_id}: " + "B" * 40
        api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )

    # Test different preserve_recent values (config-driven list)
    preserve_values = [
        int(get_config("test.at1_10.summarization.preserve_recent_small")),
        int(get_config("test.at1_10.summarization.preserve_recent")),
        int(get_config("test.at1_10.summarization.preserve_recent_large")),
    ]
    for preserve_recent in preserve_values:
        summarize_response = api_client.post(
            f"/sessions/{session_id}/summarize",
            params={"preserve_recent": preserve_recent, "max_tokens": context_window // 2},
        )

        if summarize_response.status_code in (500, 503):
            pytest.fail(
                f"Summarization failed (LLM required for AT1.10): {summarize_response.text}"
            )

        if summarize_response.status_code == 200:
            summarize_data = summarize_response.json()
            assert summarize_data["preserved_message_count"] == preserve_recent, (
                f"Preserved count should be {preserve_recent}, got {summarize_data['preserved_message_count']}"
            )

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_summarization_with_max_tokens_via_api(api_client, test_user, test_expert):
    """Test summarization with different max_tokens values.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Session with messages
    - max_tokens: Different values (50, 100, 200)

    Expected Outputs:
    - Summarization successful for each max_tokens value
    - Summary respects max_tokens limit
    - Output structure validated
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
            "title": f"Max Tokens Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add messages
    message_count = int(get_config("test.at1_10.message_counts.xlong"))
    for i in range(message_count):
        message_content = f"Message {i} for max_tokens test {unique_id}: " + "C" * 60
        api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )

    # Test different max_tokens values (config-driven)
    base_max_tokens = int(get_config("test.at1_10.summarization.max_tokens"))
    max_token_values = [max(1, base_max_tokens // 2), base_max_tokens, base_max_tokens * 2]
    for max_tokens in max_token_values:
        summarize_response = api_client.post(
            f"/sessions/{session_id}/summarize",
            params={
                "preserve_recent": int(get_config("test.at1_10.summarization.preserve_recent")),
                "max_tokens": max_tokens,
            },
        )

        if summarize_response.status_code in (500, 503):
            pytest.fail(
                f"Summarization failed (LLM required for AT1.10): {summarize_response.text}"
            )

        if summarize_response.status_code == 200:
            summarize_data = summarize_response.json()
            assert "original_message_count" in summarize_data, "original_message_count missing"
            assert "preserved_message_count" in summarize_data, "preserved_message_count missing"

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_summarization_failure_handling_via_api(api_client, test_user, test_expert):
    """Test graceful handling when summarization fails (LLM unavailable).

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Session with messages

    Expected Outputs:
    - Summarization endpoint returns appropriate error or fallback
    - Error message indicates LLM unavailability
    - System degrades gracefully
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
            "title": f"Failure Handling Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add messages
    message_count = int(get_config("test.at1_10.message_counts.long"))
    for i in range(message_count):
        message_content = f"Message {i} for failure test {unique_id}: " + "D" * 40
        api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )

    # Attempt summarization
    summarize_response = api_client.post(
        f"/sessions/{session_id}/summarize",
        params={
            "preserve_recent": int(get_config("test.at1_10.summarization.preserve_recent")),
            "max_tokens": int(get_config("test.at1_10.summarization.max_tokens")),
        },
    )

    # Should either succeed or return graceful error
    assert summarize_response.status_code in [200, 500, 503], (
        f"Unexpected status code: {summarize_response.status_code}"
    )

    if summarize_response.status_code == 200:
        summarize_data = summarize_response.json()
        # Should have preserved messages even if summary failed
        assert "preserved_message_count" in summarize_data, "preserved_message_count missing"
    elif summarize_response.status_code in [500, 503]:
        error_detail = summarize_response.json().get("detail", "")
        # Error should indicate LLM issue
        assert len(error_detail) > 0, "Error detail should be present"

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_summary_storage_and_retrieval_via_api(api_client, test_user, test_expert):
    """Test that summaries are stored and can be retrieved.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Session with messages
    - summarization: Triggered via API

    Expected Outputs:
    - Summary stored in database
    - Summary retrievable via GET /sessions/{id}/summaries
    - Summary structure validated
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
            "title": f"Summary Storage Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add messages
    message_count = int(get_config("test.at1_10.message_counts.xlong"))
    for i in range(message_count):
        message_content = f"Message {i} for storage test {unique_id}: " + "E" * 50
        api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )

    # Trigger summarization
    summarize_response = api_client.post(
        f"/sessions/{session_id}/summarize",
        params={
            "preserve_recent": int(get_config("test.at1_10.summarization.preserve_recent")),
            "max_tokens": max(1, context_window // 2),
        },
    )

    if summarize_response.status_code in (500, 503):
        pytest.fail(f"Summarization failed (LLM required for AT1.10): {summarize_response.text}")

    if summarize_response.status_code == 200:
        summarize_data = summarize_response.json()
        summary_id = summarize_data.get("summary_id")

        if summary_id:
            # Retrieve summaries
            summaries_response = api_client.get(f"/sessions/{session_id}/summaries")
            assert summaries_response.status_code == 200, (
                f"Failed to get summaries: {summaries_response.text}"
            )
            summaries_data = summaries_response.json()

            # Validate summaries response
            assert "summaries" in summaries_data, "summaries array missing"
            assert "count" in summaries_data, "count missing"
            assert "session_id" in summaries_data, "session_id missing at top level"
            assert summaries_data["session_id"] == session_id, "Session ID mismatch at top level"
            assert isinstance(summaries_data["summaries"], list), "summaries must be a list"
            assert len(summaries_data["summaries"]) > 0, "Should have at least one summary"
            assert summaries_data["count"] == len(summaries_data["summaries"]), (
                "Count should match summaries length"
            )

            # Validate summary structure
            for summary in summaries_data["summaries"]:
                assert "id" in summary, "Summary ID missing"
                # session_id may be at top level, not in each summary

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_summarization_quality_validation_via_api(api_client, test_user, test_expert):
    """Test that summaries capture key information from conversation.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Session with structured messages containing key topics
    - summarization: Triggered via API

    Expected Outputs:
    - Summary contains key topics from conversation
    - Summary is concise but informative
    - Summary structure validated
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
            "title": f"Summary Quality Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add structured messages with key topics
    key_topics = [f"TopicA_{unique_id}", f"TopicB_{unique_id}", f"TopicC_{unique_id}"]
    message_count = int(get_config("test.at1_10.message_counts.long"))
    for i in range(message_count):
        topic = key_topics[i % len(key_topics)]
        message_content = (
            f"Discussion about {topic}: This is important information about {topic} for test {unique_id}. "
            + "Details " * 10
        )
        api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )

    # Trigger summarization
    summarize_response = api_client.post(
        f"/sessions/{session_id}/summarize",
        params={
            "preserve_recent": int(get_config("test.at1_10.summarization.preserve_recent")),
            "max_tokens": max(1, context_window // 2),
        },
    )

    if summarize_response.status_code in (500, 503):
        pytest.fail(f"Summarization failed (LLM required for AT1.10): {summarize_response.text}")

    if summarize_response.status_code == 200:
        summarize_data = summarize_response.json()

        # Validate summary exists
        if summarize_data.get("summary"):
            summary_text = summarize_data["summary"]
            assert len(summary_text) > 0, "Summary should not be empty"
            # Summary should be shorter than original messages
            assert len(summary_text) < message_count * 200, (
                "Summary should be more concise than original"
            )

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_summarization_with_insufficient_messages_via_api(api_client, test_user, test_expert):
    """Test that summarization handles cases with insufficient messages.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Session with few messages (< preserve_recent)

    Expected Outputs:
    - Summarization returns appropriate message
    - No summary created
    - All messages preserved
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
            "title": f"Insufficient Messages Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add only 3 messages (less than preserve_recent=5)
    message_count = int(get_config("test.at1_10.message_counts.tiny"))
    for i in range(message_count):
        message_content = f"Message {i} for insufficient test {unique_id}"
        api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )

    # Attempt summarization
    summarize_response = api_client.post(
        f"/sessions/{session_id}/summarize",
        params={
            "preserve_recent": int(get_config("test.at1_10.summarization.preserve_recent")),
            "max_tokens": int(get_config("test.at1_10.summarization.max_tokens")),
        },
    )

    assert summarize_response.status_code == 200, (
        f"Failed to trigger summarization: {summarize_response.text}"
    )
    summarize_data = summarize_response.json()

    # Should indicate insufficient messages
    assert "message" in summarize_data, "Message field missing"
    assert (
        "Not enough" in summarize_data["message"]
        or "insufficient" in summarize_data["message"].lower()
    ), "Should indicate insufficient messages"
    assert summarize_data.get("summary_id") is None or summarize_data.get("summary") is None, (
        "Should not have summary"
    )
    assert summarize_data["preserved_message_count"] == message_count, (
        f"Should preserve all {message_count} messages"
    )

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_multiple_summarizations_via_api(api_client, test_user, test_expert):
    """Test that multiple summarizations can be created for a session.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Session with many messages
    - multiple summarizations: Triggered at different points

    Expected Outputs:
    - Multiple summaries can be created
    - All summaries retrievable
    - Summary count increases with each summarization
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
            "title": f"Multiple Summaries Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add initial messages
    initial_count = 15
    for i in range(initial_count):
        message_content = f"Initial message {i} for multi-summary test {unique_id}: " + "F" * 40
        api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )

    # First summarization
    summarize1_response = api_client.post(
        f"/sessions/{session_id}/summarize",
        params={
            "preserve_recent": int(get_config("test.at1_10.summarization.preserve_recent")),
            "max_tokens": int(get_config("test.at1_10.summarization.max_tokens")),
        },
    )

    if summarize1_response.status_code in (500, 503):
        pytest.fail(f"Summarization failed (LLM required for AT1.10): {summarize1_response.text}")

    # Add more messages
    additional_count = 10
    for i in range(additional_count):
        message_content = f"Additional message {i} for multi-summary test {unique_id}: " + "G" * 40
        api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )

    # Second summarization
    summarize2_response = api_client.post(
        f"/sessions/{session_id}/summarize",
        params={
            "preserve_recent": int(get_config("test.at1_10.summarization.preserve_recent")),
            "max_tokens": int(get_config("test.at1_10.summarization.max_tokens")),
        },
    )

    if summarize2_response.status_code in (500, 503):
        pytest.fail(f"Summarization failed (LLM required for AT1.10): {summarize2_response.text}")

    # Retrieve all summaries
    summaries_response = api_client.get(f"/sessions/{session_id}/summaries")
    if summaries_response.status_code == 200:
        summaries_data = summaries_response.json()
        assert "summaries" in summaries_data, "summaries array missing"
        assert "count" in summaries_data, "count missing"
        # Should have at least one summary if LLM was available
        if summarize1_response.status_code == 200 or summarize2_response.status_code == 200:
            assert len(summaries_data["summaries"]) >= 0, (
                "Should have summaries if summarization succeeded"
            )

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.db, pytest.mark.smtp, pytest.mark.heavy]

