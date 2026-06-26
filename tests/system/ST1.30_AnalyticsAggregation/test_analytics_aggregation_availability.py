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


def _base(section: str) -> str:
    h, p = get_config(f"{section}.host"), get_config(f"{section}.port")
    if not h or p is None:
        pytest.fail(f"{section}.host/{section}.port not configured")
    return f"http://{h}:{int(p)}"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-045")


def test_st130_analytics_aggregation_availability(test_env_file):
    load_config.cache_clear()
    timeout = float(get_config("test.http_timeout_seconds") or 60)
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")

    api = requests.Session()
    api.headers.update({"X-API-Key": str(api_key)})
    api_url = _base("api_server")
    u = uuid.uuid4().hex[:8]
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    domain = str(base_email).split("@", 1)[1]

    user = api.post(
        f"{api_url}/users",
        json={
            "username": f"{base_username}_st130_{u}",
            "email": f"st130_{u}@{domain}",
            "password": str(password),
            "display_name": f"ST130 {u}",
        },
        timeout=timeout,
    )
    assert user.status_code == 200, user.text
    user_id = int(user.json()["id"])

    expert = api.post(
        f"{api_url}/experts",
        json={
            "name": f"st130_expert_{u}",
            "title": f"ST130 Expert {u}",
            "description": f"ST1.30 analytics availability expert token {u}.",
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

    channel = api.post(
        f"{api_url}/channels",
        json={
            "name": f"ST130 Channel {u}",
            "expert_config_id": expert_id,
            "description": f"analytics availability {u}",
            "enabled": True,
        },
        timeout=timeout,
    )
    assert channel.status_code == 200, channel.text
    channel_id = int(channel.json()["id"])

    try:
        async_resp = api.post(
            f"{api_url}/channels/{channel_id}/chat",
            json={"message": "analytics counters", "user_id": user_id, "async_mode": True},
            timeout=timeout,
        )
        assert async_resp.status_code == 200, async_resp.text
        job_id = int(async_resp.json()["job_id"])

        queue = api.get(f"{api_url}/jobs/queue/status", timeout=timeout)
        assert queue.status_code == 200, queue.text
        q = queue.json()
        assert isinstance(q.get("status_counts"), dict)
        assert isinstance(q.get("total"), int)

        eval_resp = api.post(
            f"{api_url}/quality/evaluate",
            json={"job_id": job_id, "prompt": "p", "response": "r"},
            timeout=timeout,
        )
        assert eval_resp.status_code == 200, eval_resp.text
        assert eval_resp.json().get("success") is True

        metrics = api.get(f"{api_url}/quality/job/{job_id}", timeout=timeout)
        assert metrics.status_code == 200, metrics.text
        assert isinstance(metrics.json().get("quality_metrics"), dict)
    finally:
        api.delete(f"{api_url}/channels/{channel_id}", timeout=timeout)
        api.delete(f"{api_url}/experts/{expert_id}", timeout=timeout)
        api.delete(f"{api_url}/users/{user_id}", timeout=timeout)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.smtp, pytest.mark.slow, pytest.mark.heavy]

