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
Integration Test: IT2.43 — IDAM negative + group-share cascade (PS-IDAM-ROLE-CASCADE §4).

License: Apache 2.0
Ownership: Cloud-Dog, Viewdeck Engineering Limited
Description:
    W28E-1809B Stream-B D5 deliverable. Against the live API/MCP surfaces:
      * anonymous (no key) is denied 401 on API and MCP;
      * a wrong-role (read-only/non-admin) caller is denied 403 on an admin-only
        write surface;
      * the group-share access cascade with LIVE revocation (no restart): an
        admin shares a session with a group; a user that is NOT a member is
        denied (403); after the admin adds the user to the group the user is
        allowed (200); after the admin removes the user the access is revoked
        (403) without any service restart — exercising FR-019 end-to-end through
        the session read surface (sessions._require_read_access -> can_access_session).

Related Requirements: FR-019, CS-001, CS-006
Related Tests: IT2.43
"""

from __future__ import annotations

import uuid

import pytest
import requests

from src.config.loader import get_config, load_config


def _require_timeout() -> float:
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    return float(timeout)


def _base_url(section: str) -> str:
    configured = get_config(f"{section}.base_url")
    if configured:
        return str(configured).rstrip("/")
    host = get_config(f"{section}.host")
    port = get_config(f"{section}.port")
    scheme = str(get_config(f"{section}.scheme") or "http").strip().lower()
    if not host or not port:
        pytest.fail(f"{section}.host/{section}.port not configured")
    return f"{scheme}://{host}:{port}"


def _mcp_rpc_url(base_url: str) -> str:
    return base_url if base_url.endswith("/mcp") else f"{base_url}/mcp"


@pytest.fixture
def ctx(test_env_file):
    load_config.cache_clear()
    timeout = _require_timeout()
    verify_tls = bool(get_config("test.http_verify_tls") if get_config("test.http_verify_tls") is not None else True)
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured")

    api_url = _base_url("api_server")
    mcp_url = _base_url("mcp_server")

    admin = requests.Session()
    admin.headers.update({"X-API-Key": str(api_key)})
    admin.verify = verify_tls
    health = admin.get(f"{api_url}/health", timeout=timeout)
    assert health.status_code == 200, f"API server not healthy: {health.text}"

    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_email or not password:
        pytest.fail("test.user.email/test.user.password not configured")
    domain = str(base_email).split("@", 1)[1]

    return {
        "admin": admin,
        "api_url": api_url,
        "mcp_url": _mcp_rpc_url(mcp_url),
        "timeout": timeout,
        "verify_tls": verify_tls,
        "domain": domain,
        "password": str(password),
    }


def _make_user_with_key(ctx, role: str = "user"):
    """Create a user (default role) + an API key; return (user_id, plaintext_key)."""
    admin = ctx["admin"]
    api_url = ctx["api_url"]
    timeout = ctx["timeout"]
    token = uuid.uuid4().hex[:8]
    created = admin.post(
        f"{api_url}/users",
        json={
            "username": f"it243_{role}_{token}",
            "email": f"it243_{role}_{token}@{ctx['domain']}",
            "password": ctx["password"],
            "display_name": f"IT243 {role} {token}",
            "role": role,
        },
        timeout=timeout,
    )
    assert created.status_code == 200, created.text
    user_id = int(created.json()["id"])
    key_resp = admin.post(
        f"{api_url}/api-keys",
        json={"user_id": user_id, "name": f"it243_{role}_{token}", "expires_days": 1},
        timeout=timeout,
    )
    assert key_resp.status_code == 200, key_resp.text
    return user_id, str(key_resp.json()["key"])


@pytest.mark.IT
@pytest.mark.api
@pytest.mark.mcp
@pytest.mark.negative
@pytest.mark.req("FR-019")
def test_anonymous_denied_on_api_and_mcp(ctx):
    """Anonymous (no API key) is denied 401 on API and MCP tool-call surfaces."""
    timeout = ctx["timeout"]
    verify = ctx["verify_tls"]

    api_anon = requests.get(f"{ctx['api_url']}/sessions", timeout=timeout, verify=verify)
    assert api_anon.status_code == 401, f"anon API must be 401, got {api_anon.status_code}: {api_anon.text[:160]}"

    mcp_anon = requests.post(
        ctx["mcp_url"],
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "list_sessions", "arguments": {}}},
        timeout=timeout,
        verify=verify,
    )
    assert mcp_anon.status_code == 401, f"anon MCP must be 401, got {mcp_anon.status_code}: {mcp_anon.text[:160]}"


@pytest.mark.IT
@pytest.mark.api
@pytest.mark.negative
@pytest.mark.req("FR-019")
def test_wrong_role_forbidden_on_admin_surface(ctx):
    """A read-only (non-admin) caller is 403 on an admin-only write surface."""
    admin = ctx["admin"]
    api_url = ctx["api_url"]
    timeout = ctx["timeout"]
    user_id, user_key = _make_user_with_key(ctx, role="user")
    try:
        forbidden = requests.post(
            f"{api_url}/experts",
            headers={"X-API-Key": user_key},
            json={"name": f"it243_unauth_{uuid.uuid4().hex[:6]}", "title": "Nope",
                  "description": "Non-admin must not create experts."},
            timeout=timeout,
            verify=ctx["verify_tls"],
        )
        assert forbidden.status_code == 403, (
            f"non-admin create expert must be 403, got {forbidden.status_code}: {forbidden.text[:160]}"
        )
    finally:
        admin.delete(f"{api_url}/users/{user_id}", timeout=timeout)


@pytest.mark.IT
@pytest.mark.api
@pytest.mark.req("FR-019")
def test_group_share_live_revoke_cascade(ctx):
    """FR-019: shared-group read access is granted on membership and revoked
    live (no restart) when the membership is removed."""
    admin = ctx["admin"]
    api_url = ctx["api_url"]
    timeout = ctx["timeout"]
    token = uuid.uuid4().hex[:8]

    # Expert + admin-owned session.
    expert = admin.post(
        f"{api_url}/experts",
        json={"name": f"it243_expert_{token}", "title": "IT243 Expert",
              "description": "IT2.43 group-share cascade expert."},
        timeout=timeout,
    )
    assert expert.status_code == 200, expert.text
    expert_id = int(expert.json()["id"])

    owner_id, _owner_key = _make_user_with_key(ctx, role="user")
    session = admin.post(
        f"{api_url}/sessions",
        json={"user_id": owner_id, "expert_config_id": expert_id, "title": "IT243 shared session",
              "check_limits": False},
        timeout=timeout,
    )
    assert session.status_code == 200, session.text
    session_id = int(session.json()["id"])

    user_id, user_key = _make_user_with_key(ctx, role="user")
    group = admin.post(f"{api_url}/groups", json={"name": f"IT243 Group {token}", "enabled": True}, timeout=timeout)
    assert group.status_code == 200, group.text
    group_id = int(group.json()["id"])

    def _user_read():
        return requests.get(
            f"{api_url}/sessions/{session_id}",
            headers={"X-API-Key": user_key},
            timeout=timeout,
            verify=ctx["verify_tls"],
        ).status_code

    try:
        # Share the admin's session with the group.
        shared = admin.post(
            f"{api_url}/sessions/{session_id}/share",
            json={"group_ids": [group_id]},
            timeout=timeout,
        )
        assert shared.status_code == 200, shared.text

        # 1) Not a member yet -> denied.
        assert _user_read() == 403, "non-member must not read a group-shared session"

        # 2) Add to group -> allowed (cascade grant).
        added = admin.post(f"{api_url}/groups/{group_id}/members", json={"user_id": user_id}, timeout=timeout)
        assert added.status_code in (200, 201), added.text
        assert _user_read() == 200, "group member must read the group-shared session"

        # 3) Remove from group -> revoked live, no restart.
        removed = admin.delete(f"{api_url}/groups/{group_id}/members/{user_id}", timeout=timeout)
        assert removed.status_code in (200, 204), removed.text
        assert _user_read() == 403, "access must be revoked immediately after membership removal"
    finally:
        admin.delete(f"{api_url}/sessions/{session_id}", timeout=timeout)
        admin.delete(f"{api_url}/groups/{group_id}", timeout=timeout)
        admin.delete(f"{api_url}/users/{user_id}", timeout=timeout)
        admin.delete(f"{api_url}/users/{owner_id}", timeout=timeout)
        admin.delete(f"{api_url}/experts/{expert_id}", timeout=timeout)
