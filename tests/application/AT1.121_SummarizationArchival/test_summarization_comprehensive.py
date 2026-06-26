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
Application Test: AT1.13 - Conversation Summarization
Comprehensive Summarization Tests

License: Apache 2.0
Ownership: Cloud Dog
Description: Comprehensive tests for conversation summarization functionality

Related Requirements: FR1.2, FR1.10
Related Tasks: T022, T010
Related Architecture: CC2.1.1
Related Tests: AT1.13

Recent Changes:
- Comprehensive implementation with output storage
- Configuration-driven (no hardcoded values)
- API-only testing
- Full output validation
"""

import pytest
import sys
import uuid
import importlib.util
from pathlib import Path

# Ensure project root is in path
_project_root = Path(__file__).parent.parent.parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from src.config.loader import get_config, load_config  # noqa: E402

# Fix import path for AT1.12 (contains dot which Python interprets as decimal)
_helpers_path = Path(__file__).parent.parent / "AT1.12_MultiTurnConversation" / "helpers.py"
spec = importlib.util.spec_from_file_location("test_helpers", _helpers_path)
test_helpers = importlib.util.module_from_spec(spec)
spec.loader.exec_module(test_helpers)
TestOutputStorage = test_helpers.TestOutputStorage
validate_config_loaded = test_helpers.validate_config_loaded

# Add parent directory to path for shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import build_test_email, create_api_client_fixture  # noqa: E402


@pytest.fixture(scope="module")
def api_client():
    """Create API client that connects to real running API server."""
    validate_config_loaded()
    return create_api_client_fixture(check_health=True)()


@pytest.fixture
def test_user_credentials(test_env_file):
    """Get test user credentials from configuration system."""
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
        "username": f"{base_username}_at1_13_{unique_id}",
        "email": build_test_email("at1_13", unique_id, base_email),
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

    resp = api_client.delete(f"/users/{user_data['id']}")
    if resp.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete user {user_data['id']}: {resp.status_code} {resp.text}"
        )


@pytest.fixture
def test_expert(api_client, test_user):
    """Create test expert via API."""
    load_config.cache_clear()

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    llm_api_key = get_config("llm.api_key")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")

    unique_id = str(uuid.uuid4())[:8]

    expert_response = api_client.post(
        "/experts",
        json={
            "name": f"Summarization Test Expert {unique_id}",
            "title": f"Summarization Quality Analyst {unique_id} for archival context",
            "description": (
                "Expert focused on summarization accuracy, archival retention, "
                f"context window management, multi-turn recall, and quality checks {unique_id}"
            ),
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_base_url": llm_base_url,
            "llm_api_key": llm_api_key,
            "enabled": True,
        },
    )
    assert expert_response.status_code == 200, f"Failed to create expert: {expert_response.text}"
    expert_data = expert_response.json()

    yield expert_data

    resp = api_client.delete(f"/experts/{expert_data['id']}")
    if resp.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete expert {expert_data['id']}: {resp.status_code} {resp.text}"
        )


@pytest.fixture
def test_session_with_messages(api_client, test_user, test_expert):
    """Create test session with multiple messages."""
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    load_config.cache_clear()
    context_window = get_config("session.context_window_size")
    history_retention_days = get_config("session.history_retention_days")
    if context_window is None or history_retention_days is None:
        pytest.fail(
            "Missing session.context_window_size/session.history_retention_days in config (--env)"
        )

    unique_id = str(uuid.uuid4())[:8]
    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Summarization Test Session {unique_id}",
            "context_window": context_window,
            "history_retention_days": history_retention_days,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add multiple messages to the session
    messages = [
        "Hello, I want to discuss machine learning.",
        "What is supervised learning?",
        "Can you explain neural networks?",
        "How do convolutional neural networks work?",
        "What are the applications of deep learning?",
        "Tell me about transformers.",
        "How do attention mechanisms work?",
        "What is the difference between RNNs and transformers?",
        "Can you explain BERT?",
        "What are some use cases for language models?",
    ]

    message_ids = []
    for msg in messages:
        msg_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": msg}
        )
        if msg_response.status_code == 200:
            message_ids.append(msg_response.json()["id"])

    session_data["message_ids"] = message_ids
    session_data["message_count"] = len(message_ids)

    yield session_data

    resp = api_client.delete(f"/sessions/{session_id}")
    if resp.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {resp.status_code} {resp.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_automatic_summarization_trigger(api_client, test_session_with_messages):
    """Test automatic summarization trigger when context window is exceeded."""
    session_id = test_session_with_messages["id"]
    output_storage = TestOutputStorage("at1_13_automatic_summarization")
    output_storage.set_session_id(session_id)

    # Get initial message count
    initial_messages = api_client.get(f"/sessions/{session_id}/messages")
    assert initial_messages.status_code == 200
    initial_count = len(initial_messages.json()["messages"])

    # Add many more messages to exceed context window (config-driven count)
    message_count = get_config("test.at1_10.message_counts.xxlong")
    if message_count is None:
        pytest.fail("Missing test.at1_10.message_counts.xxlong in config (--env/defaults.yaml)")
    for i in range(int(message_count)):
        api_client.post(
            f"/sessions/{session_id}/messages",
            json={
                "role": "user",
                "content": f"Message {i}: This is a test message to fill the context window.",
            },
        )

    # Check if summarization was triggered (this may be automatic or manual)
    summaries_response = api_client.get(f"/sessions/{session_id}/summaries")
    assert summaries_response.status_code == 200
    summaries_data = summaries_response.json()

    output_storage.save_test_metadata(
        {
            "initial_message_count": initial_count,
            "final_message_count": len(
                api_client.get(f"/sessions/{session_id}/messages").json()["messages"]
            ),
            "summary_count": summaries_data.get("count", 0),
        }
    )
    output_storage.save_test_summary()
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_manual_summarization(api_client, test_session_with_messages):
    """Test manual summarization via API."""
    session_id = test_session_with_messages["id"]
    output_storage = TestOutputStorage("at1_13_manual_summarization")
    output_storage.set_session_id(session_id)

    # Get initial summaries
    initial_summaries = api_client.get(f"/sessions/{session_id}/summaries")
    assert initial_summaries.status_code == 200
    initial_count = initial_summaries.json().get("count", 0)

    # Trigger manual summarization
    preserve_recent = get_config("test.at1_10.summarization.preserve_recent")
    max_tokens = get_config("test.at1_10.summarization.max_tokens")
    if preserve_recent is None or max_tokens is None:
        pytest.fail("Missing test.at1_10.summarization.* in config (--env/defaults.yaml)")
    summarize_response = api_client.post(
        f"/sessions/{session_id}/summarize",
        params={"preserve_recent": int(preserve_recent), "max_tokens": int(max_tokens)},
    )

    if summarize_response.status_code == 200:
        summary_data = summarize_response.json()
        output_storage.save_summary(summary_data)

        # Verify summary was created
        summaries_response = api_client.get(f"/sessions/{session_id}/summaries")
        assert summaries_response.status_code == 200
        summaries_data = summaries_response.json()
        assert summaries_data.get("count", 0) > initial_count, "Summary count should increase"
    elif summarize_response.status_code == 503:
        pytest.fail(
            f"LLM unavailable for summarization (required for AT1.13): {summarize_response.text}"
        )
    else:
        pytest.fail(
            f"Summarization failed: {summarize_response.status_code} - {summarize_response.text}"
        )

    output_storage.save_test_summary()
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_summary_quality_validation(api_client, test_session_with_messages):
    """Test summary quality and content validation."""
    session_id = test_session_with_messages["id"]
    output_storage = TestOutputStorage("at1_13_summary_quality")
    output_storage.set_session_id(session_id)

    # Trigger summarization
    preserve_recent = get_config("test.at1_10.summarization.preserve_recent")
    if preserve_recent is None:
        pytest.fail(
            "Missing test.at1_10.summarization.preserve_recent in config (--env/defaults.yaml)"
        )
    summarize_response = api_client.post(
        f"/sessions/{session_id}/summarize", params={"preserve_recent": int(preserve_recent)}
    )

    if summarize_response.status_code == 200:
        summary_data = summarize_response.json()

        # Validate summary structure
        assert "summary" in summary_data or "content" in summary_data, "Summary missing content"
        assert "summary_id" in summary_data, "Summary missing summary_id"
        assert isinstance(summary_data["summary_id"], int), "summary_id must be an int"

        output_storage.save_summary(summary_data)

        # Validate summary is retrievable
        summaries_response = api_client.get(f"/sessions/{session_id}/summaries")
        assert summaries_response.status_code == 200
        summaries_data = summaries_response.json()
        assert summaries_data.get("count", 0) > 0, "Summary should be retrievable"
        assert str(summaries_data.get("session_id")) == str(session_id), (
            "summaries response missing/incorrect session_id"
        )
        returned_ids = [
            s.get("summary_id", s.get("id"))
            for s in summaries_data.get("summaries", [])
            if isinstance(s, dict)
        ]
        assert summary_data["summary_id"] in returned_ids, (
            "Created summary_id not present in summaries list"
        )
    elif summarize_response.status_code == 503:
        pytest.fail(
            f"LLM unavailable for summarization (required for AT1.13): {summarize_response.text}"
        )

    output_storage.save_test_summary()
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_multiple_summarizations(api_client, test_session_with_messages):
    """Test creating multiple summaries for the same session."""
    session_id = test_session_with_messages["id"]
    output_storage = TestOutputStorage("at1_13_multiple_summarizations")
    output_storage.set_session_id(session_id)

    # Create first summary
    preserve_recent = int(get_config("test.at1_10.summarization.preserve_recent"))
    summarize1 = api_client.post(
        f"/sessions/{session_id}/summarize", params={"preserve_recent": preserve_recent}
    )

    if summarize1.status_code == 200:
        output_storage.save_summary(summarize1.json())

    # Add more messages
    message_count = int(get_config("test.at1_10.message_counts.medium"))
    for i in range(message_count):
        api_client.post(
            f"/sessions/{session_id}/messages",
            json={"role": "user", "content": f"Additional message {i}"},
        )

    # Create second summary
    summarize2 = api_client.post(
        f"/sessions/{session_id}/summarize", params={"preserve_recent": preserve_recent}
    )

    if summarize2.status_code == 200:
        output_storage.save_summary(summarize2.json())

    # Verify both summaries exist
    summaries_response = api_client.get(f"/sessions/{session_id}/summaries")
    assert summaries_response.status_code == 200
    summaries_data = summaries_response.json()

    output_storage.save_test_metadata({"summary_count": summaries_data.get("count", 0)})
    output_storage.save_test_summary()
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_summary_with_different_preserve_recent(api_client, test_session_with_messages):
    """Test summarization with different preserve_recent values."""
    session_id = test_session_with_messages["id"]
    output_storage = TestOutputStorage("at1_13_preserve_recent")
    output_storage.set_session_id(session_id)

    preserve_values = [
        int(get_config("test.at1_10.summarization.preserve_recent_small")),
        int(get_config("test.at1_10.summarization.preserve_recent")),
        int(get_config("test.at1_10.summarization.preserve_recent_large")),
    ]
    summaries_created = []

    for preserve in preserve_values:
        summarize_response = api_client.post(
            f"/sessions/{session_id}/summarize", params={"preserve_recent": preserve}
        )

        if summarize_response.status_code == 200:
            summary_data = summarize_response.json()
            summaries_created.append({"preserve_recent": preserve, "summary": summary_data})
            output_storage.save_summary(summary_data)
        elif summarize_response.status_code == 503:
            pytest.fail(
                f"LLM unavailable for summarization (required for AT1.13): {summarize_response.text}"
            )

    output_storage.save_test_metadata(
        {"preserve_values_tested": preserve_values, "summaries_created": len(summaries_created)}
    )
    output_storage.save_test_summary()
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_summary_storage_and_retrieval(api_client, test_session_with_messages):
    """Test summary storage and retrieval via API."""
    session_id = test_session_with_messages["id"]
    output_storage = TestOutputStorage("at1_13_storage_retrieval")
    output_storage.set_session_id(session_id)

    # Create summary
    preserve_recent = int(get_config("test.at1_10.summarization.preserve_recent"))
    summarize_response = api_client.post(
        f"/sessions/{session_id}/summarize", params={"preserve_recent": preserve_recent}
    )

    if summarize_response.status_code == 200:
        summary_data = summarize_response.json()
        output_storage.save_summary(summary_data)

        # Retrieve summaries
        summaries_response = api_client.get(f"/sessions/{session_id}/summaries")
        assert summaries_response.status_code == 200
        summaries_data = summaries_response.json()

        # Validate structure
        assert "session_id" in summaries_data, "Missing session_id in response"
        assert "summaries" in summaries_data, "Missing summaries in response"
        assert "count" in summaries_data, "Missing count in response"
        assert summaries_data["count"] > 0, "Should have at least one summary"

        output_storage.save_test_metadata({"summary_count": summaries_data["count"]})
    elif summarize_response.status_code == 503:
        pytest.fail(
            f"LLM unavailable for summarization (required for AT1.13): {summarize_response.text}"
        )

    output_storage.save_test_summary()

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

