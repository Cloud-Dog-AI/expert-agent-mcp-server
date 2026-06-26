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
System Test: ST1.4 - Web UI Route and Critical Flow Contract

License: Apache 2.0
Ownership: Cloud Dog
Description: Real Web UI endpoint validation against running web server

Related Requirements: FR1.8, FR1.21, FR1.22
Related Tasks: T048, T049, T059, T060
Related Architecture: CC1.1.2, AI1.4
Related Tests: ST1.4
"""

import time
import uuid

import pytest
import requests

from src.config.loader import get_config, load_config


def _require_timeout() -> float:
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    return float(timeout)


def _require_bool(path: str, default: bool) -> bool:
    value = get_config(path)
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _require_base_url(host_key: str, port_key: str, scheme_key: str) -> str:
    host = get_config(host_key)
    port = get_config(port_key)
    if not host or port is None:
        pytest.fail(f"{host_key}/{port_key} not configured")
    scheme = str(get_config(scheme_key) or "http").strip().lower()
    if scheme not in {"http", "https"}:
        pytest.fail(f"Unsupported scheme for {scheme_key}: {scheme}")
    return f"{scheme}://{host}:{int(port)}"


def _wait_for_health(session: requests.Session, url: str, timeout: float, label: str) -> None:
    last_error = None
    for _ in range(5):
        try:
            response = session.get(url, timeout=timeout)
            if response.status_code == 200:
                return
        except requests.RequestException as exc:
            last_error = str(exc)
        time.sleep(0.5)
    pytest.fail(f"{label} not healthy at {url}. last_error={last_error}")


@pytest.fixture
def web_client(test_env_file):
    load_config.cache_clear()
    timeout = _require_timeout()
    base_url = _require_base_url("web_server.host", "web_server.port", "web_server.scheme")
    session = requests.Session()
    session.verify = _require_bool("test.http_verify_tls", True)
    _wait_for_health(session, f"{base_url}/health", timeout, "Web server")
    session.base_url = base_url
    session.timeout_seconds = timeout
    return session


@pytest.fixture
def api_base_url(test_env_file):
    load_config.cache_clear()
    return _require_base_url("api_server.host", "api_server.port", "api_server.scheme")


def _assert_html_response(response: requests.Response) -> None:
    assert response.status_code == 200, response.text
    content_type = response.headers.get("content-type", "").lower()
    assert "text/html" in content_type


def _assert_spa_shell(response: requests.Response) -> None:
    _assert_html_response(response)
    body = response.text
    assert 'id="root"' in body
    assert "/runtime-config.js" in body
    assert "type=\"module\"" in body
@pytest.mark.ST
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_web_health_contract(web_client):
    response = web_client.get(
        f"{web_client.base_url}/health",
        timeout=web_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload.get("status") == "healthy"
    assert payload.get("server") == "Web Server"
    assert payload.get("application") == "expert-agent-mcp-server"
    assert payload.get("version")
    env = payload.get("env")
    assert isinstance(env, dict)
    assert "config_env_file" in env
    config_env_file = env.get("config_env_file")
    assert (config_env_file is None) or isinstance(config_env_file, str)
@pytest.mark.ST
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_web_index_contract(web_client, api_base_url):
    response = web_client.get(
        f"{web_client.base_url}/",
        timeout=web_client.timeout_seconds,
    )
    _assert_spa_shell(response)
    body = response.text
    assert "<title>" in body.lower()
    assert "expert agent" in body.lower()
    assert "/runtime-config.js" in body
@pytest.mark.ST
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_web_runtime_config_contract(web_client):
    response = web_client.get(
        f"{web_client.base_url}/runtime-config.js",
        timeout=web_client.timeout_seconds,
    )
    assert response.status_code == 200, response.text
    content_type = response.headers.get("content-type", "").lower()
    assert "javascript" in content_type
    body = response.text
    assert "window.__RUNTIME_CONFIG__" in body
    assert "\"API_BASE_URL\"" in body
    assert "\"WEB_API_BASE_URL\": \"/web/api\"" in body
    assert "\"AUTH_MODE\": \"cookie\"" in body
@pytest.mark.ST
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_web_chat_route_contract(web_client):
    response = web_client.get(
        f"{web_client.base_url}/chat",
        timeout=web_client.timeout_seconds,
    )
    _assert_spa_shell(response)
@pytest.mark.ST
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_web_channels_route_contract(web_client):
    response = web_client.get(
        f"{web_client.base_url}/channels",
        timeout=web_client.timeout_seconds,
    )
    _assert_spa_shell(response)
@pytest.mark.ST
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_web_assets_mount_contract(web_client):
    response = web_client.get(
        f"{web_client.base_url}/assets/health-check.css",
        timeout=web_client.timeout_seconds,
    )
    assert response.status_code in {200, 404}
@pytest.mark.ST
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_web_unknown_browser_route_returns_spa_shell(web_client):
    response = web_client.get(
        f"{web_client.base_url}/__st1_4_missing_route__",
        timeout=web_client.timeout_seconds,
    )
    _assert_spa_shell(response)
@pytest.mark.ST
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_uc133_critical_web_ui_routes_present(web_client):
    # UC1.33 "Complete Web UI Coverage" critical baseline routes
    required_paths = ["/", "/chat", "/channels", "/login", "/web/auth/login", "/health"]
    for path in required_paths:
        response = web_client.get(
            f"{web_client.base_url}{path}",
            timeout=web_client.timeout_seconds,
        )
        assert response.status_code == 200, f"route {path} failed with {response.status_code}"
@pytest.mark.ST
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_web_login_route_serves_spa_shell(web_client):
    response = web_client.get(
        f"{web_client.base_url}/web/auth/login",
        timeout=web_client.timeout_seconds,
    )
    _assert_spa_shell(response)
@pytest.mark.ST
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_web_login_rejects_invalid_credentials(web_client):
    response = web_client.post(
        f"{web_client.base_url}/web/auth/login",
        json={"username": "invalid-user", "password": "invalid-password"},
        timeout=web_client.timeout_seconds,
    )
    assert response.status_code in {401, 403}, response.text
@pytest.mark.ST
@pytest.mark.webui
@pytest.mark.req("FR-032")


def test_web_username_password_login_and_api_proxy(web_client):
    # Covers: FR1.43
    username = get_config("test.user.username")
    password = get_config("test.user.password")
    base_email = get_config("test.user.email")
    if not username or not password or not base_email:
        pytest.fail("test.user.username/test.user.password/test.user.email not configured")

    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")
    api_base_url = _require_base_url("api_server.host", "api_server.port", "api_server.scheme")

    unique = uuid.uuid4().hex[:8]
    if "@" not in str(base_email):
        pytest.fail("test.user.email must include a domain")
    domain = str(base_email).split("@", 1)[1]
    login_username = f"{username}_st14_{unique}"
    login_password = str(password)

    api_session = requests.Session()
    api_session.headers.update({"X-API-Key": str(api_key)})
    create_user = api_session.post(
        f"{api_base_url}/users",
        json={
            "username": login_username,
            "email": f"st14_{unique}@{domain}",
            "password": login_password,
            "display_name": f"ST1.4 User {unique}",
        },
        timeout=web_client.timeout_seconds,
    )
    assert create_user.status_code == 200, create_user.text
    created_user = create_user.json()
    user_id = created_user.get("id")

    try:
        login_response = web_client.post(
            f"{web_client.base_url}/web/auth/login",
            json={"username": login_username, "password": login_password},
            timeout=web_client.timeout_seconds,
        )
        assert login_response.status_code == 200, login_response.text
        login_payload = login_response.json()
        assert login_payload.get("authenticated") is True
        assert login_payload.get("user_id")

        status_response = web_client.get(
            f"{web_client.base_url}/web/auth/status",
            timeout=web_client.timeout_seconds,
        )
        assert status_response.status_code == 200, status_response.text
        status_payload = status_response.json()
        assert status_payload.get("authenticated") is True
        assert status_payload.get("user_id") == login_payload.get("user_id")

        proxy_health = web_client.get(
            f"{web_client.base_url}/web/api/health",
            timeout=web_client.timeout_seconds,
        )
        assert proxy_health.status_code == 200, proxy_health.text
        proxy_payload = proxy_health.json()
        assert proxy_payload.get("status") == "healthy"

        logout_response = web_client.post(
            f"{web_client.base_url}/web/auth/logout",
            timeout=web_client.timeout_seconds,
        )
        assert logout_response.status_code == 200, logout_response.text

        blocked_proxy = web_client.get(
            f"{web_client.base_url}/web/api/health",
            timeout=web_client.timeout_seconds,
        )
        assert blocked_proxy.status_code == 401
    finally:
        if user_id:
            api_session.delete(
                f"{api_base_url}/users/{user_id}", timeout=web_client.timeout_seconds
            )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.smtp, pytest.mark.mcp, pytest.mark.slow, pytest.mark.heavy]
