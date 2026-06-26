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
Health and Status Routes

License: Apache 2.0
Ownership: Cloud Dog
Description: Health check and system status endpoints

Related Requirements: FR1.9
Related Tasks: T030
Related Architecture: CC1.1.1, MO1.1
Related Tests: ST1.1

Recent Changes:
- Initial implementation
- Expanded runtime status payload for UI Review #2 adoption
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from cloud_dog_storage.backends.local import LocalStorage as _PlatformLocalStorage

from src.config.loader import get_config
from src.database.connection import get_db
from src.database.models import Channel, ExpertConfig, Job, KnowledgeEntry, Session as SessionModel
from src.database.models import User
from src.servers.api.auth import verify_api_key
try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover - optional dependency in runtime environments
    psutil = None

router = APIRouter(tags=["health"])

# EA-03: resolve the displayed version from build metadata (build-info.json baked
# at image build) so the dashboard reflects the real build, not a hardcoded or
# stale config value. Falls back to config then the package literal.
_BUILD_INFO_FILE = Path("/app/build-info.json")


def _app_version() -> str:
    if _BUILD_INFO_FILE.exists():
        try:
            v = json.loads(_BUILD_INFO_FILE.read_text(encoding="utf-8")).get("version")
            if v:
                return str(v)
        except Exception:
            pass
    return get_config("app.version") or "0.1.1RC1"

_START_TIME = time.time()

# Root-scoped storage backend for disk metrics.
_fs = _PlatformLocalStorage(root_path="/")


def _safe_percent(numerator: float, denominator: float) -> float:
    if denominator <= 0:
        return 0.0
    return round((numerator / denominator) * 100.0, 2)


def _build_status_payload(db: Session) -> Dict[str, Any]:
    uptime_seconds = int(max(0, time.time() - _START_TIME))
    memory_mb = 0.0
    memory_percent = 0.0
    cpu_percent = 0.0

    if psutil is not None:
      process = psutil.Process()
      memory_mb = round(process.memory_info().rss / (1024 * 1024), 2)
      try:
          memory_percent = round(process.memory_percent(), 2)
      except Exception:
          virtual = psutil.virtual_memory()
          memory_percent = _safe_percent(process.memory_info().rss, float(virtual.total))
      cpu_percent = round(process.cpu_percent(interval=None), 2)

    disk_usage_fn = getattr(_fs, "disk_usage", None)
    if callable(disk_usage_fn):
        disk_total, disk_used, _disk_free = disk_usage_fn()
    else:
        fallback_usage = shutil.disk_usage("/")
        disk_total, disk_used, _disk_free = (
            fallback_usage.total,
            fallback_usage.used,
            fallback_usage.free,
        )
    disk_percent = _safe_percent(float(disk_used), float(disk_total))

    active_sessions = db.query(func.count(SessionModel.id)).filter(SessionModel.status == 'active').scalar() or 0
    expert_count = db.query(func.count(ExpertConfig.id)).scalar() or 0
    knowledge_item_count = db.query(func.count(KnowledgeEntry.id)).scalar() or 0
    channel_count = db.query(func.count(Channel.id)).scalar() or 0
    queue_depth = (
        db.query(func.count(Job.id))
        .filter(Job.status.in_(['pending', 'queued', 'processing']))
        .scalar()
        or 0
    )
    active_jobs = (
        db.query(func.count(Job.id))
        .filter(Job.status.in_(['running', 'processing']))
        .scalar()
        or 0
    )

    return {
        'status': 'running',
        'service': 'Expert Agent MCP Server',
        'application': 'expert-agent-mcp-server',
        'version': _app_version(),
        'uptime_seconds': uptime_seconds,
        'memory_mb': memory_mb,
        'memory_percent': memory_percent,
        'cpu_percent': cpu_percent,
        'disk_percent': disk_percent,
        'active_connections': 0,
        'active_sessions': int(active_sessions),
        'expert_count': int(expert_count),
        'knowledge_item_count': int(knowledge_item_count),
        'channel_count': int(channel_count),
        'queue_depth': int(queue_depth),
        'active_jobs': int(active_jobs),
    }


@router.get('/health')
async def health() -> Dict[str, Any]:
    """Health check endpoint."""
    env_file = get_config('expert.env_file')
    secrets_files = get_config('expert.env_secrets_files')
    return {
        'status': 'healthy',
        'service': 'Expert Agent MCP Server',
        'application': 'expert-agent-mcp-server',
        'version': _app_version(),
        'env': {
            'config_env_file': env_file,
            'secrets_env_files': secrets_files,
            'testing': get_config('test.enabled'),
        },
    }


@router.get('/health/status')
async def health_status(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Detailed status endpoint under the historical health namespace."""
    return _build_status_payload(db)


@router.get('/status')
async def status(db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Detailed status endpoint for UI polling."""
    return _build_status_payload(db)


_BUILD_INFO_PATH = Path("/app/build-info.json")


@router.get('/build-info')
async def build_info(_user: "User" = Depends(verify_api_key)) -> Dict[str, Any]:
    """EA10 (W28M-FIX-1617): authed build-provenance manifest.

    Returns /app/build-info.json written at image build time (version, git
    commit, git branch, build time). Falls back to a minimal manifest when the
    file is absent (e.g. a native/dev run outside a built image) so the route
    never 500s — it always returns JSON provenance, never the SPA shell.
    """
    if _BUILD_INFO_PATH.exists():
        try:
            return json.loads(_BUILD_INFO_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "version": get_config("app.version") or "0.1.1RC1",
        "git_commit": "unknown",
        "git_branch": "unknown",
        "build_time": "unknown",
        "source": "fallback-no-build-info-json",
    }
