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
Application Test: AT1.11 - MCP Tool Workflows (Basic Session Key Tests)

License: Apache 2.0
Ownership: Cloud Dog
Description: Basic tests for session keys and history keys via API

Related Requirements: FR1.26, FR1.27
Related Tasks: T064, T065
Related Architecture: CC2.1.2, CC2.1.3
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
        "username": f"{base_username}_at1_11_{unique_id}",
        "email": build_test_email("at1_11", unique_id, base_email),
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
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")

    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_at1_11_{unique_id}",
        "title": f"Session Keys Expert {unique_id} session_key history_key continuity recovery sharing",
        "description": "Session key generation scenario with unique vocabulary: acorn basil cipher dune ember fjord glyph helios isotope juniper keystone",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
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
@pytest.mark.req("FR-018")


def test_session_creation_with_keys_via_api(api_client, test_user, test_expert):
    """Test that session creation automatically generates session_key and history_key."""
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    session_title = f"Session with Keys {unique_id}"

    context_window = get_config("session.context_window_size")
    history_retention_days = get_config("session.history_retention_days")
    if context_window is None or history_retention_days is None:
        pytest.fail(
            "Missing session.context_window_size/session.history_retention_days in config (--env)"
        )

    # Create session via API
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
    assert response.status_code == 200, f"Failed to create session: {response.text}"
    session_data = response.json()

    # Validate outputs
    assert "id" in session_data
    assert "session_key" in session_data, "session_key should be in response"
    assert "history_key" in session_data, "history_key should be in response"
    assert session_data["session_key"] is not None, "session_key should not be None"
    assert session_data["history_key"] is not None, "history_key should not be None"
    assert len(session_data["session_key"]) == 36, "session_key should be UUID (36 chars)"
    assert len(session_data["history_key"]) == 36, "history_key should be UUID (36 chars)"

    # Cleanup via API
    try:
        api_client.delete(f"/sessions/{session_data['id']}")
    except Exception:
        pass
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-018")


def test_get_session_by_key_via_api(api_client, test_user, test_expert):
    """Test getting session by session_key."""
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    session_title = f"Session Key Test {unique_id}"

    # Create session
    create_response = api_client.post(
        "/sessions",
        json={"user_id": user_id, "expert_config_id": expert_id, "title": session_title},
    )
    assert create_response.status_code == 200
    session_data = create_response.json()
    session_key = session_data["session_key"]

    # Get session by key
    get_response = api_client.get(f"/sessions/key/{session_key}")
    assert get_response.status_code == 200, f"Failed to get session by key: {get_response.text}"
    retrieved_session = get_response.json()

    # Validate outputs
    assert retrieved_session["id"] == session_data["id"]
    assert retrieved_session["session_key"] == session_key
    assert retrieved_session["history_key"] == session_data["history_key"]

    # Cleanup via API
    try:
        api_client.delete(f"/sessions/{session_data['id']}")
    except Exception:
        pass
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-018")


def test_get_history_by_key_via_api(api_client, test_user, test_expert):
    """Test getting history by history_key."""
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]
    session_title = f"History Key Test {unique_id}"

    # Create session
    create_response = api_client.post(
        "/sessions",
        json={"user_id": user_id, "expert_config_id": expert_id, "title": session_title},
    )
    assert create_response.status_code == 200
    session_data = create_response.json()
    history_key = session_data["history_key"]
    session_id = session_data["id"]

    # Add a message
    add_message_response = api_client.post(
        f"/sessions/{session_id}/messages",
        json={"role": "user", "content": f"Test message for history key {unique_id}"},
    )
    assert add_message_response.status_code == 200

    # Get history by key
    get_history_response = api_client.get(f"/sessions/history/{history_key}")
    assert get_history_response.status_code == 200, (
        f"Failed to get history by key: {get_history_response.text}"
    )
    history_data = get_history_response.json()

    # Validate outputs
    assert history_data["session_id"] == session_id
    assert history_data["history_key"] == history_key
    assert "messages" in history_data
    assert history_data["count"] == 1
    assert history_data["messages"][0]["content"] == f"Test message for history key {unique_id}"

    # Cleanup via API
    try:
        api_client.delete(f"/sessions/{session_id}")
    except Exception:
        pass

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.mcp, pytest.mark.heavy]

