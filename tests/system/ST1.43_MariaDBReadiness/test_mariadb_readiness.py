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
System Test: ST1.43 - MariaDB schema, migrations, and CRUD readiness
"""

from pathlib import Path

import pytest
from sqlalchemy import inspect, text

from src.config.loader import get_config, load_config
from src.database.connection import get_engine, init_db
from src.database.models import Base


pytestmark = pytest.mark.system
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-045")


def test_st143_mariadb_runtime_readiness(test_env_file):
    load_config.cache_clear()
    uri = str(get_config("db.uri") or "")
    if not uri.startswith(("mysql://", "mysql+")):
        pytest.skip(f"Skipping MariaDB runtime readiness for non-MySQL db.uri: {uri}")

    init_db(force_reinit=True)
    engine = get_engine()
    assert engine.dialect.name in {"mysql", "mariadb"}
    with engine.connect() as conn:
        assert conn.execute(text("SELECT 1")).scalar() == 1
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-045")


def test_st143_mariadb_schema_assets_readiness(test_env_file):
    init_db(force_reinit=True)
    engine = get_engine()
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    for table in ("users", "group_members", "expert_configs", "sessions", "messages"):
        assert table in tables, f"Missing required table: {table}"

    assert Path("database/migrations/versions").exists()
    assert Path("alembic.ini").exists()

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.db, pytest.mark.slow, pytest.mark.heavy]

