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

"""Unify expert access_control to the {type, roles, demo_surface, demo_collection,
allowed_groups} schema (W28C-1704 EA7 / W28M-FIX-1615).

Migrates the two legacy shapes in expert_configs.access_control_json:
  * {"roles": [...]}                          -> {"type": "rbac", ...}
  * {"demo": true, "collection", "surface"}   -> {"type": "demo", ...}
The conversion is loss-free (group gates + demo metadata preserved) and
idempotent (rows already in unified shape are skipped). The normalisation logic
is inlined so the migration is self-contained and does not import service code.

Revision ID: 008
Revises: 007
Create Date: 2026-06-10
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "008"
down_revision = "007"
branch_labels = None
depends_on = None

_UNIFIED_KEYS = {"type", "roles", "demo_surface", "demo_collection", "allowed_groups"}


def _normalise(raw):
    if not isinstance(raw, dict):
        return {
            "type": "rbac",
            "roles": [],
            "demo_surface": None,
            "demo_collection": None,
            "allowed_groups": [],
        }
    roles = list(raw.get("roles") or [])
    allowed_groups = list(raw.get("allowed_groups") or [])
    if raw.get("type") in ("rbac", "demo"):
        return {
            "type": str(raw["type"]),
            "roles": roles,
            "demo_surface": raw.get("demo_surface") or raw.get("surface"),
            "demo_collection": raw.get("demo_collection") or raw.get("collection"),
            "allowed_groups": allowed_groups,
        }
    if raw.get("demo") is True or raw.get("surface") or raw.get("collection"):
        return {
            "type": "demo",
            "roles": roles,
            "demo_surface": raw.get("surface") or raw.get("demo_surface"),
            "demo_collection": raw.get("collection") or raw.get("demo_collection"),
            "allowed_groups": allowed_groups,
        }
    return {
        "type": "rbac",
        "roles": roles,
        "demo_surface": None,
        "demo_collection": None,
        "allowed_groups": allowed_groups,
    }


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "expert_configs" not in set(inspector.get_table_names()):
        return

    rows = bind.execute(
        sa.text("SELECT id, access_control_json FROM expert_configs")
    ).fetchall()
    for row in rows:
        expert_id, raw_json = row[0], row[1]
        if not raw_json:
            continue
        try:
            parsed = json.loads(raw_json)
        except Exception:
            continue
        # Idempotent: skip rows already in the unified shape.
        if (
            isinstance(parsed, dict)
            and parsed.get("type") in ("rbac", "demo")
            and _UNIFIED_KEYS.issubset(set(parsed.keys()))
        ):
            continue
        unified = _normalise(parsed)
        bind.execute(
            sa.text(
                "UPDATE expert_configs SET access_control_json = :ac WHERE id = :id"
            ),
            {"ac": json.dumps(unified), "id": expert_id},
        )


def downgrade() -> None:
    # Non-reversible data normalisation; legacy shapes are not reconstructed.
    pass
