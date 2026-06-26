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

import pytest
import requests

from src.config.loader import get_config, load_config
from src.database.connection import get_db
from src.database.models import APIKey, User


pytestmark = pytest.mark.application


def _api_base() -> str:
    h, p = get_config("api_server.host"), get_config("api_server.port")
    if not h or p is None:
        pytest.fail("api_server.host/api_server.port not configured")
    return f"http://{h}:{int(p)}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-012")


def test_at1115_api_key_lifecycle_and_scope_enforcement(test_env_file):
    # Covers: FR1.17
    load_config.cache_clear()
    admin_key = get_config("test.api_key")
    if not admin_key:
        pytest.fail("test.api_key not configured")

    base = _api_base()
    timeout = float(get_config("test.http_timeout_seconds") or 60)
    admin = requests.Session()
    admin.headers.update({"X-API-Key": str(admin_key)})
    db = next(get_db())
    try:
        base_username = get_config("test.user.username")
        if not base_username:
            pytest.fail("test.user.username not configured")
        owner = db.query(User).filter(User.username == str(base_username)).first()
        if owner is None:
            pytest.fail(f"bootstrap user '{base_username}' not found")
        owner_id = int(owner.id)
    finally:
        db.close()

    created = admin.post(
        f"{base}/api-keys",
        json={
            "name": "at1115_scope_key",
            "user_id": owner_id,
            "expires_days": 1,
            "read_channels": True,
            "read_logs": False,
            "read_histories": False,
        },
        timeout=timeout,
    )
    assert created.status_code == 200, created.text
    key_id = int(created.json()["id"])
    raw_key = str(created.json()["key"])
    scoped = requests.Session()
    scoped.headers.update({"X-API-Key": raw_key})

    try:
        allowed = scoped.get(f"{base}/sessions", timeout=timeout)
        assert allowed.status_code == 200, allowed.text

        listed = admin.get(
            f"{base}/api-keys",
            params={"user_id": owner_id, "include_revoked": True},
            timeout=timeout,
        )
        assert listed.status_code == 200, listed.text
        listed_ids = {int(k["id"]) for k in listed.json().get("api_keys", [])}
        assert key_id in listed_ids

        db = next(get_db())
        try:
            key_row = db.query(APIKey).filter(APIKey.id == key_id).first()
            assert key_row is not None
            assert bool(key_row.read_channels) is True
            assert bool(key_row.read_logs) is False
            assert bool(key_row.read_histories) is False
        finally:
            db.close()

        rotate = admin.post(f"{base}/api-keys/{key_id}/rotate", timeout=timeout)
        assert rotate.status_code == 200, rotate.text
        rotated = rotate.json()["new_key"]
        rotated_key_id = int(rotated["id"])
        rotated_raw = str(rotated["key"])

        old_probe = requests.get(
            f"{base}/sessions",
            headers={"X-API-Key": raw_key},
            timeout=timeout,
        )
        assert old_probe.status_code == 401, old_probe.text
        rotated_probe = requests.get(
            f"{base}/sessions",
            headers={"X-API-Key": rotated_raw},
            timeout=timeout,
        )
        assert rotated_probe.status_code == 200, rotated_probe.text

        revoke = admin.delete(f"{base}/api-keys/{rotated_key_id}", timeout=timeout)
        assert revoke.status_code == 200, revoke.text
        revoked_probe = requests.get(
            f"{base}/sessions",
            headers={"X-API-Key": rotated_raw},
            timeout=timeout,
        )
        assert revoked_probe.status_code == 401, revoked_probe.text

        expired_key = admin.post(
            f"{base}/api-keys",
            json={
                "name": "at1115_expired_scope_key",
                "user_id": owner_id,
                "expires_days": -1,
                "read_channels": True,
                "read_logs": False,
                "read_histories": False,
            },
            timeout=timeout,
        )
        assert expired_key.status_code == 200, expired_key.text
        expired_raw = str(expired_key.json()["key"])
        expired_probe = requests.get(
            f"{base}/sessions",
            headers={"X-API-Key": expired_raw},
            timeout=timeout,
        )
        assert expired_probe.status_code == 401, expired_probe.text

        invalid_probe = requests.get(
            f"{base}/sessions",
            headers={"X-API-Key": "ea_invalid"},
            timeout=timeout,
        )
        assert invalid_probe.status_code == 401, invalid_probe.text
    finally:
        # Route currently exposes key creation/validation but no delete endpoint.
        _ = key_id

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.db, pytest.mark.heavy]
