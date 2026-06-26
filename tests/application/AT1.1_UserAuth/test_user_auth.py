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
Application Test: AT1.1 - User Registration and Authentication

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for user registration, login, logout, token validation and password change via API.

Related Requirements: CS1.1, FR1.5
Related Tasks: T006, T005
Related Architecture: SE1.1, CC5.1.1
Related Tests: AT1.1

Recent Changes:
- Uses real running API server (requests) via shared APIClient
- No hardcoded values (all from config/env hierarchy)
- Adds auth API coverage (/auth/login, /auth/logout, /auth/validate)
"""

import pytest
import time
import uuid
import sys
from pathlib import Path

from src.config.loader import get_config

# Shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import build_test_email, create_api_client_fixture, validate_config_loaded


@pytest.fixture(scope="module")
def api_client():
    """Create API client that connects to real running API server."""
    validate_config_loaded()
    return create_api_client_fixture(check_health=True)()


@pytest.fixture
def base_user_credentials(test_config):
    """Base test user credentials from config hierarchy."""
    username = get_config("test.user.username")
    email = get_config("test.user.email")
    password = get_config("test.user.password")
    display_name = get_config("test.user.display_name")

    if not username or not email or not password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in --env file")

    return {
        "username": username,
        "email": email,
        "password": password,
        "display_name": display_name or username,
    }


@pytest.fixture
def unique_user_credentials(base_user_credentials):
    unique_id = str(uuid.uuid4())[:8]
    base = base_user_credentials
    return {
        "username": f"{base['username']}_at1_1_{unique_id}",
        "email": build_test_email("at1_1", unique_id, base["email"]),
        "password": base["password"],
        "display_name": f"{base['display_name']} {unique_id}",
    }


def _create_user(api_client, creds: dict, password: str | None):
    payload = {
        "username": creds["username"],
        "email": creds["email"],
        "password": password,
        "display_name": creds.get("display_name") or creds["username"],
        "role": "user",
    }
    return api_client.post("/users", json=payload)


def _login(api_client, username: str, password: str, expires_in_seconds: int | None = None):
    payload: dict = {"username": username, "password": password}
    if expires_in_seconds is not None:
        payload["expires_in_seconds"] = expires_in_seconds
    return api_client.post("/auth/login", json=payload)


def _logout(api_client, token: str):
    return api_client.post("/auth/logout", json={"token": token})
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_registration(api_client, unique_user_credentials):
    resp = _create_user(
        api_client, unique_user_credentials, password=unique_user_credentials["password"]
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "id" in data
    assert data["username"] == unique_user_credentials["username"]
    assert data["email"] == unique_user_credentials["email"]

    api_client.delete(f"/users/{data['id']}")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_registration_duplicate_username(api_client, unique_user_credentials):
    resp1 = _create_user(
        api_client, unique_user_credentials, password=unique_user_credentials["password"]
    )
    assert resp1.status_code == 200, resp1.text
    user_id = resp1.json()["id"]

    dup = dict(unique_user_credentials)
    dup["email"] = build_test_email("dup", uuid.uuid4().hex[:8], unique_user_credentials["email"])
    resp2 = _create_user(api_client, dup, password=dup["password"])
    assert resp2.status_code == 400, resp2.text

    api_client.delete(f"/users/{user_id}")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_registration_duplicate_email(api_client, unique_user_credentials):
    resp1 = _create_user(
        api_client, unique_user_credentials, password=unique_user_credentials["password"]
    )
    assert resp1.status_code == 200, resp1.text
    user_id = resp1.json()["id"]

    dup = dict(unique_user_credentials)
    dup["username"] = f"dup_{uuid.uuid4().hex[:8]}"
    resp2 = _create_user(api_client, dup, password=dup["password"])
    assert resp2.status_code == 400, resp2.text

    api_client.delete(f"/users/{user_id}")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_login_success(api_client, unique_user_credentials):
    create = _create_user(
        api_client, unique_user_credentials, password=unique_user_credentials["password"]
    )
    assert create.status_code == 200, create.text
    user_id = create.json()["id"]

    login = _login(
        api_client, unique_user_credentials["username"], unique_user_credentials["password"]
    )
    assert login.status_code == 200, login.text
    assert login.json().get("token")

    api_client.delete(f"/users/{user_id}")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_login_invalid_username(api_client):
    base_username = get_config("test.user.username")
    base_password = get_config("test.user.password")
    if not base_username or not base_password:
        pytest.fail("Missing test.user.username/test.user.password in --env file")
    resp = _login(api_client, f"{base_username}_missing_{uuid.uuid4().hex[:8]}", base_password)
    assert resp.status_code == 401
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_login_invalid_password(api_client, unique_user_credentials):
    create = _create_user(
        api_client, unique_user_credentials, password=unique_user_credentials["password"]
    )
    assert create.status_code == 200, create.text
    user_id = create.json()["id"]

    wrong_password = get_config("test.user.password_weak")
    if not wrong_password:
        pytest.fail("Missing test.user.password_weak in --env file")
    if wrong_password == unique_user_credentials["password"]:
        pytest.fail("test.user.password_weak must differ from test.user.password")
    resp = _login(api_client, unique_user_credentials["username"], wrong_password)
    assert resp.status_code == 401

    api_client.delete(f"/users/{user_id}")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_login_disabled_user(api_client, unique_user_credentials):
    create = _create_user(
        api_client, unique_user_credentials, password=unique_user_credentials["password"]
    )
    assert create.status_code == 200, create.text
    user_id = create.json()["id"]

    disable = api_client.put(f"/users/{user_id}", json={"enabled": False})
    assert disable.status_code == 200, disable.text

    resp = _login(
        api_client, unique_user_credentials["username"], unique_user_credentials["password"]
    )
    assert resp.status_code == 401

    api_client.delete(f"/users/{user_id}")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_logout_token_revocation(api_client, unique_user_credentials):
    create = _create_user(
        api_client, unique_user_credentials, password=unique_user_credentials["password"]
    )
    assert create.status_code == 200, create.text
    user_id = create.json()["id"]

    login = _login(
        api_client, unique_user_credentials["username"], unique_user_credentials["password"]
    )
    assert login.status_code == 200, login.text
    token = login.json()["token"]

    logout = _logout(api_client, token)
    assert logout.status_code == 200, logout.text

    validate = api_client.get(f"/auth/validate?token={token}")
    assert validate.status_code == 200
    assert validate.json().get("valid") is False

    api_client.delete(f"/users/{user_id}")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_token_expiration(api_client, unique_user_credentials):
    create = _create_user(
        api_client, unique_user_credentials, password=unique_user_credentials["password"]
    )
    assert create.status_code == 200, create.text
    user_id = create.json()["id"]

    login = _login(
        api_client,
        unique_user_credentials["username"],
        unique_user_credentials["password"],
        expires_in_seconds=1,
    )
    assert login.status_code == 200, login.text
    token = login.json()["token"]

    time.sleep(2)
    validate = api_client.get(f"/auth/validate?token={token}")
    assert validate.status_code == 200
    assert validate.json().get("valid") is False

    api_client.delete(f"/users/{user_id}")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_registration_external_user(api_client, base_user_credentials):
    uid = uuid.uuid4().hex[:8]
    creds = {
        "username": f"external_{uid}",
        "email": build_test_email("external", uid, base_user_credentials["email"]),
        "display_name": f"External {uid}",
    }
    create = _create_user(api_client, creds, password=None)
    assert create.status_code == 200, create.text
    user_id = create.json()["id"]

    login = _login(api_client, creds["username"], "any-password")
    assert login.status_code == 401

    api_client.delete(f"/users/{user_id}")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_password_change(api_client, unique_user_credentials):
    create = _create_user(
        api_client, unique_user_credentials, password=unique_user_credentials["password"]
    )
    assert create.status_code == 200, create.text
    user_id = create.json()["id"]

    new_password = f"{unique_user_credentials['password']}_new"
    update = api_client.put(f"/users/{user_id}", json={"password": new_password})
    assert update.status_code == 200, update.text

    old_login = _login(
        api_client, unique_user_credentials["username"], unique_user_credentials["password"]
    )
    assert old_login.status_code == 401

    new_login = _login(api_client, unique_user_credentials["username"], new_password)
    assert new_login.status_code == 200, new_login.text

    api_client.delete(f"/users/{user_id}")

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]

