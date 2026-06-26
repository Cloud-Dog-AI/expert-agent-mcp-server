import pytest
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
System Test: ST1.7 - Database Schema Creation and Migration

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for database schema creation and migration

Related Requirements: NF1.8
Related Tasks: T002
Related Architecture: CC6.1.1
Related Tests: ST1.7

Recent Changes:
- Initial implementation
"""

from sqlalchemy import inspect
from src.database.connection import get_engine, init_db
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_database_initialization():
    """Test database initialization."""
    init_db()
    engine = get_engine()
    assert engine is not None
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_schema_creation(db_session):
    """Test that all tables are created."""
    inspector = inspect(get_engine())
    tables = inspector.get_table_names()

    # Check for core tables
    required_tables = [
        "users",
        "groups",
        "group_members",
        "expert_configs",
        "sessions",
        "messages",
        "vector_stores",
        "audit_events",
    ]

    for table in required_tables:
        assert table in tables, f"Table {table} not found in database"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_user_table_schema(db_session):
    """Test user table schema."""
    inspector = inspect(get_engine())
    columns = {col["name"]: col for col in inspector.get_columns("users")}

    # Check required columns
    assert "id" in columns
    assert "username" in columns
    assert "email" in columns
    assert "pwd_hash" in columns
    assert "role" in columns
    assert "enabled" in columns
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_expert_config_table_schema(db_session):
    """Test expert_configs table schema."""
    inspector = inspect(get_engine())
    columns = {col["name"]: col for col in inspector.get_columns("expert_configs")}

    # Check required columns
    assert "id" in columns
    assert "name" in columns
    assert "title" in columns
    assert "llm_provider" in columns
    assert "llm_model" in columns
    assert "enabled" in columns
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_session_table_schema(db_session):
    """Test sessions table schema."""
    inspector = inspect(get_engine())
    columns = {col["name"]: col for col in inspector.get_columns("sessions")}

    # Check required columns
    assert "id" in columns
    assert "user_id" in columns
    assert "expert_config_id" in columns
    assert "status" in columns
    assert "context_window" in columns
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_foreign_key_constraints(db_session):
    """Test foreign key constraints."""
    inspector = inspect(get_engine())

    # Check foreign keys in sessions table
    fks = inspector.get_foreign_keys("sessions")
    fk_columns = {fk["constrained_columns"][0]: fk["referred_table"] for fk in fks}

    assert "user_id" in fk_columns
    assert fk_columns["user_id"] == "users"
    assert "expert_config_id" in fk_columns
    assert fk_columns["expert_config_id"] == "expert_configs"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_indexes_creation(db_session):
    """Test that indexes are created."""
    inspector = inspect(get_engine())

    # Check indexes on users table
    indexes = inspector.get_indexes("users")
    index_names = [idx["name"] for idx in indexes]

    # Should have indexes on username and email
    assert any("username" in str(idx) for idx in indexes) or any(
        "ix_users_username" in name for name in index_names
    )
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_migration_script_exists():
    """Test that migration scripts exist."""
    from pathlib import Path

    migrations_dir = Path("database/migrations/versions")

    if migrations_dir.exists():
        migration_files = list(migrations_dir.glob("*.py"))
        assert len(migration_files) > 0, "No migration scripts found"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_alembic_configuration():
    """Test Alembic configuration."""
    from pathlib import Path

    alembic_ini = Path("alembic.ini")
    assert alembic_ini.exists(), "alembic.ini not found"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.vdb, pytest.mark.db, pytest.mark.smtp, pytest.mark.slow, pytest.mark.heavy]

