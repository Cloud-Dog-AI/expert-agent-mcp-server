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

import uuid

import pytest
import requests

from src.config.loader import get_config, load_config


pytestmark = pytest.mark.application


def _api_base() -> str:
    host, port = get_config("api_server.host"), get_config("api_server.port")
    if not host or port is None:
        pytest.fail("api_server.host/api_server.port not configured")
    return f"http://{host}:{int(port)}"


    # Covers: NF1.4
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-036")
def test_at122_gdpr_export_and_deletion_roundtrip(test_env_file):
    load_config.cache_clear()
    api_key = get_config("test.api_key")
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not api_key:
        pytest.fail("test.api_key not configured")
    if not base_username or not base_email or not password:
        pytest.fail("test.user.username/test.user.email/test.user.password not configured")
    if "@" not in str(base_email):
        pytest.fail("test.user.email must include a domain")

    timeout = float(get_config("test.http_timeout_seconds") or 60)
    base_url = _api_base()
    session = requests.Session()
    session.headers.update({"X-API-Key": str(api_key)})

    token = uuid.uuid4().hex[:8]
    domain = str(base_email).split("@", 1)[1]
    created_user_id = None
    created_expert_id = None

    try:
        created_user = session.post(
            f"{base_url}/users",
            json={
                "username": f"{base_username}_at122_{token}",
                "email": f"at122_{token}@{domain}",
                "password": str(password),
                "display_name": f"AT122 {token}",
            },
            timeout=timeout,
        )
        assert created_user.status_code == 200, created_user.text
        created_user_id = int(created_user.json()["id"])

        created_expert = session.post(
            f"{base_url}/experts",
            json={
                "name": f"at122_expert_{token}",
                "title": f"AT122 GDPR Expert {token}",
                "description": f"GDPR export/deletion flow validation {token}",
                "llm_provider": str(get_config("llm.provider")),
                "llm_model": str(get_config("llm.model")),
                "llm_base_url": str(get_config("llm.base_url")),
                "enabled": True,
            },
            timeout=timeout,
        )
        assert created_expert.status_code == 200, created_expert.text
        created_expert_id = int(created_expert.json()["id"])

        created_session = session.post(
            f"{base_url}/sessions",
            json={
                "user_id": created_user_id,
                "expert_config_id": created_expert_id,
                "title": f"AT122 Session {token}",
            },
            timeout=timeout,
        )
        assert created_session.status_code == 200, created_session.text
        session_id = int(created_session.json()["id"])

        add_message = session.post(
            f"{base_url}/sessions/{session_id}/messages",
            json={"role": "user", "content": f"AT122 message {token}"},
            timeout=timeout,
        )
        assert add_message.status_code == 200, add_message.text

        exported = session.get(f"{base_url}/users/{created_user_id}/gdpr/export", timeout=timeout)
        assert exported.status_code == 200, exported.text
        payload = exported.json()
        assert int(payload["user"]["id"]) == created_user_id
        assert payload["counts"]["sessions"] >= 1
        assert payload["counts"]["messages"] >= 1

        deleted = session.delete(f"{base_url}/users/{created_user_id}/gdpr/delete", timeout=timeout)
        assert deleted.status_code == 200, deleted.text
        deleted_payload = deleted.json()
        assert deleted_payload.get("deleted", {}).get("users") == 1

        verify_absent = session.get(f"{base_url}/users/{created_user_id}", timeout=timeout)
        assert verify_absent.status_code == 404, verify_absent.text

        created_user_id = None
    finally:
        if created_expert_id is not None:
            session.delete(f"{base_url}/experts/{created_expert_id}", timeout=timeout)
        if created_user_id is not None:
            session.delete(f"{base_url}/users/{created_user_id}", timeout=timeout)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]
