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
Unit Test: UT1.44 - MCP Stdio Mode

License: Apache 2.0
Ownership: Cloud Dog
Description: Validates stdio MCP mode startup path and JSON-RPC execution contract

Related Requirements: FR1.7, FR1.25
Related Tasks: T039, T063
Related Architecture: CC1.1.3, AI1.2
Related Tests: ST1.2
"""

import asyncio

import pytest

from src.servers.mcp.server import MCPServer
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


@pytest.mark.asyncio
async def test_stdio_mode_start_path_creates_stdio_task():
    server = MCPServer()
    server.transport = "stdio"

    ran = {"value": False}

    async def fake_stdio_loop():
        ran["value"] = True
        await asyncio.sleep(0)

    server._run_stdio_loop = fake_stdio_loop  # type: ignore[method-assign]

    await server.start()
    await asyncio.sleep(0)

    assert hasattr(server, "_stdio_task")
    assert ran["value"] is True

    await server.stop()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


@pytest.mark.asyncio
async def test_execute_jsonrpc_initialize_tools_list_contract():
    server = MCPServer()

    initialize = await server._execute_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
        },
        session_id="stdio-session",
    )
    assert initialize["jsonrpc"] == "2.0"
    assert initialize["id"] == 1
    assert initialize["result"]["protocolVersion"] == "2024-11-05"

    server._rpc_sessions["stdio-session"] = {"initialized": True}
    tools = await server._execute_jsonrpc(
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        session_id="stdio-session",
    )
    assert tools["jsonrpc"] == "2.0"
    assert tools["id"] == 2
    tool_names = {item.get("name") for item in tools["result"]["tools"]}
    assert "chat" in tool_names
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-031")


@pytest.mark.asyncio
async def test_execute_jsonrpc_invalid_method_error_contract():
    server = MCPServer()
    server._rpc_sessions["stdio-session"] = {"initialized": True}

    response = await server._execute_jsonrpc(
        {"jsonrpc": "2.0", "id": 3, "method": "does/not/exist"},
        session_id="stdio-session",
    )
    assert response["jsonrpc"] == "2.0"
    assert response["id"] == 3
    assert response["error"]["code"] == -32601

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.mcp, pytest.mark.fast]

