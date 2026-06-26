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

import time
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
@pytest.mark.req("FR-023")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_it232_response_quality_scoring_integration(test_env_file):
    load_config.cache_clear()
    key = get_config("test.api_key")
    if not key:
        pytest.fail("test.api_key not configured")

    base = _api_base()
    timeout = float(get_config("test.http_timeout_seconds") or 60)
    s = requests.Session()
    s.headers.update({"X-API-Key": str(key)})

    token = uuid.uuid4().hex[:8]
    u = s.post(
        f"{base}/users",
        json={
            "username": f"{get_config('test.user.username')}_it232_{token}",
            "email": f"it232_{token}@{str(get_config('test.user.email')).split('@', 1)[1]}",
            "password": str(get_config("test.user.password")),
            "display_name": f"IT232 {token}",
        },
        timeout=timeout,
    )
    assert u.status_code == 200, u.text
    user_id = int(u.json()["id"])

    e = s.post(
        f"{base}/experts",
        json={
            "name": f"it232_expert_{token}",
            "title": f"IT232 Expert {token}",
            "description": f"Quality scoring integration expert {token}.",
            "llm_provider": str(get_config("llm.provider")),
            "llm_model": str(get_config("llm.model")),
            "llm_base_url": str(get_config("llm.base_url")),
            "llm_api_key": get_config("llm.api_key"),
            "enabled": True,
        },
        timeout=timeout,
    )
    assert e.status_code == 200, e.text
    expert_id = int(e.json()["id"])

    c = s.post(
        f"{base}/channels",
        json={"name": f"IT232 Channel {token}", "expert_config_id": expert_id, "enabled": True},
        timeout=timeout,
    )
    assert c.status_code == 200, c.text
    channel_id = int(c.json()["id"])

    try:
        async_chat = s.post(
            f"{base}/channels/{channel_id}/chat",
            json={"message": "quality scoring", "user_id": user_id, "async_mode": True},
            timeout=timeout,
        )
        assert async_chat.status_code == 200, async_chat.text
        job_id = int(async_chat.json()["job_id"])

        # Wait for completion to ensure prompt/response available.
        for _ in range(50):
            j = s.get(f"{base}/jobs/{job_id}", timeout=timeout)
            assert j.status_code == 200, j.text
            if j.json().get("status") in {"completed", "failed"}:
                break
            time.sleep(0.5)

        evaluated = s.post(f"{base}/quality/evaluate", json={"job_id": job_id}, timeout=timeout)
        assert evaluated.status_code == 200, evaluated.text
        metrics = evaluated.json().get("metrics")
        assert isinstance(metrics, dict)
        assert "overall_score" in metrics

        feedback = s.post(
            f"{base}/quality/feedback", json={"job_id": job_id, "rating": 4}, timeout=timeout
        )
        assert feedback.status_code == 200, feedback.text

        fetched = s.get(f"{base}/quality/job/{job_id}", timeout=timeout)
        assert fetched.status_code == 200, fetched.text
        assert isinstance(fetched.json().get("quality_metrics"), dict)
    finally:
        s.delete(f"{base}/channels/{channel_id}", timeout=timeout)
        s.delete(f"{base}/experts/{expert_id}", timeout=timeout)
        s.delete(f"{base}/users/{user_id}", timeout=timeout)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.smtp, pytest.mark.heavy]

