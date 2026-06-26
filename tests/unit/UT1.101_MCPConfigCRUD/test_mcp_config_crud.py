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
Unit Test: UT1.101 - MCP Config CRUD

License: Apache 2.0
Ownership: Cloud Dog
Description: Validates admin MCP config CRUD tools and RBAC

Related Requirements: FR1.7, FR1.11
Related Tasks: T039, T044
Related Architecture: CC1.1.3, CC1.1.4
Related Tests: IT2.42
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from src.core.auth.api_key_manager import APIKeyManager
from src.core.auth.user_manager import UserManager
from src.servers.mcp.server import MCPServer
from src.servers.mcp.tools import MCPTools


@pytest.fixture
def admin_auth_context(db_session):
    """Provision a real admin API key for MCP admin tool tests."""
    user = UserManager(db_session).create_user(
        username="ut101_admin",
        email="ut101_admin@example.com",
        password="AdminPass123!",
        role="admin",
    )
    result = APIKeyManager(db_session).generate_key(user_id=user.id, name="ut101-admin-key")
    return {"api_key": result["key"]}


@pytest.fixture
def mcp_tools(db_session):
    """Bind MCPTools to the per-test DB fixture."""
    tools = MCPTools()

    @contextmanager
    def _db_scope():
        yield db_session

    tools._db_scope = _db_scope  # type: ignore[method-assign]
    return tools
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_admin_expert_crud_tools_publish_events(monkeypatch, mcp_tools, admin_auth_context):
    """Admin expert create/delete via MCP emits config events."""
    events: list[dict[str, object]] = []
    monkeypatch.setattr(
        "src.servers.mcp.tools.publish_config_change_event",
        lambda **payload: events.append(payload) or True,
    )

    created = mcp_tools.admin_create_expert_tool(
        name="ut101_expert",
        title="UT101 Expert Alpha Beta",
        description="Expert for MCP config CRUD validation with sufficient unique wording.",
        auth_context=admin_auth_context,
        llm_provider="ollama",
        llm_model="qwen3:14b",
        llm_base_url="https://llm.example.com",
    )
    assert "error" not in created
    assert created["name"] == "ut101_expert"

    listed = mcp_tools.admin_list_experts_tool(auth_context=admin_auth_context)
    names = {entry["name"] for entry in listed["experts"]}
    assert "ut101_expert" in names

    deleted = mcp_tools.admin_delete_expert_tool(created["id"], auth_context=admin_auth_context)
    assert deleted == {"success": True, "id": created["id"], "name": "ut101_expert"}

    assert events[0]["action"] == "create"
    assert events[0]["resource_type"] == "expert"
    assert events[1]["action"] == "delete"
    assert events[1]["resource_type"] == "expert"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


def test_admin_user_and_api_key_tools_require_admin(monkeypatch, db_session, mcp_tools):
    """Non-admin auth contexts are rejected by the admin MCP tools."""
    user = UserManager(db_session).create_user(
        username="ut101_user",
        email="ut101_user@example.com",
        password="UserPass123!",
        role="user",
    )
    key = APIKeyManager(db_session).generate_key(user_id=user.id, name="ut101-user-key")
    monkeypatch.setattr(
        "src.servers.mcp.tools.publish_config_change_event",
        lambda **_: True,
    )

    denied_users = mcp_tools.admin_list_users_tool(auth_context={"api_key": key["key"]})
    assert denied_users["error"] == "Admin access required"

    denied_key = mcp_tools.admin_create_api_key_tool(
        auth_context={"api_key": key["key"]},
        user_id=user.id,
        name="ut101-denied",
    )
    assert denied_key["error"] == "Admin access required"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


@pytest.mark.asyncio
async def test_jsonrpc_tools_list_contains_config_crud_tools():
    """The MCP JSON-RPC tool catalogue exposes the new admin config tools."""
    server = MCPServer()
    server._rpc_sessions["ut101-session"] = {"initialized": True}

    response = await server._execute_jsonrpc(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        session_id="ut101-session",
    )

    names = {entry["name"] for entry in response["result"]["tools"]}
    assert {
        "admin_list_experts",
        "admin_create_expert",
        "admin_update_expert",
        "admin_delete_expert",
        "admin_list_users",
        "admin_create_api_key",
        "admin_revoke_api_key",
    }.issubset(names)


pytestmark = [pytest.mark.unit, pytest.mark.mcp, pytest.mark.db, pytest.mark.fast]
