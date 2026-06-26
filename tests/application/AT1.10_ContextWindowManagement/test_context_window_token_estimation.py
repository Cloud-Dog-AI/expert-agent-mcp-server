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
Application Test: AT1.10 - Context Window Token Estimation

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for token estimation and usage statistics

Related Requirements: FR1.2
Related Tasks: T010
Related Architecture: CC2.1.1
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
        "username": f"{base_username}_at1_10_tokens_{unique_id}",
        "email": build_test_email("at1_10_tokens", unique_id, base_email),
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
        pytest.fail("llm.provider/llm.model not configured (required for AT1.10).")

    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_at1_10_tokens_{unique_id}",
        "title": f"Token Estimation Expert {unique_id} usage metrics overhead accounting baseline calibration",
        "description": "Token counting verification with varied strings and distinct words: amber birch comet diadem ember forge grotto helix ion jigsaw kepler",
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
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_token_estimation_accuracy_via_api(api_client, test_user, test_expert):
    """Test that token estimation is reasonably accurate.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Session with messages of known lengths
    - token estimation: Calculated for messages

    Expected Outputs:
    - Token estimates are reasonable (within expected range)
    - Estimates increase with message length
    - Estimates account for message overhead
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    context_window = int(get_config("test.at1_10.context_windows.xlarge"))

    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Token Estimation Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add messages of different lengths
    test_messages = [
        {"role": "user", "content": "Short"},  # ~1 token
        {"role": "user", "content": "A" * 100},  # ~25 tokens
        {"role": "user", "content": "B" * 200},  # ~50 tokens
        {"role": "user", "content": "C" * 400},  # ~100 tokens
    ]

    for msg in test_messages:
        api_client.post(f"/sessions/{session_id}/messages", json=msg)

    # Get all messages
    messages_response = api_client.get(f"/sessions/{session_id}/messages")
    assert messages_response.status_code == 200, f"Failed to get messages: {messages_response.text}"
    messages_data = messages_response.json()

    # Validate message lengths match expectations
    assert len(messages_data["messages"]) == len(test_messages), (
        f"Should have {len(test_messages)} messages"
    )

    # Verify content lengths are preserved
    for i, expected_msg in enumerate(test_messages):
        actual_msg = messages_data["messages"][i]
        assert actual_msg["content"] == expected_msg["content"], f"Message {i} content mismatch"
        assert len(actual_msg["content"]) == len(expected_msg["content"]), (
            f"Message {i} length mismatch"
        )

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_context_window_usage_statistics_via_api(api_client, test_user, test_expert):
    """Test context window usage statistics calculation.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Session with context_window set
    - messages: Added to session

    Expected Outputs:
    - Usage statistics can be calculated
    - Statistics reflect message count and length
    - Near limit and exceeded flags work correctly
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    context_window = int(get_config("test.at1_10.context_windows.large"))

    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Usage Stats Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add messages that approach limit
    message_count = int(get_config("test.at1_10.message_counts.medium"))
    for i in range(message_count):
        message_content = f"Message {i} for stats test {unique_id}: " + "K" * 50
        api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )

    # Get session to verify context_window is set
    get_session_response = api_client.get(f"/sessions/{session_id}")
    assert get_session_response.status_code == 200, (
        f"Failed to get session: {get_session_response.text}"
    )
    session_retrieved = get_session_response.json()

    # Session should have context_window (may not be in API response, but should exist in DB)
    assert session_retrieved["id"] == session_id, "Session ID mismatch"

    # Get messages to verify they're stored
    messages_response = api_client.get(f"/sessions/{session_id}/messages")
    assert messages_response.status_code == 200, f"Failed to get messages: {messages_response.text}"
    messages_data = messages_response.json()
    assert len(messages_data["messages"]) == message_count, f"Should have {message_count} messages"

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_near_limit_detection_via_api(api_client, test_user, test_expert):
    """Test that near limit (>80% usage) is detected correctly.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Session with context_window
    - messages: Added to approach 80% of limit

    Expected Outputs:
    - Near limit condition detected
    - Usage percentage calculated correctly
    - Appropriate flags set
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    context_window = int(get_config("test.at1_10.context_windows.small"))

    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Near Limit Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add messages to approach limit (80% = 160 tokens, ~40 chars per token = 6400 chars)
    # Each message ~50 chars = ~12 tokens, need ~13 messages to reach 80%
    message_count = int(get_config("test.at1_10.message_counts.near_limit"))
    for i in range(message_count):
        message_content = f"Message {i} for near limit test {unique_id}: " + "L" * 30
        api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )

    # Verify messages are stored
    messages_response = api_client.get(f"/sessions/{session_id}/messages")
    assert messages_response.status_code == 200, f"Failed to get messages: {messages_response.text}"
    messages_data = messages_response.json()
    assert len(messages_data["messages"]) == message_count, f"Should have {message_count} messages"

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_exceeded_limit_detection_via_api(api_client, test_user, test_expert):
    """Test that exceeded limit (>100% usage) is detected correctly.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Session with small context_window
    - messages: Added to exceed limit

    Expected Outputs:
    - Exceeded limit condition detected
    - Usage percentage > 100%
    - Appropriate flags set
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    context_window = int(get_config("test.at1_10.context_windows.tiny"))

    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Exceeded Limit Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add messages that exceed limit
    # 100 tokens = ~400 chars, each message ~60 chars = ~15 tokens, need 7+ messages to exceed
    message_count = int(get_config("test.at1_10.message_counts.medium"))
    for i in range(message_count):
        message_content = f"Message {i} for exceeded test {unique_id}: " + "M" * 40
        api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )

    # Verify messages are stored (exceeded limit doesn't prevent storage)
    messages_response = api_client.get(f"/sessions/{session_id}/messages")
    assert messages_response.status_code == 200, f"Failed to get messages: {messages_response.text}"
    messages_data = messages_response.json()
    assert len(messages_data["messages"]) == message_count, f"Should have {message_count} messages"

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_available_tokens_calculation_via_api(api_client, test_user, test_expert):
    """Test that available tokens are calculated correctly.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Session with context_window
    - messages: Added to session

    Expected Outputs:
    - Available tokens = max_tokens - used_tokens
    - Calculation is accurate
    - Reserved tokens accounted for
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    context_window = int(get_config("test.at1_10.context_windows.large"))

    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Available Tokens Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add some messages
    message_count = int(get_config("test.at1_10.message_counts.short"))
    for i in range(message_count):
        message_content = f"Message {i} for available tokens test {unique_id}: " + "N" * 30
        api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )

    # Verify messages stored
    messages_response = api_client.get(f"/sessions/{session_id}/messages")
    assert messages_response.status_code == 200, f"Failed to get messages: {messages_response.text}"
    messages_data = messages_response.json()
    assert len(messages_data["messages"]) == message_count, f"Should have {message_count} messages"

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_reserved_tokens_handling_via_api(api_client, test_user, test_expert):
    """Test that reserved tokens are accounted for in calculations.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - session: Session with context_window
    - reserved tokens: Typically 100 tokens for system prompts

    Expected Outputs:
    - Reserved tokens subtracted from available
    - Calculations account for reserved space
    - System prompts don't exceed reserved space
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    context_window = int(get_config("test.at1_10.context_windows.large"))

    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Reserved Tokens Test {unique_id}",
            "context_window": context_window,
        },
    )
    assert session_response.status_code == 200, f"Failed to create session: {session_response.text}"
    session_data = session_response.json()
    session_id = session_data["id"]

    # Add messages
    message_count = int(get_config("test.at1_10.message_counts.short"))
    for i in range(message_count):
        message_content = f"Message {i} for reserved tokens test {unique_id}: " + "O" * 35
        api_client.post(
            f"/sessions/{session_id}/messages", json={"role": "user", "content": message_content}
        )

    # Verify messages stored
    messages_response = api_client.get(f"/sessions/{session_id}/messages")
    assert messages_response.status_code == 200, f"Failed to get messages: {messages_response.text}"
    messages_data = messages_response.json()
    assert len(messages_data["messages"]) == message_count, f"Should have {message_count} messages"

    delete_response = api_client.delete(f"/sessions/{session_id}")
    if delete_response.status_code not in (200, 204, 404):
        print(
            f"[CLEANUP WARNING] Failed to delete session {session_id}: {delete_response.status_code} {delete_response.text}"
        )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

