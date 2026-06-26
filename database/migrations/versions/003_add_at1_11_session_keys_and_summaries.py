"""Add session keys, history keys, and summaries for AT1.11

Revision ID: 003
Revises: 002
Create Date: 2025-01-XX

Adds:
- session_key, history_key to sessions table
- shared_with_user_ids, shared_with_group_ids to sessions table
- session_key_expires_at to sessions table
- summaries table for context summarization
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add session key and history key fields to sessions table
    op.add_column("sessions", sa.Column("session_key", sa.String(255), nullable=True))
    op.add_column("sessions", sa.Column("history_key", sa.String(255), nullable=True))
    op.add_column("sessions", sa.Column("shared_with_user_ids", sa.Text(), nullable=True))
    op.add_column("sessions", sa.Column("shared_with_group_ids", sa.Text(), nullable=True))
    op.add_column("sessions", sa.Column("session_key_expires_at", sa.DateTime(), nullable=True))

    # Create indexes for session_key and history_key
    op.create_index("idx_sessions_session_key", "sessions", ["session_key"], unique=True)
    op.create_index("idx_sessions_history_key", "sessions", ["history_key"])

    # Create summaries table
    op.create_table(
        "summaries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("session_id", sa.Integer(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=False),
        sa.Column("original_message_count", sa.Integer(), nullable=False),
        sa.Column("preserved_message_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_summaries_session_id", "summaries", ["session_id"])


def downgrade() -> None:
    # Drop summaries table
    op.drop_index("idx_summaries_session_id", table_name="summaries")
    op.drop_table("summaries")

    # Drop indexes
    op.drop_index("idx_sessions_history_key", table_name="sessions")
    op.drop_index("idx_sessions_session_key", table_name="sessions")

    # Remove columns from sessions table
    op.drop_column("sessions", "session_key_expires_at")
    op.drop_column("sessions", "shared_with_group_ids")
    op.drop_column("sessions", "shared_with_user_ids")
    op.drop_column("sessions", "history_key")
    op.drop_column("sessions", "session_key")
