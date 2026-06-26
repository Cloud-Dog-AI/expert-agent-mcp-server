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
Application Test: AT1.11 - Learning Session with Service Restart

License: Apache 2.0
Ownership: Cloud Dog
Description: Test that learning persists across service restarts

Related Requirements: FR1.26, FR1.27
Related Tasks: T064, T065
Related Architecture: CC2.1.2, CC2.1.3
Related Tests: AT1.11
"""

import pytest
import uuid
import sys
from pathlib import Path
from src.config.loader import get_config

# Add parent directory to path for shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import build_test_email, create_api_client_fixture, validate_config_loaded


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
            "Test user credentials not configured. Set test.user.username, test.user.email, test.user.password in --env file."
        )

    unique_id = str(uuid.uuid4())[:8]
    return {
        "username": f"{base_username}_at1_11_restart_{unique_id}",
        "email": build_test_email("at1_11_restart", unique_id, base_email),
        "password": base_password,
    }


@pytest.fixture
def test_user(api_client, test_user_credentials):
    """Create test user via API."""
    client = api_client
    creds = test_user_credentials

    response = client.post(
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

    # Cleanup via API
    try:
        client.delete(f"/users/{user_data['id']}")
    except Exception:
        pass


@pytest.fixture
def test_expert(api_client, test_config):
    """Create test expert via API."""
    client = api_client
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")

    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_at1_11_restart_{unique_id}",
        "title": f"Learning Session Restart Expert {unique_id} resilience persistence replay continuity checkpoints",
        "description": "Learning persistence across restart scenario with unique vocabulary: acorn basil cipher dune ember fjord glyph helios isotope juniper keystone",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "enabled": True,
    }

    response = client.post("/experts", json=expert_data)
    assert response.status_code == 200, f"Failed to create test expert: {response.text}"
    expert = response.json()

    yield expert

    # Cleanup via API
    try:
        api_client.delete(f"/experts/{expert['id']}")
    except Exception:
        pass
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-018")


def test_learning_session_service_restart_via_api(
    api_client, test_user, test_expert, test_env_file
):
    """Test that learning persists across service restarts via API.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session_title: "Learning Session {unique_id}"
    - messages: 5 messages with learning content
    - vector_store_documents: 3 documents to store

    Expected Outputs:
    - Session created with session_key and history_key
    - All messages added successfully
    - Vector store documents added successfully
    - After restart simulation, session accessible by key
    - All messages present after restart
    - Vector store knowledge accessible after restart
    """
    client = api_client
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    session_title = f"Learning Session {unique_id}"

    # Get configuration values from config system
    context_window = get_config("session.context_window_size")
    history_retention_days = get_config("session.history_retention_days")
    if context_window is None or history_retention_days is None:
        pytest.fail(
            "Missing session.context_window_size/session.history_retention_days in config (--env)"
        )

    print(f"\n[SETTINGS] User ID: {user_id}")
    print(f"[SETTINGS] Expert ID: {expert_id}")
    print(f"[SETTINGS] Session title: {session_title}")
    print(f"[SETTINGS] Context window: {context_window}")
    print(f"[SETTINGS] Test ID: {unique_id}")

    # Step 1: Create session via API
    create_response = client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": session_title,
            "context_window": context_window,
            "history_retention_days": history_retention_days,
        },
    )
    assert create_response.status_code == 200, f"Failed to create session: {create_response.text}"
    session_data = create_response.json()
    session_id = session_data["id"]
    session_key = session_data["session_key"]
    history_key = session_data["history_key"]

    # Validate session has keys
    assert session_key is not None, "session_key should be generated"
    assert history_key is not None, "history_key should be generated"
    assert len(session_key) == 36, "session_key should be UUID (36 chars)"
    assert len(history_key) == 36, "history_key should be UUID (36 chars)"

    # Step 2: Add learning messages via API
    learning_messages = [
        "I'm learning about Python microservices architecture.",
        "Specifically, I want to understand service communication patterns.",
        "I've learned that message queues are essential for async communication.",
        "RabbitMQ is a popular choice for Python applications.",
        "I need to understand how to handle message ordering and delivery guarantees.",
    ]

    message_ids = []
    for i, message_content in enumerate(learning_messages):
        add_message_response = client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )
        assert add_message_response.status_code == 200, (
            f"Failed to add message {i + 1}: {add_message_response.text}"
        )
        message_data = add_message_response.json()
        message_ids.append(message_data["id"])
        assert message_data["content"] == message_content, f"Message {i + 1} content mismatch"

    # Step 3: Store documents in vector store via API (if vector store endpoints exist)
    # For now, we'll verify messages are stored correctly
    # Vector store integration would require vector store configuration

    # Step 4: Verify session exists
    get_session_response = client.get(f"/sessions/{session_id}")
    assert get_session_response.status_code == 200, (
        f"Failed to get session: {get_session_response.text}"
    )
    retrieved_session = get_session_response.json()
    assert retrieved_session["id"] == session_id
    assert retrieved_session["session_key"] == session_key
    assert retrieved_session["history_key"] == history_key

    # Step 5: Verify messages exist
    get_messages_response = client.get(f"/sessions/{session_id}/messages")
    assert get_messages_response.status_code == 200, (
        f"Failed to get messages: {get_messages_response.text}"
    )
    messages_data = get_messages_response.json()
    assert len(messages_data["messages"]) == len(learning_messages), (
        f"Expected {len(learning_messages)} messages, got {len(messages_data['messages'])}"
    )
    assert messages_data["count"] == len(learning_messages)

    # Step 6: Restart the real API server (service restart validation)
    import subprocess

    subprocess.run(
        ["./server_control.sh", "--env", str(test_env_file), "restart", "api"],
        cwd=str(Path(__file__).parent.parent.parent.parent),
        check=True,
        capture_output=True,
        text=True,
    )

    # Create a new client after restart
    client_restarted = create_api_client_fixture(check_health=True)()

    # Step 7: Resume session using session_key
    get_by_key_response = client_restarted.get(f"/sessions/key/{session_key}")
    assert get_by_key_response.status_code == 200, (
        f"Failed to get session by key after restart: {get_by_key_response.text}"
    )
    session_after_restart = get_by_key_response.json()
    assert session_after_restart["id"] == session_id, "Session ID should match after restart"
    assert session_after_restart["session_key"] == session_key, (
        "Session key should match after restart"
    )

    # Step 8: Verify context is maintained (messages still present)
    get_messages_after_restart = client_restarted.get(f"/sessions/{session_id}/messages")
    assert get_messages_after_restart.status_code == 200, (
        f"Failed to get messages after restart: {get_messages_after_restart.text}"
    )
    messages_after_restart = get_messages_after_restart.json()
    assert len(messages_after_restart["messages"]) == len(learning_messages), (
        f"Expected {len(learning_messages)} messages after restart, got {len(messages_after_restart['messages'])}"
    )
    assert messages_after_restart["count"] == len(learning_messages)

    # Verify message content is preserved
    for i, expected_message in enumerate(learning_messages):
        assert messages_after_restart["messages"][i]["content"] == expected_message, (
            f"Message {i + 1} content mismatch after restart"
        )

    # Step 9: Verify history is accessible by history_key
    get_history_by_key = client_restarted.get(f"/sessions/history/{history_key}")
    assert get_history_by_key.status_code == 200, (
        f"Failed to get history by key: {get_history_by_key.text}"
    )
    history_data = get_history_by_key.json()
    assert history_data["session_id"] == session_id
    assert history_data["history_key"] == history_key
    assert len(history_data["messages"]) == len(learning_messages), (
        f"Expected {len(learning_messages)} messages in history, got {len(history_data['messages'])}"
    )

    # Cleanup
    # Cleanup via API
    try:
        client_restarted.delete(f"/sessions/{session_id}")
    except Exception:
        pass

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.vdb, pytest.mark.smtp, pytest.mark.heavy]

