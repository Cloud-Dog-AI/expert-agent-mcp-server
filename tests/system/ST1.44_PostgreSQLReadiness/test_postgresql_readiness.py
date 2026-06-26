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
System Test: ST1.44 - PostgreSQL schema, migrations, and CRUD readiness
"""

from pathlib import Path
import os
import time

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import OperationalError

from src.config.loader import get_config, load_config
from src.database.connection import get_engine, init_db
from src.database.models import Base


pytestmark = pytest.mark.system


def _postgres_candidate_uris() -> list[str]:
    candidates: list[str] = []
    primary = str(get_config("db.uri") or "")
    fallback = str(get_config("test.vector_stores.pgvector.database_uri") or "")
    for uri in (primary, fallback):
        if uri.startswith(("postgresql://", "postgresql+")) and uri not in candidates:
            candidates.append(uri)
    return candidates


def _with_postgres_engine(check):
    key = "CLOUD_DOG__EXPERT__DB__URI"
    previous = os.environ.get(key)
    last_error = None
    try:
        for uri in _postgres_candidate_uris():
            os.environ[key] = uri
            load_config.cache_clear()
            for attempt in range(4):
                init_db(force_reinit=True)
                engine = get_engine()
                try:
                    return check(engine)
                except OperationalError as exc:
                    engine.dispose()
                    message = str(exc).lower()
                    if "too many clients already" not in message:
                        raise
                    last_error = f"{uri}: {exc}"
                    time.sleep(2.0 * (attempt + 1))
                finally:
                    try:
                        engine.dispose()
                    except Exception:
                        pass

        pytest.fail(f"PostgreSQL readiness exhausted retries: {last_error}")
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous
        load_config.cache_clear()
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-045")


def test_st144_postgresql_runtime_readiness(test_env_file):
    load_config.cache_clear()
    uri = str(get_config("db.uri") or "")
    if not uri.startswith(("postgresql://", "postgresql+")):
        pytest.skip(f"Skipping PostgreSQL runtime readiness for non-PostgreSQL db.uri: {uri}")

    def check(engine):
        assert engine.dialect.name == "postgresql"
        with engine.connect() as conn:
            assert conn.execute(text("SELECT 1")).scalar() == 1

    _with_postgres_engine(check)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-045")


def test_st144_postgresql_schema_assets_readiness(test_env_file):
    def check(engine):
        Base.metadata.create_all(bind=engine)
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        for table in ("users", "group_members", "expert_configs", "sessions", "messages"):
            assert table in tables, f"Missing required table: {table}"

    _with_postgres_engine(check)

    assert Path("database/migrations/versions").exists()
    assert Path("alembic.ini").exists()

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.db, pytest.mark.slow, pytest.mark.heavy]
