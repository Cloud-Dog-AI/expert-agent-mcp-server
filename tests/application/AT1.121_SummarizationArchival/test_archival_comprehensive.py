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
Application Test: AT1.13 - Conversation Archival
Comprehensive Archival Tests

License: Apache 2.0
Ownership: Cloud Dog
Description: Comprehensive tests for conversation archival functionality

Related Requirements: FR1.2, FR1.11
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
            "Test user credentials not configured. Set test.user.username, test.user.email, "
            "test.user.password in --env file or defaults.yaml"
        )

    unique_id = str(uuid.uuid4())[:8]
    return {
        "username": f"{base_username}_at1_13_arch_{unique_id}",
        "email": build_test_email("at1_13_arch", unique_id, base_email),
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
            "name": f"Archival Test Expert {unique_id}",
            "title": "Test Expert",
            "description": "Expert for archival testing and retention validation.",
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
            "title": f"Archival Test Session {unique_id}",
            "context_window": context_window,
            "history_retention_days": history_retention_days,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add multiple messages
    messages = [
        "This is message 1 for archival testing.",
        "This is message 2 for archival testing.",
        "This is message 3 for archival testing.",
        "This is message 4 for archival testing.",
        "This is message 5 for archival testing.",
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

    # Cleanup handled by individual tests
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_archival(api_client, test_session_with_messages):
    """Test session archival (deletion with retention)."""
    session_id = test_session_with_messages["id"]
    output_storage = TestOutputStorage("at1_13_session_archival")
    output_storage.set_session_id(session_id)

    # Get session before archival
    session_before = api_client.get(f"/sessions/{session_id}")
    assert session_before.status_code == 200
    session_before.json()

    # Get messages before archival
    messages_before = api_client.get(f"/sessions/{session_id}/messages")
    assert messages_before.status_code == 200
    messages_data_before = messages_before.json()

    # Archive session (delete)
    api_client.delete(f"/sessions/{session_id}")

    # Verify session is deleted
    session_after = api_client.get(f"/sessions/{session_id}")
    assert session_after.status_code == 404, "Session should be deleted"

    output_storage.save_test_metadata(
        {
            "session_id": session_id,
            "messages_before_archival": messages_data_before.get("count", 0),
            "archival_status": "deleted",
        }
    )
    output_storage.save_test_summary()
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_message_archival(api_client, test_session_with_messages):
    """Test message archival and retention."""
    session_id = test_session_with_messages["id"]
    output_storage = TestOutputStorage("at1_13_message_archival")
    output_storage.set_session_id(session_id)

    # Get initial messages
    initial_messages = api_client.get(f"/sessions/{session_id}/messages")
    assert initial_messages.status_code == 200
    initial_count = len(initial_messages.json()["messages"])

    # Add more messages
    message_count = int(get_config("test.at1_10.message_counts.medium"))
    for i in range(message_count):
        api_client.post(
            f"/sessions/{session_id}/messages",
            json={"role": "user", "content": f"Archival test message {i}"},
        )

    # Get messages after addition
    final_messages = api_client.get(f"/sessions/{session_id}/messages")
    assert final_messages.status_code == 200
    final_count = len(final_messages.json()["messages"])

    assert final_count >= initial_count + message_count, "Messages should be retained"

    output_storage.save_test_metadata(
        {
            "initial_message_count": initial_count,
            "final_message_count": final_count,
            "messages_added": message_count,
        }
    )
    output_storage.save_test_summary()

    # Cleanup
    try:
        api_client.delete(f"/sessions/{session_id}")
    except Exception:
        pass
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_summary_archival(api_client, test_session_with_messages):
    """Test summary archival and retrieval."""
    session_id = test_session_with_messages["id"]
    output_storage = TestOutputStorage("at1_13_summary_archival")
    output_storage.set_session_id(session_id)

    # Add more messages to ensure we have enough for summarization
    preserve_recent = get_config("test.at1_10.summarization.preserve_recent")
    if preserve_recent is None:
        pytest.fail(
            "Missing test.at1_10.summarization.preserve_recent in config (--env/defaults.yaml)"
        )
    preserve_recent = int(preserve_recent)
    additional_messages = max(
        preserve_recent + 1, int(get_config("test.at1_10.message_counts.short"))
    )
    for i in range(additional_messages):
        api_client.post(
            f"/sessions/{session_id}/messages",
            json={"role": "user", "content": f"Additional message {i} for summarization test."},
        )

    # Create summary (preserve_recent=5, so we need >5 messages - we now have 11)
    summarize_response = api_client.post(
        f"/sessions/{session_id}/summarize", params={"preserve_recent": int(preserve_recent)}
    )

    if summarize_response.status_code == 200:
        summary_data = summarize_response.json()
        output_storage.save_summary(summary_data)

        # Retrieve summary
        summaries_response = api_client.get(f"/sessions/{session_id}/summaries")
        assert summaries_response.status_code == 200
        summaries_data = summaries_response.json()

        assert summaries_data.get("count", 0) > 0, "Summary should be archived and retrievable"

        output_storage.save_test_metadata({"summary_count": summaries_data.get("count", 0)})
    elif summarize_response.status_code == 503:
        pytest.fail(
            f"LLM unavailable for summarization (required for AT1.13): {summarize_response.text}"
        )

    output_storage.save_test_summary()

    # Cleanup
    try:
        api_client.delete(f"/sessions/{session_id}")
    except Exception:
        pass
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_archive_retrieval(api_client, test_session_with_messages):
    """Test archive retrieval via API."""
    session_id = test_session_with_messages["id"]
    output_storage = TestOutputStorage("at1_13_archive_retrieval")
    output_storage.set_session_id(session_id)

    # Get session
    session_response = api_client.get(f"/sessions/{session_id}")
    assert session_response.status_code == 200
    session_data = session_response.json()

    # Get messages
    messages_response = api_client.get(f"/sessions/{session_id}/messages")
    assert messages_response.status_code == 200
    messages_data = messages_response.json()

    # Get summaries
    summaries_response = api_client.get(f"/sessions/{session_id}/summaries")
    assert summaries_response.status_code == 200
    summaries_data = summaries_response.json()

    # Validate all data is retrievable
    assert "id" in session_data, "Session data should be retrievable"
    assert "messages" in messages_data, "Messages should be retrievable"
    assert "summaries" in summaries_data, "Summaries should be retrievable"

    output_storage.save_test_metadata(
        {
            "session_retrievable": True,
            "messages_retrievable": True,
            "summaries_retrievable": True,
            "message_count": messages_data.get("count", 0),
            "summary_count": summaries_data.get("count", 0),
        }
    )
    output_storage.save_test_summary()

    # Cleanup
    try:
        api_client.delete(f"/sessions/{session_id}")
    except Exception:
        pass
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_archive_search(api_client, test_user, test_expert):
    """Test archive search functionality."""
    user_id = test_user["id"]
    expert_id = test_expert["id"]
    output_storage = TestOutputStorage("at1_13_archive_search")

    load_config.cache_clear()
    context_window = get_config("session.context_window_size")
    history_retention_days = get_config("session.history_retention_days")
    if context_window is None or history_retention_days is None:
        pytest.fail(
            "Missing session.context_window_size/session.history_retention_days in config (--env)"
        )

    # Create multiple sessions
    session_ids = []
    session_count = int(get_config("test.at1_10.message_counts.tiny"))
    for i in range(session_count):
        unique_id = str(uuid.uuid4())[:8]
        session_response = api_client.post(
            "/sessions",
            json={
                "user_id": user_id,
                "expert_config_id": expert_id,
                "title": f"Search Test Session {i} {unique_id}",
                "context_window": context_window,
                "history_retention_days": history_retention_days,
            },
        )
        if session_response.status_code == 200:
            session_ids.append(session_response.json()["id"])

    # List sessions (search)
    list_response = api_client.get("/sessions")
    assert list_response.status_code == 200
    sessions_data = list_response.json()

    assert "sessions" in sessions_data, "Should return sessions list"
    assert len(sessions_data["sessions"]) >= len(session_ids), "Should find created sessions"

    output_storage.save_test_metadata(
        {"sessions_created": len(session_ids), "sessions_found": len(sessions_data["sessions"])}
    )
    output_storage.save_test_summary()

    # Cleanup
    for sid in session_ids:
        try:
            api_client.delete(f"/sessions/{sid}")
        except Exception:
            pass
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_archive_lifecycle(api_client, test_session_with_messages):
    """Test archive lifecycle (create, use, archive, retrieve)."""
    session_id = test_session_with_messages["id"]
    output_storage = TestOutputStorage("at1_13_archive_lifecycle")
    output_storage.set_session_id(session_id)

    # 1. Create session (already done in fixture)
    session_response = api_client.get(f"/sessions/{session_id}")
    assert session_response.status_code == 200

    # 2. Add messages (already done in fixture)
    messages_response = api_client.get(f"/sessions/{session_id}/messages")
    assert messages_response.status_code == 200
    initial_count = len(messages_response.json()["messages"])

    # 3. Use session (add more messages)
    message_count = int(get_config("test.at1_10.message_counts.short"))
    for i in range(message_count):
        api_client.post(
            f"/sessions/{session_id}/messages",
            json={"role": "user", "content": f"Lifecycle test message {i}"},
        )

    # 4. Create summary
    summarize_response = api_client.post(
        f"/sessions/{session_id}/summarize",
        params={"preserve_recent": int(get_config("test.at1_10.summarization.preserve_recent"))},
    )

    # 5. Retrieve archive
    final_messages = api_client.get(f"/sessions/{session_id}/messages")
    assert final_messages.status_code == 200
    final_count = len(final_messages.json()["messages"])

    summaries_response = api_client.get(f"/sessions/{session_id}/summaries")
    assert summaries_response.status_code == 200

    output_storage.save_test_metadata(
        {
            "initial_messages": initial_count,
            "final_messages": final_count,
            "messages_added": message_count,
            "summary_created": summarize_response.status_code == 200,
        }
    )
    output_storage.save_test_summary()

    # Cleanup
    try:
        api_client.delete(f"/sessions/{session_id}")
    except Exception:
        pass

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

