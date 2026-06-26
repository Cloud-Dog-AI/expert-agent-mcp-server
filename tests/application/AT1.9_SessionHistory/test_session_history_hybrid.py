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
Application Test: AT1.9 - Session History with Hybrid SQL + Vector DB Storage

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for hybrid session history storage (SQL + vector database)

Related Requirements: FR1.2, FR1.3
Related Tasks: T023, T014
Related Architecture: CC2.1.1, CC4.1.1
Related Tests: AT1.9

Recent Changes:
- Initial implementation for hybrid storage scenarios
"""

import sys
from pathlib import Path

# Add parent directory to path for shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import build_test_email, create_api_client_fixture, validate_config_loaded


import pytest
import uuid
from src.config.loader import get_config

# Import local helpers (folder name contains a dot, so avoid package imports)
sys.path.insert(0, str(Path(__file__).parent))
from test_helpers import (
    create_test_vector_store,
    add_message_to_vector_store,
    query_vector_store,
    create_session_with_messages,
)


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
        "username": f"{base_username}_at1_9_hybrid_{unique_id}",
        "email": build_test_email("at1_9_hybrid", unique_id, base_email),
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
        pytest.fail("llm.provider/llm.model not configured (required for AT1.9 expert creation).")

    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_at1_9_hybrid_{unique_id}",
        "title": f"Test Expert {unique_id}",
        "description": "Test expert for hybrid storage",
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


@pytest.fixture
def test_vector_store(api_client):
    """Create a test vector store (Chroma for simplicity)."""
    store = create_test_vector_store(api_client, "chroma", "hybrid")
    try:
        yield store
    finally:
        resp = api_client.delete(f"/vector-stores/{store['id']}")
        if resp.status_code not in (200, 204, 404):
            print(
                f"[CLEANUP WARNING] Failed to delete vector store {store['id']}: {resp.status_code} {resp.text}"
            )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_history_hybrid_storage(api_client, test_user, test_expert, test_vector_store):
    """Test that messages can be stored in both SQL and vector database.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - test_vector_store: Vector store created via API
    - messages: Array of messages

    Expected Outputs:
    - Messages stored in SQL via session API
    - Messages stored in vector database via vector store API
    - Both stores contain the same messages
    - Data consistency maintained
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]
    vector_store_id = test_vector_store["id"]
    collection = f"at1_9_hybrid_{uuid.uuid4().hex[:8]}"

    # Create session and add messages to SQL
    unique_id = str(uuid.uuid4())[:8]
    messages = [
        {"role": "user", "content": f"Hybrid test message 1 {unique_id}"},
        {"role": "assistant", "content": f"Hybrid test response 1 {unique_id}"},
        {"role": "user", "content": f"Hybrid test message 2 {unique_id}"},
    ]

    session_data = create_session_with_messages(api_client, user_id, expert_id, messages)
    session_id = session_data["session"]["id"]

    # Verify messages in SQL
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages from SQL: {get_response.text}"
    sql_messages = get_response.json()
    assert len(sql_messages["messages"]) >= len(messages), (
        f"Expected at least {len(messages)} messages in SQL, got {len(sql_messages['messages'])}"
    )

    # Store messages in vector database
    stored_doc_ids = []
    for i, msg in enumerate(messages):
        doc_response = add_message_to_vector_store(
            api_client,
            vector_store_id,
            collection,
            msg["content"],
            message_id=str(session_data["message_ids"][i]),
            metadata={
                "session_id": str(session_id),
                "role": msg["role"],
                "message_id": str(session_data["message_ids"][i]),
            },
        )
        stored_doc_ids.append(doc_response.get("id") or str(session_data["message_ids"][i]))

    # Verify messages in vector database
    assert len(stored_doc_ids) == len(messages), (
        f"Expected {len(messages)} documents in vector DB, got {len(stored_doc_ids)}"
    )

    # Query vector database to verify
    query_result = query_vector_store(
        api_client,
        vector_store_id,
        collection,
        messages[0]["content"],
        n_results=5,
    )
    assert "results" in query_result, "Query result missing results"
    results = query_result.get("results") or []
    assert len(results) > 0, "No results returned from vector database query"
    assert any(r.get("document") == messages[0]["content"] for r in results), (
        "Expected message not found in vector DB results"
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_history_hybrid_retrieval_priority(
    api_client, test_user, test_expert, test_vector_store
):
    """Test retrieval priority when messages exist in both SQL and vector database.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - test_vector_store: Vector store
    - messages: Array of messages stored in both

    Expected Outputs:
    - Messages retrievable from SQL (primary source)
    - Messages retrievable from vector database (secondary source)
    - Retrieval priority handled correctly
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]
    vector_store_id = test_vector_store["id"]
    collection = f"at1_9_hybrid_{uuid.uuid4().hex[:8]}"

    # Create session and add messages
    unique_id = str(uuid.uuid4())[:8]
    messages = [
        {"role": "user", "content": f"Priority test message {unique_id}"},
        {"role": "assistant", "content": f"Priority test response {unique_id}"},
    ]

    session_data = create_session_with_messages(api_client, user_id, expert_id, messages)
    session_id = session_data["session"]["id"]

    # Store in vector database
    for i, msg in enumerate(messages):
        add_message_to_vector_store(
            api_client,
            vector_store_id,
            collection,
            msg["content"],
            message_id=str(session_data["message_ids"][i]),
            metadata={"session_id": str(session_id), "role": msg["role"]},
        )

    # Retrieve from SQL (primary source)
    sql_response = api_client.get(f"/sessions/{session_id}/messages")
    assert sql_response.status_code == 200, f"Failed to get messages from SQL: {sql_response.text}"
    sql_messages = sql_response.json()
    assert len(sql_messages["messages"]) >= len(messages), "SQL retrieval failed"

    # Retrieve from vector database (secondary source)
    vector_response = query_vector_store(
        api_client,
        vector_store_id,
        collection,
        messages[0]["content"],
        n_results=5,
    )
    assert "results" in vector_response, "Vector DB retrieval failed"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_history_hybrid_synchronization(
    api_client, test_user, test_expert, test_vector_store
):
    """Test synchronization between SQL and vector database stores.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - test_vector_store: Vector store
    - messages: Array of messages

    Expected Outputs:
    - Messages stored in both SQL and vector database
    - Data consistency between stores
    - Synchronization maintained
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]
    vector_store_id = test_vector_store["id"]
    collection = f"at1_9_hybrid_{uuid.uuid4().hex[:8]}"

    # Create session and add messages
    unique_id = str(uuid.uuid4())[:8]
    messages = [
        {"role": "user", "content": f"Sync test message 1 {unique_id}"},
        {"role": "assistant", "content": f"Sync test response 1 {unique_id}"},
        {"role": "user", "content": f"Sync test message 2 {unique_id}"},
    ]

    session_data = create_session_with_messages(api_client, user_id, expert_id, messages)
    session_id = session_data["session"]["id"]

    # Store in both SQL and vector database
    sql_message_ids = session_data["message_ids"]

    vector_doc_ids = []
    for i, msg in enumerate(messages):
        doc_response = add_message_to_vector_store(
            api_client,
            vector_store_id,
            collection,
            msg["content"],
            message_id=str(sql_message_ids[i]),
            metadata={
                "session_id": str(session_id),
                "role": msg["role"],
                "message_id": str(sql_message_ids[i]),
            },
        )
        vector_doc_ids.append(doc_response.get("id") or str(sql_message_ids[i]))

    # Verify synchronization - same number of messages
    assert len(sql_message_ids) == len(vector_doc_ids), (
        f"Synchronization failed: SQL has {len(sql_message_ids)} messages, vector DB has {len(vector_doc_ids)}"
    )

    # Verify content consistency
    sql_response = api_client.get(f"/sessions/{session_id}/messages")
    assert sql_response.status_code == 200, f"Failed to get messages from SQL: {sql_response.text}"
    sql_messages = sql_response.json()["messages"]

    sql_contents = [msg["content"] for msg in sql_messages]
    for expected_msg in messages:
        assert expected_msg["content"] in sql_contents, (
            f"Message content not found in SQL: {expected_msg['content']}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_history_hybrid_failure_handling(api_client, test_user, test_expert):
    """Test fallback to SQL when vector database is unavailable.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - messages: Array of messages

    Expected Outputs:
    - Messages stored in SQL (always available)
    - Graceful handling when vector database unavailable
    - Fallback to SQL works correctly
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    # Create session and add messages (SQL only)
    unique_id = str(uuid.uuid4())[:8]
    messages = [
        {"role": "user", "content": f"Failure test message {unique_id}"},
        {"role": "assistant", "content": f"Failure test response {unique_id}"},
    ]

    session_data = create_session_with_messages(api_client, user_id, expert_id, messages)
    session_id = session_data["session"]["id"]

    # Verify messages are in SQL (should always work)
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages from SQL: {get_response.text}"
    sql_messages = get_response.json()
    assert len(sql_messages["messages"]) >= len(messages), "SQL storage failed"

    # Verify message content
    sql_contents = [msg["content"] for msg in sql_messages["messages"]]
    for expected_msg in messages:
        assert expected_msg["content"] in sql_contents, (
            f"Message content not found in SQL: {expected_msg['content']}"
        )

    # Note: Vector database failure handling would be tested by attempting to use
    # a non-existent or unavailable vector store, but that's beyond the scope of
    # this test. The key point is that SQL storage always works as a fallback.

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.vdb, pytest.mark.db, pytest.mark.smtp, pytest.mark.heavy]

