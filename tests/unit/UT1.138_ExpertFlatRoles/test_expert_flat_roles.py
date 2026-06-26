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

"""W28A-729-R5 — expert-agent flat WebUI login: admin / read-write / read-only.

Covers the three flat roles resolved via the ONE shared (INSTALLED)
cloud_dog_idam.RBACEngine guard (no fork), the locally-defined baseline grant,
the 738-decoupled baseline resolver, the fail-closed role normalisation, the
read-only write-gate path classification, and the flat-role-aware PS-76 job
permissions. The full login-flow + read-only-403-over-proxy is exercised by the
WebUI AT pack (real backend); these are the pure-logic unit checks.

Covers: FR1.6
"""


from __future__ import annotations
import pytest

from cloud_dog_idam.rbac import RBACEngine

from src.core.auth import expert_flat_roles as flat


# --------------------------------------------------------------------------- #
# Flat-role catalog — shared-guard derived, NO fork
# --------------------------------------------------------------------------- #
@pytest.mark.UT
@pytest.mark.req("CS-016")  # W28C-1711-R3.5 binding
@pytest.mark.req("CS-012")  # W28C-1711-R3.5 binding
@pytest.mark.mcp
@pytest.mark.req("FR-030")
def test_flat_roles_are_exactly_three():
    assert flat.FLAT_ROLES == ("admin", "read-write", "read-only")
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-030")


def test_admin_is_wildcard():
    assert flat.permissions_for_role("admin") == ["*"]
    assert flat.role_is_admin("admin") is True
    assert flat.role_can_write("admin") is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-030")


def test_read_write_has_baseline_plus_expert_use_perms():
    perms = set(flat.permissions_for_role("read-write"))
    # shared user baseline + expert use-permissions; never the wildcard.
    assert "*" not in perms
    assert "expert:tool:execute" in perms
    assert "sessions:create" in perms
    assert flat.role_can_write("read-write") is True
    assert flat.role_is_admin("read-write") is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-030")


def test_read_only_is_view_only_baseline():
    perms = set(flat.permissions_for_role("read-only"))
    assert "*" not in perms
    assert "expert:tool:execute" not in perms
    assert "sessions:create" not in perms
    assert flat.role_can_write("read-only") is False
    assert flat.role_is_admin("read-only") is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-030")


def test_normalise_is_fail_closed():
    # Expert DB roles collapse onto the three flat roles.
    assert flat.normalise_flat_role("admin") == "admin"
    assert flat.normalise_flat_role("user") == "read-write"
    assert flat.normalise_flat_role("viewer") == "read-only"
    assert flat.normalise_flat_role("owner") == "admin"
    # Unknown / empty always fails closed to read-only (never silent write access).
    assert flat.normalise_flat_role("totally-unknown") == "read-only"
    assert flat.normalise_flat_role("") == "read-only"
    assert flat.normalise_flat_role(None) == "read-only"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-030")


def test_build_expert_rbac_engine_is_installed_engine_not_a_fork():
    # AC1: the flat layer loads the INSTALLED cloud_dog_idam.RBACEngine with a
    # locally-defined catalog — it is not a bespoke/forked engine.
    engine = flat.build_expert_rbac_engine()
    assert isinstance(engine, RBACEngine)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-030")


def test_738_decoupled_baseline_resolves_without_unlanded_symbol():
    # AC6: read-only/read-write are anchored on the shared user baseline, which
    # must resolve against the CURRENT idam (BASELINE_ROLE_PERMISSIONS["user"])
    # without importing a post-738 symbol that has not landed yet.
    baseline = flat._shared_user_baseline()
    assert isinstance(baseline, set) and baseline  # non-empty, fail-safe floor at worst
    # read-only's perms are exactly the shared baseline (pure view role).
    assert set(flat.permissions_for_role("read-only")) == baseline


# --------------------------------------------------------------------------- #
# Read-only write-gate — 403-inline on data writes; reads + auth never gated
# --------------------------------------------------------------------------- #
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-030")
def test_write_gate_path_classification():
    # Expert data/mutation surfaces are gated — both the web (/web/api/*) and the
    # direct API (/v1/*) forms (the latter is the "727 hole" the API-tier gate closes).
    for p in (
        "/experts",
        "/sessions/abc/messages",
        "/web/api/experts",
        "/admin/users",
        "/v1/admin/users",
        "/knowledge",
        "/channels",
        "/mcp",
        "/v1/channels",
        "/v1/sessions",
        "/v1/knowledge",
        "/v1/prompts",
        "/v1/experts/1",
    ):
        assert flat.is_write_gated_data_path(p) is True, p
    # Auth (web AND API /v1/auth/*), health, login bootstrap, runtime-config: never gated.
    for p in (
        "/auth/login",
        "/auth/logout",
        "/web/auth/login",
        "/web/auth/logout",
        "/v1/auth/login",
        "/v1/auth/logout",
        "/health",
        "/v1/health",
        "/runtime-config.js",
        "/login",
        "/",
    ):
        assert flat.is_write_gated_data_path(p) is False, p


# --------------------------------------------------------------------------- #
# PS-76 job permissions — flat-role aware (admin + read-write may write jobs)
# --------------------------------------------------------------------------- #
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-030")
def test_job_permissions_for_role_is_flat_role_aware():
    from src.servers.api.auth import job_permissions_for_role

    admin = job_permissions_for_role("admin")
    assert "admin" in admin and "write_jobs" in admin and "read_jobs" in admin

    rw = job_permissions_for_role("user")  # normalises -> read-write
    assert "write_jobs" in rw and "read_jobs" in rw and "admin" not in rw

    ro = job_permissions_for_role("viewer")  # normalises -> read-only
    assert ro == ["read_jobs"]

    # Fail-closed: unknown role gets read-only job access.
    assert job_permissions_for_role("totally-unknown") == ["read_jobs"]


# --------------------------------------------------------------------------- #
# API-tier RBAC — read-only VIEWS data (200) but never writes; read-write uses
# --------------------------------------------------------------------------- #
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-030")
def test_api_rbac_read_only_can_view_data_surfaces_no_write():
    from src.servers.api.auth import _RBAC_ROLE_PERMISSIONS as R

    viewer = R["viewer"]
    user = R["user"]

    # read-only (DB role "viewer") can VIEW every named data surface.
    for p in (
        "expert:read",
        "experts:read",
        "sessions:read",
        "channels:read",
        "knowledge:read",
        "prompts:read",
        "services:read",
    ):
        assert p in viewer, f"viewer missing read perm {p}"

    # read-only has NO write/delete/admin/IDAM perms (view-only).
    for p in (
        "experts:create",
        "experts:update",
        "experts:delete",
        "sessions:create",
        "expert:execute",
        "users:read",
        "audit:read",
        "*",
    ):
        assert p not in viewer, f"viewer must NOT have {p}"

    # read-write (DB role "user") can view + use (execute, own-session create),
    # but not admin/IDAM CRUD.
    assert {"experts:read", "expert:execute", "sessions:create"} <= user
    for p in ("users:read", "experts:delete", "*"):
        assert p not in user, f"user must NOT have {p}"
