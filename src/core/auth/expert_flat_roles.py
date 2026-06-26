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

"""W28A-729-R5 — flat WebUI roles for expert-agent.

The *simple, flat* login that gets the demo back: three roles —
``admin`` (full), ``read-write`` (use it), ``read-only`` (view). No
granularity. Roles are computed via the ONE shared guard
(``cloud_dog_idam.RBACEngine`` + the canonical PS-82 §7 permission catalog) —
there is **no per-service RBAC fork** here; this module only *names* the three
flat roles and derives their permission sets from the shared catalog, then
loads them into the INSTALLED ``cloud_dog_idam.rbac.RBACEngine``.

The shared idam ships baseline roles (``admin`` -> ``*`` and ``user`` -> the
PS-82 §7.2 default grant). The flat lane maps:

* ``admin``      -> the shared ``admin`` baseline (wildcard ``*``).
* ``read-write`` -> the shared ``user`` baseline PLUS the expert use-permissions
  a demo operator needs to actually *use* the service (run tools, manage their
  own sessions, read expert config).
* ``read-only``  -> the shared ``user`` baseline only (view + self-service);
  every write resolves to a 403 at the enforcement point (never a blank UI).

This mirrors the canonical chat-client
``servers/web_flat_roles.py`` (W28A-727-R5) exactly; only the service-specific
*use* permissions differ (expert:* vs chat:*).
**W28A-738** (central baseline-user grant) is decoupled for this lane — the
``_shared_user_baseline()`` resolver builds against the current AND the
post-738 idam without crashing on a symbol that has not landed yet.
"""

from __future__ import annotations

from cloud_dog_idam import RBACEngine  # type: ignore[import-untyped]
from cloud_dog_idam.rbac import role_catalog as _rc  # type: ignore[import-untyped]

# The shared idam wildcard ("*") is the one stable, always-present symbol.
WILDCARD_PERMISSION: str = getattr(_rc, "WILDCARD_PERMISSION", "*")


def _shared_user_baseline() -> set[str]:
    """Return the shared idam ``user`` baseline grant.

    The flat lane anchors read-write/read-only on the SAME ``user`` baseline
    every other service inherits, so the flat roles stay consistent with the
    central catalog and there is no per-service fork. The richer catalog
    (``USER_BASELINE_PERMISSIONS`` + named CONFIG/PROFILES grants) lands with
    W28A-738; until it is published the deployed idam exposes the baseline via
    ``BASELINE_ROLE_PERMISSIONS["user"]`` (currently ``{"resources:read"}``).
    Resolve whichever the installed idam provides so this builds against both
    the current AND the post-738 idam — never crashing on an import of a symbol
    that has not landed yet.
    """
    explicit = getattr(_rc, "USER_BASELINE_PERMISSIONS", None)
    if explicit:
        return set(explicit)
    baseline = getattr(_rc, "BASELINE_ROLE_PERMISSIONS", {}) or {}
    user_grant = baseline.get("user")
    if user_grant:
        return set(user_grant)
    # Last-resort floor: a read-only view grant so a read-only session is never
    # empty (fail-safe, still view-only).
    return {"resources:read"}


def _shared_write_permissions() -> set[str]:
    """Named config/profiles WRITE grants from the shared catalog, if present.

    Uses the canonical strings when the richer catalog is installed; absent
    those symbols, contributes nothing extra (the literal expert-use permissions
    below still let a read-write operator use the system).
    """
    out: set[str] = set()
    for name in ("CONFIG_WRITE", "PROFILES_WRITE"):
        value = getattr(_rc, name, None)
        if isinstance(value, str) and value:
            out.add(value)
    return out


#: The three flat roles, in descending privilege order.
ADMIN_ROLE = "admin"
READ_WRITE_ROLE = "read-write"
READ_ONLY_ROLE = "read-only"

FLAT_ROLES: tuple[str, ...] = (ADMIN_ROLE, READ_WRITE_ROLE, READ_ONLY_ROLE)

# expert-agent use-permissions the read-write operator needs on top of the
# shared §7.2 user baseline. These are the strings the expert service authorises
# on (see src/core/auth/rbac.py _ROLE_PERMISSIONS["user"] + the API/MCP guards).
# Kept minimal and flat; granularity is a later thread.
_EXPERT_USE_PERMISSIONS: set[str] = {
    "expert:tool:execute",
    "expert:tool:list",
    "expert:config:read",
    "sessions:create",
    "sessions:read",
    "sessions:update",
    "experts:read",
    "api:access",
    "config:read",
}


