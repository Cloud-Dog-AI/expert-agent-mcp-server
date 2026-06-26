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


def test_st131_api_key_lifecycle_enforcement(test_env_file):
    load_config.cache_clear()
    timeout = float(get_config("test.http_timeout_seconds") or 60)
    admin_key = get_config("test.api_key")
    if not admin_key:
        pytest.fail("test.api_key not configured")

    api_url = _base("api_server")
    admin = requests.Session()
    admin.headers.update({"X-API-Key": str(admin_key)})

    u = uuid.uuid4().hex[:8]
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    domain = str(base_email).split("@", 1)[1]

    user = admin.post(
        f"{api_url}/users",
        json={
            "username": f"{base_username}_st131_{u}",
            "email": f"st131_{u}@{domain}",
            "password": str(password),
            "display_name": f"ST131 {u}",
        },
        timeout=timeout,
    )
    assert user.status_code == 200, user.text
    user_id = int(user.json()["id"])

    try:
        key_resp = admin.post(
            f"{api_url}/api-keys",
            json={"user_id": user_id, "name": f"st131_live_{u}", "expires_days": 7},
            timeout=timeout,
        )
        assert key_resp.status_code == 200, key_resp.text
        live_key_id = int(key_resp.json()["id"])
        live_key = key_resp.json()["key"]

        live = requests.get(
            f"{api_url}/sessions", headers={"X-API-Key": str(live_key)}, timeout=timeout
        )
        assert live.status_code == 200, live.text

        listed = admin.get(
            f"{api_url}/api-keys",
            params={"user_id": user_id, "include_revoked": True},
            timeout=timeout,
        )
        assert listed.status_code == 200, listed.text
        listed_ids = {int(k["id"]) for k in listed.json().get("api_keys", [])}
        assert live_key_id in listed_ids

        rotate = admin.post(f"{api_url}/api-keys/{live_key_id}/rotate", timeout=timeout)
        assert rotate.status_code == 200, rotate.text
        rotated = rotate.json()["new_key"]
        rotated_key_id = int(rotated["id"])
        rotated_key = str(rotated["key"])

        old_probe = requests.get(
            f"{api_url}/sessions", headers={"X-API-Key": str(live_key)}, timeout=timeout
        )
        assert old_probe.status_code == 401, old_probe.text
        rotated_probe = requests.get(
            f"{api_url}/sessions", headers={"X-API-Key": rotated_key}, timeout=timeout
        )
        assert rotated_probe.status_code == 200, rotated_probe.text

        revoke = admin.delete(f"{api_url}/api-keys/{rotated_key_id}", timeout=timeout)
        assert revoke.status_code == 200, revoke.text
        revoked_probe = requests.get(
            f"{api_url}/sessions", headers={"X-API-Key": rotated_key}, timeout=timeout
        )
        assert revoked_probe.status_code == 401, revoked_probe.text

        expired_key_resp = admin.post(
            f"{api_url}/api-keys",
            json={"user_id": user_id, "name": f"st131_expired_{u}", "expires_days": -1},
            timeout=timeout,
        )
        assert expired_key_resp.status_code == 200, expired_key_resp.text
        expired_key = expired_key_resp.json()["key"]

        expired = requests.get(
            f"{api_url}/sessions", headers={"X-API-Key": str(expired_key)}, timeout=timeout
        )
        assert expired.status_code == 401, expired.text

        invalid = requests.get(
            f"{api_url}/sessions", headers={"X-API-Key": "ea_invalid"}, timeout=timeout
        )
        assert invalid.status_code == 401, invalid.text
    finally:
        admin.delete(f"{api_url}/users/{user_id}", timeout=timeout)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.smtp, pytest.mark.slow, pytest.mark.heavy]

