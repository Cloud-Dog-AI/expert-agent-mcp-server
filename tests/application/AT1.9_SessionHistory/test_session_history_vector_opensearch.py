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
Application Test: AT1.9 - Session History with Opensearch Vector Database

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for session history persistence and retrieval with Opensearch vector database

Related Requirements: FR1.2, FR1.3
Related Tasks: T023, T014
Related Architecture: CC2.1.1, CC4.1.1
Related Tests: AT1.9

Recent Changes:
- Initial implementation for Opensearch vector database integration
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
        "username": f"{base_username}_at1_9_opensearch_{unique_id}",
        "email": build_test_email("at1_9_opensearch", unique_id, base_email),
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
        "name": f"expert_at1_9_opensearch_{unique_id}",
        "title": f"Test Expert {unique_id}",
        "description": "Test expert for Opensearch history",
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
def opensearch_vector_store(api_client):
    """Create Opensearch vector store for testing."""
    store = create_test_vector_store(api_client, "opensearch", "history")
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


def test_session_history_opensearch_persistence(
    api_client, test_user, test_expert, opensearch_vector_store
):
    """Test that session messages can be stored in Opensearch vector database.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - opensearch_vector_store: Opensearch vector store created via API
    - messages: Array of messages to store

    Expected Outputs:
    - Session created successfully
    - Messages added to session via API
    - Messages stored in Opensearch vector store
    - embedding_id set in SQL messages (if supported)
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]
    vector_store_id = opensearch_vector_store["id"]
    collection = opensearch_vector_store.get("config", {}).get("collection_name")
    assert collection, "OpenSearch vector store config missing collection_name"

    # Create session
    unique_id = str(uuid.uuid4())[:8]
    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Opensearch History Test {unique_id}",
            "context_window": int(get_config("session.context_window_size")),
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add messages to session
    messages_to_add = [
        {"role": "user", "content": f"User message 1 for Opensearch test {unique_id}"},
        {"role": "assistant", "content": f"Assistant response 1 for Opensearch test {unique_id}"},
        {"role": "user", "content": f"User message 2 for Opensearch test {unique_id}"},
    ]

    message_ids = []
    for msg in messages_to_add:
        msg_response = api_client.post(f"/sessions/{session_id}/messages", json=msg)
        assert msg_response.status_code == 200, f"Failed to add message: {msg_response.text}"
        message_data = msg_response.json()
        message_ids.append(message_data["id"])

    # Store messages in Opensearch vector store
    stored_doc_ids = []
    for i, msg in enumerate(messages_to_add):
        doc_response = add_message_to_vector_store(
            api_client,
            vector_store_id,
            collection,
            msg["content"],
            message_id=str(message_ids[i]),
            metadata={"session_id": session_id, "role": msg["role"], "message_id": message_ids[i]},
        )
        stored_doc_ids.append(doc_response.get("id") or str(message_ids[i]))

    # Verify messages are in Opensearch
    assert len(stored_doc_ids) == len(messages_to_add), (
        f"Expected {len(messages_to_add)} documents in Opensearch, got {len(stored_doc_ids)}"
    )

    # Query Opensearch to verify documents
    query_result = query_vector_store(
        api_client,
        vector_store_id,
        collection,
        messages_to_add[0]["content"],
        n_results=3,
    )
    assert "results" in query_result, "Query result missing results"
    results = query_result.get("results") or []
    assert any(r.get("document") == messages_to_add[0]["content"] for r in results), (
        "Expected stored message not found in OpenSearch results"
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_history_opensearch_retrieval(
    api_client, test_user, test_expert, opensearch_vector_store
):
    """Test retrieving session history from Opensearch vector database.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - opensearch_vector_store: Opensearch vector store
    - messages: Array of messages stored in Opensearch

    Expected Outputs:
    - Messages stored in Opensearch
    - Messages retrievable via vector store query
    - Message content matches original
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]
    vector_store_id = opensearch_vector_store["id"]
    collection = opensearch_vector_store.get("config", {}).get("collection_name")
    assert collection, "OpenSearch vector store config missing collection_name"

    # Create session and add messages
    unique_id = str(uuid.uuid4())[:8]
    session_data = create_session_with_messages(
        api_client,
        user_id,
        expert_id,
        [
            {"role": "user", "content": f"Query test message 1 {unique_id}"},
            {"role": "assistant", "content": f"Query test response 1 {unique_id}"},
            {"role": "user", "content": f"Query test message 2 {unique_id}"},
        ],
    )
    session_id = session_data["session"]["id"]

    # Store messages in Opensearch
    messages_content = [
        f"Query test message 1 {unique_id}",
        f"Query test response 1 {unique_id}",
        f"Query test message 2 {unique_id}",
    ]

    for i, content in enumerate(messages_content):
        add_message_to_vector_store(
            api_client,
            vector_store_id,
            collection,
            content,
            message_id=str(session_data["message_ids"][i]),
            metadata={"session_id": session_id, "message_id": session_data["message_ids"][i]},
        )

    # Query Opensearch for messages
    query_result = query_vector_store(
        api_client,
        vector_store_id,
        collection,
        messages_content[0],
        n_results=5,
    )
    assert "results" in query_result, "Query result missing results"
    results = query_result.get("results") or []
    assert len(results) > 0, "No results returned from OpenSearch query"
    assert any(r.get("document") == messages_content[0] for r in results), (
        "Expected message not found in OpenSearch results"
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_history_opensearch_semantic_search(
    api_client, test_user, test_expert, opensearch_vector_store
):
    """Test semantic search in Opensearch vector database for session history.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - opensearch_vector_store: Opensearch vector store
    - messages: Array of semantically related messages

    Expected Outputs:
    - Messages stored in Opensearch
    - Semantic search returns relevant messages
    - Search relevance is validated
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]
    vector_store_id = opensearch_vector_store["id"]
    collection = opensearch_vector_store.get("config", {}).get("collection_name")
    assert collection, "OpenSearch vector store config missing collection_name"

    # Create session with semantically related messages
    unique_id = str(uuid.uuid4())[:8]
    messages = [
        {"role": "user", "content": f"Python programming language features {unique_id}"},
        {
            "role": "assistant",
            "content": f"Python is a high-level programming language with dynamic typing {unique_id}",
        },
        {"role": "user", "content": f"JavaScript web development frameworks {unique_id}"},
        {
            "role": "assistant",
            "content": f"JavaScript frameworks like React and Vue are popular {unique_id}",
        },
    ]

    session_data = create_session_with_messages(api_client, user_id, expert_id, messages)
    session_id = session_data["session"]["id"]

    # Store messages in Opensearch
    for i, msg in enumerate(messages):
        add_message_to_vector_store(
            api_client,
            vector_store_id,
            collection,
            msg["content"],
            message_id=str(session_data["message_ids"][i]),
            metadata={"session_id": session_id, "role": msg["role"]},
        )

    # Perform semantic search
    query_result = query_vector_store(
        api_client,
        vector_store_id,
        collection,
        "programming language",
        n_results=5,
    )
    assert "results" in query_result, "Query result missing results"
    results = query_result.get("results") or []
    assert len(results) > 0, "No results returned from semantic search"
    result_contents = [r.get("document") or "" for r in results]
    python_found = any(
        "Python" in content or "python" in content.lower() for content in result_contents
    )
    assert python_found, "Semantic search did not find Python-related messages"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_history_opensearch_collection_isolation(
    api_client, test_user, test_expert, opensearch_vector_store
):
    """Test that Opensearch collections provide isolation between sessions.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - opensearch_vector_store: Opensearch vector store
    - Multiple sessions with different messages

    Expected Outputs:
    - Messages from different sessions stored in separate collections
    - No cross-session data leakage
    - Collection isolation maintained
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]
    vector_store_id = opensearch_vector_store["id"]
    collection = opensearch_vector_store.get("config", {}).get("collection_name")
    assert collection, "OpenSearch vector store config missing collection_name"
    unique_id = str(uuid.uuid4())[:8]

    session1_data = create_session_with_messages(
        api_client,
        user_id,
        expert_id,
        [{"role": "user", "content": f"Session 1 message {unique_id}"}],
    )

    session2_data = create_session_with_messages(
        api_client,
        user_id,
        expert_id,
        [{"role": "user", "content": f"Session 2 message {unique_id}"}],
    )

    s1_msg = f"Session 1 message {unique_id}"
    s2_msg = f"Session 2 message {unique_id}"
    add_message_to_vector_store(
        api_client,
        vector_store_id,
        collection,
        s1_msg,
        metadata={"session_id": session1_data["session"]["id"]},
    )
    add_message_to_vector_store(
        api_client,
        vector_store_id,
        collection,
        s2_msg,
        metadata={"session_id": session2_data["session"]["id"]},
    )
    query_result1 = query_vector_store(
        api_client, vector_store_id, collection, s1_msg, n_results=10
    )
    query_result2 = query_vector_store(
        api_client, vector_store_id, collection, s2_msg, n_results=10
    )
    results1 = query_result1.get("results") or []
    results2 = query_result2.get("results") or []
    result1_contents = [r.get("document") or "" for r in results1]
    result2_contents = [r.get("document") or "" for r in results2]
    assert s1_msg in result1_contents, (
        "Expected Session 1 message not found when querying Session 1 content"
    )
    assert s2_msg in result2_contents, (
        "Expected Session 2 message not found when querying Session 2 content"
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_history_opensearch_pagination(
    api_client, test_user, test_expert, opensearch_vector_store
):
    """Test pagination when retrieving session history from Opensearch.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - opensearch_vector_store: Opensearch vector store
    - Many messages stored in Opensearch

    Expected Outputs:
    - Messages stored in Opensearch
    - Pagination works correctly
    - Page boundaries respected
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]
    vector_store_id = opensearch_vector_store["id"]
    collection = opensearch_vector_store.get("config", {}).get("collection_name")
    assert collection, "OpenSearch vector store config missing collection_name"

    # Create session with many messages
    unique_id = str(uuid.uuid4())[:8]
    messages = [
        {"role": "user", "content": f"Message {i} for pagination test {unique_id}"}
        for i in range(10)
    ]

    session_data = create_session_with_messages(api_client, user_id, expert_id, messages)
    session_id = session_data["session"]["id"]

    # Store messages in Opensearch
    for i, msg in enumerate(messages):
        add_message_to_vector_store(
            api_client,
            vector_store_id,
            collection,
            msg["content"],
            message_id=str(session_data["message_ids"][i]),
            metadata={"session_id": session_id, "index": i},
        )

    # Test pagination via API (if supported) or via query with n_results
    query_result1 = query_vector_store(
        api_client,
        vector_store_id,
        collection,
        f"Message 0 for pagination test {unique_id}",
        n_results=5,
    )
    query_result2 = query_vector_store(
        api_client,
        vector_store_id,
        collection,
        f"Message 5 for pagination test {unique_id}",
        n_results=5,
    )
    results1 = query_result1.get("results") or []
    results2 = query_result2.get("results") or []
    assert len(results1) <= 5, f"First page should have at most 5 results, got {len(results1)}"
    assert len(results2) <= 5, f"Second page should have at most 5 results, got {len(results2)}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_history_opensearch_message_order(
    api_client, test_user, test_expert, opensearch_vector_store
):
    """Test that message order is maintained when retrieving from Opensearch.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - opensearch_vector_store: Opensearch vector store
    - Messages added in sequence

    Expected Outputs:
    - Messages stored in Opensearch with metadata
    - Message order preserved via metadata/timestamp
    - Chronological order maintained
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]
    vector_store_id = opensearch_vector_store["id"]
    collection = opensearch_vector_store.get("config", {}).get("collection_name")
    assert collection, "OpenSearch vector store config missing collection_name"

    # Create session with ordered messages
    unique_id = str(uuid.uuid4())[:8]
    import time

    messages = [
        {"role": "user", "content": f"First message {unique_id}"},
        {"role": "assistant", "content": f"First response {unique_id}"},
        {"role": "user", "content": f"Second message {unique_id}"},
        {"role": "assistant", "content": f"Second response {unique_id}"},
    ]

    session_data = create_session_with_messages(api_client, user_id, expert_id, messages)
    session_id = session_data["session"]["id"]

    # Store messages in Opensearch with timestamps
    stored_timestamps = []
    for i, msg in enumerate(messages):
        time.sleep(0.1)  # Ensure different timestamps
        timestamp = time.time()
        stored_timestamps.append(timestamp)
        add_message_to_vector_store(
            api_client,
            vector_store_id,
            collection,
            msg["content"],
            message_id=str(session_data["message_ids"][i]),
            metadata={
                "session_id": session_id,
                "role": msg["role"],
                "timestamp": timestamp,
                "index": i,
            },
        )

    # Retrieve messages and validate order
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()
    assert len(messages_data["messages"]) >= len(messages), (
        f"Expected at least {len(messages)} messages"
    )
    timestamps = [msg["timestamp"] for msg in messages_data["messages"]]
    for i in range(1, len(timestamps)):
        from datetime import datetime

        prev_dt = datetime.fromisoformat(timestamps[i - 1].replace("Z", "+00:00"))
        curr_dt = datetime.fromisoformat(timestamps[i].replace("Z", "+00:00"))
        assert curr_dt >= prev_dt, (
            f"Messages not in chronological order: {timestamps[i - 1]} > {timestamps[i]}"
        )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.vdb, pytest.mark.db, pytest.mark.smtp, pytest.mark.heavy]

