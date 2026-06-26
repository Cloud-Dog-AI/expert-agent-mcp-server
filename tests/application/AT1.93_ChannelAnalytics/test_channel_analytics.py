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
Application Test: AT1.93 - Channel Analytics End-to-End

License: Apache 2.0
Ownership: Cloud Dog
Description: Validates implemented channel analytics/statistics surfaces and access contracts

Related Requirements: FR1.23, UC1.17
Related Tasks: T061
Related Architecture: MO1.4
Related Tests: AT1.93
"""

import uuid

import pytest
import requests

from src.config.loader import get_config, load_config


pytestmark = pytest.mark.application


def _require_timeout() -> float:
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    return float(timeout)


def _require_base_url(section: str) -> str:
    host = get_config(f"{section}.host")
    port = get_config(f"{section}.port")
    if not host or port is None:
        pytest.fail(f"{section}.host/{section}.port not configured")
    return f"http://{host}:{int(port)}"


@pytest.fixture
def clients(test_env_file):
    load_config.cache_clear()
    timeout = _require_timeout()
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")

    api_url = _require_base_url("api_server")
    web_url = _require_base_url("web_server")

    api = requests.Session()
    api.headers.update({"X-API-Key": str(api_key)})
    api.timeout_seconds = timeout

    anonymous = requests.Session()
    anonymous.timeout_seconds = timeout

    web = requests.Session()
    web.timeout_seconds = timeout

    return {
        "api": api,
        "anonymous": anonymous,
        "web": web,
        "api_url": api_url,
        "web_url": web_url,
    }


@pytest.fixture
def analytics_job(clients):
    api = clients["api"]
    api_url = clients["api_url"]
    timeout = api.timeout_seconds
    unique = uuid.uuid4().hex[:8]

    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in config")
    if "@" not in str(base_email):
        pytest.fail("test.user.email must include a domain")
    domain = str(base_email).split("@", 1)[1]

    user_response = api.post(
        f"{api_url}/users",
        json={
            "username": f"{base_username}_at193_{unique}",
            "email": f"at193_{unique}@{domain}",
            "password": str(password),
            "display_name": f"AT1.93 User {unique}",
        },
        timeout=timeout,
    )
    assert user_response.status_code == 200, user_response.text
    user = user_response.json()

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    llm_api_key = get_config("llm.api_key")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config")

    expert_response = api.post(
        f"{api_url}/experts",
        json={
            "name": f"at193_expert_{unique}",
            "title": f"AT1.93 Expert Alpha Beta {unique}",
            "description": f"Supports AT1.93 analytics workflow token {unique}.",
            "llm_provider": str(llm_provider),
            "llm_model": str(llm_model),
            "llm_base_url": str(llm_base_url),
            "llm_api_key": llm_api_key,
            "enabled": True,
        },
        timeout=timeout,
    )
    assert expert_response.status_code == 200, expert_response.text
    expert = expert_response.json()

    channel_response = api.post(
        f"{api_url}/channels",
        json={
            "name": f"AT193 Channel {unique}",
            "expert_config_id": int(expert["id"]),
            "description": f"AT1.93 analytics channel {unique}",
            "enabled": True,
        },
        timeout=timeout,
    )
    assert channel_response.status_code == 200, channel_response.text
    channel = channel_response.json()

    chat_response = api.post(
        f"{api_url}/channels/{channel['id']}/chat",
        json={
            "message": "Create analytics job record",
            "user_id": int(user["id"]),
            "async_mode": True,
        },
        timeout=timeout,
    )
    assert chat_response.status_code == 200, chat_response.text
    chat_payload = chat_response.json()
    assert chat_payload.get("mode") == "async"
    job_id = int(chat_payload["job_id"])

    yield {
        "job_id": job_id,
        "channel_id": int(channel["id"]),
        "user_id": int(user["id"]),
        "expert_id": int(expert["id"]),
    }

    api.delete(f"{api_url}/channels/{channel['id']}", timeout=timeout)
    api.delete(f"{api_url}/experts/{expert['id']}", timeout=timeout)
    api.delete(f"{api_url}/users/{user['id']}", timeout=timeout)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-017")


def test_web_admin_panel_exposes_queue_and_metrics_contract(clients):
    web = clients["web"]
    web_url = clients["web_url"]

    response = web.get(f"{web_url}/", timeout=web.timeout_seconds)
    assert response.status_code == 200, response.text
    body = response.text

    assert '<div id="root"></div>' in body
    assert "/runtime-config.js" in body
    assert "/api-docs" in body
    assert "/testing" in body
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-017")


def test_queue_status_requires_authentication(clients):
    anonymous = clients["anonymous"]
    api_url = clients["api_url"]

    response = anonymous.get(f"{api_url}/jobs/queue/status", timeout=anonymous.timeout_seconds)
    assert response.status_code == 401, response.text
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-017")


def test_queue_status_available_for_configured_api_key(clients):
    api = clients["api"]
    api_url = clients["api_url"]

    response = api.get(f"{api_url}/jobs/queue/status", timeout=api.timeout_seconds)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert isinstance(payload.get("status_counts"), dict)
    assert isinstance(payload.get("total"), int)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-017")


def test_quality_metrics_and_feedback_contracts(clients, analytics_job):
    api = clients["api"]
    api_url = clients["api_url"]
    job_id = int(analytics_job["job_id"])

    evaluate_response = api.post(
        f"{api_url}/quality/evaluate",
        json={
            "job_id": job_id,
            "prompt": "Summarize reliability posture.",
            "response": "Reliability posture is stable under current constraints.",
        },
        timeout=api.timeout_seconds,
    )
    assert evaluate_response.status_code == 200, evaluate_response.text
    evaluate_payload = evaluate_response.json()
    assert evaluate_payload.get("success") is True
    assert int(evaluate_payload.get("job_id")) == job_id
    assert isinstance(evaluate_payload.get("metrics"), dict)

    feedback_response = api.post(
        f"{api_url}/quality/feedback",
        json={"job_id": job_id, "rating": 4, "feedback_text": "Good completeness."},
        timeout=api.timeout_seconds,
    )
    assert feedback_response.status_code == 200, feedback_response.text
    feedback_payload = feedback_response.json()
    assert feedback_payload.get("success") is True
    assert int(feedback_payload.get("job_id")) == job_id

    metrics_response = api.get(f"{api_url}/quality/job/{job_id}", timeout=api.timeout_seconds)
    assert metrics_response.status_code == 200, metrics_response.text
    metrics_payload = metrics_response.json()
    assert int(metrics_payload.get("job_id")) == job_id
    assert isinstance(metrics_payload.get("quality_metrics"), dict)
    assert isinstance(metrics_payload.get("user_feedback"), list)
    assert metrics_payload["user_feedback"], "Expected at least one feedback entry"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-017")


def test_quality_feedback_rejects_invalid_rating(clients, analytics_job):
    api = clients["api"]
    api_url = clients["api_url"]
    job_id = int(analytics_job["job_id"])

    response = api.post(
        f"{api_url}/quality/feedback",
        json={"job_id": job_id, "rating": 6, "feedback_text": "invalid"},
        timeout=api.timeout_seconds,
    )
    assert response.status_code == 400, response.text
    assert "Rating must be between 1 and 5" in response.text

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.llm, pytest.mark.smtp, pytest.mark.heavy]
