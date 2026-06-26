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
    h, p = get_config("api_server.host"), get_config("api_server.port")
    if not h or p is None:
        pytest.fail("api_server.host/api_server.port not configured")
    return f"http://{h}:{int(p)}"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-045")


def test_st136_group_admin_permission_enforcement(test_env_file):
    load_config.cache_clear()
    key = get_config("test.api_key")
    pwd = str(get_config("test.user.password"))
    if not key:
        pytest.fail("test.api_key not configured")

    base = _api_base()
    timeout = float(get_config("test.http_timeout_seconds") or 60)
    admin = requests.Session()
    admin.headers.update({"X-API-Key": str(key)})

    token = uuid.uuid4().hex[:8]
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    domain = str(base_email).split("@", 1)[1]

    u = admin.post(
        f"{base}/users",
        json={
            "username": f"{base_username}_it229_{token}",
            "email": f"it229_{token}@{domain}",
            "password": pwd,
            "display_name": f"IT229 {token}",
        },
        timeout=timeout,
    )
    assert u.status_code == 200, u.text
    user_id = int(u.json()["id"])

    g = admin.post(
        f"{base}/groups", json={"name": f"IT229 Group {token}", "enabled": True}, timeout=timeout
    )
    assert g.status_code == 200, g.text
    group_id = int(g.json()["id"])

    try:
        add = admin.post(
            f"{base}/groups/{group_id}/members",
            json={"user_id": user_id, "role": "member"},
            timeout=timeout,
        )
        assert add.status_code == 200, add.text

        assign = admin.post(
            f"{base}/groups/{group_id}/admins", json={"user_id": user_id}, timeout=timeout
        )
        assert assign.status_code == 200, assign.text

        admins = admin.get(f"{base}/groups/{group_id}/admins", timeout=timeout)
        assert admins.status_code == 200, admins.text
        assert any(int(x["id"]) == user_id for x in admins.json().get("admins", []))

        login = requests.post(
            f"{base}/auth/login",
            json={"username": f"{base_username}_it229_{token}", "password": pwd},
            timeout=timeout,
        )
        assert login.status_code == 200, login.text
        user_token = str(login.json().get("token") or "")
        assert user_token

        forbidden = requests.post(
            f"{base}/groups/{group_id}/admins",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"user_id": user_id},
            timeout=timeout,
        )
        assert forbidden.status_code == 403, forbidden.text
    finally:
        admin.delete(f"{base}/groups/{group_id}", timeout=timeout)
        admin.delete(f"{base}/users/{user_id}", timeout=timeout)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.smtp, pytest.mark.slow, pytest.mark.heavy]

