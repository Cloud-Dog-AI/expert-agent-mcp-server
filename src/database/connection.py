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
Database Connection Management

License: Apache 2.0
Ownership: Cloud Dog
Description: Database connection pooling and session management via cloud_dog_db

Related Requirements: NF1.8
Related Tasks: T002
Related Architecture: CC6.1.1
Related Tests: ST1.7

Recent Changes:
- Migrated to cloud_dog_db engine/session factories (W23A-P2)
"""

from __future__ import annotations

import os
from typing import AsyncGenerator, Generator

from sqlalchemy import Engine, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker

from alembic import command
from alembic.config import Config as AlembicConfig
from cloud_dog_db import (
    DatabaseSettings,
    build_async_engine,
    build_sync_engine,
)

from src.config.loader import get_config
from src.utils.logger import get_logger

from cloud_dog_storage.backends.local import LocalStorage as _PlatformLocalStorage

_fs = _PlatformLocalStorage(root_path="/")

logger = get_logger(__name__)

# Global engine and session factories
_engine: Engine | None = None
_async_engine: AsyncEngine | None = None
_SessionLocal: sessionmaker[Session] | None = None
_AsyncSessionLocal: async_sessionmaker[AsyncSession] | None = None
_migrations_applied = False


def _to_bool(v, default: bool = False) -> bool:
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, str):
        return v.lower() in ("true", "1", "yes")
    return bool(v)


def _to_int(v, default: int) -> int:
    try:
        return default if v is None else int(v)
    except (ValueError, TypeError):
        return default


def _normalise_db_uri(raw_uri: str) -> str:
    """Normalise DB URIs so MySQL defaults to the supported PyMySQL driver."""
    uri = raw_uri.strip()
    lower_uri = uri.lower()
    if lower_uri.startswith("mysql://"):
        return f"mysql+pymysql://{uri[len('mysql://') :]}"
    if lower_uri.startswith("mariadb://"):
        return f"mysql+pymysql://{uri[len('mariadb://') :]}"
    return uri


def _build_settings() -> DatabaseSettings:
    """Build DatabaseSettings from the project's config hierarchy."""
    raw_uri = get_config("db.uri")
    if not raw_uri:
        raise RuntimeError("db.uri not configured (set via env/config hierarchy)")
    uri = _normalise_db_uri(str(raw_uri))

    echo = _to_bool(get_config("db.echo"), default=False)
    pool_size = _to_int(get_config("db.pool_size"), 20)
    max_overflow = _to_int(get_config("db.max_overflow"), 40)
    pool_timeout = _to_int(get_config("db.pool_timeout"), 60)

    return DatabaseSettings(
        url=uri,
        echo=echo,
        pool_size=pool_size,
        max_overflow=max_overflow,
        pool_timeout_seconds=pool_timeout,
    )


def get_db_uri() -> tuple[str, str]:
    """Get database URI pair (sync, async) from configuration."""
    settings = _build_settings()
    sync_url = settings.to_sync_url()
    async_url = settings.to_async_url()

    # Defensive unmasking: keep real credentials for DB drivers even if an
    # upstream URL formatter emits masked password placeholders.
    if "***" in sync_url or "***" in async_url:
        raw_uri = _normalise_db_uri(str(get_config("db.uri") or ""))
        if raw_uri and "***" not in raw_uri:
            parsed = make_url(raw_uri)
            sync_url = parsed.render_as_string(hide_password=False)

            async_driver = parsed.drivername
            if async_driver.startswith("sqlite+"):
                async_driver = "sqlite+aiosqlite"
            elif async_driver.startswith("mysql+"):
                async_driver = "mysql+aiomysql"
            elif async_driver.startswith("postgresql+"):
                async_driver = "postgresql+asyncpg"
            elif async_driver == "sqlite":
                async_driver = "sqlite+aiosqlite"
            elif async_driver == "mysql":
                async_driver = "mysql+aiomysql"
            elif async_driver == "postgresql":
                async_driver = "postgresql+asyncpg"
            async_url = parsed.set(drivername=async_driver).render_as_string(hide_password=False)

    return sync_url, async_url


