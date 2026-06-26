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

"""Add signature column to audit_events.

Revision ID: 005
Revises: 004
Create Date: 2026-03-25
"""

from alembic import op
import sqlalchemy as sa


revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "audit_events" not in tables:
        return

    audit_columns = {col["name"] for col in inspector.get_columns("audit_events")}
    if "signature" in audit_columns:
        return

    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.add_column(sa.Column("signature", sa.String(length=255), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "audit_events" not in tables:
        return

    audit_columns = {col["name"] for col in inspector.get_columns("audit_events")}
    if "signature" not in audit_columns:
        return

    with op.batch_alter_table("audit_events") as batch_op:
        batch_op.drop_column("signature")
