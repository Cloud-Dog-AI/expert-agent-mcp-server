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
Application Test: AT1.11 - MCP Tool Workflows

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for MCP tool workflows via API endpoints

Related Requirements: FR1.7, FR1.24
Related Tasks: T039, T040, T041, T042, T043
Related Architecture: AI1.2
Related Tests: AT1.11

Recent Changes:
- Refactored to use API endpoints only (no direct manager calls)
- Removed all hard-coded values (all from config system)
- All operations via api_client
- All cleanup via API DELETE endpoints
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
            "Test user credentials not configured. "
            "Set test.user.username/test.user.email/test.user.password in your --env file."
        )

    unique_id = str(uuid.uuid4())[:8]
    return {
        "username": f"{base_username}_mcp_{unique_id}",
        "email": build_test_email("mcp", unique_id, base_email),
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

    # Cleanup via API
    try:
        api_client.delete(f"/users/{user_data['id']}")
    except Exception:
        pass


@pytest.fixture
def test_expert(api_client, test_config):
    """Create test expert via API."""
    # Get LLM config from config system (no hard-coding)
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")

    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_mcp_{unique_id}",
        "title": f"MCP Workflows Expert {unique_id} tools orchestration schemas resources prompts tracing",
        "description": "MCP workflow scenario with unique vocabulary: acorn basil cipher dune ember fjord glyph helios isotope juniper keystone",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "enabled": True,
    }

    response = api_client.post("/experts", json=expert_data)
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
@pytest.mark.req("FR-031")


