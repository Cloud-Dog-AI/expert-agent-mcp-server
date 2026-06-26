# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# SPDX-License-Identifier: Apache-2.0
"""
UT1.132 — shared @cloud-dog/idam web-proxy endpoints (auth/status + admin/permissions).

License: Apache 2.0
Ownership: Cloud-Dog, Viewdeck Engineering Limited
Description:
    Regression guard for W28A-891-R2. The shared @cloud-dog/idam pages probe
    {apiBase}/auth/status (best-effort capability check) and {apiBase}/v1/admin/permissions
    (the assignable-permission catalogue). Both previously returned HTTP 404 through the
    expert web proxy, producing console errors on every authed IDAM page. This test pins:
      - GET /web/api/auth/status is served by the web tier (200, not 404).
      - the /admin/permissions catalogue returns the union of baseline role permissions.

Related Requirements: FR1.6, FR1.43, PS-71 IW3A
Related Tasks: W28A-891-R2
Related Architecture: SE1.1, CC1.15
Related Tests: UT1.131 (unauth auth-gate)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.unit, pytest.mark.security, pytest.mark.pure]
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-030")


def test_web_api_auth_status_is_served_not_404() -> None:
    """/web/api/auth/status must be served from the web session, never 404."""
    from servers.web.server import WebServer

    client = TestClient(WebServer().app)
    resp = client.get("/web/api/auth/status")
    assert resp.status_code == 200, f"auth/status must be 200 (capability probe), got {resp.status_code}"
    body = resp.json()
    assert "authenticated" in body, body
    # Unauthenticated probe reports not-authenticated (never a populated/admin principal).
    assert body.get("authenticated") is False, body
    assert body.get("user") in (None, {}), body
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-030")


@pytest.mark.asyncio
async def test_admin_permissions_catalogue_unions_baseline_roles() -> None:
    """/admin/permissions returns the assignable-permission catalogue (>= baseline perms)."""
    from servers.api.routes.admin_permissions import list_permissions

    class _DummyAdmin:
        username = "admin"

    # db=None makes the persistent store fail closed -> baseline catalogue only (still valid).
    result = await list_permissions(db=None, _admin=_DummyAdmin())
    perms = result["permissions"]
    assert isinstance(perms, list) and perms, result
    assert result["count"] == len(perms)
    # Baseline PS-70 expert-agent permission strings MUST be present.
    for expected in ("expert:admin:*", "users:read", "sessions:create", "audit:read"):
        assert expected in perms, f"missing baseline permission {expected!r} in catalogue"
