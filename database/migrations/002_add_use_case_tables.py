"""Add tables for new use cases

Revision ID: 002
Revises: 001
Create Date: 2025-01-XX

Adds tables for:
- Channels (UC1.6)
- Jobs and call logs (UC1.8)
- Tools and external services (UC1.10, UC1.13)
- API keys (UC1.11)
- Multimedia files (UC1.7)
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None

# Note: This migration depends on 001_initial_schema.py being applied first


def upgrade() -> None:
    # Channels table (UC1.6)
    op.create_table(
        "channels",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("expert_config_id", sa.Integer(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("context_type", sa.String(100), nullable=True),
        sa.Column("expected_outcomes", sa.Text(), nullable=True),
        sa.Column("history_scope", sa.String(50), nullable=True),  # user, channel, session
        sa.Column("history_limitation_json", sa.Text(), nullable=True),
        sa.Column("rerank_model", sa.String(255), nullable=True),
        sa.Column("enabled", sa.Boolean(), default=True),
        sa.Column("access_control_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Timestamp(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.Timestamp(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["expert_config_id"], ["expert_configs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_channels_name", "channels", ["name"])
    op.create_index("idx_channels_expert_config_id", "channels", ["expert_config_id"])

    # Channel vector mappings (UC1.6)
    op.create_table(
        "channel_vector_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("vector_store_id", sa.Integer(), nullable=False),
        sa.Column("access_mode", sa.String(50), default="read"),
        sa.Column("priority", sa.Integer(), default=0),
        sa.Column("created_at", sa.Timestamp(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vector_store_id"], ["vector_stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_id", "vector_store_id"),
    )

    # Channel history mappings (UC1.6)
    op.create_table(
        "channel_history_mappings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("history_scope", sa.String(50), nullable=False),
        sa.Column("history_key", sa.String(255), nullable=True),
        sa.Column("limitation_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Timestamp(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )

    # Jobs table (UC1.8)
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_type", sa.String(100), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("channel_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(50), default="pending"),
        sa.Column("prompt_sent", sa.Text(), nullable=True),
        sa.Column("response_received", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("performance_metrics_json", sa.Text(), nullable=True),
        sa.Column("vector_context_json", sa.Text(), nullable=True),
        sa.Column("tool_calls_json", sa.Text(), nullable=True),
        sa.Column("error_info_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Timestamp(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.Timestamp(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("completed_at", sa.Timestamp(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_jobs_session_id", "jobs", ["session_id"])
    op.create_index("idx_jobs_channel_id", "jobs", ["channel_id"])
    op.create_index("idx_jobs_user_id", "jobs", ["user_id"])
    op.create_index("idx_jobs_status", "jobs", ["status"])
    op.create_index("idx_jobs_created_at", "jobs", ["created_at"])

    # Call logs table (UC1.8)
    op.create_table(
        "call_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("llm_provider", sa.String(100), nullable=True),
        sa.Column("llm_model", sa.String(255), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("created_at", sa.Timestamp(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_call_logs_job_id", "call_logs", ["job_id"])

    # Tools table (UC1.10)
    op.create_table(
        "tools",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("input_schema_json", sa.Text(), nullable=True),
        sa.Column("output_schema_json", sa.Text(), nullable=True),
        sa.Column("auth_requirements_json", sa.Text(), nullable=True),
        sa.Column("usage_guidelines", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), default=True),
        sa.Column("created_at", sa.Timestamp(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.Timestamp(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )

    # Channel tools table (UC1.10)
    op.create_table(
        "channel_tools",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("tool_id", sa.Integer(), nullable=False),
        sa.Column("configuration_json", sa.Text(), nullable=True),
        sa.Column("priority", sa.Integer(), default=0),
        sa.Column("enabled", sa.Boolean(), default=True),
        sa.Column("created_at", sa.Timestamp(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tool_id"], ["tools.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_id", "tool_id"),
    )

    # External services table (UC1.13)
    op.create_table(
        "external_services",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("type", sa.String(100), nullable=False),  # mcp, a2a
        sa.Column("endpoint_url", sa.String(500), nullable=False),
        sa.Column("auth_config_json", sa.Text(), nullable=True),
        sa.Column("health_status", sa.String(50), default="unknown"),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("usage_statistics_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Timestamp(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.Timestamp(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.PrimaryKeyConstraint("id"),
    )

    # Channel external services table (UC1.13)
    op.create_table(
        "channel_external_services",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("channel_id", sa.Integer(), nullable=False),
        sa.Column("external_service_id", sa.Integer(), nullable=False),
        sa.Column("access_mode", sa.String(50), default="read"),
        sa.Column("configuration_json", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Boolean(), default=True),
        sa.Column("created_at", sa.Timestamp(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["channel_id"], ["channels.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["external_service_id"], ["external_services.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("channel_id", "external_service_id"),
    )

    # API keys table (UC1.11)
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key_hash", sa.String(255), nullable=False, unique=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("scopes_json", sa.Text(), nullable=True),
        sa.Column("read_channels", sa.Boolean(), default=False),
        sa.Column("write_channels", sa.Boolean(), default=False),
        sa.Column("read_logs", sa.Boolean(), default=False),
        sa.Column("write_logs", sa.Boolean(), default=False),
        sa.Column("read_histories", sa.Boolean(), default=False),
        sa.Column("write_histories", sa.Boolean(), default=False),
        sa.Column("expires_at", sa.Timestamp(), nullable=True),
        sa.Column("revoked", sa.Boolean(), default=False),
        sa.Column("created_at", sa.Timestamp(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.Timestamp(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("last_used_at", sa.Timestamp(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_api_keys_key_hash", "api_keys", ["key_hash"])
    op.create_index("idx_api_keys_user_id", "api_keys", ["user_id"])
    op.create_index("idx_api_keys_group_id", "api_keys", ["group_id"])

    # Multimedia files table (UC1.7)
    op.create_table(
        "multimedia_files",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=True),
        sa.Column("job_id", sa.Integer(), nullable=True),
        sa.Column("file_type", sa.String(50), nullable=False),  # image, audio, video
        sa.Column("file_path", sa.String(500), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("mime_type", sa.String(100), nullable=True),
        sa.Column("processing_status", sa.String(50), default="pending"),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Timestamp(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("processed_at", sa.Timestamp(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_multimedia_files_session_id", "multimedia_files", ["session_id"])
    op.create_index("idx_multimedia_files_job_id", "multimedia_files", ["job_id"])
    op.create_index("idx_multimedia_files_file_type", "multimedia_files", ["file_type"])


def downgrade() -> None:
    op.drop_table("multimedia_files")
    op.drop_table("api_keys")
    op.drop_table("channel_external_services")
    op.drop_table("external_services")
    op.drop_table("channel_tools")
    op.drop_table("tools")
    op.drop_table("call_logs")
    op.drop_table("jobs")
    op.drop_table("channel_history_mappings")
    op.drop_table("channel_vector_mappings")
    op.drop_table("channels")
