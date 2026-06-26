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


def _api_base() -> str:
    base = get_config("api_server.base_url")
    if base:
        return str(base).rstrip("/")
    host, port = get_config("api_server.host"), get_config("api_server.port")
    if not host or port is None:
        pytest.fail("api_server.host/api_server.port not configured")
    return f"http://{host}:{int(port)}"
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-047")


def test_it240_attach_list_detach_channel_service(test_env_file):
    load_config.cache_clear()
    api_key = get_config("test.api_key")
    timeout = float(get_config("test.http_timeout_seconds") or 60)
    if not api_key:
        pytest.fail("test.api_key not configured")

    session = requests.Session()
    session.headers.update({"X-API-Key": str(api_key)})
    base_url = _api_base()

    token = uuid.uuid4().hex[:8]
    expert_id = None
    channel_id = None
    service_id = None

    try:
        expert = session.post(
            f"{base_url}/experts",
            json={
                "name": f"it240_expert_{token}",
                "title": f"IT240 Expert {token}",
                "description": f"Channel service detach integration coverage {token}",
                "llm_provider": str(get_config("llm.provider")),
                "llm_model": str(get_config("llm.model")),
                "llm_base_url": str(get_config("llm.base_url")),
                "enabled": True,
            },
            timeout=timeout,
        )
        assert expert.status_code == 200, expert.text
        expert_id = int(expert.json()["id"])

        channel = session.post(
            f"{base_url}/channels",
            json={
                "name": f"IT240 Channel {token}",
                "expert_config_id": expert_id,
                "description": f"IT240 channel {token}",
                "enabled": True,
            },
            timeout=timeout,
        )
        assert channel.status_code == 200, channel.text
        channel_id = int(channel.json()["id"])

        service = session.post(
            f"{base_url}/services",
            json={
                "name": f"it240_service_{token}",
                "service_type": "mcp",
                "endpoint_url": f"{base_url}/health",
                "auth_config": {"type": "none"},
                "metadata": {"suite": "IT2.40", "token": token},
            },
            timeout=timeout,
        )
        assert service.status_code == 200, service.text
        service_id = int(service.json()["id"])

        attached = session.post(
            f"{base_url}/channels/{channel_id}/services/{service_id}", timeout=timeout
        )
        assert attached.status_code == 200, attached.text
        assert int(attached.json().get("service_id")) == service_id

        listed = session.get(f"{base_url}/channels/{channel_id}/services", timeout=timeout)
        assert listed.status_code == 200, listed.text
        listed_services = listed.json().get("services", [])
        assert any(int(item.get("service_id")) == service_id for item in listed_services)

        detached = session.delete(
            f"{base_url}/channels/{channel_id}/services/{service_id}", timeout=timeout
        )
        assert detached.status_code == 200, detached.text
        assert detached.json().get("removed") is True

        listed_after = session.get(f"{base_url}/channels/{channel_id}/services", timeout=timeout)
        assert listed_after.status_code == 200, listed_after.text
        assert all(int(item.get("service_id")) != service_id for item in listed_after.json().get("services", []))
    finally:
        if service_id is not None:
            session.delete(f"{base_url}/services/{service_id}", timeout=timeout)
        if channel_id is not None:
            session.delete(f"{base_url}/channels/{channel_id}", timeout=timeout)
        if expert_id is not None:
            session.delete(f"{base_url}/experts/{expert_id}", timeout=timeout)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.mcp, pytest.mark.heavy]

