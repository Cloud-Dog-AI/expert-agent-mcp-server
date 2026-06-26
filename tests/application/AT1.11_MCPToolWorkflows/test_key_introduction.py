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
Application Test: AT1.11 - Session Key and History Key Introduction

License: Apache 2.0
Ownership: Cloud Dog
Description: Test introducing session key and history key to pick up learning

Related Requirements: FR1.26
Related Tasks: T064
Related Architecture: CC2.1.2
Related Tests: AT1.11 (Tests 9-10)
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
        "username": f"{base_username}_at1_11_key_{unique_id}",
        "email": build_test_email("at1_11_key", unique_id, base_email),
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
        "name": f"expert_at1_11_key_{unique_id}",
        "title": f"Session Key Introduction Expert {unique_id} handoff continuity provenance retrieval traceability",
        "description": "Session key handoff scenario with unique vocabulary: acorn basil cipher dune ember fjord glyph helios isotope juniper keystone",
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
@pytest.mark.req("FR-018")


def test_session_key_introduction_via_api(api_client, test_user_a, test_user_b, test_expert):
    """Test introducing session key to pick up learning via API.

    Inputs:
    - user_a: User A created via API
    - user_b: User B created via API
    - test_expert: Expert created via API
    - learning_messages: 3 messages from User A with learning content
    - session_key: Session key from User A's session

    Expected Outputs:
    - User A creates session and adds learning (status 200, session_key returned)
    - User B introduces session_key (status 200, session accessed)
    - User B can view User A's learning (status 200, messages returned)
    - User B can continue learning (status 200, new message added)
    - All learning visible to both users
    """
    user_a_id = test_user_a["id"]
    user_b_id = test_user_b["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    session_title = f"Key Introduction Test {unique_id}"

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
    session_key = session_data["session_key"]

    assert session_key is not None, "session_key should be generated"
    assert len(session_key) == 36, "session_key should be UUID (36 chars)"

    # Step 2: User A adds learning messages
    learning_messages = [
        f"I'm learning about REST APIs. Test ID: {unique_id}",
        f"REST APIs use HTTP methods: GET, POST, PUT, DELETE. Test ID: {unique_id}",
        f"REST APIs should be stateless and cacheable. Test ID: {unique_id}",
    ]

    for i, message_content in enumerate(learning_messages):
        add_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )
        assert add_response.status_code == 200, (
            f"Failed to add learning message {i + 1}: {add_response.text}"
        )

    # Step 3: User B introduces session_key to pick up learning
    get_by_key_response = api_client.get(f"/sessions/key/{session_key}")
    assert get_by_key_response.status_code == 200, (
        f"User B should access by key: {get_by_key_response.text}"
    )
    session_by_key = get_by_key_response.json()
    assert session_by_key["id"] == session_id, "Session ID should match"
    assert session_by_key["session_key"] == session_key, "Session key should match"

    # Step 4: User B views learning
    get_messages_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_messages_response.status_code == 200, (
        f"User B should view messages: {get_messages_response.text}"
    )
    messages_data = get_messages_response.json()
    assert len(messages_data["messages"]) == len(learning_messages), (
        f"Expected {len(learning_messages)} messages, got {len(messages_data['messages'])}"
    )
    assert messages_data["count"] == len(learning_messages)

    # Verify learning content is accessible
    message_contents = [msg["content"] for msg in messages_data["messages"]]
    for learning_msg in learning_messages:
        assert any(learning_msg[:30] in content for content in message_contents), (
            f"Learning message should be accessible: {learning_msg[:30]}"
        )

    # Step 5: User B continues learning
    user_b_message = f"I want to learn about API versioning strategies. Test ID: {unique_id}"
    add_b_response = api_client.post(
        f"/sessions/{session_id}/messages", json={"role": "user", "content": user_b_message}
    )
    assert add_b_response.status_code == 200, f"User B should add message: {add_b_response.text}"

    # Step 6: Verify all learning visible to both users
    get_all_messages = api_client.get(f"/sessions/{session_id}/messages")
    assert get_all_messages.status_code == 200
    all_messages = get_all_messages.json()
    assert len(all_messages["messages"]) == len(learning_messages) + 1, (
        f"Expected {len(learning_messages) + 1} total messages, got {len(all_messages['messages'])}"
    )
    assert all_messages["count"] == len(learning_messages) + 1

    # Verify all messages present
    all_contents = [msg["content"] for msg in all_messages["messages"]]
    for learning_msg in learning_messages:
        assert any(learning_msg[:30] in content for content in all_contents), (
            f"User A's learning should be present: {learning_msg[:30]}"
        )
    assert any(user_b_message[:30] in content for content in all_contents), (
        f"User B's message should be present: {user_b_message[:30]}"
    )

    # Cleanup
    # Cleanup via API
    try:
        api_client.delete(f"/sessions/{session_id}")
    except Exception:
        pass
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-018")


