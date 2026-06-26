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
UT1.131 — Unauthenticated auth-gate (negative-auth) regression guard.

License: Apache 2.0
Ownership: Cloud-Dog, Viewdeck Engineering Limited
Description:
    W28A-889-B estate unauth auth-gate hardening. This is the missing
    NEGATIVE-auth test: it proves that an UNAUTHENTICATED caller (no cookie,
    no api-key) is DENIED at the web tier — the principal endpoint never hands
    back a populated/admin principal, and protected data routes return 401.

    Root cause it guards against (the index-retriever WebApiProxy bypass,
    W28A-734-R2): the shared WebApiProxy injects the service admin api-key on
    every proxy hop, so a web route that proxies an identity/data endpoint
    WITHOUT first requiring the caller's own session would resolve the service
    (admin) principal for an anonymous caller. expert-agent's web tier gates on
    the session token BEFORE proxying (server.py web_api_proxy), so the service
    key is never injected for an anonymous caller. This test fails if that gate
    is ever removed.

Related Requirements: FR1.43 (cookie-auth principal), CS (unauthenticated denial)
Related Tasks: W28A-889-B
Related Architecture: SE (auth), CC1.15 (WebApiProxy)
Related Tests: live preprod proxy-path audit (W28A-889-B evidence)

Recent Changes:
- 2026-06-09: W28A-889-B — initial negative-auth regression guard.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.unit, pytest.mark.security, pytest.mark.pure]

# The SPA cookie adapter (apps/expert-agent App.tsx) calls this principal path.
PRINCIPAL_PATH = "/web/auth/me"
# A genuinely protected admin data route proxied through the web tier.
PROTECTED_DATA_PATH = "/web/api/users"
# Tokens that must NEVER appear in an anonymous principal response.
ADMIN_LEAK_MARKERS = ('"permissions"', '"roles"', '"role"', "configured:", '"admin"')


@pytest.fixture()
def web_client() -> TestClient:
    """Build a TestClient over the real web app with NO live API backend.

    The unauthenticated paths under test are decided entirely at the web tier
    (cookie/session check) and never reach the API server, so no backend is
    required for the negative path.
    """
    from servers.web.server import WebServer

    server = WebServer()
    return TestClient(server.app)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-028")


def test_unauth_principal_is_null_never_admin(web_client: TestClient) -> None:
    """Anon principal endpoint must return user=null, never a populated principal."""
    resp = web_client.get(PRINCIPAL_PATH)
    # §0C point 5 allows 401 OR a null principal; expert-agent returns null+200.
    assert resp.status_code in (200, 401), resp.text
    if resp.status_code == 200:
        body = resp.json()
        assert body.get("user") is None, f"anon principal must be null, got: {body}"
        assert body.get("authenticated") is False, body
        # Hard guard: no admin principal leak in the serialised body.
        raw = json.dumps(body)
        assert '"roles"' not in raw and '"permissions"' not in raw, raw
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-028")


def test_unauth_protected_data_route_denied(web_client: TestClient) -> None:
    """Anon protected data route must be 401 — the service key is NOT injected."""
    resp = web_client.get(PROTECTED_DATA_PATH)
    assert resp.status_code == 401, (
        f"anon {PROTECTED_DATA_PATH} must be 401 (no key injection); "
        f"got {resp.status_code}: {resp.text[:200]}"
    )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-028")


def test_forged_session_cookie_does_not_bypass(web_client: TestClient) -> None:
    """A forged/garbage session cookie must not establish a principal."""
    resp = web_client.get(
        PRINCIPAL_PATH,
        cookies={"expert_web_session": "forged-not-a-real-session-id"},
    )
    assert resp.status_code in (200, 401), resp.text
    if resp.status_code == 200:
        assert resp.json().get("user") is None, resp.text
    # And a forged cookie must not unlock protected data either.
    data_resp = web_client.get(
        PROTECTED_DATA_PATH,
        cookies={"expert_web_session": "forged-not-a-real-session-id"},
    )
    assert data_resp.status_code == 401, data_resp.text
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-028")


def test_unauth_bootstrap_paths_return_empty_not_data(web_client: TestClient) -> None:
    """The three GET bootstrap paths return EMPTY lists for anon — never real data.

    server.py web_api_proxy intentionally returns empty bootstrap payloads for
    a small allow-list ({sessions, channels, experts}) so the SPA can render its
    shell pre-login. This test pins that they stay EMPTY (no data leak) — a
    regression that returned real rows here would be an unauth data exposure.
    """
    for path in ("sessions", "channels", "experts"):
        resp = web_client.get(f"/web/api/{path}")
        assert resp.status_code == 200, f"/web/api/{path}: {resp.status_code}"
        assert resp.json() == [], f"/web/api/{path} must be empty for anon, got {resp.text[:200]}"


# ── EA1 (W28C-1704 / 1601-C): anonymous /mcp tool dispatch must be 401 ─────────
# Extends the W28A-889-B negative-auth gate to the MCP JSON-RPC surface. Before
# W28C-1704 the MCP server had no auth middleware and anonymous callers defaulted
# to role "user" (the 340-session anon leak); these tests pin anon tools/call ->
# 401 for every MCP JSON-RPC POST, including discovery.

_MCP_TOOLS = [
    "list_experts", "list_sessions", "chat", "execute_tool", "code_execute",
    "vector_search", "invoke_service_tool", "list_services",
    "admin_list_experts", "admin_create_expert", "admin_update_expert",
    "admin_delete_expert", "admin_list_users", "admin_create_api_key",
    "admin_revoke_api_key",
]


@pytest.fixture()
def mcp_client() -> TestClient:
    """Build a TestClient over the real MCP app (auth gate active)."""
    from servers.mcp.server import MCPServer

    return TestClient(MCPServer().app)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-028")


@pytest.mark.parametrize("tool", _MCP_TOOLS)
def test_mcp_anon_tools_call_is_401(mcp_client: TestClient, tool: str) -> None:
    """Anon POST /mcp tools/call must be 401 for EVERY tool (incl. all admin_*)."""
    resp = mcp_client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": tool, "arguments": {}}},
    )
    assert resp.status_code == 401, f"anon tools/call {tool} must be 401, got {resp.status_code}: {resp.text[:160]}"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-028")


def test_mcp_anon_handshake_and_discovery_are_401(mcp_client: TestClient) -> None:
    """Anonymous JSON-RPC initialize + tools/list must be denied before transport discovery."""
    init = mcp_client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert init.status_code == 401, init.text
    tl = mcp_client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert tl.status_code == 401, tl.text
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-028")


def test_mcp_authed_tools_call_returns_business_result(db_session, monkeypatch) -> None:
    """A valid X-API-Key passes the gate and returns a real MCP business result."""
    import servers.mcp.server as mcp_server_module
    from servers.mcp.server import MCPServer

    real_get_config = mcp_server_module.get_config

    def _test_get_config(key, *args, **kwargs):
        if key == "api_key":
            return "ut131-admin-key"
        return real_get_config(key, *args, **kwargs)

    monkeypatch.setattr(mcp_server_module, "get_config", _test_get_config)
    mcp_client = TestClient(MCPServer().app)
    resp = mcp_client.post(
        "/mcp",
        headers={"X-API-Key": "ut131-admin-key"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/call",
              "params": {"name": "list_experts", "arguments": {}}},
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert "result" in payload, payload
    assert "error" not in payload, payload
    assert "error" not in payload["result"], payload
