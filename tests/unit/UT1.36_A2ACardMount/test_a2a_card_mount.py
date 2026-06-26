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
Unit Test: UT1.36 - A2A Card Router Mounted At Both Root And Prefix (W28A-970e3)

Asserts the W28A-970e3 fix: the A2A agent card must be discoverable at both
the platform-canonical root path ``/.well-known/agent.json`` AND the
legacy prefixed path ``/a2a/.well-known/agent.json`` (the latter preserved
for Traefik strip-prefix deployments and existing clients).

Related Tests: UT1.36
Related Requirements: PS-92 base_path; W28A-970e3 .well-known root-mount
"""

import ast
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from cloud_dog_api_kit.a2a.card import A2ASkill, create_a2a_card_router


A2A_SERVER_PATH = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "src"
    / "servers"
    / "a2a"
    / "server.py"
)


def _mount_card_like_server(base_path: str) -> FastAPI:
    """Mirror ``A2AServer._register_routes`` mount pattern without triggering
    full config/signal-handler bootstrap.

    Registers the A2A card router twice: once under the configured A2A base
    path (existing behaviour) and once at root (the W28A-970e3 fix).
    """
    app = FastAPI()

    skills = [
        A2ASkill(id="chat", name="Chat", description="Converse"),
    ]

    prefixed_router = create_a2a_card_router(
        name="expert-agent",
        description="Expert agent A2A server",
        skills=skills,
    )
    app.include_router(prefixed_router, prefix=base_path or "")

    root_router = create_a2a_card_router(
        name="expert-agent",
        description="Expert agent A2A server",
        skills=skills,
    )
    app.include_router(root_router)
    return app
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


def test_well_known_agent_json_registered_at_root():
    """GET /.well-known/agent.json must return the A2A agent card at root.

    This is the W28A-970e3 F-01 fix — prior to the fix the card was only
    reachable under the /a2a prefix and root returned 404 in preprod.
    """
    app = _mount_card_like_server("/a2a")
    client = TestClient(app)

    response = client.get("/.well-known/agent.json")

    assert response.status_code == 200, f"root well-known must be 200, got {response.status_code}"
    payload = response.json()
    assert payload.get("name") == "expert-agent"
    assert payload.get("description")
    assert isinstance(payload.get("skills"), list)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


def test_well_known_agent_json_registered_at_a2a_prefix():
    """GET /a2a/.well-known/agent.json must continue to return 200.

    The prefixed mount is preserved for Traefik strip-prefix deployments
    and any existing clients.
    """
    app = _mount_card_like_server("/a2a")
    client = TestClient(app)

    response = client.get("/a2a/.well-known/agent.json")

    assert response.status_code == 200, f"prefixed well-known must be 200, got {response.status_code}"
    payload = response.json()
    assert payload.get("name") == "expert-agent"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


def test_server_module_registers_root_mount():
    """Static-source check: ``src/servers/a2a/server.py`` must include the
    A2A card router at root (no prefix) in addition to the prefixed mount.

    Guard against regressions that would accidentally drop the root mount
    and re-break ``/.well-known/agent.json`` in production.
    """
    source = A2A_SERVER_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    include_router_calls = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        # Match ``self.app.include_router(...)``
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "include_router"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "app"
        ):
            include_router_calls.append(node)

    # At least two include_router calls on self.app (prefixed + root)
    assert len(include_router_calls) >= 2, (
        "A2AServer must include the A2A card router twice "
        "(prefixed under /a2a AND at root for /.well-known/agent.json). "
        f"Found {len(include_router_calls)} include_router call(s)."
    )

    # At least one call MUST NOT pass a `prefix=` keyword (== root mount)
    has_root_mount = any(
        not any(kw.arg == "prefix" for kw in call.keywords) for call in include_router_calls
    )
    assert has_root_mount, (
        "A2AServer must include at least one card router at root (no prefix=) "
        "so /.well-known/agent.json answers at the platform-canonical path."
    )
