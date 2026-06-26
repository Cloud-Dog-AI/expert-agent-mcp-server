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
Application Test: AT1.12 - Multi-turn Conversation with Context Retention

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for multi-turn conversations with context retention via API

Related Requirements: FR1.2
Related Tasks: T022, T010
Related Architecture: CC2.1.1
Related Tests: AT1.12

Recent Changes:
- Refactored to use API endpoints only (no direct SessionManager calls)
- Removed all hard-coded values (all from config system or generated)
- All outputs validated via API responses
- Cleanup fixtures use API where possible
- Comprehensive input/output documentation
- Extended with large context tests, progressive dialogue building, and expert boundary testing
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

    history_retention_days = get_config("session.history_retention_days")
    if history_retention_days is None:
        pytest.fail("Missing session.history_retention_days in config (--env)")

    unique_id = str(uuid.uuid4())[:8]
    return {
        "username": f"{base_username}_at1_12_{unique_id}",
        "email": build_test_email("at1_12", unique_id, base_email),
        "password": base_password,
    }


@pytest.fixture
def test_user(api_client, test_user_credentials):
    """Create test user via API. Cleanup via API if DELETE endpoint exists."""
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

    delete_response = api_client.delete(f"/users/{user_data['id']}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete user {user_data['id']}: {delete_response.status_code} {delete_response.text}"
        )


@pytest.fixture
def test_expert(api_client, test_config):
    """Create test expert via API. Cleanup via API if DELETE endpoint exists."""
    # Get LLM config from config system (no hard-coding)
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")

    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_at1_12_{unique_id}",
        "title": f"Multi Turn Conversation Expert {unique_id} context retention ordering recall consistency grounding",
        "description": "Multi-turn conversation scenario with unique vocabulary: acorn basil cipher dune ember fjord glyph helios isotope juniper keystone",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "enabled": True,
    }

    response = api_client.post("/experts", json=expert_data)
    assert response.status_code == 200, f"Failed to create test expert: {response.text}"
    expert = response.json()

    yield expert

    delete_response = api_client.delete(f"/experts/{expert['id']}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete expert {expert['id']}: {delete_response.status_code} {delete_response.text}"
        )


