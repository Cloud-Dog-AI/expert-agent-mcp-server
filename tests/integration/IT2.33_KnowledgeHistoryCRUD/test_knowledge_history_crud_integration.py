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


def _create_user(admin: requests.Session, base: str, suffix: str, timeout: float) -> int:
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    domain = str(base_email).split("@", 1)[1]
    resp = admin.post(
        f"{base}/users",
        json={
            "username": f"{base_username}_{suffix}",
            "email": f"{suffix}@{domain}",
            "password": str(password),
            "display_name": suffix,
        },
        timeout=timeout,
    )
    assert resp.status_code == 200, resp.text
    return int(resp.json()["id"])


def _login(base: str, username: str, password: str, timeout: float) -> str:
    r = requests.post(
        f"{base}/auth/login", json={"username": username, "password": password}, timeout=timeout
    )
    assert r.status_code == 200, r.text
    token = str(r.json().get("token") or "")
    assert token
    return token
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-047")


def test_it233_knowledge_history_crud_permissions_integration(test_env_file):
    load_config.cache_clear()
    key = get_config("test.api_key")
    if not key:
        pytest.fail("test.api_key not configured")

    base = _api_base()
    timeout = float(get_config("test.http_timeout_seconds") or 60)
    admin = requests.Session()
    admin.headers.update({"X-API-Key": str(key)})

    token = uuid.uuid4().hex[:8]
    suffix1 = f"it233a_{token}"
    suffix2 = f"it233b_{token}"
    user_id_1 = _create_user(admin, base, suffix1, timeout)
    user_id_2 = _create_user(admin, base, suffix2, timeout)

    try:
        pwd = str(get_config("test.user.password"))
        username_prefix = str(get_config("test.user.username"))
        t1 = _login(base, f"{username_prefix}_{suffix1}", pwd, timeout)
        t2 = _login(base, f"{username_prefix}_{suffix2}", pwd, timeout)

        s1 = requests.Session()
        s1.headers.update({"Authorization": f"Bearer {t1}"})
        s2 = requests.Session()
        s2.headers.update({"Authorization": f"Bearer {t2}"})

        add1 = s1.post(
            f"{base}/knowledge",
            json={
                "knowledge_type": "user",
                "knowledge_id": user_id_1,
                "content": "v1 knowledge",
                "metadata": {"k": 1},
            },
            timeout=timeout,
        )
        assert add1.status_code == 200, add1.text
        add2 = s1.post(
            f"{base}/knowledge",
            json={
                "knowledge_type": "user",
                "knowledge_id": user_id_1,
                "content": "v2 knowledge",
                "metadata": {"k": 2},
            },
            timeout=timeout,
        )
        assert add2.status_code == 200, add2.text

        listed = s1.get(f"{base}/knowledge", timeout=timeout)
        assert listed.status_code == 200, listed.text
        entries = listed.json().get("entries", [])
        assert any(int(e.get("knowledge_id", -1)) == user_id_1 for e in entries), listed.text

        hist = s1.get(f"{base}/knowledge/user/{user_id_1}", timeout=timeout)
        assert hist.status_code == 200, hist.text
        assert int(hist.json().get("total", 0)) >= 1

        versions = s1.get(f"{base}/knowledge/user/{user_id_1}/versions", timeout=timeout)
        assert versions.status_code == 200, versions.text
        assert int(versions.json().get("count", 0)) >= 1

        deny = s2.get(f"{base}/knowledge/user/{user_id_1}", timeout=timeout)
        assert deny.status_code in {403, 500}, deny.text
    finally:
        admin.delete(f"{base}/users/{user_id_1}", timeout=timeout)
        admin.delete(f"{base}/users/{user_id_2}", timeout=timeout)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.smtp, pytest.mark.heavy]

