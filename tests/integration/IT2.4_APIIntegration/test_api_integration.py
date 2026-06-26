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
Integration Test: IT2.7 - API Integration

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for API integration with session and user management

Related Requirements: FR1.7
Related Tasks: T030
Related Architecture: AI1.1
Related Tests: IT2.7

Recent Changes:
- Initial implementation
"""

import pytest
import requests
import time
import uuid
from src.config.loader import get_config, load_config


def _require_bool(path: str, default: bool) -> bool:
    value = get_config(path)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


@pytest.fixture
def api_client(test_env_file):
    """Requests client to a real running API server."""
    load_config.cache_clear()
    base_url_cfg = get_config("api_server.base_url")
    if base_url_cfg:
        base_url = str(base_url_cfg).rstrip("/")
    else:
        host = get_config("api_server.host")
        port = get_config("api_server.port")
        scheme = str(get_config("api_server.scheme") or "http").strip().lower()
        if not host or port is None:
            pytest.fail("api_server.host/api_server.port not configured (use --env <env-file>)")
        if scheme not in {"http", "https"}:
            pytest.fail(f"Unsupported api_server.scheme: {scheme}")
        base_url = f"{scheme}://{host}:{int(port)}"
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured (set TEST_API_KEY in private/env-*-secrets)")
    verify_tls = _require_bool("test.http_verify_tls", True)
    session = requests.Session()
    session.headers.update({"X-API-Key": str(api_key)})
    session.verify = verify_tls
    for attempt in range(3):
        try:
            r = session.get(f"{base_url}/health", timeout=float(timeout))
            if r.status_code == 200:
                break
        except requests.RequestException:
            if attempt < 2:
                time.sleep(1)
            else:
                pytest.fail(
                    f"API server not running at {base_url}. Start it with: ./server_control.sh start api --env <env-file>"
                )
    session.base_url = base_url
    session.timeout_seconds = float(timeout)
    return session


@pytest.fixture
def test_user(api_client):
    """Create a test user via API."""
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail(
            "Missing test.user.username/test.user.email/test.user.password in config (--env)"
        )
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    unique = uuid.uuid4().hex[:8]
    domain = base_email.split("@", 1)[1]
    response = api_client.post(
        f"{api_client.base_url}/users",
        json={
            "username": f"{base_username}_it2_4_{unique}",
            "email": f"it2_4_{unique}@{domain}",
            "password": password,
        },
        timeout=api_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    user = response.json()
    yield user
    api_client.delete(
        f"{api_client.base_url}/users/{user['id']}", timeout=api_client.timeout_seconds
    )


@pytest.fixture
def test_expert(api_client):
    """Create a test expert configuration via API."""
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    llm_api_key = get_config("llm.api_key")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")
    unique = uuid.uuid4().hex[:8]
    response = api_client.post(
        f"{api_client.base_url}/experts",
        json={
            "name": f"test_expert_it2_4_{unique}",
            "title": f"API Integration Expert Alpha Beta {unique}",
            "description": (
                "Exercises user, session, and message endpoints via API calls "
                f"with unique token {unique} for entropy validation."
            ),
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_base_url": llm_base_url,
            "llm_api_key": llm_api_key,
            "enabled": True,
        },
        timeout=api_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    expert = response.json()
    yield expert
    api_client.delete(
        f"{api_client.base_url}/experts/{expert['id']}", timeout=api_client.timeout_seconds
    )
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_api_create_user(api_client):
    """Test creating user via API."""
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail(
            "Missing test.user.username/test.user.email/test.user.password in config (--env)"
        )
    unique = uuid.uuid4().hex[:8]
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    domain = base_email.split("@", 1)[1]
    username = f"{base_username}_api_{unique}"
    email = f"api_{unique}@{domain}"
    response = api_client.post(
        f"{api_client.base_url}/users",
        json={
            "username": username,
            "email": email,
            "password": password,
            "display_name": "API User",
        },
        timeout=api_client.timeout_seconds,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert "id" in data
    assert data["username"] == username
    assert data["email"] == email
    api_client.delete(
        f"{api_client.base_url}/users/{data['id']}",
        timeout=api_client.timeout_seconds,
    )
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_api_get_user(api_client, test_user):
    """Test getting user via API."""
    user_id = test_user["id"] if isinstance(test_user, dict) else test_user.id
    response = api_client.get(
        f"{api_client.base_url}/users/{user_id}",
        timeout=api_client.timeout_seconds,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["id"] == user_id
    assert data["username"] == (
        test_user["username"] if isinstance(test_user, dict) else test_user.username
    )
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_api_create_session(api_client, test_user, test_expert):
    """Test creating session via API."""
    user_id = test_user["id"] if isinstance(test_user, dict) else test_user.id
    expert_id = test_expert["id"] if isinstance(test_expert, dict) else test_expert.id

    response = api_client.post(
        f"{api_client.base_url}/sessions",
        json={"user_id": user_id, "expert_config_id": expert_id, "title": "API Test Session"},
        timeout=api_client.timeout_seconds,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert "id" in data
    assert data["title"] == "API Test Session"
    assert data["user_id"] == user_id
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_api_get_session(api_client, test_user, test_expert):
    """Test getting session via API."""
    user_id = test_user["id"] if isinstance(test_user, dict) else test_user.id
    expert_id = test_expert["id"] if isinstance(test_expert, dict) else test_expert.id

    # Create session via API
    create_response = api_client.post(
        f"{api_client.base_url}/sessions",
        json={"user_id": user_id, "expert_config_id": expert_id, "title": "Test Session"},
        timeout=api_client.timeout_seconds,
    )
    assert create_response.status_code == 200, create_response.text
    session_data = create_response.json()
    session_id = session_data["id"]

    # Get via API
    response = api_client.get(
        f"{api_client.base_url}/sessions/{session_id}",
        timeout=api_client.timeout_seconds,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert data["id"] == session_id
    assert data["title"] == "Test Session"
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_api_add_message(api_client, test_user, test_expert):
    """Test adding message via API."""
    user_id = test_user["id"] if isinstance(test_user, dict) else test_user.id
    expert_id = test_expert["id"] if isinstance(test_expert, dict) else test_expert.id

    # Create session via API
    create_response = api_client.post(
        f"{api_client.base_url}/sessions",
        json={"user_id": user_id, "expert_config_id": expert_id},
        timeout=api_client.timeout_seconds,
    )
    assert create_response.status_code == 200, create_response.text
    session_data = create_response.json()
    session_id = session_data["id"]

    # Add message via API
    response = api_client.post(
        f"{api_client.base_url}/sessions/{session_id}/messages",
        json={"role": "user", "content": "Hello from API", "tokens_used": 5},
        timeout=api_client.timeout_seconds,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert "id" in data
    assert data["role"] == "user"
    assert data["content"] == "Hello from API"
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_api_get_messages(api_client, test_user, test_expert):
    """Test getting messages via API."""
    user_id = test_user["id"] if isinstance(test_user, dict) else test_user.id
    expert_id = test_expert["id"] if isinstance(test_expert, dict) else test_expert.id

    # Create session via API
    create_response = api_client.post(
        f"{api_client.base_url}/sessions",
        json={"user_id": user_id, "expert_config_id": expert_id},
        timeout=api_client.timeout_seconds,
    )
    assert create_response.status_code == 200, create_response.text
    session_data = create_response.json()
    session_id = session_data["id"]

    # Add messages via API
    msg1_response = api_client.post(
        f"{api_client.base_url}/sessions/{session_id}/messages",
        json={"role": "user", "content": "Message 1"},
        timeout=api_client.timeout_seconds,
    )
    assert msg1_response.status_code == 200, msg1_response.text

    msg2_response = api_client.post(
        f"{api_client.base_url}/sessions/{session_id}/messages",
        json={"role": "assistant", "content": "Response 1"},
        timeout=api_client.timeout_seconds,
    )
    assert msg2_response.status_code == 200, msg2_response.text

    # Get messages via API
    response = api_client.get(
        f"{api_client.base_url}/sessions/{session_id}/messages",
        timeout=api_client.timeout_seconds,
    )

    assert response.status_code == 200, response.text
    data = response.json()
    assert "messages" in data
    assert len(data["messages"]) >= 2
    # Messages might be in different order, so check both exist
    contents = [msg["content"] for msg in data["messages"]]
    assert "Message 1" in contents
    assert "Response 1" in contents

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.smtp, pytest.mark.heavy]

