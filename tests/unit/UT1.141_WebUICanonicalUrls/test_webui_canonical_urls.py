# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# SPDX-License-Identifier: Apache-2.0
"""
UT1.141 — WebUI URL canonicalisation (PS-WEBUI-URL-CANONICAL v1.0).

License: Apache 2.0
Ownership: Cloud-Dog, Viewdeck Engineering Limited
Description:
    W28E-1809C Stream-C. Pins the canonical WebUI URL contract for the expert-agent
    web tier so the SPA fallback can never mask URL drift (WURL-001/002/004/009):
      - every legacy alias returns HTTP 308 to its single canonical route, with the
        query string preserved (WURL-002/010);
      - every canonical taxonomy route serves the SPA shell (HTTP 200, WURL-001);
      - real FastAPI Swagger/OpenAPI/ReDoc endpoints (/docs, /openapi.json, /redoc)
        are NOT redirected through a WebUI alias (WURL-008);
      - an unknown WebUI route returns 404 (WURL-007).
    Negative/positive route coverage lives at unit tier so CI catches a regression
    locally, not only in preprod (COMMON-FINAL-EVIDENCE §0C.5).

Related Requirements: FR-032 (WebUI common operator taxonomy), FR-031 (API docs surface), FR-028
Related Tasks: W28E-1809C
Related Standards: PS-WEBUI-URL-CANONICAL v1.0 (WURL-001..014)
Related Tests: UT1.132 (idam web proxy), AT_WEBUI_E2E (browser E2E)
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.unit, pytest.mark.pure]

# PS-WEBUI-URL-CANONICAL §2 — legacy alias -> canonical route (web base path "").
LEGACY_TO_CANONICAL = {
    "/ui/login": "/login",
    "/auth/login": "/login",
    "/audit": "/audit-log",
    "/diagnostics-audit": "/audit-log",
    "/observability": "/audit-log",
    "/logs": "/audit-log",
    "/idam/users": "/admin/users",
    "/idam/groups": "/admin/groups",
    "/idam/api-keys": "/admin/api-keys",
    "/apikeys": "/admin/api-keys",
    "/api-keys": "/admin/api-keys",
    "/idam/roles": "/admin/roles",
    "/idam/rbac": "/admin/rbac",
    "/rbac": "/admin/rbac",
    "/api-docs": "/developer/api-docs",
    "/mcp-console": "/developer/mcp-console",
    "/a2a-console": "/developer/a2a-console",
    "/jobs": "/system/jobs",
    "/settings": "/system/settings",
    "/about": "/system/about",
}

CANONICAL_ROUTES = [
    "/",
    "/login",
    "/audit-log",
    "/admin/users",
    "/admin/groups",
    "/admin/api-keys",
    "/admin/roles",
    "/admin/rbac",
    "/developer/api-docs",
    "/developer/mcp-console",
    "/developer/a2a-console",
    "/system/jobs",
    "/system/settings",
    "/system/about",
]


@pytest.fixture(scope="module")
def client() -> TestClient:
    from servers.web.server import WebServer

    return TestClient(WebServer().app, follow_redirects=False)


@pytest.mark.UT
@pytest.mark.webui
@pytest.mark.req("FR-032")
@pytest.mark.parametrize("alias,canonical", sorted(LEGACY_TO_CANONICAL.items()))
def test_legacy_alias_redirects_308_to_canonical(client: TestClient, alias: str, canonical: str) -> None:
    """Every legacy WebUI alias 308-redirects to its single canonical route (WURL-002)."""
    resp = client.get(alias)
    assert resp.status_code == 308, f"{alias} must 308 (got {resp.status_code})"
    assert resp.headers.get("location") == canonical, (
        f"{alias} must redirect to {canonical}, got {resp.headers.get('location')}"
    )


@pytest.mark.UT
@pytest.mark.webui
@pytest.mark.req("FR-032")
def test_redirect_preserves_query_string(client: TestClient) -> None:
    """Redirects preserve the query string (WURL-010)."""
    resp = client.get("/idam/users?actor_id=admin&tab=roles")
    assert resp.status_code == 308, resp.status_code
    assert resp.headers.get("location") == "/admin/users?actor_id=admin&tab=roles", resp.headers.get("location")


@pytest.mark.UT
@pytest.mark.webui
@pytest.mark.req("FR-032")
@pytest.mark.parametrize("route", CANONICAL_ROUTES)
def test_canonical_route_serves_spa_200(client: TestClient, route: str) -> None:
    """Every canonical taxonomy route serves the SPA shell (200, never a 308) (WURL-001)."""
    resp = client.get(route)
    assert resp.status_code == 200, f"{route} must serve the SPA (got {resp.status_code})"
    assert "text/html" in resp.headers.get("content-type", ""), resp.headers.get("content-type")


@pytest.mark.UT
@pytest.mark.webui
@pytest.mark.req("FR-031")
@pytest.mark.parametrize("real_endpoint", ["/docs", "/openapi.json", "/redoc"])
def test_real_openapi_endpoints_not_redirected(client: TestClient, real_endpoint: str) -> None:
    """Real Swagger/OpenAPI/ReDoc endpoints are retained, never redirected as WebUI aliases (WURL-008)."""
    resp = client.get(real_endpoint)
    assert resp.status_code != 308, f"{real_endpoint} must NOT be a WebUI 308 alias (WURL-008)"
    assert resp.status_code == 200, f"{real_endpoint} must remain a live endpoint (got {resp.status_code})"


@pytest.mark.UT
@pytest.mark.webui
@pytest.mark.negative
@pytest.mark.req("FR-028")
def test_unknown_webui_route_404(client: TestClient) -> None:
    """Unknown WebUI route returns 404 — SPA fallback must not mask drift (WURL-007)."""
    resp = client.get("/nonexistent-webui-route-zzz")
    assert resp.status_code == 404, resp.status_code