def apply_migrations(force: bool = False) -> None:
    """Apply Alembic migrations to the configured database."""
    global _migrations_applied

    if _migrations_applied and not force:
        return

    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    alembic_ini = os.path.join(repo_root, "alembic.ini")
    if _fs.stat(alembic_ini) is None:
        raise RuntimeError(f"Alembic config not found: {alembic_ini}")

    cfg = AlembicConfig(alembic_ini)
    migration_paths = [
        os.path.join(repo_root, "database", "migrations"),
        os.path.join(repo_root, "migrations"),
    ]
    script_location = next((path for path in migration_paths if _fs.stat(path) is not None), None)
    if script_location is None:
        checked = ", ".join(migration_paths)
        raise RuntimeError(f"Alembic migrations not found. Checked: {checked}")
    cfg.set_main_option("script_location", script_location)
    sync_url, _ = get_db_uri()
    cfg.set_main_option("sqlalchemy.url", sync_url)

    bootstrap_engine = build_sync_engine(DatabaseSettings(url=sync_url))
    try:
        inspector = inspect(bootstrap_engine)
        tables = set(inspector.get_table_names())
        if "alembic_version" not in tables:
            session_columns = (
                {col["name"] for col in inspector.get_columns("sessions")}
                if "sessions" in tables
                else set()
            )
            audit_columns = (
                {col["name"] for col in inspector.get_columns("audit_events")}
                if "audit_events" in tables
                else set()
            )
            orchestration_tables = {
                "service_bindings",
                "sub_expert_bindings",
                "prompt_templates",
                "expert_prompt_assignments",
                "service_invocation_logs",
            }

            if "parent_session_id" in session_columns and orchestration_tables.issubset(tables):
                stamp_revision = "005" if "signature" in audit_columns else "004"
                command.stamp(cfg, stamp_revision)
                logger.info(f"Stamped existing database schema to Alembic revision {stamp_revision}")
            elif {
                "session_key",
                "history_key",
                "shared_with_user_ids",
                "shared_with_group_ids",
                "session_key_expires_at",
            }.issubset(session_columns) and "summaries" in tables:
                command.stamp(cfg, "003")
    finally:
        bootstrap_engine.dispose()

    command.upgrade(cfg, "head")
    _migrations_applied = True
    logger.info("Database migrations applied to head")


def _ensure_idam_role_tables(engine: Engine) -> None:
    """Create the canonical cloud_dog_idam role tables (W28A-876 Gate 4b).

    Ensures the PS-71 §IW3A Roles page (/api/v1/admin/roles) is backed by the
    shared ``SqlAlchemyRoleStore``. Only the role-related tables are created
    here; the other cloud_dog_idam ORM tables are not part of this service's
    schema and are intentionally excluded from the targeted ``create_all``.
    """
    from cloud_dog_idam.storage.sqlalchemy.models import (
        PermissionORM as _PermissionORM,
        RoleORM as _RoleORM,
        RolePermissionORM as _RolePermissionORM,
    )

    _RoleORM.metadata.create_all(
        bind=engine,
        checkfirst=True,
        tables=[
            _RoleORM.__table__,
            _PermissionORM.__table__,
            _RolePermissionORM.__table__,
        ],
    )


def init_db(force_reinit: bool = False) -> None:
    """Initialize database connection."""
    global _engine, _async_engine, _SessionLocal, _AsyncSessionLocal

    if _engine is not None and not force_reinit:
        return

    # Reset globals
    _engine = None
    _async_engine = None
    _SessionLocal = None
    _AsyncSessionLocal = None

    settings = _build_settings()

    _engine = build_sync_engine(settings)
    _ensure_idam_role_tables(_engine)
    _SessionLocal = sessionmaker(
        bind=_engine,
        autocommit=False,
        autoflush=False,
        expire_on_commit=False,
    )

    _async_engine = build_async_engine(settings)
    _AsyncSessionLocal = async_sessionmaker(
        bind=_async_engine,
        expire_on_commit=False,
    )

    display_url = str(_engine.url)
    if "@" in display_url:
        display_url = display_url.split("@", 1)[-1]
    logger.info(f"Database initialized: {display_url}")


def get_db() -> Generator[Session, None, None]:
    """Get database session (sync).  Caller is responsible for commit/rollback."""
    if _SessionLocal is None:
        init_db()
    assert _SessionLocal is not None

    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Get database session (async).  Caller is responsible for commit/rollback."""
    if _AsyncSessionLocal is None:
        init_db()
    assert _AsyncSessionLocal is not None

    async with _AsyncSessionLocal() as session:
        yield session


def get_engine() -> Engine:
    """Get sync database engine."""
    if _engine is None:
        init_db()
    assert _engine is not None
    return _engine


def get_async_engine() -> AsyncEngine:
    """Get async database engine."""
    if _async_engine is None:
        init_db()
    assert _async_engine is not None
    return _async_engine
