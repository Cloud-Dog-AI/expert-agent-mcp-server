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
    h, p = get_config("api_server.host"), get_config("api_server.port")
    if not h or p is None:
        pytest.fail("api_server.host/api_server.port not configured")
    return f"http://{h}:{int(p)}"


    # Covers: FR1.20
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-014")
def test_at196_log_history_search_download_and_access_control(test_env_file):
    load_config.cache_clear()
    admin_key = get_config("test.api_key")
    if not admin_key:
        pytest.fail("test.api_key not configured")

    base = _api_base()
    timeout = float(get_config("test.http_timeout_seconds") or 60)

    admin = requests.Session()
    admin.headers.update({"X-API-Key": str(admin_key)})

    suffix = uuid.uuid4().hex[:8]
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    domain = str(base_email).split("@", 1)[1]

    user_resp = admin.post(
        f"{base}/users",
        json={
            "username": f"{base_username}_at196_{suffix}",
            "email": f"at196_{suffix}@{domain}",
            "password": str(password),
            "display_name": f"AT196 {suffix}",
        },
        timeout=timeout,
    )
    assert user_resp.status_code == 200, user_resp.text
    user_id = int(user_resp.json()["id"])

    try:
        login = requests.post(
            f"{base}/auth/login",
            json={"username": f"{base_username}_at196_{suffix}", "password": str(password)},
            timeout=timeout,
        )
        assert login.status_code == 200, login.text
        token = str(login.json().get("token") or "")
        assert token

        own_events = requests.get(
            f"{base}/audit",
            headers={"Authorization": f"Bearer {token}"},
            params={"user_id": user_id, "limit": 10},
            timeout=timeout,
        )
        assert own_events.status_code == 200, own_events.text

        forbidden_export = requests.get(
            f"{base}/audit/export/json",
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout,
        )
        assert forbidden_export.status_code == 403, forbidden_export.text

        admin_export = admin.get(f"{base}/audit/export/json", timeout=timeout)
        assert admin_export.status_code == 200, admin_export.text
    finally:
        admin.delete(f"{base}/users/{user_id}", timeout=timeout)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.smtp, pytest.mark.heavy]
