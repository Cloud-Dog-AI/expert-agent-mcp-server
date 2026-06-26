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
System Test: ST1.1 - API Server Startup and Endpoint Accessibility

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for API server startup and endpoint accessibility

Related Requirements: FR1.7
Related Tasks: T030
Related Architecture: CC1.1.1
Related Tests: ST1.1

Recent Changes:
- Initial implementation
"""

import pytest
import requests
import time
import uuid

from src.config.loader import get_config, load_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


@pytest.fixture(scope="module")
def api_client(test_env_file):
    """Requests client to a real running API server (RULES.md compliant)."""
    load_config.cache_clear()

    host = get_config("api_server.host")
    port = get_config("api_server.port")
    if not host or port is None:
        pytest.fail("api_server.host/api_server.port not configured (use --env <env-file>)")

    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")

    scheme = str(get_config("api_server.scheme") or "http").strip().lower()
    if scheme not in {"http", "https"}:
        pytest.fail(f"Unsupported api_server.scheme: {scheme}")
    base_url = f"{scheme}://{host}:{int(port)}"
    session = requests.Session()
    verify_tls = get_config("test.http_verify_tls")
    if verify_tls is None:
        session.verify = True
    else:
        session.verify = str(verify_tls).strip().lower() in {"1", "true", "yes", "on"}
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured (set TEST_API_KEY in private/env-*-secrets)")
    session.headers.update({"X-API-Key": str(api_key)})

    # Health check with retries
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
                    f"API server not running at {base_url}. "
                    "Start it with: ./server_control.sh start api --env <env-file>"
                )

    session.base_url = base_url
    session.timeout_seconds = float(timeout)
    logger.info(f"Connected to API server at {base_url}")
    return session
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_api_server_startup(api_client):
    """Test API server can start and respond."""
    response = api_client.get(f"{api_client.base_url}/health", timeout=api_client.timeout_seconds)
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_health_endpoint(api_client):
    """Test health check endpoint."""
    response = api_client.get(f"{api_client.base_url}/health", timeout=api_client.timeout_seconds)
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["status"] == "healthy"
    # Check for either "server" or "service" field (implementation may vary)
    assert "server" in data or "service" in data
    assert "version" in data
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_api_docs_endpoint(api_client):
    """Test API documentation endpoint."""
    response = api_client.get(f"{api_client.base_url}/docs", timeout=api_client.timeout_seconds)
    assert response.status_code == 200
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_api_docs_routes_endpoint(api_client):
    """Test backward-compatible API route summary endpoint."""
    response = api_client.get(
        f"{api_client.base_url}/docs/routes", timeout=api_client.timeout_seconds
    )
    assert response.status_code == 200
    data = response.json()
    required_keys = {"health", "sessions", "users", "experts", "channels", "mcp_chat"}
    missing = required_keys - set(data.keys())
    assert not missing, f"Missing route summary keys: {sorted(missing)}"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_openapi_endpoint(api_client):
    """Test OpenAPI JSON endpoint."""
    response = api_client.get(
        f"{api_client.base_url}/openapi.json", timeout=api_client.timeout_seconds
    )
    assert response.status_code == 200
    data = response.json()
    assert "openapi" in data
    assert "info" in data
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_sessions_endpoint_list(api_client):
    """Test sessions list endpoint."""
    response = api_client.get(f"{api_client.base_url}/sessions", timeout=api_client.timeout_seconds)
    assert response.status_code == 200
    data = response.json()
    assert "sessions" in data
    assert "total" in data
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_sessions_endpoint_create(api_client):
    """Test session creation endpoint."""
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in config")

    unique = uuid.uuid4().hex[:8]
    username = f"{base_username}_st1_{unique}"
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    domain = base_email.split("@", 1)[1]
    email = f"st1_{unique}@{domain}"

    # Create test user via API
    user_response = api_client.post(
        f"{api_client.base_url}/users",
        json={
            "username": username,
            "email": email,
            "password": password,
        },
        timeout=api_client.timeout_seconds,
    )
    assert user_response.status_code == 200
    user_id = user_response.json()["id"]

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    llm_api_key = get_config("llm.api_key")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config")

    expert_response = api_client.post(
        f"{api_client.base_url}/experts",
        json={
            "name": f"ST1 Expert {unique}",
            "title": "ST1 Expert",
            "description": "System test expert for API validation workflows.",
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_base_url": llm_base_url,
            "llm_api_key": llm_api_key,
            "enabled": True,
        },
        timeout=api_client.timeout_seconds,
    )
    assert expert_response.status_code == 200, expert_response.text
    expert_id = expert_response.json()["id"]

    # Create session via API
    response = api_client.post(
        f"{api_client.base_url}/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"ST1 Session {unique}",
        },
        timeout=api_client.timeout_seconds,
    )

    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert "title" in data

    # Cleanup (best-effort)
    api_client.delete(
        f"{api_client.base_url}/sessions/{data['id']}", timeout=api_client.timeout_seconds
    )
    api_client.delete(
        f"{api_client.base_url}/experts/{expert_id}", timeout=api_client.timeout_seconds
    )
    api_client.delete(f"{api_client.base_url}/users/{user_id}", timeout=api_client.timeout_seconds)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_users_endpoint_create(api_client):
    """Test user creation endpoint."""
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in config")

    unique = uuid.uuid4().hex[:8]
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    domain = base_email.split("@", 1)[1]

    response = api_client.post(
        f"{api_client.base_url}/users",
        json={
            "username": f"{base_username}_new_{unique}",
            "email": f"new_{unique}@{domain}",
            "password": password,
            "display_name": f"New User {unique}",
        },
        timeout=api_client.timeout_seconds,
    )

    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["username"]
    assert data["email"]

    api_client.delete(
        f"{api_client.base_url}/users/{data['id']}", timeout=api_client.timeout_seconds
    )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.smtp, pytest.mark.slow, pytest.mark.heavy]

