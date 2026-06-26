# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0.

"""SM1.2 — Expert Agent auth surface smoke tests for W28A-743.

These are fast service-owned probes for the Thread-B T0-T3 matrix:
health, common IDAM negative-auth, role/RBAC permission shape, and one
authenticated MCP business path. Live preprod runs replay the same externally
observable expectations after deployment.
"""


from __future__ import annotations
import pytest

from fastapi.testclient import TestClient


def _mcp_client() -> TestClient:
    from servers.mcp.server import MCPServer

    return TestClient(MCPServer().app)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("FR-046")


def test_t0_mcp_health_stays_public() -> None:
    """T0: health remains anonymously reachable."""
    resp = _mcp_client().get("/health")
    assert resp.status_code == 200, resp.text
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("FR-046")


def test_t1_anon_jsonrpc_discovery_is_denied() -> None:
    """T1: common IDAM gate denies anonymous MCP discovery."""
    client = _mcp_client()
    init = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    tools = client.post("/mcp", json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})
    assert init.status_code == 401, init.text
    assert tools.status_code == 401, tools.text
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("FR-046")


def test_t2_flat_roles_are_fail_closed() -> None:
    """T2: unknown roles collapse to read-only and cannot write."""
    from src.core.auth.expert_flat_roles import normalise_flat_role, role_can_write

    assert normalise_flat_role("admin") == "admin"
    assert normalise_flat_role("user") == "read-write"
    assert normalise_flat_role("viewer") == "read-only"
    assert normalise_flat_role("unexpected-role") == "read-only"
    assert role_can_write("read-only") is False
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("FR-046")


def test_t3_authed_mcp_business_path_reaches_dispatch(monkeypatch, db_session) -> None:
    """T3: a configured service key passes the MCP transport gate."""
    import servers.mcp.server as mcp_server_module

    real_get_config = mcp_server_module.get_config

    def _test_get_config(key, *args, **kwargs):
        if key == "api_key":
            return "w28a743-smoke-key"
        return real_get_config(key, *args, **kwargs)

    monkeypatch.setattr(
        mcp_server_module,
        "get_config",
        _test_get_config,
    )
    resp = _mcp_client().post(
        "/mcp",
        headers={"X-API-Key": "w28a743-smoke-key"},
        json={
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "list_experts", "arguments": {}},
        },
    )
    assert resp.status_code == 200, resp.text
    payload = resp.json()
    assert "result" in payload, payload
    assert "error" not in payload, payload
    assert "error" not in payload["result"], payload
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("FR-046")


def test_t3_group_bound_api_key_cascades_with_membership(db_session) -> None:
    """T3: group-bound user keys fail closed, activate on membership, revoke on removal."""
    from src.core.auth.api_key_manager import APIKeyManager
    from src.core.auth.group_manager import GroupManager
    from src.core.auth.user_manager import UserManager
    from src.servers.api.auth import _validate_api_key_user

    user = UserManager(db_session).create_user(
        username="w28a743_cascade_user",
        email="w28a743_cascade_user@example.invalid",
        password="W28a743-cascade-password!",
        role="viewer",
    )
    group = GroupManager(db_session).create_group(
        name="w28a743_cascade_group",
        description="W28A-743 cascade smoke group",
    )
    created = APIKeyManager(db_session).generate_key(
        user_id=user.id,
        group_id=group.id,
        name="w28a743_cascade_key",
    )
    plain_key = created["key"]

    assert _validate_api_key_user(plain_key, db_session) is None

    assert GroupManager(db_session).add_member(group.id, user.id, role="member") is True
    active_user = _validate_api_key_user(plain_key, db_session)
    assert active_user is not None
    assert active_user.id == user.id

    assert GroupManager(db_session).remove_member(group.id, user.id) is True
    assert _validate_api_key_user(plain_key, db_session) is None
