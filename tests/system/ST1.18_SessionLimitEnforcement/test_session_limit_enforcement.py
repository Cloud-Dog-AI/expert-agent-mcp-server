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
System Test: ST1.18 - Session Limit Enforcement at System Level

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for system-level session limit enforcement

Related Requirements: FR1.11
Related Tasks: T027
Related Architecture: CP1.1.5
Related Tests: ST1.18

Recent Changes:
- Initial implementation
"""

import pytest
import requests
import time
import uuid

from src.config.loader import get_config, load_config


@pytest.fixture(scope="module")
def api_client(test_env_file):
    """Requests client to a real running API server."""
    load_config.cache_clear()

    host = get_config("api_server.host")
    port = get_config("api_server.port")
    if not host or port is None:
        pytest.fail("api_server.host/api_server.port not configured (use --env <env-file>)")

    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")

    base_url = f"http://{host}:{int(port)}"
    s = requests.Session()
    s.base_url = base_url
    s.timeout_seconds = float(timeout)
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured (set TEST_API_KEY in private/env-*-secrets)")
    s.headers.update({"X-API-Key": str(api_key)})

    for attempt in range(3):
        try:
            r = s.get(f"{base_url}/health", timeout=s.timeout_seconds)
            if r.status_code == 200:
                break
        except requests.RequestException:
            if attempt < 2:
                time.sleep(1)
            else:
                pytest.fail(
                    f"API server not running at {base_url}. Start it with: ./server_control.sh start api --env <env-file>"
                )

    return s
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_system_enforces_user_session_limit(api_client):
    """System should enforce per-user session limits via the API."""
    max_sessions = get_config("session.max_sessions_per_user")
    if max_sessions is None:
        pytest.fail("session.max_sessions_per_user not configured")
    max_sessions = int(max_sessions)

    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in config")

    unique = uuid.uuid4().hex[:8]
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    domain = base_email.split("@", 1)[1]

    r_user = api_client.post(
        f"{api_client.base_url}/users",
        json={
            "username": f"{base_username}_st1_18_{unique}",
            "email": f"st1_18_{unique}@{domain}",
            "password": password,
        },
        timeout=api_client.timeout_seconds,
    )
    assert r_user.status_code == 200, r_user.text
    user_id = r_user.json()["id"]

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    llm_api_key = get_config("llm.api_key")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config")

    r_expert = api_client.post(
        f"{api_client.base_url}/experts",
        json={
            "name": f"ST1.18 Expert {unique}",
            "title": "ST1.18 Expert",
            "description": "System test expert for session limit enforcement.",
            "llm_provider": llm_provider,
            "llm_model": llm_model,
            "llm_base_url": llm_base_url,
            "llm_api_key": llm_api_key,
            "enabled": True,
        },
        timeout=api_client.timeout_seconds,
    )
    assert r_expert.status_code == 200, r_expert.text
    expert_id = r_expert.json()["id"]

    created_session_ids = []
    try:
        for i in range(max_sessions):
            r_sess = api_client.post(
                f"{api_client.base_url}/sessions",
                json={
                    "user_id": user_id,
                    "expert_config_id": expert_id,
                    "title": f"ST1.18 Session {i}",
                },
                timeout=api_client.timeout_seconds,
            )
            assert r_sess.status_code == 200, r_sess.text
            created_session_ids.append(r_sess.json()["id"])

        r_extra = api_client.post(
            f"{api_client.base_url}/sessions",
            json={
                "user_id": user_id,
                "expert_config_id": expert_id,
                "title": "ST1.18 Extra Session",
            },
            timeout=api_client.timeout_seconds,
        )
        # Depending on configuration, the system may either reject the request OR queue it.
        if r_extra.status_code == 200:
            data = r_extra.json()
            assert data.get("status") == "queued", r_extra.text
            assert "queue_position" in data, r_extra.text
            assert isinstance(data.get("queue_position"), int), r_extra.text
        else:
            assert r_extra.status_code in (400, 409, 422, 429), r_extra.text
    finally:
        for sid in created_session_ids:
            api_client.delete(
                f"{api_client.base_url}/sessions/{sid}", timeout=api_client.timeout_seconds
            )
        api_client.delete(
            f"{api_client.base_url}/experts/{expert_id}", timeout=api_client.timeout_seconds
        )
        api_client.delete(
            f"{api_client.base_url}/users/{user_id}", timeout=api_client.timeout_seconds
        )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.smtp, pytest.mark.slow, pytest.mark.heavy]

