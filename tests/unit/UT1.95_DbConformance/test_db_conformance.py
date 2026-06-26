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
UT1.95 — Database Conformance Tests (W23A-P2)

Verifies that the expert-agent ORM models conform to cloud_dog_db standards:
- PlatformBase is the single declarative base
- Naming convention applied to metadata
- DateTime columns use timezone=True
- FK constraints enforced via PRAGMA foreign_keys=ON
"""

from __future__ import annotations
import pytest

from sqlalchemy import DateTime, inspect, text

from src.database.models import Base
from src.database import models_channel_extensions  # noqa: F401
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


def test_base_is_platform_base():
    """QG-DB-1: All models use PlatformBase."""
    assert Base.__name__ == "PlatformBase"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


def test_naming_convention_present():
    """QG-DB-6: Naming convention attached to metadata."""
    nc = Base.metadata.naming_convention
    assert nc is not None
    assert "ix" in nc
    assert "uq" in nc
    assert "fk" in nc
    assert "pk" in nc
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


def test_all_datetime_columns_have_timezone():
    """QG-DB-5: Every DateTime column in the schema has timezone=True."""
    violations = []
    for table in Base.metadata.sorted_tables:
        # Skip test-only tables from platform-db unit tests
        if table.name.startswith("test_"):
            continue
        for col in table.columns:
            if isinstance(col.type, DateTime) and not col.type.timezone:
                violations.append(f"{table.name}.{col.name}")
    assert violations == [], f"DateTime columns missing timezone=True: {violations}"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


def test_expected_tables_registered():
    """All 19 expected tables are registered in PlatformBase.metadata."""
    expected = {
        "users",
        "groups",
        "group_members",
        "expert_configs",
        "sessions",
        "summaries",
        "messages",
        "vector_stores",
        "channels",
        "jobs",
        "call_logs",
        "tools",
        "api_keys",
        "external_services",
        "multimedia_files",
        "audit_events",
        "knowledge_versions",
        "knowledge_entries",
        "channel_vector_store_mappings",
    }
    actual = {t.name for t in Base.metadata.sorted_tables if not t.name.startswith("test_")}
    missing = expected - actual
    assert missing == set(), f"Missing tables: {missing}"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


def test_sqlite_pragma_foreign_keys_on():
    """QG-DB-6: SQLite engines from cloud_dog_db enforce PRAGMA foreign_keys=ON."""
    from cloud_dog_db import DatabaseSettings, build_sync_engine

    settings = DatabaseSettings(dialect="sqlite", database=":memory:")
    engine = build_sync_engine(settings)
    with engine.connect() as conn:
        result = conn.execute(text("PRAGMA foreign_keys"))
        row = result.fetchone()
        assert row is not None and row[0] == 1
    engine.dispose()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


def test_create_all_tables_in_memory():
    """Smoke test: create all tables in an in-memory SQLite database."""
    from cloud_dog_db import DatabaseSettings, build_sync_engine

    settings = DatabaseSettings(dialect="sqlite", database=":memory:")
    engine = build_sync_engine(settings)
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    assert "users" in tables
    assert "sessions" in tables
    assert "channels" in tables
    assert "channel_vector_store_mappings" in tables
    engine.dispose()

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.vdb, pytest.mark.db, pytest.mark.fast]

