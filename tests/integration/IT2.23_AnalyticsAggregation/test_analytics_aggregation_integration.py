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


pytestmark = pytest.mark.integration


def _base(section: str) -> str:
    base = get_config(f"{section}.base_url")
    if base:
        return str(base).rstrip("/")
    h, p = get_config(f"{section}.host"), get_config(f"{section}.port")
    if not h or p is None:
        pytest.fail(f"{section}.host/{section}.port not configured")
    return f"http://{h}:{int(p)}"


@pytest.fixture
def clients(test_env_file):
    load_config.cache_clear()
    api_key = get_config("test.api_key")
    timeout = float(get_config("test.http_timeout_seconds") or 60)
    if not api_key:
        pytest.fail("test.api_key not configured")
    api = requests.Session()
    api.headers.update({"X-API-Key": str(api_key)})
    api.timeout_seconds = timeout
    return {"api": api, "api_url": _base("api_server")}
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-047")


def test_it223_analytics_pipeline_job_quality_queue(clients):
    api, api_url = clients["api"], clients["api_url"]
    u = uuid.uuid4().hex[:8]
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    domain = str(base_email).split("@", 1)[1]

    user = api.post(
        f"{api_url}/users",
        json={
            "username": f"{base_username}_it223_{u}",
            "email": f"it223_{u}@{domain}",
            "password": str(password),
            "display_name": f"IT223 {u}",
        },
        timeout=api.timeout_seconds,
    )
    assert user.status_code == 200, user.text
    user_id = int(user.json()["id"])

    expert = api.post(
        f"{api_url}/experts",
        json={
            "name": f"it223_expert_{u}",
            "title": f"IT223 Expert {u}",
            "description": f"IT2.23 analytics aggregation integration expert token {u}.",
            "llm_provider": str(get_config("llm.provider")),
            "llm_model": str(get_config("llm.model")),
            "llm_base_url": str(get_config("llm.base_url")),
            "llm_api_key": get_config("llm.api_key"),
            "enabled": True,
        },
        timeout=api.timeout_seconds,
    )
    assert expert.status_code == 200, expert.text
    expert_id = int(expert.json()["id"])

    channel = api.post(
        f"{api_url}/channels",
        json={
            "name": f"IT223 Channel {u}",
            "expert_config_id": expert_id,
            "description": f"Analytics pipeline integration {u}",
            "enabled": True,
        },
        timeout=api.timeout_seconds,
    )
    assert channel.status_code == 200, channel.text
    channel_id = int(channel.json()["id"])

    try:
        async_chat = api.post(
            f"{api_url}/channels/{channel_id}/chat",
            json={"message": "analytics pipeline event", "user_id": user_id, "async_mode": True},
            timeout=api.timeout_seconds,
        )
        assert async_chat.status_code == 200, async_chat.text
        job_id = int(async_chat.json()["job_id"])

        # Queue status should be available and contain counters.
        queue = api.get(f"{api_url}/jobs/queue/status", timeout=api.timeout_seconds)
        assert queue.status_code == 200, queue.text
        queue_data = queue.json()
        assert isinstance(queue_data.get("status_counts"), dict)
        assert isinstance(queue_data.get("total"), int)

        # Quality metrics pipeline for job record.
        quality = api.post(
            f"{api_url}/quality/evaluate",
            json={"job_id": job_id, "prompt": "p", "response": "r"},
            timeout=api.timeout_seconds,
        )
        assert quality.status_code == 200, quality.text
        assert quality.json().get("success") is True

        feedback = api.post(
            f"{api_url}/quality/feedback",
            json={"job_id": job_id, "rating": 4, "feedback_text": "ok"},
            timeout=api.timeout_seconds,
        )
        assert feedback.status_code == 200, feedback.text

        metrics = api.get(f"{api_url}/quality/job/{job_id}", timeout=api.timeout_seconds)
        assert metrics.status_code == 200, metrics.text
        metrics_data = metrics.json()
        assert isinstance(metrics_data.get("quality_metrics"), dict)
        assert isinstance(metrics_data.get("user_feedback"), list)
    finally:
        api.delete(f"{api_url}/channels/{channel_id}", timeout=api.timeout_seconds)
        api.delete(f"{api_url}/experts/{expert_id}", timeout=api.timeout_seconds)
        api.delete(f"{api_url}/users/{user_id}", timeout=api.timeout_seconds)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.smtp, pytest.mark.heavy]
