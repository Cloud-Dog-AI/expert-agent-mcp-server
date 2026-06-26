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
Unified expert access-control schema + authorization dispatch.

License: Apache 2.0
Ownership: Cloud Dog
Description:
    W28M-FIX-1615 (EA7). Historically two incompatible ``access_control`` shapes
    coexisted on ``expert_configs.access_control_json``:
      * RBAC-style:  ``{"roles": ["admin", "viewer"]}`` (with optional
        ``{"allowed_groups": [...]}`` actually enforced by the session manager)
      * Demo-style:  ``{"demo": true, "collection": "...", "surface": "DEMO-024"}``
    This module normalises BOTH into a single schema and provides a single
    ``is_authorized`` dispatch keyed on ``type`` so consumers no longer special-case
    each shape. Normalisation is loss-free (group gates and demo metadata preserved)
    and behaviour-preserving: a row with no ``allowed_groups`` stays open exactly as
    before; demo rows stay open within their surface.

Unified schema:
    {
      "type": "rbac" | "demo",
      "roles": [str, ...],
      "demo_surface": str | None,
      "demo_collection": str | None,
      "allowed_groups": [int, ...],
    }

Related Requirements: FR1.5 (expert access), CS1.1
Related Tasks: W28M-FIX-1615 / W28C-1704 EA7
Related Tests: UT1.134 (access_control unification)
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

UNIFIED_TYPES = ("rbac", "demo")


def normalise_access_control(raw: Any) -> Dict[str, Any]:
    """Convert any legacy or partial ``access_control`` shape to the unified schema.

    Idempotent: re-normalising an already-unified row returns the same value.
    """
    if not isinstance(raw, dict):
        return {
            "type": "rbac",
            "roles": [],
            "demo_surface": None,
            "demo_collection": None,
            "allowed_groups": [],
        }

    roles: List[Any] = list(raw.get("roles") or [])
    allowed_groups: List[Any] = list(raw.get("allowed_groups") or [])

    # Already unified — backfill any missing keys without changing type.
    if raw.get("type") in UNIFIED_TYPES:
        return {
            "type": str(raw["type"]),
            "roles": roles,
            "demo_surface": raw.get("demo_surface") or raw.get("surface"),
            "demo_collection": raw.get("demo_collection") or raw.get("collection"),
            "allowed_groups": allowed_groups,
        }

    # Legacy demo shape: {"demo": true, "collection": ..., "surface": ...}
    if raw.get("demo") is True or raw.get("surface") or raw.get("collection"):
        return {
            "type": "demo",
            "roles": roles,
            "demo_surface": raw.get("surface") or raw.get("demo_surface"),
            "demo_collection": raw.get("collection") or raw.get("demo_collection"),
            "allowed_groups": allowed_groups,
        }

    # Legacy RBAC shape: {"roles": [...]} and/or {"allowed_groups": [...]} or empty.
    return {
        "type": "rbac",
        "roles": roles,
        "demo_surface": None,
        "demo_collection": None,
        "allowed_groups": allowed_groups,
    }


def is_authorized(
    access_control: Any,
    *,
    user_role: Optional[str] = None,
    user_group_ids: Optional[Iterable[int]] = None,
) -> bool:
    """Authorize a caller against a (possibly legacy) access_control value.

    Dispatches on the unified ``type``:
      * ``demo``  — open within the demo surface (subject to any explicit group gate).
      * ``rbac``  — enforced via the historical ``allowed_groups`` membership gate;
        when ``allowed_groups`` is empty the expert is open (behaviour-preserving).

    The ``roles`` list is metadata that does not tighten access here (it never did);
    it is preserved on the row for downstream RBAC tooling and surfaced to callers.
    """
    ac = normalise_access_control(access_control)
    allowed_groups = [g for g in (ac.get("allowed_groups") or [])]

    # Admin is always permitted.
    if str(user_role or "").strip().lower() == "admin":
        return True

    if allowed_groups:
        member = set(user_group_ids or [])
        return any(g in member for g in allowed_groups)

    # No explicit group gate: open (both rbac-open and demo surfaces).
    return True
