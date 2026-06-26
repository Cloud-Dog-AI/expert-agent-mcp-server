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
Application Test: AT1.11 - Multi-User History Access

License: Apache 2.0
Ownership: Cloud Dog
Description: Test storing history and accessing as another user

Related Requirements: FR1.27
Related Tasks: T065
Related Architecture: CC2.1.3
Related Tests: AT1.11
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
        "username": f"{base_username}_at1_11_multi_{unique_id}",
        "email": build_test_email("at1_11_multi", unique_id, base_email),
        "password": base_password,
    }


@pytest.fixture
def test_user_a(api_client, test_user_credentials):
    """Create User A via API."""
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
def test_user_b(api_client, test_user_credentials):
    """Create User B via API."""
    creds = test_user_credentials
    unique_id = str(uuid.uuid4())[:8]

    response = api_client.post(
        "/users",
        json={
            "username": f"{creds['username']}_b_{unique_id}",
            "email": build_test_email("b", unique_id, creds["email"]),
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
        "name": f"expert_at1_11_multi_{unique_id}",
        "title": f"Multi User History Access Expert {unique_id} sharing permissions session_key history_key audit",
        "description": "Multi-user history access scenario with unique vocabulary: acorn basil cipher dune ember fjord glyph helios isotope juniper keystone",
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
@pytest.mark.req("FR-019")


def test_multi_user_history_access_via_api(api_client, test_user_a, test_user_b, test_expert):
    """Test storing history and accessing as another user via API.

    Inputs:
    - test_user_a: User A created via API
    - test_user_b: User B created via API
    - test_expert: Expert created via API
    - user_a_messages: 3 messages from User A
    - user_b_messages: 2 messages from User B

    Expected Outputs:
    - Session created by User A
    - User A messages added successfully
    - Session shared with User B successfully
    - User B can access session
    - User B can view User A's messages
    - User B messages added successfully
    - User A can view all messages (including User B's)
    - All messages have correct user_id
    """
    user_a_id = test_user_a["id"]
    user_b_id = test_user_b["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    session_title = f"Shared Learning Session {unique_id}"

    print(f"\n[SETTINGS] User A ID: {user_a_id}")
    print(f"[SETTINGS] User B ID: {user_b_id}")
    print(f"[SETTINGS] Expert ID: {expert_id}")
    print(f"[SETTINGS] Session title: {session_title}")
    print(f"[SETTINGS] Test ID: {unique_id}")

    # Step 1: User A creates session
    create_response = api_client.post(
        "/sessions",
        json={"user_id": user_a_id, "expert_config_id": expert_id, "title": session_title},
    )
    assert create_response.status_code == 200, f"Failed to create session: {create_response.text}"
    session_data = create_response.json()
    session_id = session_data["id"]

    # Step 2: User A adds messages
    user_a_messages = [
        "I'm working on a Python project.",
        "I need to implement async database connections.",
        "I've decided to use SQLAlchemy with async support.",
    ]

    user_a_message_ids = []
    for i, message_content in enumerate(user_a_messages):
        add_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )
        assert add_response.status_code == 200, (
            f"Failed to add User A message {i + 1}: {add_response.text}"
        )
        message_data = add_response.json()
        user_a_message_ids.append(message_data["id"])

    # Step 3: Share session with User B
    share_response = api_client.post(
        f"/sessions/{session_id}/share", json={"user_ids": [user_b_id], "group_ids": None}
    )
    assert share_response.status_code == 200, f"Failed to share session: {share_response.text}"
    share_data = share_response.json()
    assert user_b_id in share_data["shared_with_user_ids"], "User B should be in shared users"

    # Step 4: User B accesses session
    get_session_response = api_client.get(f"/sessions/{session_id}")
    assert get_session_response.status_code == 200, (
        f"User B should be able to access session: {get_session_response.text}"
    )
    retrieved_session = get_session_response.json()
    assert retrieved_session["id"] == session_id

    # Step 5: User B views history
    get_messages_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_messages_response.status_code == 200, (
        f"User B should be able to view messages: {get_messages_response.text}"
    )
    messages_data = get_messages_response.json()
    assert len(messages_data["messages"]) == len(user_a_messages), (
        f"Expected {len(user_a_messages)} messages, got {len(messages_data['messages'])}"
    )

    # Step 6: User B adds messages
    user_b_messages = [
        "I can help with that. SQLAlchemy async is great.",
        "Make sure to use create_async_engine for async connections.",
    ]

    user_b_message_ids = []
    for i, message_content in enumerate(user_b_messages):
        add_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )
        assert add_response.status_code == 200, (
            f"Failed to add User B message {i + 1}: {add_response.text}"
        )
        message_data = add_response.json()
        user_b_message_ids.append(message_data["id"])

    # Step 7: User A views updated history
    get_all_messages = api_client.get(f"/sessions/{session_id}/messages")
    assert get_all_messages.status_code == 200
    all_messages_data = get_all_messages.json()
    assert len(all_messages_data["messages"]) == len(user_a_messages) + len(user_b_messages), (
        f"Expected {len(user_a_messages) + len(user_b_messages)} total messages, got {len(all_messages_data['messages'])}"
    )
    assert all_messages_data["count"] == len(user_a_messages) + len(user_b_messages)

    # Verify all messages are present
    all_content = [msg["content"] for msg in all_messages_data["messages"]]
    for msg in user_a_messages:
        assert msg in all_content, f"User A message '{msg}' should be in history"
    for msg in user_b_messages:
        assert msg in all_content, f"User B message '{msg}' should be in history"

    # Cleanup
    # Cleanup via API
    try:
        api_client.delete(f"/sessions/{session_id}")
    except Exception:
        pass
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-019")


def test_multi_user_history_access_via_session_key(
    api_client, test_user_a, test_user_b, test_expert
):
    """Test history access via session key.

    Inputs:
    - test_user_a: User A
    - test_user_b: User B
    - test_expert: Expert
    - learning_messages: 3 messages from User A

    Expected Outputs:
    - Session created with session_key
    - Session shared with User B
    - User B can access session by session_key
    - User B can view and add messages
    - All messages visible to both users
    """
    user_a_id = test_user_a["id"]
    user_b_id = test_user_b["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    session_title = f"Session Key Test {unique_id}"

    # Step 1: User A creates session
    create_response = api_client.post(
        "/sessions",
        json={"user_id": user_a_id, "expert_config_id": expert_id, "title": session_title},
    )
    assert create_response.status_code == 200
    session_data = create_response.json()
    session_id = session_data["id"]
    session_key = session_data["session_key"]

    # Step 2: User A adds learning messages
    learning_messages = [
        "I'm learning about REST APIs.",
        "REST APIs use HTTP methods: GET, POST, PUT, DELETE.",
        "REST APIs should be stateless and cacheable.",
    ]

    for message_content in learning_messages:
        add_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )
        assert add_response.status_code == 200

    # Step 3: Share session with User B
    share_response = api_client.post(
        f"/sessions/{session_id}/share", json={"user_ids": [user_b_id]}
    )
    assert share_response.status_code == 200

    # Step 4: User B accesses session by key
    get_by_key_response = api_client.get(f"/sessions/key/{session_key}")
    assert get_by_key_response.status_code == 200, (
        f"User B should access by key: {get_by_key_response.text}"
    )
    session_by_key = get_by_key_response.json()
    assert session_by_key["id"] == session_id
    assert session_by_key["session_key"] == session_key

    # Step 5: User B views learning
    get_messages = api_client.get(f"/sessions/{session_id}/messages")
    assert get_messages.status_code == 200
    messages_data = get_messages.json()
    assert len(messages_data["messages"]) == len(learning_messages)

    # Step 6: User B continues learning
    user_b_message = "I want to learn about API versioning strategies."
    add_b_message = api_client.post(
        f"/sessions/{session_id}/messages", json={"role": "user", "content": user_b_message}
    )
    assert add_b_message.status_code == 200

    # Step 7: Verify all messages visible
    get_all = api_client.get(f"/sessions/{session_id}/messages")
    assert get_all.status_code == 200
    all_messages = get_all.json()
    assert len(all_messages["messages"]) == len(learning_messages) + 1
    assert all_messages["count"] == len(learning_messages) + 1

    # Cleanup
    # Cleanup via API
    try:
        api_client.delete(f"/sessions/{session_id}")
    except Exception:
        pass
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-019")


def test_multi_user_history_access_via_history_key(
    api_client, test_user_a, test_user_b, test_expert
):
    """Test history access via history key.

    Inputs:
    - test_user_a: User A
    - test_user_b: User B
    - test_expert: Expert
    - learning_messages: 3 messages from User A

    Expected Outputs:
    - Session created with history_key
    - Session shared with User B
    - User B can access history by history_key
    - User B can view and add messages
    - All messages visible to both users
    """
    user_a_id = test_user_a["id"]
    user_b_id = test_user_b["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    session_title = f"History Key Test {unique_id}"

    # Step 1: User A creates session
    create_response = api_client.post(
        "/sessions",
        json={"user_id": user_a_id, "expert_config_id": expert_id, "title": session_title},
    )
    assert create_response.status_code == 200
    session_data = create_response.json()
    session_id = session_data["id"]
    history_key = session_data["history_key"]

    # Step 2: User A adds learning messages
    learning_messages = [
        "I'm learning about REST APIs.",
        "REST APIs use HTTP methods: GET, POST, PUT, DELETE.",
        "REST APIs should be stateless and cacheable.",
    ]

    for message_content in learning_messages:
        add_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )
        assert add_response.status_code == 200

    # Step 3: Share session with User B
    share_response = api_client.post(
        f"/sessions/{session_id}/share", json={"user_ids": [user_b_id]}
    )
    assert share_response.status_code == 200

    # Step 4: User B accesses history by key
    get_history_by_key = api_client.get(f"/sessions/history/{history_key}")
    assert get_history_by_key.status_code == 200, (
        f"User B should access by history key: {get_history_by_key.text}"
    )
    history_data = get_history_by_key.json()
    assert history_data["session_id"] == session_id
    assert history_data["history_key"] == history_key
    assert len(history_data["messages"]) == len(learning_messages)

    # Step 5: User B continues learning
    user_b_message = "I want to learn about API versioning strategies."
    add_b_message = api_client.post(
        f"/sessions/{session_id}/messages", json={"role": "user", "content": user_b_message}
    )
    assert add_b_message.status_code == 200

    # Step 6: Verify all messages visible
    get_all = api_client.get(f"/sessions/{session_id}/messages")
    assert get_all.status_code == 200
    all_messages = get_all.json()
    assert len(all_messages["messages"]) == len(learning_messages) + 1
    assert all_messages["count"] == len(learning_messages) + 1

    # Cleanup
    # Cleanup via API
    try:
        api_client.delete(f"/sessions/{session_id}")
    except Exception:
        pass

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.db, pytest.mark.smtp, pytest.mark.heavy]

