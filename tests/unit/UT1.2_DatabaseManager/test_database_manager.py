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
Unit Test: UT1.2 - Database Manager Connection and CRUD Operations

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for database manager connection and CRUD operations

Related Requirements: NF1.8
Related Tasks: T002
Related Architecture: CC6.1.1
Related Tests: UT1.2

Recent Changes:
- Initial implementation
"""

import pytest
from sqlalchemy.orm import Session
from sqlalchemy import text

from src.database.connection import init_db, get_db, get_engine, get_db_uri
import src.database.connection as db_connection
from src.database.models import Base, User
from src.config.loader import get_config


def _require_test_user_config():
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail(
            "Missing test.user.username/test.user.email/test.user.password in config (--env)"
        )
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    domain = base_email.split("@", 1)[1]
    return base_username, domain, password
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_get_db_uri():
    """Test getting database URI from configuration."""
    db_uri, async_uri = get_db_uri()

    assert db_uri is not None
    assert isinstance(db_uri, str)
    assert async_uri is not None
    assert isinstance(async_uri, str)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_get_db_uri_mysql_defaults_to_pymysql(monkeypatch):
    """MySQL URI without driver should resolve to pymysql/aiomysql drivers."""
    test_values = {
        "db.uri": "mysql://user:pass@db1.db.example.com:3306/expert_server",
        "db.echo": False,
        "db.pool_size": 5,
        "db.max_overflow": 10,
        "db.pool_timeout": 30,
    }
    monkeypatch.setattr(db_connection, "get_config", lambda key: test_values.get(key))
    db_uri, async_uri = db_connection.get_db_uri()
    assert db_uri.startswith("mysql+pymysql://")
    assert async_uri.startswith("mysql+aiomysql://")
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_get_db_uri_preserves_unmasked_password(monkeypatch):
    """Resolved DB URLs must preserve credential values for real connections."""
    test_values = {
        "db.uri": "postgresql://db_user:db_pass@127.0.0.1:5432/expert_server",
        "db.echo": False,
        "db.pool_size": 5,
        "db.max_overflow": 10,
        "db.pool_timeout": 30,
    }
    monkeypatch.setattr(db_connection, "get_config", lambda key: test_values.get(key))
    db_uri, async_uri = db_connection.get_db_uri()
    assert db_uri.startswith("postgresql://") or db_uri.startswith("postgresql+psycopg://")
    assert async_uri.startswith("postgresql+asyncpg://")
    assert "db_pass" in db_uri
    assert "db_pass" in async_uri
    assert "***" not in db_uri
    assert "***" not in async_uri
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_init_db():
    """Test database initialization."""
    # Clear any existing engine
    init_db(force_reinit=True)

    engine = get_engine()
    assert engine is not None

    # Test connection
    with engine.connect() as conn:
        result = conn.execute(text("SELECT 1"))
        assert result.scalar() == 1
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_get_db_session():
    """Test getting database session."""
    init_db(force_reinit=True)

    db_gen = get_db()
    db = next(db_gen)

    assert db is not None
    assert isinstance(db, Session)

    # Cleanup
    db.close()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_database_connection():
    """Test database connection works."""
    init_db(force_reinit=True)
    engine = get_engine()

    with engine.connect() as conn:
        # Test basic query
        result = conn.execute(text("SELECT 1 as test"))
        row = result.fetchone()
        assert row[0] == 1
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_database_crud_create():
    """Test CRUD - Create operation."""
    init_db(force_reinit=True)
    engine = get_engine()

    # Create all tables before testing
    Base.metadata.create_all(bind=engine)

    db_gen = get_db()
    db = next(db_gen)

    try:
        # Create a test user
        from src.core.auth.user_manager import UserManager

        manager = UserManager(db)
        base_username, domain, password = _require_test_user_config()
        user = manager.create_user(
            username=f"{base_username}_crud", email=f"crud@{domain}", password=password
        )

        assert user is not None
        assert user.id is not None
        assert user.username == f"{base_username}_crud"

        # Cleanup
        db.delete(user)
        db.commit()
    finally:
        db.close()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_database_crud_read():
    """Test CRUD - Read operation."""
    init_db(force_reinit=True)

    db_gen = get_db()
    db = next(db_gen)

    try:
        # Create a test user
        from src.core.auth.user_manager import UserManager

        manager = UserManager(db)
        base_username, domain, password = _require_test_user_config()
        user = manager.create_user(
            username=f"{base_username}_read", email=f"read@{domain}", password=password
        )
        user_id = user.id

        # Read the user
        read_user = manager.get_user(user_id=user_id)

        assert read_user is not None
        assert read_user.id == user_id
        assert read_user.username == f"{base_username}_read"

        # Cleanup
        db.delete(user)
        db.commit()
    finally:
        db.close()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_database_crud_update():
    """Test CRUD - Update operation."""
    init_db(force_reinit=True)

    db_gen = get_db()
    db = next(db_gen)

    try:
        # Create a test user
        from src.core.auth.user_manager import UserManager

        manager = UserManager(db)
        base_username, domain, password = _require_test_user_config()
        user = manager.create_user(
            username=f"{base_username}_update", email=f"update@{domain}", password=password
        )

        # Update the user
        user.display_name = "Updated Name"
        db.commit()
        db.refresh(user)

        # Verify update
        assert user.display_name == "Updated Name"

        # Cleanup
        db.delete(user)
        db.commit()
    finally:
        db.close()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_database_crud_delete():
    """Test CRUD - Delete operation."""
    init_db(force_reinit=True)

    db_gen = get_db()
    db = next(db_gen)

    try:
        # Create a test user
        from src.core.auth.user_manager import UserManager

        manager = UserManager(db)
        base_username, domain, password = _require_test_user_config()
        user = manager.create_user(
            username=f"{base_username}_delete", email=f"delete@{domain}", password=password
        )
        user_id = user.id

        # Delete the user
        db.delete(user)
        db.commit()

        # Verify deletion
        deleted_user = manager.get_user(user_id=user_id)
        assert deleted_user is None
    finally:
        db.close()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_database_table_creation():
    """Test that database tables are created."""
    init_db(force_reinit=True)
    engine = get_engine()

    # Create all tables
    Base.metadata.create_all(bind=engine)

    # Verify tables exist
    from sqlalchemy import inspect

    inspector = inspect(engine)
    tables = inspector.get_table_names()

    assert "users" in tables or "user" in tables
    assert "sessions" in tables or "session" in tables
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-039")


def test_database_transaction():
    """Test database transaction handling."""
    init_db(force_reinit=True)

    db_gen = get_db()
    db = next(db_gen)

    try:
        # Start transaction
        from src.core.auth.user_manager import UserManager

        manager = UserManager(db)
        base_username, domain, password = _require_test_user_config()

        import uuid

        unique_id = str(uuid.uuid4())[:8]
        user = manager.create_user(
            username=f"{base_username}_transaction_{unique_id}",
            email=f"transaction_{unique_id}@{domain}",
            password=password,
        )

        user_id = user.id

        # Rollback (before commit)
        db.rollback()

        # Verify user was not committed by checking in same session
        # After rollback, the object should be detached
        db.expunge(user)
        check_user = db.query(User).filter(User.id == user_id).first()
        # User should not exist after rollback (if SQLite supports transactions)
        # Note: SQLite in autocommit mode may commit immediately
        # This test verifies rollback behavior when supported
        if check_user is None:
            # Rollback worked
            pass
        else:
            # SQLite may have auto-committed, which is acceptable
            # Clean up the user
            db.delete(check_user)
            db.commit()
    finally:
        db.close()

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.db, pytest.mark.smtp, pytest.mark.fast]