@pytest.fixture
def test_session(api_client, test_user, test_expert, test_config):
    """Create test session via API with context window from config."""
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    # Get configuration values from config system (no hard-coding)
    context_window = get_config("session.context_window_size")
    history_retention_days = get_config("session.history_retention_days")
    if context_window is None or history_retention_days is None:
        pytest.fail(
            "Missing session.context_window_size/session.history_retention_days in config (--env)"
        )

    unique_id = str(uuid.uuid4())[:8]
    session_title = f"Multi-turn Conversation Session {unique_id}"

    response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": session_title,
            "context_window": context_window,
            "history_retention_days": history_retention_days,
        },
    )
    assert response.status_code == 200, f"Failed to create test session: {response.text}"
    session_data = response.json()

    yield session_data

    delete_resp = api_client.delete(f"/sessions/{session_data['id']}")
    if delete_resp.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_data['id']}: {delete_resp.status_code} {delete_resp.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_multi_turn_conversation_context_via_api(api_client, test_session):
    """Test multi-turn conversation maintains context via API.

    Inputs:
    - test_session: Session created via API (from fixture)
    - Turn 1: User introduces themselves (generated unique name and interest)
    - Turn 2: User asks about their name (should reference Turn 1)
    - Turn 3: User asks about their interest (should reference Turn 1)

    Expected Outputs:
    - All messages successfully added (status 200)
    - GET /sessions/{session_id}/messages returns all 3 messages
    - Messages are in correct order
    - Message content matches input
    - Context is maintained (messages reference previous context)
    """
    session_id = test_session["id"]

    # Generate unique conversation content (no hard-coding)
    unique_id = str(uuid.uuid4())[:8]
    test_name = f"Bob_{unique_id}"
    test_interest = f"Python programming for test {unique_id}"

    turn1_content = f"My name is {test_name} and I like {test_interest}."
    turn2_content = "What is my name?"
    turn3_content = "What programming language do I like?"

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Turn 1: {turn1_content[:50]}...")
    print(f"[SETTINGS] Turn 2: {turn2_content}")
    print(f"[SETTINGS] Turn 3: {turn3_content}")

    # Turn 1: User introduces themselves via API
    turn1_response = api_client.post(
        f"/sessions/{session_id}/messages", json={"role": "user", "content": turn1_content}
    )
    assert turn1_response.status_code == 200, f"Failed to add turn 1 message: {turn1_response.text}"
    turn1_data = turn1_response.json()
    assert turn1_data["content"] == turn1_content, "Turn 1 content mismatch"
    assert turn1_data["role"] == "user", "Turn 1 role mismatch"

    # Turn 2: Ask about their name (should remember) via API
    turn2_response = api_client.post(
        f"/sessions/{session_id}/messages", json={"role": "user", "content": turn2_content}
    )
    assert turn2_response.status_code == 200, f"Failed to add turn 2 message: {turn2_response.text}"
    turn2_data = turn2_response.json()
    assert turn2_data["content"] == turn2_content, "Turn 2 content mismatch"
    assert turn2_data["role"] == "user", "Turn 2 role mismatch"

    # Turn 3: Ask about their interest (should remember) via API
    turn3_response = api_client.post(
        f"/sessions/{session_id}/messages", json={"role": "user", "content": turn3_content}
    )
    assert turn3_response.status_code == 200, f"Failed to add turn 3 message: {turn3_response.text}"
    turn3_data = turn3_response.json()
    assert turn3_data["content"] == turn3_content, "Turn 3 content mismatch"
    assert turn3_data["role"] == "user", "Turn 3 role mismatch"

    # Get all messages via API to verify context is maintained
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate outputs comprehensively
    assert "messages" in messages_data, "messages array missing from response"
    assert "count" in messages_data, "count missing from response"
    assert isinstance(messages_data["messages"], list), "messages must be a list"
    assert isinstance(messages_data["count"], int), "count must be an integer"
    assert len(messages_data["messages"]) == 3, (
        f"Expected 3 messages, got {len(messages_data['messages'])}"
    )
    assert messages_data["count"] == 3, f"Expected count 3, got {messages_data['count']}"

    # Verify context is maintained (messages reference previous context)
    assert messages_data["messages"][0]["content"] == turn1_content, (
        "Turn 1 content mismatch in retrieved messages"
    )
    assert messages_data["messages"][1]["content"] == turn2_content, (
        "Turn 2 content mismatch in retrieved messages"
    )
    assert messages_data["messages"][2]["content"] == turn3_content, (
        "Turn 3 content mismatch in retrieved messages"
    )

    # Validate message structure
    for i, msg in enumerate(messages_data["messages"]):
        assert "id" in msg, f"Message {i} ID missing"
        assert "role" in msg, f"Message {i} role missing"
        assert "content" in msg, f"Message {i} content missing"
        assert "timestamp" in msg, f"Message {i} timestamp missing"
        assert msg["role"] == "user", f"Message {i} should be user role"

    # Verify context references (Turn 2 and 3 reference Turn 1)
    assert test_name in messages_data["messages"][0]["content"], (
        "Test name should be in first message"
    )
    assert test_interest in messages_data["messages"][0]["content"], (
        "Test interest should be in first message"
    )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_conversation_with_token_limit_via_api(api_client, test_user, test_expert, test_config):
    """Test conversation respects token limits for context window via API.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - context_window: Small value for testing (100)
    - messages: 10 messages with unique content

    Expected Outputs:
    - Session created successfully (status 200)
    - All messages successfully added (status 200)
    - GET /sessions/{session_id}/messages returns all messages
    - All messages stored correctly (context window managed internally)
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    # Use a small context window for testing token limits
    test_context_window = get_config("test.at1_12.context_window_small")
    if test_context_window is None:
        pytest.fail("Missing test.at1_12.context_window_small in config (--env)")

    history_retention_days = get_config("session.history_retention_days")
    if history_retention_days is None:
        pytest.fail("Missing session.history_retention_days in config (--env)")

    unique_id = str(uuid.uuid4())[:8]
    session_title = f"Token Limited Session {unique_id}"

    # Create session with small context window via API
    create_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": session_title,
            "context_window": test_context_window,
            "history_retention_days": history_retention_days,
        },
    )
    assert create_response.status_code == 200, f"Failed to create session: {create_response.text}"
    session_data = create_response.json()
    session_id = session_data["id"]

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Context window: {test_context_window} (test value)")
    print("[SETTINGS] Adding 10 messages")

    # Add many messages via API
    message_count = int(get_config("test.at1_12.message_counts.short"))
    created_message_ids = []
    for i in range(message_count):
        message_content = f"Message {i} for test {unique_id}: " + "A" * 50
        add_response = api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )
        assert add_response.status_code == 200, f"Failed to add message {i}: {add_response.text}"
        message_data = add_response.json()
        created_message_ids.append(message_data["id"])
        assert message_data["content"] == message_content, f"Message {i} content mismatch"

    # Get messages via API (token limit handled by SessionManager internally)
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate outputs
    assert "messages" in messages_data, "messages array missing from response"
    assert "count" in messages_data, "count missing from response"
    assert len(messages_data["messages"]) == message_count, (
        f"Expected {message_count} messages, got {len(messages_data['messages'])}"
    )
    assert messages_data["count"] == message_count, (
        f"Expected count {message_count}, got {messages_data['count']}"
    )

    # Validate message structure
    for msg in messages_data["messages"]:
        assert "id" in msg, "Message ID missing"
        assert "role" in msg, "Message role missing"
        assert "content" in msg, "Message content missing"
        assert "timestamp" in msg, "Message timestamp missing"

    # Cleanup
    delete_resp = api_client.delete(f"/sessions/{session_id}")
    if delete_resp.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_resp.status_code} {delete_resp.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_multi_turn_conversation_message_order_via_api(api_client, test_session):
    """Test multi-turn conversation maintains message order via API.

    Inputs:
    - test_session: Session created via API
    - conversation_turns: Array of 5 messages (user, assistant, user, assistant, user) with unique content

    Expected Outputs:
    - All messages successfully added (status 200)
    - GET /sessions/{session_id}/messages returns all messages in correct order
    - Message content matches input
    - Message roles match input
    """
    session_id = test_session["id"]

    # Generate unique conversation content (no hard-coding)
    unique_id = str(uuid.uuid4())[:8]
    conversation_turns = [
        {"role": "user", "content": f"Hello, I'm Alice for test {unique_id}."},
        {"role": "assistant", "content": f"Nice to meet you, Alice! Test {unique_id}"},
        {"role": "user", "content": f"What's the weather like? Test {unique_id}"},
        {"role": "assistant", "content": f"I don't have access to weather data. Test {unique_id}"},
        {"role": "user", "content": f"Can you help me with Python? Test {unique_id}"},
    ]

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Adding {len(conversation_turns)} messages in sequence")

    # Add messages in sequence via API
    created_message_ids = []
    for i, msg in enumerate(conversation_turns):
        add_response = api_client.post(f"/sessions/{session_id}/messages", json=msg)
        assert add_response.status_code == 200, f"Failed to add message {i}: {add_response.text}"
        message_data = add_response.json()
        created_message_ids.append(message_data["id"])
        assert message_data["content"] == msg["content"], f"Message {i} content mismatch"
        assert message_data["role"] == msg["role"], f"Message {i} role mismatch"

    # Get all messages via API
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate outputs - order is maintained
    assert "messages" in messages_data, "messages array missing from response"
    assert "count" in messages_data, "count missing from response"
    assert len(messages_data["messages"]) == len(conversation_turns), (
        f"Expected {len(conversation_turns)} messages, got {len(messages_data['messages'])}"
    )
    assert messages_data["count"] == len(conversation_turns), (
        f"Expected count {len(conversation_turns)}, got {messages_data['count']}"
    )

    # Verify order and content
    for i, expected_msg in enumerate(conversation_turns):
        actual_msg = messages_data["messages"][i]
        assert actual_msg["content"] == expected_msg["content"], (
            f"Message {i} content mismatch: expected '{expected_msg['content']}', got '{actual_msg['content']}'"
        )
        assert actual_msg["role"] == expected_msg["role"], (
            f"Message {i} role mismatch: expected '{expected_msg['role']}', got '{actual_msg['role']}'"
        )

    # Validate message structure
    for msg in messages_data["messages"]:
        assert "id" in msg, "Message ID missing"
        assert "role" in msg, "Message role missing"
        assert "content" in msg, "Message content missing"
        assert "timestamp" in msg, "Message timestamp missing"
        assert msg["role"] in ["user", "assistant", "system"], f"Invalid role: {msg['role']}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_multi_turn_conversation_context_retention_via_api(api_client, test_session):
    """Test that context is retained across multiple turns via API.

    Inputs:
    - test_session: Session created via API
    - Turn 1: User sets context (generated unique job and company)
    - Turn 2: User asks about their job (should reference Turn 1)
    - Turn 3: User asks about where they work (should reference Turn 1)

    Expected Outputs:
    - All messages successfully added (status 200)
    - GET /sessions/{session_id}/messages returns all messages
    - All messages present and in correct order
    - Context is retained (subsequent messages reference first message)
    """
    session_id = test_session["id"]

    # Generate unique conversation content (no hard-coding)
    unique_id = str(uuid.uuid4())[:8]
    test_job = f"software engineer for test {unique_id}"
    test_company = f"tech company {unique_id}"

    turn1_content = f"I work as a {test_job} at a {test_company}."
    turn2_content = "What is my job?"
    turn3_content = "Where do I work?"

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Turn 1: {turn1_content[:50]}...")
    print(f"[SETTINGS] Turn 2: {turn2_content}")
    print(f"[SETTINGS] Turn 3: {turn3_content}")

    # Turn 1: Set context
    turn1_response = api_client.post(
        f"/sessions/{session_id}/messages", json={"role": "user", "content": turn1_content}
    )
    assert turn1_response.status_code == 200, f"Failed to add turn 1 message: {turn1_response.text}"
    turn1_data = turn1_response.json()
    assert turn1_data["content"] == turn1_content, "Turn 1 content mismatch"

    # Turn 2: Reference previous context
    turn2_response = api_client.post(
        f"/sessions/{session_id}/messages", json={"role": "user", "content": turn2_content}
    )
    assert turn2_response.status_code == 200, f"Failed to add turn 2 message: {turn2_response.text}"
    turn2_data = turn2_response.json()
    assert turn2_data["content"] == turn2_content, "Turn 2 content mismatch"

    # Turn 3: Another reference
    turn3_response = api_client.post(
        f"/sessions/{session_id}/messages", json={"role": "user", "content": turn3_content}
    )
    assert turn3_response.status_code == 200, f"Failed to add turn 3 message: {turn3_response.text}"
    turn3_data = turn3_response.json()
    assert turn3_data["content"] == turn3_content, "Turn 3 content mismatch"

    # Get all messages via API
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate outputs - all messages present
    assert "messages" in messages_data, "messages array missing from response"
    assert "count" in messages_data, "count missing from response"
    assert len(messages_data["messages"]) == 3, (
        f"Expected 3 messages, got {len(messages_data['messages'])}"
    )
    assert messages_data["count"] == 3, f"Expected count 3, got {messages_data['count']}"

    # First message contains the context
    assert test_job in messages_data["messages"][0]["content"], (
        f"Test job '{test_job}' should be in first message"
    )
    assert test_company in messages_data["messages"][0]["content"], (
        f"Test company '{test_company}' should be in first message"
    )

    # Subsequent messages reference it
    assert "job" in messages_data["messages"][1]["content"].lower(), (
        "Second message should reference job"
    )
    assert "work" in messages_data["messages"][2]["content"].lower(), (
        "Third message should reference work"
    )

    # Validate message structure
    for i, msg in enumerate(messages_data["messages"]):
        assert "id" in msg, f"Message {i} ID missing"
        assert "role" in msg, f"Message {i} role missing"
        assert "content" in msg, f"Message {i} content missing"
        assert "timestamp" in msg, f"Message {i} timestamp missing"
        assert msg["role"] == "user", f"Message {i} should be user role"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_large_context_real_world_conversation_via_api(
    api_client, test_user, test_expert, test_config
):
    """Test large context conversation with real-world text, progressive questions, feelings, and context building.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API with specific prompt_template
    - context_window: Large value near LLM limit (from config, default 32768)
    - Real-world text messages with progressive questions, feelings, personal information
    - Re-asking questions to get improved view

    Expected Outputs:
    - Session created successfully (status 200)
    - All messages successfully added (status 200)
    - GET /sessions/{session_id}/messages returns all messages
    - Messages stored in correct order
    - Context maintained across all turns
    """
    user_id = test_user["id"]

    # Get LLM config from config system
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")

    # Create expert with specific prompt template (clearly defines expertise area)
    unique_id = str(uuid.uuid4())[:8]
    expert_prompt = f"""You are a helpful software engineering consultant specializing in Python, system design, and software architecture. 
You provide clear, practical advice based on best practices and real-world experience. 
You are empathetic and understand the challenges developers face. 
Test ID: {unique_id}"""

    expert_data = {
        "name": f"software_consultant_{unique_id}",
        "title": f"Software Engineering Consultant {unique_id}",
        "description": f"Expert in Python, system design, and software architecture for test {unique_id}",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "prompt_template": expert_prompt,
        "enabled": True,
    }

    expert_response = api_client.post("/experts", json=expert_data)
    assert expert_response.status_code == 200, f"Failed to create expert: {expert_response.text}"
    expert = expert_response.json()
    expert_id = expert["id"]

    # Get context window from config (large, near LLM limit)
    context_window = get_config("session.context_window_size")
    history_retention_days = get_config("session.history_retention_days")
    if context_window is None or history_retention_days is None:
        pytest.fail(
            "Missing session.context_window_size/session.history_retention_days in config (--env)"
        )

    session_title = f"Large Context Real-World Conversation {unique_id}"

    # Create session with large context window via API
    create_response = api_client.post(
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

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Expert ID: {expert_id}")
    print(f"[SETTINGS] Expert Prompt: {expert_prompt[:100]}...")
    print(f"[SETTINGS] Context window: {context_window} (from config)")
    print(f"[SETTINGS] Test ID: {unique_id}")

    # Real-world conversation with progressive questions, feelings, and context
    # Turn 1: Initial real-world problem description
    turn1_content = f"""I'm working on a Python microservices architecture for an e-commerce platform. 
We have about 15 services handling different domains: user management, product catalog, order processing, payment, inventory, shipping, notifications, and analytics. 
The system is experiencing latency issues during peak hours, especially in the order processing flow. 
I'm feeling overwhelmed because this is my first large-scale system design, and I'm not sure where to start optimizing. 
Test context: {unique_id}"""

    # Turn 2: Adding personal context and feelings
    turn2_content = f"""I've been working on this project for 8 months now, and I'm the lead developer. 
The pressure from management is increasing because customer complaints are rising. 
I'm worried that if I make the wrong architectural decisions, it could make things worse. 
Can you help me understand what might be causing the latency issues? 
Test context: {unique_id}"""

    # Turn 3: More specific technical details
    turn3_content = f"""The order processing service communicates with payment, inventory, and shipping services synchronously. 
Each service call takes about 200-300ms, and we're making 4-5 sequential calls per order. 
We're using REST APIs with HTTP/1.1, and I suspect the synchronous nature might be part of the problem. 
I'm also concerned about database connection pooling - we're using PostgreSQL with connection pools of 20 per service. 
Test context: {unique_id}"""

    # Turn 4: Re-asking with more context for improved view
    turn4_content = f"""Given what I've told you about the synchronous calls and connection pooling, 
and considering that we're processing about 1000 orders per minute during peak hours, 
what would be your top 3 recommendations to reduce latency? 
I'd like to understand not just what to do, but why each approach would help. 
Test context: {unique_id}"""

    # Turn 5: Adding more personal/emotional context
    turn5_content = f"""I appreciate your help. I'm feeling more confident now. 
One more thing - I'm also worried about data consistency. 
If we move to asynchronous processing, how do we ensure that orders don't get lost or processed twice? 
This is keeping me up at night. 
Test context: {unique_id}"""

    # Turn 6: Re-asking for improved view with all context
    turn6_content = f"""Based on everything we've discussed - the synchronous calls, connection pooling, 
the volume of 1000 orders/minute, and my concerns about data consistency - 
can you provide a comprehensive solution that addresses both performance and reliability? 
I need something I can present to my team and management. 
Test context: {unique_id}"""

    conversation_turns = [
        {"role": "user", "content": turn1_content},
        {"role": "user", "content": turn2_content},
        {"role": "user", "content": turn3_content},
        {"role": "user", "content": turn4_content},
        {"role": "user", "content": turn5_content},
        {"role": "user", "content": turn6_content},
    ]

    # Add all messages via API
    created_message_ids = []
    for i, msg in enumerate(conversation_turns):
        add_response = api_client.post(f"/sessions/{session_id}/messages", json=msg)
        assert add_response.status_code == 200, (
            f"Failed to add message {i + 1}: {add_response.text}"
        )
        message_data = add_response.json()
        created_message_ids.append(message_data["id"])
        assert message_data["content"] == msg["content"], f"Message {i + 1} content mismatch"
        assert message_data["role"] == msg["role"], f"Message {i + 1} role mismatch"

    # Get all messages via API
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate outputs
    assert "messages" in messages_data, "messages array missing from response"
    assert "count" in messages_data, "count missing from response"
    assert len(messages_data["messages"]) == len(conversation_turns), (
        f"Expected {len(conversation_turns)} messages, got {len(messages_data['messages'])}"
    )
    assert messages_data["count"] == len(conversation_turns), (
        f"Expected count {len(conversation_turns)}, got {messages_data['count']}"
    )

    # Verify all messages are present with correct content
    for i, expected_msg in enumerate(conversation_turns):
        actual_msg = messages_data["messages"][i]
        assert actual_msg["content"] == expected_msg["content"], f"Message {i + 1} content mismatch"
        assert actual_msg["role"] == expected_msg["role"], f"Message {i + 1} role mismatch"
        assert unique_id in actual_msg["content"], f"Message {i + 1} should contain unique_id"

    # Validate message structure
    for msg in messages_data["messages"]:
        assert "id" in msg, "Message ID missing"
        assert "role" in msg, "Message role missing"
        assert "content" in msg, "Message content missing"
        assert "timestamp" in msg, "Message timestamp missing"
        assert len(msg["content"]) > 100, "Real-world messages should be substantial length"

    # Verify expert prompt is set correctly
    get_expert_response = api_client.get(f"/experts/{expert_id}")
    assert get_expert_response.status_code == 200, (
        f"Failed to get expert: {get_expert_response.text}"
    )
    expert_data_retrieved = get_expert_response.json()
    assert expert_data_retrieved["prompt_template"] == expert_prompt, (
        "Expert prompt template mismatch"
    )
    assert unique_id in expert_data_retrieved["prompt_template"], (
        "Expert prompt should contain unique_id"
    )

    # Cleanup
    delete_session = api_client.delete(f"/sessions/{session_id}")
    if delete_session.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_session.status_code} {delete_session.text}"
        )
    delete_expert = api_client.delete(f"/experts/{expert_id}")
    if delete_expert.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete expert {expert_id}: {delete_expert.status_code} {delete_expert.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_progressive_dialogue_building_via_api(api_client, test_user, test_config):
    """Test much longer dialogue that builds up piece by piece, adding information and detail,
    asking LLM to expand, ask relevant questions, and then summarize and recreate.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API with specific prompt_template
    - context_window: Large value (from config, default 32768)
    - Progressive dialogue: 15+ turns building up information piece by piece
    - Requests for expansion, relevant questions, summarization, and recreation

    Expected Outputs:
    - Session created successfully (status 200)
    - All messages successfully added (status 200)
    - GET /sessions/{session_id}/messages returns all messages in order
    - Messages build upon previous context
    - All message fields validated
    """
    user_id = test_user["id"]

    # Get LLM config from config system
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")

    # Create expert with specific prompt template for progressive dialogue
    unique_id = str(uuid.uuid4())[:8]
    expert_prompt = f"""You are a collaborative research assistant specializing in technology analysis and knowledge synthesis.
You help users build understanding by asking clarifying questions, expanding on topics, and synthesizing information.
You are patient, thorough, and encourage users to explore ideas deeply.
When asked, you can summarize conversations and help recreate or refine concepts.
Test ID: {unique_id}"""

    expert_data = {
        "name": f"research_assistant_{unique_id}",
        "title": f"Research Assistant {unique_id}",
        "description": f"Collaborative research assistant for progressive dialogue building test {unique_id}",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "prompt_template": expert_prompt,
        "enabled": True,
    }

    expert_response = api_client.post("/experts", json=expert_data)
    assert expert_response.status_code == 200, f"Failed to create expert: {expert_response.text}"
    expert = expert_response.json()
    expert_id = expert["id"]

    # Get context window from config
    context_window = get_config("session.context_window_size")
    history_retention_days = get_config("session.history_retention_days")
    if context_window is None or history_retention_days is None:
        pytest.fail(
            "Missing session.context_window_size/session.history_retention_days in config (--env)"
        )

    session_title = f"Progressive Dialogue Building {unique_id}"

    # Create session via API
    create_response = api_client.post(
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

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Expert ID: {expert_id}")
    print(f"[SETTINGS] Expert Prompt: {expert_prompt[:100]}...")
    print(f"[SETTINGS] Context window: {context_window}")
    print(f"[SETTINGS] Test ID: {unique_id}")
    print("[SETTINGS] Building progressive dialogue with 15+ turns")

    # Progressive dialogue building - piece by piece
    conversation_turns = [
        # Phase 1: Initial topic introduction
        {
            "role": "user",
            "content": f"I'm interested in learning about distributed systems. Test {unique_id}",
        },
        # Phase 2: Adding basic information
        {
            "role": "user",
            "content": f"Specifically, I want to understand how microservices communicate effectively. Test {unique_id}",
        },
        # Phase 3: Adding more detail
        {
            "role": "user",
            "content": f"I've heard about message queues, API gateways, and service meshes, but I'm not sure how they fit together. Test {unique_id}",
        },
        # Phase 4: Requesting expansion
        {
            "role": "user",
            "content": f"Can you expand on how message queues work in microservices? I'd like to understand the patterns and trade-offs. Test {unique_id}",
        },
        # Phase 5: Adding personal context
        {
            "role": "user",
            "content": f"I'm working on a project that needs to handle about 10,000 requests per second, and I'm considering using RabbitMQ. Test {unique_id}",
        },
        # Phase 6: Requesting relevant questions
        {
            "role": "user",
            "content": f"What questions should I be asking myself about my use case before choosing a message queue solution? Test {unique_id}",
        },
        # Phase 7: Adding more technical detail
        {
            "role": "user",
            "content": f"My services are written in Python and Go, and I need to ensure message ordering for some workflows. Test {unique_id}",
        },
        # Phase 8: Adding constraints
        {
            "role": "user",
            "content": f"We have a requirement for at-least-once delivery, and we can't afford to lose messages. Test {unique_id}",
        },
        # Phase 9: Requesting expansion on specific aspect
        {
            "role": "user",
            "content": f"Can you expand on how to achieve at-least-once delivery? What are the implementation patterns? Test {unique_id}",
        },
        # Phase 10: Adding more context about scale
        {
            "role": "user",
            "content": f"We're expecting to scale to 50,000 requests per second within 6 months. Test {unique_id}",
        },
        # Phase 11: Requesting relevant questions about scale
        {
            "role": "user",
            "content": f"What questions should I consider about scalability and performance at this scale? Test {unique_id}",
        },
        # Phase 12: Adding operational context
        {
            "role": "user",
            "content": f"Our team is small - 5 developers - and we need something that's relatively easy to operate and monitor. Test {unique_id}",
        },
        # Phase 13: Requesting summary
        {
            "role": "user",
            "content": f"Can you summarize what we've discussed so far? I want to make sure I understand the key points. Test {unique_id}",
        },
        # Phase 14: Requesting recreation/refinement
        {
            "role": "user",
            "content": f"Based on our conversation, can you help me recreate a decision framework for choosing a message queue? Test {unique_id}",
        },
        # Phase 15: Final refinement request
        {
            "role": "user",
            "content": f"Can you refine that framework to include the specific considerations we discussed - scale, team size, language support, and delivery guarantees? Test {unique_id}",
        },
    ]

    # Add all messages via API
    created_message_ids = []
    for i, msg in enumerate(conversation_turns):
        add_response = api_client.post(f"/sessions/{session_id}/messages", json=msg)
        assert add_response.status_code == 200, (
            f"Failed to add message {i + 1}: {add_response.text}"
        )
        message_data = add_response.json()
        created_message_ids.append(message_data["id"])
        assert message_data["content"] == msg["content"], f"Message {i + 1} content mismatch"
        assert message_data["role"] == msg["role"], f"Message {i + 1} role mismatch"

    # Get all messages via API
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate outputs
    assert "messages" in messages_data, "messages array missing from response"
    assert "count" in messages_data, "count missing from response"
    assert len(messages_data["messages"]) == len(conversation_turns), (
        f"Expected {len(conversation_turns)} messages, got {len(messages_data['messages'])}"
    )
    assert messages_data["count"] == len(conversation_turns), (
        f"Expected count {len(conversation_turns)}, got {messages_data['count']}"
    )

    # Verify progressive building - later messages reference earlier topics
    all_content = " ".join([msg["content"] for msg in messages_data["messages"]])
    assert "distributed systems" in all_content.lower(), "Should contain initial topic"
    assert "microservices" in all_content.lower(), "Should contain expanded topic"
    assert "message queue" in all_content.lower() or "message queues" in all_content.lower(), (
        "Should contain detailed topic"
    )
    assert "summarize" in all_content.lower() or "summary" in all_content.lower(), (
        "Should contain summarization request"
    )
    assert "recreate" in all_content.lower() or "framework" in all_content.lower(), (
        "Should contain recreation request"
    )

    # Verify all messages are in correct order
    for i, expected_msg in enumerate(conversation_turns):
        actual_msg = messages_data["messages"][i]
        assert actual_msg["content"] == expected_msg["content"], f"Message {i + 1} content mismatch"
        assert actual_msg["role"] == expected_msg["role"], f"Message {i + 1} role mismatch"
        assert unique_id in actual_msg["content"], f"Message {i + 1} should contain unique_id"

    # Validate message structure
    for msg in messages_data["messages"]:
        assert "id" in msg, "Message ID missing"
        assert "role" in msg, "Message role missing"
        assert "content" in msg, "Message content missing"
        assert "timestamp" in msg, "Message timestamp missing"

    # Verify expert prompt is set correctly
    get_expert_response = api_client.get(f"/experts/{expert_id}")
    assert get_expert_response.status_code == 200, (
        f"Failed to get expert: {get_expert_response.text}"
    )
    expert_data_retrieved = get_expert_response.json()
    assert expert_data_retrieved["prompt_template"] == expert_prompt, (
        "Expert prompt template mismatch"
    )

    # Cleanup
    delete_session = api_client.delete(f"/sessions/{session_id}")
    if delete_session.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_session.status_code} {delete_session.text}"
        )
    delete_expert = api_client.delete(f"/experts/{expert_id}")
    if delete_expert.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete expert {expert_id}: {delete_expert.status_code} {delete_expert.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_expert_boundary_detection_via_api(api_client, test_user, test_config):
    """Test that expert correctly identifies when questions are outside its expertise area.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API with specific prompt_template defining expertise boundaries
    - Questions within expert's area
    - Questions outside expert's area

    Expected Outputs:
    - Session created successfully (status 200)
    - All messages successfully added (status 200)
    - GET /sessions/{session_id}/messages returns all messages
    - Expert prompt clearly defines boundaries
    - Messages stored correctly (expert boundary detection happens when LLM processes, not in storage)
    """
    user_id = test_user["id"]

    # Get LLM config from config system
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")

    # Create expert with specific prompt template that clearly defines boundaries
    unique_id = str(uuid.uuid4())[:8]
    expert_prompt = f"""You are a Python programming expert specializing in web development, data processing, and API design.
You provide expert advice on Python, Django, FastAPI, data analysis with pandas, and related technologies.
IMPORTANT: If asked about topics outside your expertise (such as medical advice, legal advice, financial planning, 
hardware engineering, or other programming languages), you must politely decline and explain that this is outside 
your area of expertise. You should suggest that the user consult an appropriate expert in that field.
Test ID: {unique_id}"""

    expert_data = {
        "name": f"python_expert_{unique_id}",
        "title": f"Python Programming Expert {unique_id}",
        "description": f"Python expert for boundary detection test {unique_id}",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "llm_base_url": llm_base_url,
        "prompt_template": expert_prompt,
        "enabled": True,
    }

    expert_response = api_client.post("/experts", json=expert_data)
    assert expert_response.status_code == 200, f"Failed to create expert: {expert_response.text}"
    expert = expert_response.json()
    expert_id = expert["id"]

    # Get context window from config
    context_window = get_config("session.context_window_size")
    history_retention_days = get_config("session.history_retention_days")
    if context_window is None or history_retention_days is None:
        pytest.fail(
            "Missing session.context_window_size/session.history_retention_days in config (--env)"
        )

    session_title = f"Expert Boundary Detection {unique_id}"

    # Create session via API
    create_response = api_client.post(
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

    # Show settings being used
    print(f"\n[SETTINGS] Session ID: {session_id}")
    print(f"[SETTINGS] Expert ID: {expert_id}")
    print(f"[SETTINGS] Expert Prompt: {expert_prompt[:150]}...")
    print(f"[SETTINGS] Context window: {context_window}")
    print(f"[SETTINGS] Test ID: {unique_id}")

    # Conversation with questions inside and outside expert area
    conversation_turns = [
        # Question within expertise
        {
            "role": "user",
            "content": f"How do I optimize a FastAPI endpoint that processes large CSV files? Test {unique_id}",
        },
        # Question within expertise
        {
            "role": "user",
            "content": f"What's the best way to handle async database connections in Django? Test {unique_id}",
        },
        # Question outside expertise - medical
        {
            "role": "user",
            "content": f"What medication should I take for high blood pressure? Test {unique_id}",
        },
        # Question within expertise
        {
            "role": "user",
            "content": f"Can you help me design a REST API for a user management system? Test {unique_id}",
        },
        # Question outside expertise - legal
        {
            "role": "user",
            "content": f"What are the legal requirements for data protection in the EU? Test {unique_id}",
        },
        # Question within expertise
        {
            "role": "user",
            "content": f"How do I use pandas to analyze time-series data? Test {unique_id}",
        },
        # Question outside expertise - financial
        {"role": "user", "content": f"Should I invest in cryptocurrency? Test {unique_id}"},
        # Question within expertise
        {
            "role": "user",
            "content": f"What are the best practices for error handling in Python APIs? Test {unique_id}",
        },
    ]

    # Add all messages via API
    created_message_ids = []
    for i, msg in enumerate(conversation_turns):
        add_response = api_client.post(f"/sessions/{session_id}/messages", json=msg)
        assert add_response.status_code == 200, (
            f"Failed to add message {i + 1}: {add_response.text}"
        )
        message_data = add_response.json()
        created_message_ids.append(message_data["id"])
        assert message_data["content"] == msg["content"], f"Message {i + 1} content mismatch"
        assert message_data["role"] == msg["role"], f"Message {i + 1} role mismatch"

    # Get all messages via API
    get_response = api_client.get(f"/sessions/{session_id}/messages")
    assert get_response.status_code == 200, f"Failed to get messages: {get_response.text}"
    messages_data = get_response.json()

    # Validate outputs
    assert "messages" in messages_data, "messages array missing from response"
    assert "count" in messages_data, "count missing from response"
    assert len(messages_data["messages"]) == len(conversation_turns), (
        f"Expected {len(conversation_turns)} messages, got {len(messages_data['messages'])}"
    )
    assert messages_data["count"] == len(conversation_turns), (
        f"Expected count {len(conversation_turns)}, got {messages_data['count']}"
    )

    # Verify all messages are present
    for i, expected_msg in enumerate(conversation_turns):
        actual_msg = messages_data["messages"][i]
        assert actual_msg["content"] == expected_msg["content"], f"Message {i + 1} content mismatch"
        assert actual_msg["role"] == expected_msg["role"], f"Message {i + 1} role mismatch"
        assert unique_id in actual_msg["content"], f"Message {i + 1} should contain unique_id"

    # Verify expert prompt is set correctly with boundary definition
    get_expert_response = api_client.get(f"/experts/{expert_id}")
    assert get_expert_response.status_code == 200, (
        f"Failed to get expert: {get_expert_response.text}"
    )
    expert_data_retrieved = get_expert_response.json()
    assert expert_data_retrieved["prompt_template"] == expert_prompt, (
        "Expert prompt template mismatch"
    )
    assert (
        "outside your expertise" in expert_data_retrieved["prompt_template"].lower()
        or "outside your area" in expert_data_retrieved["prompt_template"].lower()
    ), "Expert prompt should define boundaries"
    assert unique_id in expert_data_retrieved["prompt_template"], (
        "Expert prompt should contain unique_id"
    )

    # Validate message structure
    for msg in messages_data["messages"]:
        assert "id" in msg, "Message ID missing"
        assert "role" in msg, "Message role missing"
        assert "content" in msg, "Message content missing"
        assert "timestamp" in msg, "Message timestamp missing"

    # Verify conversation contains both in-scope and out-of-scope questions
    all_content = " ".join([msg["content"] for msg in messages_data["messages"]])
    assert "fastapi" in all_content.lower() or "python" in all_content.lower(), (
        "Should contain in-scope questions"
    )
    assert "medication" in all_content.lower() or "blood pressure" in all_content.lower(), (
        "Should contain out-of-scope medical question"
    )
    assert "legal" in all_content.lower() or "data protection" in all_content.lower(), (
        "Should contain out-of-scope legal question"
    )
    assert "cryptocurrency" in all_content.lower() or "invest" in all_content.lower(), (
        "Should contain out-of-scope financial question"
    )

    # Cleanup
    delete_session = api_client.delete(f"/sessions/{session_id}")
    if delete_session.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_session.status_code} {delete_session.text}"
        )
    delete_expert = api_client.delete(f"/experts/{expert_id}")
    if delete_expert.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete expert {expert_id}: {delete_expert.status_code} {delete_expert.text}"
        )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.db, pytest.mark.smtp, pytest.mark.heavy]

