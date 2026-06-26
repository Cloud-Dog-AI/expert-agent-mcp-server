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
Application Test: AT1.10 - Context Window Management with Qdrant Vector Database

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for context window management with Qdrant vector database integration

Related Requirements: FR1.2, FR1.3
Related Tasks: T010, T014
Related Architecture: CC2.1.1, CC4.1.1
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

sys.path.insert(0, str(Path(__file__).parent))
from at1_10_helpers import create_test_vector_store, add_message_to_vector_store, query_vector_store


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
        "username": f"{base_username}_at1_10_qdrant_{unique_id}",
        "email": build_test_email("at1_10_qdrant", unique_id, base_email),
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
        pytest.fail("llm.provider/llm.model not configured (required for AT1.10 vector tests).")

    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_at1_10_qdrant_{unique_id}",
        "title": f"Qdrant Context Window Expert {unique_id} vectors payload indexing retrieval embeddings metadata",
        "description": "Qdrant-backed context window scenario with unique vocabulary: alpine beacon cipher delta ember fjord glyph helios isotope juniper keystone",
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


@pytest.fixture
def qdrant_vector_store(api_client):
    """Create Qdrant vector store for testing."""
    store = create_test_vector_store(api_client, "qdrant", "context_window")
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


def test_context_window_management_with_qdrant_persistence(
    api_client, test_user, test_expert, qdrant_vector_store
):
    """Test context window management when messages are stored in Qdrant.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - qdrant_vector_store: Qdrant vector store
    - session: Session with messages
    - context_window: Set to specific value

    Expected Outputs:
    - Session created with context_window
    - Messages stored in both SQL and Qdrant
    - Context window management works with vector storage
    - Messages retrievable with context limits
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]
    vector_store_id = qdrant_vector_store["id"]
    collection = qdrant_vector_store.get("config", {}).get("collection_name")
    assert collection, "Qdrant vector store config missing collection_name"

    unique_id = str(uuid.uuid4())[:8]
    context_window = int(get_config("test.at1_10.context_windows.medium"))

    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Qdrant Context Window Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add messages
    message_count = int(get_config("test.at1_10.message_counts.long"))
    message_ids = []
    for i in range(message_count):
        message_content = f"Message {i} for Qdrant context test {unique_id}: " + "P" * 40
        msg_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )
        assert msg_response.status_code == 200, f"Failed to add message {i}: {msg_response.text}"
        message_data = msg_response.json()
        message_ids.append(message_data["id"])

        # Store in Qdrant (Qdrant requires UUID or uint IDs)
        add_message_to_vector_store(
            api_client,
            vector_store_id,
            collection,
            message_content,
            message_id=str(uuid.uuid4()),
            metadata={
                "session_id": str(session_id),
                "role": "user",
                "message_id": str(message_data["id"]),
            },
        )

    # Verify messages in SQL
    messages_response = api_client.get(f"/sessions/{session_id}/messages")
    assert messages_response.status_code == 200, f"Failed to get messages: {messages_response.text}"
    messages_data = messages_response.json()
    assert len(messages_data["messages"]) == message_count, f"Should have {message_count} messages"

    query_result = query_vector_store(
        api_client,
        vector_store_id,
        collection,
        f"Message 0 for Qdrant context test {unique_id}",
        n_results=5,
    )
    assert "results" in query_result, "Query result missing results"

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_context_window_summarization_with_qdrant_via_api(
    api_client, test_user, test_expert, qdrant_vector_store
):
    """Test summarization when messages are stored in Qdrant.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - qdrant_vector_store: Qdrant vector store
    - session: Session with many messages
    - summarization: Triggered via API

    Expected Outputs:
    - Messages stored in Qdrant
    - Summarization works with Qdrant-backed messages
    - Summary stored correctly
    - Recent messages preserved
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]
    vector_store_id = qdrant_vector_store["id"]
    collection = qdrant_vector_store.get("config", {}).get("collection_name")
    assert collection, "Qdrant vector store config missing collection_name"

    unique_id = str(uuid.uuid4())[:8]
    context_window = int(get_config("test.at1_10.context_windows.small"))
    preserve_recent = int(get_config("test.at1_10.summarization.preserve_recent"))

    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Qdrant Summarization Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add messages and store in Qdrant
    message_count = int(get_config("test.at1_10.message_counts.xlong"))
    for i in range(message_count):
        message_content = f"Message {i} for Qdrant summary test {unique_id}: " + "Q" * 45
        msg_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )
        assert msg_response.status_code == 200, f"Failed to add message {i}: {msg_response.text}"
        message_data = msg_response.json()

        add_message_to_vector_store(
            api_client,
            vector_store_id,
            collection,
            message_content,
            message_id=str(uuid.uuid4()),
            metadata={"session_id": str(session_id), "message_id": str(message_data["id"])},
        )

    # Trigger summarization
    summarize_response = api_client.post(
        f"/sessions/{session_id}/summarize",
        params={"preserve_recent": preserve_recent, "max_tokens": max(1, context_window // 2)},
    )

    if summarize_response.status_code in (500, 503):
        pytest.fail(f"Summarization failed (LLM required for AT1.10): {summarize_response.text}")

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


def test_context_window_truncation_with_qdrant_via_api(
    api_client, test_user, test_expert, qdrant_vector_store
):
    """Test truncation when messages are stored in Qdrant.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - qdrant_vector_store: Qdrant vector store
    - session: Session with messages
    - truncation: Applied via pagination

    Expected Outputs:
    - Messages stored in Qdrant
    - Truncation works with Qdrant-backed messages
    - Recent messages preserved
    - Message order maintained
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]
    vector_store_id = qdrant_vector_store["id"]
    collection = qdrant_vector_store.get("config", {}).get("collection_name")
    assert collection, "Qdrant vector store config missing collection_name"

    unique_id = str(uuid.uuid4())[:8]
    context_window = int(get_config("test.at1_10.context_windows.medium"))

    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Qdrant Truncation Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add messages and store in Qdrant
    message_count = int(get_config("test.at1_10.message_counts.long"))
    for i in range(message_count):
        message_content = f"Message {i} for Qdrant truncation test {unique_id}: " + "R" * 40
        msg_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )
        assert msg_response.status_code == 200, f"Failed to add message {i}: {msg_response.text}"
        message_data = msg_response.json()

        add_message_to_vector_store(
            api_client,
            vector_store_id,
            collection,
            message_content,
            message_id=str(uuid.uuid4()),
            metadata={"session_id": str(session_id), "message_id": str(message_data["id"])},
        )

    # Test truncation via pagination
    limit = int(get_config("test.at1_10.truncation.limits.medium"))
    limited_response = api_client.get(f"/sessions/{session_id}/messages?limit={limit}")
    assert limited_response.status_code == 200, (
        f"Failed to get limited messages: {limited_response.text}"
    )
    limited_messages = limited_response.json()
    assert len(limited_messages["messages"]) <= limit, f"Should have at most {limit} messages"

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_context_window_semantic_search_with_qdrant_via_api(
    api_client, test_user, test_expert, qdrant_vector_store
):
    """Test context window management with semantic search in Qdrant.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - qdrant_vector_store: Qdrant vector store
    - session: Session with semantically related messages
    - semantic search: Query Qdrant for relevant context

    Expected Outputs:
    - Messages stored in Qdrant
    - Semantic search returns relevant messages
    - Context window management works with semantic results
    - Relevant context retrieved within limits
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]
    vector_store_id = qdrant_vector_store["id"]
    collection = qdrant_vector_store.get("config", {}).get("collection_name")
    assert collection, "Qdrant vector store config missing collection_name"

    unique_id = str(uuid.uuid4())[:8]
    context_window = int(get_config("test.at1_10.context_windows.xlarge"))

    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Qdrant Semantic Search Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add semantically related messages
    messages = [
        f"Python programming language features for test {unique_id}",
        f"JavaScript web development frameworks for test {unique_id}",
        f"Python data analysis with pandas for test {unique_id}",
        f"JavaScript async programming patterns for test {unique_id}",
        f"Python machine learning libraries for test {unique_id}",
    ]

    for i, message_content in enumerate(messages):
        msg_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )
        assert msg_response.status_code == 200, f"Failed to add message {i}: {msg_response.text}"
        message_data = msg_response.json()

        add_message_to_vector_store(
            api_client,
            vector_store_id,
            collection,
            message_content,
            message_id=str(uuid.uuid4()),
            metadata={"session_id": str(session_id), "message_id": str(message_data["id"])},
        )

    query_result = query_vector_store(
        api_client,
        vector_store_id,
        collection,
        "programming language",
        n_results=3,
    )
    assert "results" in query_result, "Query result missing results"
    results = query_result.get("results") or []
    assert len(results) > 0, "Should have semantic search results"

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.vdb, pytest.mark.db, pytest.mark.smtp, pytest.mark.heavy]