#: Flat role -> permission set, built from the shared canonical catalog.
#: ``admin`` is the shared wildcard; ``read-write`` and ``read-only`` are both
#: anchored on the shared ``user`` baseline so they stay consistent with every
#: other service that inherits the same idam.
FLAT_ROLE_PERMISSIONS: dict[str, set[str]] = {
    ADMIN_ROLE: {WILDCARD_PERMISSION},
    READ_WRITE_ROLE: (
        _shared_user_baseline()
        | _shared_write_permissions()
        | _EXPERT_USE_PERMISSIONS
    ),
    READ_ONLY_ROLE: _shared_user_baseline(),
}


def normalise_flat_role(role: str | None) -> str:
    """Map an arbitrary role string onto one of the three flat roles.

    Anything that is not clearly admin / read-write resolves to the safest flat
    role (``read-only``) so an unknown role can never silently gain write access
    (fail-closed). The expert DB roles map: ``admin``->admin, ``user``->
    read-write, ``viewer``->read-only. The legacy ``viewer`` role maps to
    ``read-only``.
    """
    raw = str(role or "").strip().lower().replace("_", "-")
    if raw in {ADMIN_ROLE, "owner", "superuser", "super-admin"}:
        return ADMIN_ROLE
    if raw in {READ_WRITE_ROLE, "readwrite", "writer", "editor", "user", "member"}:
        return READ_WRITE_ROLE
    return READ_ONLY_ROLE


def build_expert_rbac_engine() -> RBACEngine:
    """Return the ONE shared RBACEngine loaded with the flat role catalog.

    This constructs the INSTALLED ``cloud_dog_idam.rbac.RBACEngine`` with the
    locally-defined flat role catalog (the "baseline grant defined locally").
    It is NOT a fork — the engine is the platform package; only the catalog is
    local.
    """
    return RBACEngine(
        role_permissions={name: set(perms) for name, perms in FLAT_ROLE_PERMISSIONS.items()}
    )


def permissions_for_role(role: str) -> list[str]:
    """Return the sorted effective permissions for a flat role via the shared engine."""
    flat = normalise_flat_role(role)
    engine = build_expert_rbac_engine()
    uid = f"flat:{flat}"
    engine.assign_role_to_user(uid, flat)
    return sorted(engine.get_effective_permissions(uid))


def role_can_write(role: str) -> bool:
    """True when the flat role may perform write/mutation operations."""
    return normalise_flat_role(role) in {ADMIN_ROLE, READ_WRITE_ROLE}


def role_is_admin(role: str) -> bool:
    """True when the flat role is the full-admin flat role."""
    return normalise_flat_role(role) == ADMIN_ROLE


def is_write_gated_data_path(path: str) -> bool:
    """Return True for DATA surfaces a read-only flat role may not mutate.

    The read-only write-gate only applies to the data/mutation surfaces. It MUST
    NOT swallow the auth endpoints (login/logout have their own handling and
    read-only must still be able to log in/out), nor any health/readiness probe,
    nor a static SPA asset, nor the runtime-config bootstrap. Read methods are
    never gated — read-only is a VIEW role; the gate is applied by the caller
    only for POST/PUT/PATCH/DELETE.
    """
    cleaned = "/" + str(path or "").strip().lstrip("/")
    # Never gate auth/login/logout (web `/auth/…`/`/web/auth/…` OR API `/v1/auth/…`)
    # or health/readiness/liveness probes. read-only must always be able to
    # authenticate and sign out.
    if "/auth/" in cleaned or cleaned.rstrip("/").endswith("/auth") or cleaned in {"/login", "/logout"}:
        return False
    if cleaned.endswith("/health") or cleaned in {
        "/health",
        "/status",
        "/ready",
        "/live",
        "/runtime-config.js",
    }:
        return False
    gated_prefixes = (
        "/api",
        "/v1",
        "/web/api",
        "/webapi",
        "/a2a",
        "/weba2a",
        "/mcp",
        "/webmcp",
        "/messages",
        "/sessions",
        "/experts",
        "/channels",
        "/knowledge",
        "/prompts",
        "/services",
        "/files",
        "/admin",
        "/idam",
        "/events",
        "/tasks",
    )
    for prefix in gated_prefixes:
        if cleaned == prefix or cleaned.startswith(prefix + "/"):
            return True
    return False
