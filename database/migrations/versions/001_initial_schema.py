"""Initial database schema

Revision ID: 001
Revises:
Create Date: 2025-01-XX

Creates initial database schema from 001_initial_schema.sql
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Users table
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("pwd_hash", sa.String(255), nullable=True),
        sa.Column("role", sa.String(50), server_default="user"),
        sa.Column("user_type", sa.String(50), server_default="local"),
        sa.Column("language", sa.String(10), server_default="en"),
        sa.Column("timezone", sa.String(50), server_default="UTC"),
        sa.Column("enabled", sa.Boolean(), server_default="1"),
        sa.Column("external_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("username"),
        sa.UniqueConstraint("email"),
    )
    op.create_index("idx_users_username", "users", ["username"])
    op.create_index("idx_users_email", "users", ["email"])

    # Groups table
    op.create_table(
        "groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default="1"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Group members table
    op.create_table(
        "group_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(50), server_default="member"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "user_id"),
    )

    # Expert configurations table
    op.create_table(
        "expert_configs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("llm_provider", sa.String(100), nullable=False),
        sa.Column("llm_model", sa.String(255), nullable=False),
        sa.Column("llm_params_json", sa.Text(), nullable=True),
        sa.Column("prompt_template", sa.Text(), nullable=True),
        sa.Column("tools_json", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default="1"),
        sa.Column("access_control_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Sessions table
    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("expert_config_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(255), nullable=True),
        sa.Column("status", sa.String(50), server_default="active"),
        sa.Column("context_window", sa.Integer(), server_default="4096"),
        sa.Column("history_retention_days", sa.Integer(), server_default="30"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["expert_config_id"], ["expert_configs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_sessions_user_id", "sessions", ["user_id"])
    op.create_index("idx_sessions_expert_config_id", "sessions", ["expert_config_id"])

    # Messages table
    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("embedding_id", sa.String(255), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_messages_session_id", "messages", ["session_id"])
    op.create_index("idx_messages_timestamp", "messages", ["timestamp"])

    # Vector stores table
    op.create_table(
        "vector_stores",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(100), nullable=False),
        sa.Column("config_json", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), server_default="1"),
        sa.Column("access_control_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )

    # Session vector store mappings table
    op.create_table(
        "session_vector_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("vector_store_id", sa.Integer(), nullable=False),
        sa.Column("access_mode", sa.String(50), server_default="read"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vector_store_id"], ["vector_stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", "vector_store_id"),
    )

    # Audit events table
    op.create_table(
        "audit_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(100), nullable=False),
        sa.Column("ref", sa.String(255), nullable=True),
        sa.Column("actor", sa.String(255), nullable=True),
        sa.Column("data", sa.Text(), nullable=True),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_audit_events_created_at", "audit_events", ["created_at"])
    op.create_index("idx_audit_events_kind", "audit_events", ["kind"])

    # External identities table
    op.create_table(
        "external_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("refresh_token", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "provider_user_id"),
    )


def downgrade() -> None:
    op.drop_table("external_identities")
    op.drop_table("audit_events")
    op.drop_table("session_vector_mappings")
    op.drop_table("vector_stores")
    op.drop_table("messages")
    op.drop_table("sessions")
    op.drop_table("expert_configs")
    op.drop_table("group_members")
    op.drop_table("groups")
    op.drop_table("users")
