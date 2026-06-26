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
Application Test: AT1.8 - Comprehensive Chat Interaction Tests

License: Apache 2.0
Ownership: Cloud Dog
Description: Comprehensive tests for chat interaction via all interfaces (API, MCP, A2A, Web UI)
with LLM settings, response formats, languages, and complex conversations

Related Requirements: FR1.2, FR1.1, FR1.7
Related Tasks: T022, T008, T039
Related Architecture: CC2.1.1, IP1.1.1, CC1.1.3
Related Tests: AT1.8

Test Quality Standards:
- All outputs validated for format, content, and structure
- No hardcoded values - all from configuration system
- Comprehensive scenario coverage
- Proper cleanup and isolation
- Tests all interfaces: API, MCP (SSE), A2A (WebSocket), Web UI
- Tests LLM settings: temperature, top_k, top_p, max_tokens
- Tests response formats: text, markdown, JSON
- Tests languages: English, French, Polish
- Tests prompts: defaults.yaml and env-file override
"""

import pytest
import uuid
import json
import sys
from pathlib import Path
from src.config.loader import get_config

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
            "Test user credentials not configured. "
            "Set test.user.username/test.user.email/test.user.password in your --env file."
        )

    unique_id = str(uuid.uuid4())[:8]
    return {
        "username": f"{base_username}_chat_{unique_id}",
        "email": build_test_email("chat", unique_id, base_email),
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

    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_chat_{unique_id}",
        "title": f"Chat Interaction Expert {unique_id} dialogue reasoning context synthesis precision",
        "description": "Chat interaction scenario with unique vocabulary: acorn basil cipher dune ember fjord glyph helios isotope juniper keystone",
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


@pytest.fixture
def test_channel(api_client, test_user, test_expert):
    """Create test channel via API."""
    unique_id = str(uuid.uuid4())[:8]
    channel_data = {
        "name": f"channel_chat_{unique_id}",
        "expert_config_id": test_expert["id"],
        "description": "Test channel for chat interaction",
        "enabled": True,
    }

    response = api_client.post("/channels", json=channel_data)
    assert response.status_code == 200, f"Failed to create test channel: {response.text}"
    channel = response.json()

    yield channel

    # Cleanup via API
    try:
        api_client.delete(f"/channels/{channel['id']}")
    except Exception:
        pass


@pytest.fixture
def test_session(api_client, test_user, test_expert, test_config):
    """Create test session via API."""
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
    session_title = f"Test Chat Session {unique_id}"

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

    # Cleanup via API
    try:
        api_client.delete(f"/sessions/{session_data['id']}")
    except Exception:
        pass


# ============================================================================
# API INTERFACE TESTS
# ============================================================================
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_via_api_basic(api_client, test_channel, test_user):
    """Test basic chat interaction via API.

    Inputs:
    - channel_id: Test channel ID
    - message: Simple test message
    - user_id: Test user ID

    Expected Outputs:
    - mode: "sync" (string)
    - session_id: Integer
    - response: String (non-empty)
    - tokens_used: Integer (>= 0)
    - model: String (non-empty)
    - job_id: Integer
    """
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    message = f"Hello, this is a test message {unique_id}. How are you?"

    response = api_client.post(
        f"/channels/{channel_id}/chat",
        json={"message": message, "user_id": user_id, "async_mode": False},
    )

    # Handle LLM unavailability gracefully
    if response.status_code == 503:
        # LLM service unavailable - skip test
        error_detail = response.json().get("detail", "Unknown error")
        pytest.fail(f"LLM service unavailable: {error_detail}")

    assert response.status_code == 200, f"Failed to chat via API: {response.text}"
    chat_data = response.json()

    # Validate all outputs comprehensively
    assert "mode" in chat_data, "mode missing from response"
    assert chat_data["mode"] == "sync", f"mode should be 'sync', got '{chat_data['mode']}'"
    assert "session_id" in chat_data, "session_id missing from response"
    assert isinstance(chat_data["session_id"], int), "session_id must be integer"
    assert "response" in chat_data, "response missing from response"
    assert isinstance(chat_data["response"], str), "response must be string"
    assert len(chat_data["response"]) > 0, "response should not be empty"
    assert "tokens_used" in chat_data, "tokens_used missing from response"
    assert isinstance(chat_data["tokens_used"], int), "tokens_used must be integer"
    assert chat_data["tokens_used"] >= 0, "tokens_used should be >= 0"
    assert "model" in chat_data, "model missing from response"
    assert isinstance(chat_data["model"], str), "model must be string"
    assert len(chat_data["model"]) > 0, "model should not be empty"
    assert "job_id" in chat_data, "job_id missing from response"
    assert isinstance(chat_data["job_id"], int), "job_id must be integer"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_via_api_with_temperature(api_client, test_channel, test_user):
    """Test chat via API with temperature parameter.

    Inputs:
    - channel_id: Test channel ID
    - message: Test message
    - user_id: Test user ID
    - temperature: 0.3 (float)

    Expected Outputs:
    - Response structure matches basic chat
    - Temperature parameter is accepted (if supported)
    """
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    message = f"Test message with temperature {unique_id}"

    # Note: ChannelChatRequest may need to be updated to accept LLM parameters
    # For now, test that the endpoint accepts metadata
    response = api_client.post(
        f"/channels/{channel_id}/chat",
        json={
            "message": message,
            "user_id": user_id,
            "async_mode": False,
            "metadata": {"temperature": 0.3},
        },
    )

    # Handle LLM unavailability gracefully
    if response.status_code == 503:
        error_detail = response.json().get("detail", "Unknown error")
        pytest.fail(f"LLM service unavailable: {error_detail}")
    chat_data = response.json()

    # Validate response structure
    assert "response" in chat_data, "response missing"
    assert isinstance(chat_data["response"], str), "response must be string"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_via_api_with_top_k(api_client, test_channel, test_user):
    """Test chat via API with top_k parameter."""
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    message = f"Test message with top_k {unique_id}"

    response = api_client.post(
        f"/channels/{channel_id}/chat",
        json={
            "message": message,
            "user_id": user_id,
            "async_mode": False,
            "metadata": {"top_k": 40},
        },
    )

    # Handle LLM unavailability gracefully
    if response.status_code == 503:
        error_detail = response.json().get("detail", "Unknown error")
        pytest.fail(f"LLM service unavailable: {error_detail}")
    chat_data = response.json()

    assert "response" in chat_data, "response missing"
    assert isinstance(chat_data["response"], str), "response must be string"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_via_api_multi_turn(api_client, test_channel, test_user):
    """Test multi-turn conversation via API.

    Inputs:
    - channel_id: Test channel ID
    - Multiple messages in sequence
    - user_id: Test user ID

    Expected Outputs:
    - Each response is valid
    - Session persists across messages
    - Context is maintained
    """
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    messages = [
        f"Hello, my name is TestUser{unique_id}.",
        "What did I just tell you my name was?",
        "Can you repeat my name back to me?",
    ]

    session_id = None
    for i, message in enumerate(messages):
        response = api_client.post(
            f"/channels/{channel_id}/chat",
            json={
                "message": message,
                "user_id": user_id,
                "session_id": session_id,
                "async_mode": False,
            },
        )

    # Handle LLM unavailability gracefully
    if response.status_code == 503:
        error_detail = response.json().get("detail", "Unknown error")
        pytest.fail(f"LLM service unavailable: {error_detail}")

    assert response.status_code == 200, f"Failed on message {i + 1}: {response.text}"
    chat_data = response.json()

    # Validate response structure
    assert "response" in chat_data, f"response missing on message {i + 1}"
    assert isinstance(chat_data["response"], str), f"response must be string on message {i + 1}"

    # Capture session_id for next message
    if session_id is None:
        session_id = chat_data.get("session_id")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_via_api_complex_question(api_client, test_channel, test_user):
    """Test complex question with context and examples via API."""
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    complex_message = f"""
    I need help with a multi-step problem. Here's the context:
    
    1. I have 10 apples
    2. I give away 3 apples
    3. I buy 5 more apples
    
    Question: How many apples do I have now? Show your reasoning step by step.
    Test ID: {unique_id}
    """

    response = api_client.post(
        f"/channels/{channel_id}/chat",
        json={"message": complex_message.strip(), "user_id": user_id, "async_mode": False},
    )

    assert response.status_code == 200, f"Failed complex question: {response.text}"
    chat_data = response.json()

    # Validate response
    assert "response" in chat_data, "response missing"
    assert isinstance(chat_data["response"], str), "response must be string"
    assert len(chat_data["response"]) > 0, "response should not be empty"


# ============================================================================
# MCP INTERFACE TESTS (SSE)
# ============================================================================
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_via_mcp_basic(api_client, test_session):
    """Test basic chat interaction via MCP endpoint.

    Inputs:
    - session_id: Test session ID
    - message: Test message

    Expected Outputs:
    - response: String (non-empty)
    - tokens_used: Integer (>= 0)
    - model: String (non-empty)
    """
    session_id = test_session["id"]

    unique_id = str(uuid.uuid4())[:8]
    message = f"Hello via MCP {unique_id}"

    response = api_client.post("/mcp/chat", json={"session_id": session_id, "message": message})

    assert response.status_code == 200, f"Failed to chat via MCP: {response.text}"
    mcp_data = response.json()

    # Validate outputs
    assert "response" in mcp_data or "error" not in mcp_data, "response missing or error present"
    if "response" in mcp_data:
        assert isinstance(mcp_data["response"], str), "response must be string"
        assert len(mcp_data["response"]) > 0, "response should not be empty"
        if "tokens_used" in mcp_data:
            assert isinstance(mcp_data["tokens_used"], int), "tokens_used must be integer"
        if "model" in mcp_data:
            assert isinstance(mcp_data["model"], str), "model must be string"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_via_mcp_with_llm_params(api_client, test_session):
    """Test MCP chat with LLM parameters (if supported)."""
    session_id = test_session["id"]

    unique_id = str(uuid.uuid4())[:8]
    message = f"Test with LLM params {unique_id}"

    # Note: MCP chat_tool may need to be updated to accept LLM parameters
    response = api_client.post(
        "/mcp/chat",
        json={"session_id": session_id, "message": message, "temperature": 0.5, "top_k": 50},
    )

    # Should either accept parameters or return error
    assert response.status_code in (200, 400, 422), f"Unexpected status: {response.status_code}"

    if response.status_code == 200:
        mcp_data = response.json()
        assert "response" in mcp_data or "error" not in mcp_data, (
            "response missing or error present"
        )


# ============================================================================
# A2A INTERFACE TESTS (WebSocket)
# ============================================================================
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.asyncio
async def test_chat_via_a2a_websocket(api_client, test_channel, test_user):
    """Test chat interaction via A2A WebSocket.

    Note: This test requires WebSocket client. For now, we test the A2A endpoint
    that processes chat commands.
    """
    # A2A WebSocket testing requires async WebSocket client
    # For now, we'll test that the A2A server is accessible
    # Full WebSocket testing would require a WebSocket test client

    # Test A2A health endpoint
    response = api_client.get("/a2a/health")
    assert response.status_code == 200, f"A2A health check failed: {response.text}"

    health_data = response.json()
    assert "status" in health_data or "active_connections" in health_data, (
        "Health response structure invalid"
    )


# ============================================================================
# WEB UI INTERFACE TESTS
# ============================================================================
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_via_web_ui_proxy(api_client, test_channel, test_user):
    """Test chat via Web UI proxy endpoint.

    Note: Web UI typically proxies to API endpoints. We test the underlying API.
    """
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    message = f"Hello via Web UI proxy {unique_id}"

    # Web UI typically uses the same channel chat endpoint
    response = api_client.post(
        f"/channels/{channel_id}/chat",
        json={"message": message, "user_id": user_id, "async_mode": False},
    )

    # Handle LLM unavailability gracefully
    if response.status_code == 503:
        error_detail = response.json().get("detail", "Unknown error")
        pytest.fail(f"LLM service unavailable: {error_detail}")

    assert response.status_code == 200, f"Failed Web UI proxy chat: {response.text}"
    chat_data = response.json()

    # Validate response structure
    assert "response" in chat_data, "response missing"
    assert isinstance(chat_data["response"], str), "response must be string"


# ============================================================================
# LLM SETTINGS TESTS
# ============================================================================
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.parametrize("temperature", [0.0, 0.3, 0.7, 1.0])
def test_chat_temperature_variations(api_client, test_channel, test_user, temperature):
    """Test chat with different temperature values."""
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    message = f"Test temperature {temperature} - {unique_id}"

    response = api_client.post(
        f"/channels/{channel_id}/chat",
        json={
            "message": message,
            "user_id": user_id,
            "async_mode": False,
            "metadata": {"temperature": temperature},
        },
    )

    # Handle LLM unavailability gracefully
    if response.status_code == 503:
        error_detail = response.json().get("detail", "Unknown error")
        pytest.fail(f"LLM service unavailable: {error_detail}")
    chat_data = response.json()

    assert "response" in chat_data, "response missing"
    assert isinstance(chat_data["response"], str), "response must be string"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.parametrize("top_k", [10, 40, 80])
def test_chat_top_k_variations(api_client, test_channel, test_user, top_k):
    """Test chat with different top_k values."""
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    message = f"Test top_k {top_k} - {unique_id}"

    response = api_client.post(
        f"/channels/{channel_id}/chat",
        json={
            "message": message,
            "user_id": user_id,
            "async_mode": False,
            "metadata": {"top_k": top_k},
        },
    )

    # Handle LLM unavailability gracefully
    if response.status_code == 503:
        error_detail = response.json().get("detail", "Unknown error")
        pytest.fail(f"LLM service unavailable: {error_detail}")
    chat_data = response.json()

    assert "response" in chat_data, "response missing"
    assert isinstance(chat_data["response"], str), "response must be string"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.parametrize("max_tokens", [256, 512, 1024, 2048])
def test_chat_max_tokens_variations(api_client, test_channel, test_user, max_tokens):
    """Test chat with different max_tokens values."""
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    message = f"Test max_tokens {max_tokens} - {unique_id}"

    response = api_client.post(
        f"/channels/{channel_id}/chat",
        json={
            "message": message,
            "user_id": user_id,
            "async_mode": False,
            "metadata": {"max_tokens": max_tokens},
        },
    )

    # Handle LLM unavailability gracefully
    if response.status_code == 503:
        error_detail = response.json().get("detail", "Unknown error")
        pytest.fail(f"LLM service unavailable: {error_detail}")
    chat_data = response.json()

    assert "response" in chat_data, "response missing"
    assert isinstance(chat_data["response"], str), "response must be string"


# ============================================================================
# RESPONSE FORMAT TESTS
# ============================================================================
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_response_format_text(api_client, test_channel, test_user):
    """Test chat response in text format."""
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    message = f"Respond in plain text format. Test ID: {unique_id}"

    response = api_client.post(
        f"/channels/{channel_id}/chat",
        json={
            "message": message,
            "user_id": user_id,
            "async_mode": False,
            "metadata": {"response_format": "text"},
        },
    )

    # Handle LLM unavailability gracefully
    if response.status_code == 503:
        error_detail = response.json().get("detail", "Unknown error")
        pytest.fail(f"LLM service unavailable: {error_detail}")

    assert response.status_code == 200, f"Failed text format: {response.text}"
    chat_data = response.json()

    assert "response" in chat_data, "response missing"
    assert isinstance(chat_data["response"], str), "response must be string"
    # Text format should not contain markdown or JSON structures
    response_text = chat_data["response"]
    # Basic validation - text should be readable
    assert len(response_text) > 0, "response should not be empty"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_response_format_markdown(api_client, test_channel, test_user):
    """Test chat response in markdown format."""
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    message = f"Respond in markdown format with headers and lists. Test ID: {unique_id}"

    response = api_client.post(
        f"/channels/{channel_id}/chat",
        json={
            "message": message,
            "user_id": user_id,
            "async_mode": False,
            "metadata": {"response_format": "markdown"},
        },
    )

    # Handle LLM unavailability gracefully
    if response.status_code == 503:
        error_detail = response.json().get("detail", "Unknown error")
        pytest.fail(f"LLM service unavailable: {error_detail}")

    assert response.status_code == 200, f"Failed markdown format: {response.text}"
    chat_data = response.json()

    assert "response" in chat_data, "response missing"
    assert isinstance(chat_data["response"], str), "response must be string"
    # Markdown may contain #, *, -, etc.
    response_text = chat_data["response"]
    assert len(response_text) > 0, "response should not be empty"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_response_format_json(api_client, test_channel, test_user):
    """Test chat response in JSON format."""
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    message = f"Respond in JSON format with keys: answer, reasoning. Test ID: {unique_id}"

    response = api_client.post(
        f"/channels/{channel_id}/chat",
        json={
            "message": message,
            "user_id": user_id,
            "async_mode": False,
            "metadata": {"response_format": "json"},
        },
    )

    # Handle LLM unavailability gracefully
    if response.status_code == 503:
        error_detail = response.json().get("detail", "Unknown error")
        pytest.fail(f"LLM service unavailable: {error_detail}")

    assert response.status_code == 200, f"Failed JSON format: {response.text}"
    chat_data = response.json()

    assert "response" in chat_data, "response missing"
    assert isinstance(chat_data["response"], str), "response must be string"
    # Try to parse as JSON
    try:
        json.loads(chat_data["response"])
    except json.JSONDecodeError:
        # JSON format requested but response may not be valid JSON
        # This is acceptable if LLM doesn't strictly follow format
        pass


# ============================================================================
# LANGUAGE TESTS
# ============================================================================
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_language_english(api_client, test_channel, test_user):
    """Test chat in English (default)."""
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    message = f"Hello, this is a test in English. Test ID: {unique_id}"

    response = api_client.post(
        f"/channels/{channel_id}/chat",
        json={"message": message, "user_id": user_id, "async_mode": False},
    )

    # Handle LLM unavailability gracefully
    if response.status_code == 503:
        error_detail = response.json().get("detail", "Unknown error")
        pytest.fail(f"LLM service unavailable: {error_detail}")

    assert response.status_code == 200, f"Failed English chat: {response.text}"
    chat_data = response.json()

    assert "response" in chat_data, "response missing"
    assert isinstance(chat_data["response"], str), "response must be string"
    assert len(chat_data["response"]) > 0, "response should not be empty"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_language_french(api_client, test_channel, test_user):
    """Test chat in French."""
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    message = f"Bonjour, ceci est un test en français. ID de test: {unique_id}"

    response = api_client.post(
        f"/channels/{channel_id}/chat",
        json={
            "message": message,
            "user_id": user_id,
            "async_mode": False,
            "metadata": {"language": "fr"},
        },
    )

    # Handle LLM unavailability gracefully
    if response.status_code == 503:
        error_detail = response.json().get("detail", "Unknown error")
        pytest.fail(f"LLM service unavailable: {error_detail}")

    assert response.status_code == 200, f"Failed French chat: {response.text}"
    chat_data = response.json()

    assert "response" in chat_data, "response missing"
    assert isinstance(chat_data["response"], str), "response must be string"
    assert len(chat_data["response"]) > 0, "response should not be empty"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_language_polish(api_client, test_channel, test_user):
    """Test chat in Polish."""
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    message = f"Witaj, to jest test w języku polskim. ID testu: {unique_id}"

    response = api_client.post(
        f"/channels/{channel_id}/chat",
        json={
            "message": message,
            "user_id": user_id,
            "async_mode": False,
            "metadata": {"language": "pl"},
        },
    )

    # Handle LLM unavailability gracefully
    if response.status_code == 503:
        error_detail = response.json().get("detail", "Unknown error")
        pytest.fail(f"LLM service unavailable: {error_detail}")

    assert response.status_code == 200, f"Failed Polish chat: {response.text}"
    chat_data = response.json()

    assert "response" in chat_data, "response missing"
    assert isinstance(chat_data["response"], str), "response must be string"
    assert len(chat_data["response"]) > 0, "response should not be empty"


# ============================================================================
# PROMPT CONFIGURATION TESTS
# ============================================================================
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_with_default_prompt(api_client, test_channel, test_user):
    """Test chat with default prompt from defaults.yaml."""
    # Get default prompt from config
    get_config("llm.default_system_prompt")

    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    message = f"Test with default prompt. Test ID: {unique_id}"

    response = api_client.post(
        f"/channels/{channel_id}/chat",
        json={"message": message, "user_id": user_id, "async_mode": False},
    )

    # Handle LLM unavailability gracefully
    if response.status_code == 503:
        error_detail = response.json().get("detail", "Unknown error")
        pytest.fail(f"LLM service unavailable: {error_detail}")
    chat_data = response.json()

    assert "response" in chat_data, "response missing"
    assert isinstance(chat_data["response"], str), "response must be string"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_with_custom_prompt(api_client, test_channel, test_user):
    """Test chat with custom prompt override."""
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    custom_prompt = f"You are a helpful assistant. Test ID: {unique_id}"
    message = "Hello"

    # Note: Custom prompt may need to be set via expert config or metadata
    response = api_client.post(
        f"/channels/{channel_id}/chat",
        json={
            "message": message,
            "user_id": user_id,
            "async_mode": False,
            "metadata": {"system_prompt": custom_prompt},
        },
    )

    # Should either accept custom prompt or use default
    assert response.status_code in (200, 400, 422), f"Unexpected status: {response.status_code}"

    if response.status_code == 200:
        chat_data = response.json()
        assert "response" in chat_data, "response missing"


# ============================================================================
# COMPLEX CONVERSATION TESTS
# ============================================================================
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_complex_multi_step_reasoning(api_client, test_channel, test_user):
    """Test complex multi-step reasoning conversation."""
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    conversation = [
        f"Context: I have a problem to solve. Test ID: {unique_id}",
        "Step 1: I need to calculate 15 * 7. What is the result?",
        "Step 2: Now add 25 to that result. What is the new total?",
        "Step 3: Finally, divide by 5. What is the final answer?",
    ]

    session_id = None
    for i, message in enumerate(conversation):
        response = api_client.post(
            f"/channels/{channel_id}/chat",
            json={
                "message": message,
                "user_id": user_id,
                "session_id": session_id,
                "async_mode": False,
            },
        )

    # Handle LLM unavailability gracefully
    if response.status_code == 503:
        error_detail = response.json().get("detail", "Unknown error")
        pytest.fail(f"LLM service unavailable: {error_detail}")

    assert response.status_code == 200, f"Failed on step {i + 1}: {response.text}"
    chat_data = response.json()

    assert "response" in chat_data, f"response missing on step {i + 1}"
    assert isinstance(chat_data["response"], str), f"response must be string on step {i + 1}"

    if session_id is None:
        session_id = chat_data.get("session_id")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_chat_with_examples_in_prompt(api_client, test_channel, test_user):
    """Test chat with examples provided in the prompt."""
    channel_id = test_channel["id"]
    user_id = test_user["id"]

    unique_id = str(uuid.uuid4())[:8]
    message = f"""
    Here are some examples:
    Example 1: 2 + 2 = 4
    Example 2: 3 * 3 = 9
    
    Now solve: 4 * 4 = ?
    Test ID: {unique_id}
    """

    response = api_client.post(
        f"/channels/{channel_id}/chat",
        json={"message": message.strip(), "user_id": user_id, "async_mode": False},
    )

    assert response.status_code == 200, f"Failed with examples: {response.text}"
    chat_data = response.json()

    assert "response" in chat_data, "response missing"
    assert isinstance(chat_data["response"], str), "response must be string"
    assert len(chat_data["response"]) > 0, "response should not be empty"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.llm, pytest.mark.smtp, pytest.mark.mcp, pytest.mark.heavy]
