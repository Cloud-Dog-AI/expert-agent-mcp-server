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

from __future__ import annotations

# Covers: FR1.5
# Covers: FR1.11

from tests.helpers_orchestration import build_api_client, seed_admin, seed_expert
import pytest
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_ut199_expert_routes_require_authentication(db_session) -> None:
    _, api_key = seed_admin(db_session, api_key="ut199-expert-routes-key")
    expert = seed_expert(
        db_session,
        name="ut199_expert",
        title="UT1.99 Expert",
        description="UT1.99 auth gate coverage for expert routes.",
    )

    client = build_api_client(db_session, api_key=api_key)
    client.headers.pop("X-API-Key", None)
    client.headers.pop("Authorization", None)

    try:
        assert client.get("/experts").status_code == 401
        assert client.post(
            "/experts",
            json={
                "name": "unauth_expert",
                "title": "Unauth Expert",
                "description": "Should be rejected without credentials.",
            },
        ).status_code == 401
        assert client.get(f"/experts/{expert.id}").status_code == 401
        assert client.put(
            f"/experts/{expert.id}",
            json={"title": "Should not update"},
        ).status_code == 401
        assert client.delete(f"/experts/{expert.id}").status_code == 401
    finally:
        client.close()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_ut199_expert_routes_accept_authenticated_requests(db_session) -> None:
    _, api_key = seed_admin(db_session, api_key="ut199-expert-routes-ok-key")
    expert = seed_expert(
        db_session,
        name="ut199_expert_ok",
        title="UT1.99 Expert OK",
        description="UT1.99 authenticated access coverage for expert routes.",
    )

    client = build_api_client(db_session, api_key=api_key)
    try:
        assert client.get("/experts").status_code == 200
        assert client.get(f"/experts/{expert.id}").status_code == 200
    finally:
        client.close()
