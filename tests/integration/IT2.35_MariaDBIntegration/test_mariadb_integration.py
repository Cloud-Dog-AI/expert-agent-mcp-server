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
Integration Test: IT2.35 - MariaDB integration (schema + CRUD + migrations)
"""

import uuid
from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from src.config.loader import get_config, load_config
from src.core.auth.user_manager import UserManager
from src.database.connection import get_db, get_engine, init_db
from src.database.models import Base


pytestmark = pytest.mark.integration


def _unique() -> str:
    return uuid.uuid4().hex[:8]
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-047")


def test_it235_mariadb_uri_and_connectivity(test_env_file):
    load_config.cache_clear()
    uri = str(get_config("db.uri") or "")
    if not uri.startswith("mysql://"):
        pytest.fail(f"Expected mysql:// db.uri for MariaDB env, got: {uri}")

    init_db(force_reinit=True)
    engine = get_engine()
    assert engine.dialect.name in {"mysql", "mariadb"}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-047")


def test_it235_mariadb_schema_and_crud(test_env_file):
    init_db(force_reinit=True)
    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for table in ("users", "groups", "expert_configs", "sessions", "messages"):
        assert table in tables, f"Missing table: {table}"

    db = next(get_db())
    try:
        manager = UserManager(db)
        suffix = _unique()
        password = get_config("test.user.password")
        if not password:
            pytest.fail("test.user.password not configured")
        user = manager.create_user(
            username=f"it235_{suffix}",
            email=f"it235_{suffix}@example.com",
            password=str(password),
        )
        fetched = manager.get_user(user_id=user.id)
        assert fetched is not None
        assert fetched.username == f"it235_{suffix}"
        db.delete(user)
        db.commit()
        assert manager.get_user(user_id=user.id) is None
    finally:
        db.close()
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-047")


def test_it235_mariadb_migration_assets_present(test_env_file):
    versions = Path("database/migrations/versions")
    assert versions.exists(), "database/migrations/versions not found"
    migration_files = sorted(p for p in versions.glob("*.py") if p.name != "__init__.py")
    assert migration_files, "No migration scripts found"
    assert Path("alembic.ini").exists(), "alembic.ini not found"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.db, pytest.mark.smtp, pytest.mark.heavy]