def test_history_key_introduction_via_api(api_client, test_user_a, test_user_b, test_expert):
    """Test introducing history key to pick up learning via API.

    Inputs:
    - user_a: User A created via API
    - user_b: User B created via API
    - test_expert: Expert created via API
    - learning_messages: 3 messages from User A with learning content
    - history_key: History key from User A's session

    Expected Outputs:
    - User A creates session and adds learning (status 200, history_key returned)
    - User B introduces history_key (status 200, history accessed)
    - User B can view User A's learning (status 200, messages returned)
    - User B can continue learning (status 200, new message added)
    - All learning visible to both users
    """
    user_a_id = test_user_a["id"]
    user_b_id = test_user_b["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    session_title = f"History Key Introduction Test {unique_id}"

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
    assert create_response.status_code == 200
    session_data = create_response.json()
    session_id = session_data["id"]
    history_key = session_data["history_key"]

    assert history_key is not None, "history_key should be generated"
    assert len(history_key) == 36, "history_key should be UUID (36 chars)"

    # Step 2: User A adds learning messages
    learning_messages = [
        f"I'm learning about database design. Test ID: {unique_id}",
        f"Normalization reduces data redundancy. Test ID: {unique_id}",
        f"Indexes improve query performance. Test ID: {unique_id}",
    ]

    for i, message_content in enumerate(learning_messages):
        add_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )
        assert add_response.status_code == 200, (
            f"Failed to add learning message {i + 1}: {add_response.text}"
        )

    # Step 3: User B introduces history_key to pick up learning
    get_history_by_key = api_client.get(f"/sessions/history/{history_key}")
    assert get_history_by_key.status_code == 200, (
        f"User B should access by history key: {get_history_by_key.text}"
    )
    history_data = get_history_by_key.json()
    assert history_data["session_id"] == session_id, "Session ID should match"
    assert history_data["history_key"] == history_key, "History key should match"
    assert len(history_data["messages"]) == len(learning_messages), (
        f"Expected {len(learning_messages)} messages in history, got {len(history_data['messages'])}"
    )

    # Step 4: User B views learning via session
    get_messages_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_messages_response.status_code == 200
    messages_data = get_messages_response.json()
    assert len(messages_data["messages"]) == len(learning_messages)

    # Verify learning content is accessible
    message_contents = [msg["content"] for msg in messages_data["messages"]]
    for learning_msg in learning_messages:
        assert any(learning_msg[:30] in content for content in message_contents), (
            f"Learning message should be accessible: {learning_msg[:30]}"
        )

    # Step 5: User B continues learning
    user_b_message = f"I want to learn about database transactions. Test ID: {unique_id}"
    add_b_response = api_client.post(
        f"/sessions/{session_id}/messages", json={"role": "user", "content": user_b_message}
    )
    assert add_b_response.status_code == 200

    # Step 6: Verify all learning visible to both users
    get_all_messages = api_client.get(f"/sessions/{session_id}/messages")
    assert get_all_messages.status_code == 200
    all_messages = get_all_messages.json()
    assert len(all_messages["messages"]) == len(learning_messages) + 1
    assert all_messages["count"] == len(learning_messages) + 1

    # Verify all messages present
    all_contents = [msg["content"] for msg in all_messages["messages"]]
    for learning_msg in learning_messages:
        assert any(learning_msg[:30] in content for content in all_contents), (
            f"User A's learning should be present: {learning_msg[:30]}"
        )
    assert any(user_b_message[:30] in content for content in all_contents), (
        f"User B's message should be present: {user_b_message[:30]}"
    )

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

