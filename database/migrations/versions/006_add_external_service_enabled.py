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

"""Add enabled flag to external services.

Revision ID: 006
Revises: 005
Create Date: 2026-05-23
"""

from alembic import op
import sqlalchemy as sa


revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "external_services" not in set(inspector.get_table_names()):
        return

    columns = {column["name"] for column in inspector.get_columns("external_services")}
    if "enabled" in columns:
        return

    with op.batch_alter_table("external_services") as batch_op:
        batch_op.add_column(sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()))

    with op.batch_alter_table("external_services") as batch_op:
        batch_op.alter_column("enabled", server_default=None)


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "external_services" not in set(inspector.get_table_names()):
        return

    columns = {column["name"] for column in inspector.get_columns("external_services")}
    if "enabled" not in columns:
        return

    with op.batch_alter_table("external_services") as batch_op:
        batch_op.drop_column("enabled")
