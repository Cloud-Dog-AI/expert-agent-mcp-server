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

"""Add dedicated LLM parameter columns to expert_configs.

Revision ID: 007
Revises: 006
Create Date: 2026-05-24
"""

from alembic import op
import sqlalchemy as sa


revision = "007"
down_revision = "006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "expert_configs" not in set(inspector.get_table_names()):
        return

    columns = {column["name"] for column in inspector.get_columns("expert_configs")}

    with op.batch_alter_table("expert_configs") as batch_op:
        if "temperature" not in columns:
            batch_op.add_column(sa.Column("temperature", sa.Float(), nullable=True))
        if "top_k" not in columns:
            batch_op.add_column(sa.Column("top_k", sa.Integer(), nullable=True))
        if "max_tokens" not in columns:
            batch_op.add_column(sa.Column("max_tokens", sa.Integer(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "expert_configs" not in set(inspector.get_table_names()):
        return

    columns = {column["name"] for column in inspector.get_columns("expert_configs")}

    with op.batch_alter_table("expert_configs") as batch_op:
        if "max_tokens" in columns:
            batch_op.drop_column("max_tokens")
        if "top_k" in columns:
            batch_op.drop_column("top_k")
        if "temperature" in columns:
            batch_op.drop_column("temperature")
