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
UT1.136 — k8s-style health probes return JSON, not the SPA shell (EA9 / W28M-FIX-1617).

License: Apache 2.0
Ownership: Cloud-Dog, Viewdeck Engineering Limited
Description:
    Proves /ready, /live, /healthz, /status are served by explicit handlers
    (real JSON probe status) registered BEFORE the SPA catch-all, instead of
    falling through to the React index.html shell.

Related Tasks: W28M-FIX-1617 / W28C-1704 EA9
"""

import pytest
from fastapi.testclient import TestClient

pytestmark = [pytest.mark.unit, pytest.mark.pure]


@pytest.fixture()
def web_client() -> TestClient:
    from servers.web.server import WebServer

    return TestClient(WebServer().app)


@pytest.mark.req("CS-015")  # W28C-1711-R3.5 binding
@pytest.mark.req("CS-014")  # W28C-1711-R3.5 binding
@pytest.mark.req("CS-013")  # W28C-1711-R3.5 binding
@pytest.mark.req("CS-011")  # W28C-1711-R3.5 binding
@pytest.mark.req("CS-010")  # W28C-1711-R3.5 binding
@pytest.mark.req("CS-009")  # W28C-1711-R3.5 binding
@pytest.mark.req("CS-007")  # W28C-1711-R3.5 binding
@pytest.mark.req("CS-004")  # W28C-1711-R3.5 binding
@pytest.mark.req("CS-003")  # W28C-1711-R3.5 binding
@pytest.mark.req("CS-002")  # W28C-1711-R3.5 binding
@pytest.mark.parametrize(
    "path,expected_state",
    [
        ("/ready", "ready"),
        ("/live", "alive"),
        ("/healthz", "ok"),
        ("/status", "ok"),
    ],
)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("CS-001")
def test_probe_returns_json_not_spa_html(web_client: TestClient, path: str, expected_state: str):
    resp = web_client.get(path)
    assert resp.status_code == 200, resp.text
    ctype = resp.headers.get("content-type", "")
    assert "application/json" in ctype, f"{path} should be JSON, got {ctype}: {resp.text[:120]}"
    body = resp.json()
    assert body.get("status") == expected_state, body
    assert body.get("service") == "expert-agent-mcp-server", body
    # Must NOT be the SPA shell.
    assert "<!DOCTYPE html>" not in resp.text and "<html" not in resp.text.lower()


@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("CS-015")


def test_version_endpoint_returns_json_not_spa_html(web_client: TestClient):
    resp = web_client.get("/version")
    assert resp.status_code == 200, resp.text
    assert "application/json" in resp.headers.get("content-type", "")
    body = resp.json()
    assert body.get("service") == "expert-agent-mcp-server", body
    assert body.get("version"), body
    assert "<!DOCTYPE html>" not in resp.text and "<html" not in resp.text.lower()


# ---------------------------------------------------------- EA10 build-info ----


def _build_info_app(authed: bool) -> TestClient:
    from fastapi import FastAPI

    from src.database.models import User
    from src.servers.api.auth import verify_api_key
    from src.servers.api.routes.health import router as health_router

    app = FastAPI()
    app.include_router(health_router, prefix="/api/v1")
    if authed:
        app.dependency_overrides[verify_api_key] = lambda: User(
            id=1, username="admin", email="a@b.c", role="admin", enabled=True
        )
    return TestClient(app)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("CS-005")


def test_build_info_requires_auth():
    client = _build_info_app(authed=False)
    resp = client.get("/api/v1/build-info")
    assert resp.status_code == 401, resp.text
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("CS-006")


def test_build_info_authed_returns_manifest():
    client = _build_info_app(authed=True)
    resp = client.get("/api/v1/build-info")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # In the test env there is no /app/build-info.json, so the fallback manifest
    # is returned — but it must always carry the provenance fields.
    for key in ("version", "git_commit", "git_branch"):
        assert key in body, body
