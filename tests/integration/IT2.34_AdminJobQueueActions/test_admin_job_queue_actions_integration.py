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


def _api_base() -> str:
    base = get_config("api_server.base_url")
    if base:
        return str(base).rstrip("/")
    h, p = get_config("api_server.host"), get_config("api_server.port")
    if not h or p is None:
        pytest.fail("api_server.host/api_server.port not configured")
    return f"http://{h}:{int(p)}"
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-047")


def test_it234_admin_job_queue_actions_integration(test_env_file):
    load_config.cache_clear()
    key = get_config("test.api_key")
    if not key:
        pytest.fail("test.api_key not configured")

    s = requests.Session()
    s.headers.update({"X-API-Key": str(key)})
    base = _api_base()
    timeout = float(get_config("test.http_timeout_seconds") or 60)

    token = uuid.uuid4().hex[:8]
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    domain = str(base_email).split("@", 1)[1]

    user = s.post(
        f"{base}/users",
        json={
            "username": f"{base_username}_it234_{token}",
            "email": f"it234_{token}@{domain}",
            "password": str(password),
            "display_name": f"IT234 {token}",
        },
        timeout=timeout,
    )
    assert user.status_code == 200, user.text
    user_id = int(user.json()["id"])

    expert = s.post(
        f"{base}/experts",
        json={
            "name": f"it234_expert_{token}",
            "title": f"IT234 Expert {token}",
            "description": f"Admin job queue actions expert {token}.",
            "llm_provider": str(get_config("llm.provider")),
            "llm_model": str(get_config("llm.model")),
            "llm_base_url": str(get_config("llm.base_url")),
            "llm_api_key": get_config("llm.api_key"),
            "enabled": True,
        },
        timeout=timeout,
    )
    assert expert.status_code == 200, expert.text
    expert_id = int(expert.json()["id"])

    channel = s.post(
        f"{base}/channels",
        json={"name": f"IT234 Channel {token}", "expert_config_id": expert_id, "enabled": True},
        timeout=timeout,
    )
    assert channel.status_code == 200, channel.text
    channel_id = int(channel.json()["id"])

    try:
        message_token = f"queue-actions-{token}"
        chat = s.post(
            f"{base}/channels/{channel_id}/chat",
            json={"message": message_token, "user_id": user_id, "async_mode": True},
            timeout=timeout,
        )
        assert chat.status_code == 200, chat.text
        job_id = int(chat.json()["job_id"])

        status_resp = s.get(f"{base}/jobs/queue/status", timeout=timeout)
        assert status_resp.status_code == 200, status_resp.text

        listed = s.get(f"{base}/jobs", params={"limit": 20}, timeout=timeout)
        assert listed.status_code == 200, listed.text

        details = s.get(f"{base}/jobs/{job_id}", timeout=timeout)
        assert details.status_code == 200, details.text
        assert int(details.json().get("id")) == job_id

        # Stop/remove/resubmit endpoints must be reachable and enforce status rules.
        stop = s.post(f"{base}/jobs/{job_id}/stop", timeout=timeout)
        assert stop.status_code in {200, 400}, stop.text

        remove = s.delete(f"{base}/jobs/{job_id}", timeout=timeout)
        assert remove.status_code in {200, 400}, remove.text

        resubmit = s.post(f"{base}/jobs/{job_id}/resubmit", json={"priority": 0}, timeout=timeout)
        assert resubmit.status_code in {200, 400}, resubmit.text

        # Audit endpoint should remain accessible after queue actions.
        audit = s.get(f"{base}/audit", params={"limit": 5}, timeout=timeout)
        assert audit.status_code == 200, audit.text
    finally:
        s.delete(f"{base}/channels/{channel_id}", timeout=timeout)
        s.delete(f"{base}/experts/{expert_id}", timeout=timeout)
        s.delete(f"{base}/users/{user_id}", timeout=timeout)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.smtp, pytest.mark.heavy]