def test_mcp_chat_workflow(api_client, test_user, test_expert):
    """Test complete MCP chat workflow via API.

    Inputs:
    - test_user: Test user created via API
    - test_expert: Test expert created via API

    Expected Outputs:
    - Session created via API
    - Message added via API
    - Message content validated
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    # Create session via API (what MCP chat tool would do)
    session_response = api_client.post(
        "/sessions",
        json={"user_id": user_id, "expert_config_id": expert_id, "title": "MCP Chat Test"},
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add message via API (what MCP chat tool would do)
    message_response = api_client.post(
        f"/sessions/{session_id}/messages",
        json={"role": "user", "content": "Hello from MCP chat tool"},
    )
    assert message_response.status_code == 200, f"Failed to add message: {message_response.text}"
    message_data = message_response.json()

    # Validate outputs
    assert "id" in message_data, "Message response must contain 'id'"
    assert "content" in message_data, "Message response must contain 'content'"
    assert message_data["content"] == "Hello from MCP chat tool", "Message content must match"

    # Cleanup via API
    api_client.delete(f"/sessions/{session_id}")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_session_management_workflow(api_client, test_user, test_expert):
    """Test MCP session management workflow via API.

    Inputs:
    - test_user: Test user created via API
    - test_expert: Test expert created via API

    Expected Outputs:
    - Session created via API
    - Session retrieved via API
    - Session status validated
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    # Start session via API (what MCP start_session_tool would do)
    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": "MCP Session Management Test",
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Get session status via API (what MCP get_session_status_tool would do)
    status_response = api_client.get(f"/sessions/{session_id}")
    assert status_response.status_code == 200, f"Failed to get session: {status_response.text}"
    status_data = status_response.json()

    # Validate outputs
    assert "id" in status_data, "Session response must contain 'id'"
    assert status_data["id"] == session_id, "Session ID must match"
    assert "status" in status_data, "Session response must contain 'status'"
    assert status_data["status"] is not None, "Session status must not be None"

    # Cleanup via API
    api_client.delete(f"/sessions/{session_id}")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_history_retrieval_workflow(api_client, test_user, test_expert):
    """Test MCP history retrieval workflow via API.

    Inputs:
    - test_user: Test user created via API
    - test_expert: Test expert created via API

    Expected Outputs:
    - Session created via API
    - Messages added via API
    - History retrieved via API
    - History validated (count, roles, content)
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    # Create session via API
    session_response = api_client.post(
        "/sessions",
        json={"user_id": user_id, "expert_config_id": expert_id, "title": "MCP History Test"},
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add multiple messages via API
    messages = [
        {"role": "user", "content": "Question 1"},
        {"role": "assistant", "content": "Answer 1"},
        {"role": "user", "content": "Question 2"},
    ]

    for msg in messages:
        response = api_client.post(f"/sessions/{session_id}/messages", json=msg)
        assert response.status_code == 200, f"Failed to add message: {response.text}"

    # Retrieve history via API (what MCP get_session_history_tool would do)
    history_response = api_client.get(f"/sessions/{session_id}/messages")
    assert history_response.status_code == 200, f"Failed to get history: {history_response.text}"
    history_data = history_response.json()

    # Validate outputs
    assert "messages" in history_data, "History response must contain 'messages'"
    assert isinstance(history_data["messages"], list), "Messages must be a list"
    assert len(history_data["messages"]) == 3, "Should have 3 messages"
    assert history_data["messages"][0]["role"] == "user", "First message should be user"
    assert history_data["messages"][0]["content"] == "Question 1", (
        "First message content must match"
    )
    assert history_data["messages"][1]["role"] == "assistant", "Second message should be assistant"
    assert history_data["messages"][2]["role"] == "user", "Third message should be user"

    # Cleanup via API
    api_client.delete(f"/sessions/{session_id}")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_expert_configuration_workflow(api_client, test_expert):
    """Test MCP expert configuration workflow via API.

    Inputs:
    - test_expert: Test expert created via API

    Expected Outputs:
    - Experts listed via API
    - Expert retrieved via API
    - Expert details validated
    """
    expert_id = test_expert["id"]

    # List experts via API (what MCP list_experts_tool would do)
    list_response = api_client.get("/experts")
    assert list_response.status_code == 200, f"Failed to list experts: {list_response.text}"
    list_data = list_response.json()

    # Validate outputs
    assert "experts" in list_data, "List response must contain 'experts'"
    assert isinstance(list_data["experts"], list), "Experts must be a list"
    expert_ids = [e["id"] for e in list_data["experts"]]
    assert expert_id in expert_ids, "Test expert should be in list"

    # Get expert details via API (what MCP get_expert_tool would do)
    expert_response = api_client.get(f"/experts/{expert_id}")
    assert expert_response.status_code == 200, f"Failed to get expert: {expert_response.text}"
    expert_data = expert_response.json()

    # Validate outputs
    assert "id" in expert_data, "Expert response must contain 'id'"
    assert expert_data["id"] == expert_id, "Expert ID must match"
    assert "name" in expert_data, "Expert response must contain 'name'"
    assert expert_data["name"] == test_expert["name"], "Expert name must match"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_vector_search_workflow(api_client, test_user, test_expert):
    """Test MCP vector search workflow via API.

    Inputs:
    - test_user: Test user created via API
    - test_expert: Test expert created via API

    Expected Outputs:
    - Vector store query via API
    - Results validated
    """
    # Create a dedicated vector store and run a real add+query flow.
    qdrant_host = get_config("vector_stores_config.qdrant._DEFAULT_.host")
    qdrant_port = get_config("vector_stores_config.qdrant._DEFAULT_.port")
    qdrant_api_key = get_config("vector_stores_config.qdrant._DEFAULT_.api_key")
    qdrant_collection = get_config("vector_stores_config.qdrant._DEFAULT_.collection_name")
    if not qdrant_host or qdrant_port is None or qdrant_api_key is None or not qdrant_collection:
        pytest.fail(
            "Qdrant config missing (host/port/api_key/collection_name). Check your --env file."
        )

    unique_id = str(uuid.uuid4())[:8]
    store_name = f"mcp_vector_qdrant_{unique_id}"
    collection_name = f"{qdrant_collection}_{unique_id}"
    create_response = api_client.post(
        "/vector-stores",
        json={
            "name": store_name,
            "store_type": "qdrant",
            "config": {
                "host": qdrant_host,
                "port": int(qdrant_port),
                "api_key": qdrant_api_key,
                # Use configured collection to avoid Qdrant-side collection-creation issues
                "collection_name": collection_name,
            },
            "enabled": True,
        },
    )
    if create_response.status_code == 503 and "not available" in create_response.text.lower():
        pytest.fail(f"Vector store backend unavailable: {create_response.text}")
    assert create_response.status_code == 200, (
        f"Failed to create qdrant vector store: {create_response.text}"
    )
    store_id = create_response.json()["id"]

    try:
        doc_id = str(uuid.uuid4())
        add_response = api_client.post(
            f"/vector-stores/{store_id}/documents",
            json={
                "collection": collection_name,
                "document": f"MCP vector workflow test document {doc_id}",
                "metadata": {"test": True, "doc_id": doc_id},
                "id": doc_id,
            },
        )
        if add_response.status_code == 503 and "not available" in add_response.text.lower():
            pytest.fail(f"Vector store backend unavailable: {add_response.text}")
        assert add_response.status_code == 200, f"Failed to add document: {add_response.text}"

        query_response = api_client.post(
            f"/vector-stores/{store_id}/query",
            json={
                "collection": collection_name,
                "query": doc_id,
                "n_results": 5,
            },
        )
        if query_response.status_code == 503 and "not available" in query_response.text.lower():
            pytest.fail(f"Vector store backend unavailable: {query_response.text}")
        assert query_response.status_code == 200, (
            f"Vector store query failed: {query_response.text}"
        )
        data = query_response.json()
        assert isinstance(data.get("results"), list), f"Query response missing results: {data}"
        assert data.get("count", 0) >= 1, f"Expected at least 1 result, got: {data}"
    finally:
        try:
            api_client.delete(f"/vector-stores/{store_id}")
        except Exception:
            pass
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_complete_conversation_workflow(api_client, test_user, test_expert):
    """Test complete MCP conversation workflow via API.

    Inputs:
    - test_user: Test user created via API
    - test_expert: Test expert created via API

    Expected Outputs:
    - Session created via API
    - Messages added via API
    - History retrieved via API
    - Complete workflow validated
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    # 1. Start session via API
    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": "Complete Conversation Test",
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # 2. Add user message via API
    user_msg_response = api_client.post(
        f"/sessions/{session_id}/messages", json={"role": "user", "content": "What is the weather?"}
    )
    assert user_msg_response.status_code == 200, (
        f"Failed to add user message: {user_msg_response.text}"
    )

    # 3. Add assistant response via API (simulated)
    assistant_msg_response = api_client.post(
        f"/sessions/{session_id}/messages",
        json={"role": "assistant", "content": "I don't have access to weather data."},
    )
    assert assistant_msg_response.status_code == 200, (
        f"Failed to add assistant message: {assistant_msg_response.text}"
    )

    # 4. Retrieve conversation history via API
    history_response = api_client.get(f"/sessions/{session_id}/messages")
    assert history_response.status_code == 200, f"Failed to get history: {history_response.text}"
    history_data = history_response.json()

    # Validate complete workflow
    assert "messages" in history_data, "History response must contain 'messages'"
    assert isinstance(history_data["messages"], list), "Messages must be a list"
    assert len(history_data["messages"]) == 2, "Should have 2 messages"
    assert history_data["messages"][0]["content"] == "What is the weather?", (
        "First message content must match"
    )
    assert history_data["messages"][1]["content"] == "I don't have access to weather data.", (
        "Second message content must match"
    )

    # Cleanup via API
    api_client.delete(f"/sessions/{session_id}")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_mcp_multi_turn_conversation_workflow(api_client, test_user, test_expert):
    """Test MCP multi-turn conversation workflow via API.

    Inputs:
    - test_user: Test user created via API
    - test_expert: Test expert created via API

    Expected Outputs:
    - Session created via API
    - Multiple messages added via API
    - History retrieved via API
    - All turns validated
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    # Create session via API
    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": "Multi-turn Conversation Test",
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Multiple turns via API
    turns = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "How are you?"},
        {"role": "assistant", "content": "I'm doing well, thanks!"},
    ]

    for turn in turns:
        response = api_client.post(f"/sessions/{session_id}/messages", json=turn)
        assert response.status_code == 200, f"Failed to add message: {response.text}"

    # Verify all turns are in history via API
    history_response = api_client.get(f"/sessions/{session_id}/messages")
    assert history_response.status_code == 200, f"Failed to get history: {history_response.text}"
    history_data = history_response.json()

    # Validate outputs
    assert "messages" in history_data, "History response must contain 'messages'"
    assert isinstance(history_data["messages"], list), "Messages must be a list"
    assert len(history_data["messages"]) == 4, "Should have 4 messages"

    # Verify roles match
    for i, turn in enumerate(turns):
        assert history_data["messages"][i]["role"] == turn["role"], f"Message {i} role must match"
        assert history_data["messages"][i]["content"] == turn["content"], (
            f"Message {i} content must match"
        )

    # Cleanup via API
    api_client.delete(f"/sessions/{session_id}")

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.vdb, pytest.mark.smtp, pytest.mark.mcp, pytest.mark.heavy]

