"""Add orchestration enhancement tables for W28A-239.

Revision ID: 004
Revises: 003
Create Date: 2026-03-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    dialect = bind.dialect.name

    def table_exists(table_name: str) -> bool:
        return table_name in inspector.get_table_names()

    def column_names(table_name: str) -> set[str]:
        if not table_exists(table_name):
            return set()
        return {column["name"] for column in inspector.get_columns(table_name)}

    def index_names(table_name: str) -> set[str]:
        if not table_exists(table_name):
            return set()
        return {index["name"] for index in inspector.get_indexes(table_name)}

    session_columns = column_names("sessions")
    session_indexes = index_names("sessions")
    if "parent_session_id" not in session_columns:
        op.add_column("sessions", sa.Column("parent_session_id", sa.Integer(), nullable=True))
    if "idx_sessions_parent_session_id" not in session_indexes:
        op.create_index("idx_sessions_parent_session_id", "sessions", ["parent_session_id"])
    if dialect != "sqlite" and "parent_session_id" not in session_columns:
        op.create_foreign_key(
            "fk_sessions_parent_session_id",
            "sessions",
            "sessions",
            ["parent_session_id"],
            ["id"],
            ondelete="SET NULL",
        )

    if not table_exists("service_bindings"):
        op.create_table(
            "service_bindings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("expert_config_id", sa.Integer(), nullable=False),
            sa.Column("service_id", sa.Integer(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("timeout_seconds", sa.Integer(), nullable=True),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("circuit_breaker_threshold", sa.Integer(), nullable=True),
            sa.Column("metadata_json", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["expert_config_id"], ["expert_configs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["service_id"], ["external_services.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_service_bindings_expert", "service_bindings", ["expert_config_id"])
        op.create_index("idx_service_bindings_service", "service_bindings", ["service_id"])

    if not table_exists("sub_expert_bindings"):
        op.create_table(
            "sub_expert_bindings",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("parent_expert_id", sa.Integer(), nullable=False),
            sa.Column("child_expert_id", sa.Integer(), nullable=False),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("max_depth", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("delegation_prompt", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["parent_expert_id"], ["expert_configs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["child_expert_id"], ["expert_configs.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_sub_expert_bindings_parent", "sub_expert_bindings", ["parent_expert_id"])
        op.create_index("idx_sub_expert_bindings_child", "sub_expert_bindings", ["child_expert_id"])

    if not table_exists("prompt_templates"):
        op.create_table(
            "prompt_templates",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("content", sa.Text(), nullable=False),
            sa.Column("variables_schema", sa.Text(), nullable=True),
            sa.Column("created_by", sa.String(length=255), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_prompt_templates_name", "prompt_templates", ["name"])

    if not table_exists("expert_prompt_assignments"):
        op.create_table(
            "expert_prompt_assignments",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("expert_config_id", sa.Integer(), nullable=False),
            sa.Column("prompt_template_id", sa.Integer(), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("assigned_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.ForeignKeyConstraint(["expert_config_id"], ["expert_configs.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["prompt_template_id"], ["prompt_templates.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "idx_expert_prompt_assignments_expert", "expert_prompt_assignments", ["expert_config_id"]
        )
        op.create_index(
            "idx_expert_prompt_assignments_prompt", "expert_prompt_assignments", ["prompt_template_id"]
        )

    if not table_exists("service_invocation_logs"):
        op.create_table(
            "service_invocation_logs",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("session_id", sa.Integer(), nullable=True),
            sa.Column("service_id", sa.Integer(), nullable=True),
            sa.Column("tool_name", sa.String(length=255), nullable=False),
            sa.Column("request_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
            sa.Column("response_status", sa.String(length=50), nullable=True),
            sa.Column("tokens_used", sa.Integer(), nullable=True),
            sa.Column("duration_ms", sa.Integer(), nullable=True),
            sa.Column("request_payload_json", sa.Text(), nullable=True),
            sa.Column("response_payload_json", sa.Text(), nullable=True),
            sa.ForeignKeyConstraint(["service_id"], ["external_services.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("idx_service_invocation_logs_session", "service_invocation_logs", ["session_id"])
        op.create_index("idx_service_invocation_logs_service", "service_invocation_logs", ["service_id"])


def downgrade() -> None:
    op.drop_index("idx_service_invocation_logs_service", table_name="service_invocation_logs")
    op.drop_index("idx_service_invocation_logs_session", table_name="service_invocation_logs")
    op.drop_table("service_invocation_logs")

    op.drop_index("idx_expert_prompt_assignments_prompt", table_name="expert_prompt_assignments")
    op.drop_index("idx_expert_prompt_assignments_expert", table_name="expert_prompt_assignments")
    op.drop_table("expert_prompt_assignments")

    op.drop_index("idx_prompt_templates_name", table_name="prompt_templates")
    op.drop_table("prompt_templates")

    op.drop_index("idx_sub_expert_bindings_child", table_name="sub_expert_bindings")
    op.drop_index("idx_sub_expert_bindings_parent", table_name="sub_expert_bindings")
    op.drop_table("sub_expert_bindings")

    op.drop_index("idx_service_bindings_service", table_name="service_bindings")
    op.drop_index("idx_service_bindings_expert", table_name="service_bindings")
    op.drop_table("service_bindings")

    op.drop_constraint("fk_sessions_parent_session_id", "sessions", type_="foreignkey")
    op.drop_index("idx_sessions_parent_session_id", table_name="sessions")
    op.drop_column("sessions", "parent_session_id")
