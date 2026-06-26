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
Audit Logging Routes

License: Apache 2.0
Ownership: Cloud Dog
Description: Audit log access API endpoints

Related Requirements: FR1.10, NF1.7, T034
Related Tasks: T034
Related Architecture: SE1.3
Related Tests: AT1.6

Recent Changes:
- Initial implementation
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional, List
from datetime import datetime
from pathlib import Path
import json

from src.config.loader import load_config
from src.database.connection import get_db
from src.core.audit.api import AuditAPI
from src.servers.api.auth import require_permission, verify_api_key, verify_admin
from src.core.security.crypto import decrypt_if_enabled

router = APIRouter(prefix="/audit", tags=["audit"])

# PS-40 /logs endpoint for the monitoring WebUI (LogTablePanel expects this format)
logs_router = APIRouter(tags=["logs"], dependencies=[Depends(require_permission("audit:read"))])

_SURFACE_LOG_KEYS = {
    "audit": "audit_log",
    "api": "api_server_log",
    "web": "web_server_log",
    "mcp": "mcp_server_log",
    "a2a": "a2a_server_log",
}
_SURFACE_LABELS = {
    "audit": "Audit",
    "api": "API",
    "web": "Web",
    "mcp": "MCP",
    "a2a": "A2A",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _resolve_log_path(surface: str) -> Path:
    config = load_config()
    log_cfg = config.get("log")
    if not isinstance(log_cfg, dict):
        log_cfg = {}

    key = _SURFACE_LOG_KEYS.get(surface, "audit_log")
    default_name = {
        "audit_log": "logs/audit.log.jsonl",
        "api_server_log": "./logs/api_server.log",
        "web_server_log": "./logs/web_server.log",
        "mcp_server_log": "./logs/mcp_server.log",
        "a2a_server_log": "./logs/a2a_server.log",
    }[key]
    raw_path = str(log_cfg.get(key) or default_name)
    path = Path(raw_path)
    if not path.is_absolute():
        path = (_repo_root() / path).resolve()
    return path


def _candidate_log_paths(surface: str) -> List[Path]:
    paths = [_resolve_log_path(surface)]
    if surface == "audit":
        api_log = _resolve_log_path("api")
        if api_log not in paths:
            paths.append(api_log)
    return paths


def _coerce_actor(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return {
            "type": value.get("type"),
            "id": str(value.get("id")) if value.get("id") is not None else None,
            "roles": value.get("roles") if isinstance(value.get("roles"), list) else [],
            "ip": value.get("ip"),
            "user_agent": value.get("user_agent"),
        }
    if value is None:
        return {"type": "system", "id": "anonymous", "roles": [], "ip": None, "user_agent": None}
    return {"type": "user", "id": str(value), "roles": [], "ip": None, "user_agent": None}


def _coerce_target(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return {
            "type": value.get("type"),
            "id": str(value.get("id")) if value.get("id") is not None else None,
            "name": value.get("name"),
        }
    if value is None:
        return {"type": None, "id": None, "name": None}
    return {"type": None, "id": str(value), "name": str(value)}


def _coerce_details(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            return {"raw": value}
        return parsed if isinstance(parsed, dict) else {"value": parsed}
    return {}


def _source_relpath(path: Path) -> str:
    try:
        return str(path.relative_to(_repo_root()))
    except ValueError:
        return str(path)


def _normalize_structured_entry(
    record: Dict[str, Any],
    *,
    surface: str,
    source_path: Path,
    line_number: int,
) -> Dict[str, Any]:
    actor = _coerce_actor(record.get("actor"))
    target = _coerce_target(record.get("target"))
    details = _coerce_details(record.get("details"))

    return {
        "id": str(record.get("request_id") or record.get("trace_id") or record.get("correlation_id") or f"{surface}:{line_number}"),
        "surface": surface,
        "surface_label": _SURFACE_LABELS.get(surface, surface.upper()),
        "source_path": _source_relpath(source_path),
        "line_number": line_number,
        "timestamp": record.get("timestamp"),
        "message": record.get("message"),
        "logger": record.get("logger"),
        "level": record.get("level"),
        "event_type": record.get("event_type"),
        "action": record.get("action"),
        "outcome": record.get("outcome"),
        "severity": record.get("severity") or record.get("level"),
        "correlation_id": record.get("correlation_id"),
        "trace_id": record.get("trace_id"),
        "request_id": record.get("request_id"),
        "service": record.get("service"),
        "service_instance": record.get("service_instance"),
        "environment": record.get("environment"),
        "actor": actor,
        "target": target,
        "details": details,
        "duration_ms": record.get("duration_ms"),
        "raw": record,
    }


def _normalize_request_logging_entry(
    record: Dict[str, Any],
    *,
    surface: str,
    source_path: Path,
    line_number: int,
) -> Optional[Dict[str, Any]]:
    extra = record.get("extra")
    if not isinstance(extra, dict):
        return None

    path = extra.get("path")
    method = extra.get("method")
    status_code = extra.get("status_code")
    if path is None or status_code is None:
        return None

    status_value = None
    try:
        status_value = int(status_code)
    except (TypeError, ValueError):
        status_value = None

    action = str(method or "").strip().lower() or None
    outcome = None
    if status_value is not None:
        outcome = "success" if status_value < 400 else "failure"

    details = {
        key: value
        for key, value in {
            "status_code": status_value,
            "method": method,
            "client_ip": extra.get("client_ip"),
            "duration_ms": extra.get("duration_ms"),
        }.items()
        if value is not None
    }
    actor_id = extra.get("user")

    return {
        "id": str(extra.get("request_id") or record.get("request_id") or record.get("trace_id") or f"{surface}:{line_number}"),
        "surface": surface,
        "surface_label": _SURFACE_LABELS.get(surface, surface.upper()),
        "source_path": _source_relpath(source_path),
        "line_number": line_number,
        "timestamp": record.get("timestamp"),
        "message": record.get("message"),
        "logger": record.get("logger"),
        "level": record.get("level"),
        "event_type": f"http.{action}" if action else "http.request",
        "action": action,
        "outcome": outcome,
        "severity": record.get("level"),
        "correlation_id": record.get("correlation_id"),
        "trace_id": record.get("trace_id"),
        "request_id": extra.get("request_id") or record.get("request_id"),
        "service": record.get("service"),
        "service_instance": record.get("service_instance"),
        "environment": record.get("environment"),
        "actor": {
            "type": "user" if actor_id else "system",
            "id": str(actor_id or "anonymous"),
            "roles": [],
            "ip": extra.get("client_ip"),
            "user_agent": None,
        },
        "target": {
            "type": "endpoint",
            "id": str(path),
            "name": f"{method} {path}".strip() if method else str(path),
        },
        "details": details,
        "duration_ms": extra.get("duration_ms"),
        "raw": record,
    }


def _entry_matches_query(entry: Dict[str, Any], query: Optional[str]) -> bool:
    if not query:
        return True

    blob = " ".join(
        str(value)
        for value in (
            entry.get("surface_label"),
            entry.get("message"),
            entry.get("logger"),
            entry.get("event_type"),
            entry.get("action"),
            entry.get("outcome"),
            entry.get("severity"),
            entry.get("correlation_id"),
            entry.get("trace_id"),
            entry.get("request_id"),
            entry.get("service"),
            entry.get("service_instance"),
            entry.get("environment"),
            (entry.get("actor") or {}).get("type"),
            (entry.get("actor") or {}).get("id"),
            (entry.get("actor") or {}).get("ip"),
            (entry.get("actor") or {}).get("user_agent"),
            (entry.get("target") or {}).get("type"),
            (entry.get("target") or {}).get("id"),
            (entry.get("target") or {}).get("name"),
            entry.get("source_path"),
            entry.get("timestamp"),
            json.dumps(entry.get("details") or {}, sort_keys=True),
        )
        if value not in (None, "")
    ).lower()
    return query.lower() in blob


def _load_entries_from_path(
    surface: str,
    log_path: Path,
    limit: int,
    query: Optional[str],
) -> List[Dict[str, Any]]:
    if not log_path.exists():
        return []

    try:
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    entries: List[Dict[str, Any]] = []
    for index in range(len(lines) - 1, -1, -1):
        line = lines[index].strip()
        if not line or not line.startswith("{"):
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue

        entry = _normalize_request_logging_entry(
            payload,
            surface=surface,
            source_path=log_path,
            line_number=index + 1,
        )
        if entry is None:
            entry = _normalize_structured_entry(
                payload,
                surface=surface,
                source_path=log_path,
                line_number=index + 1,
            )

        if not _entry_matches_query(entry, query):
            continue

        entries.append(entry)
        if len(entries) >= limit:
            break

    return entries


def _entry_sort_key(entry: Dict[str, Any]) -> tuple[str, int]:
    return (
        str(entry.get("timestamp") or ""),
        int(entry.get("line_number") or 0),
    )


def _load_surface_entries(surface: str, limit: int, query: Optional[str]) -> List[Dict[str, Any]]:
    combined: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    for log_path in _candidate_log_paths(surface):
        for entry in _load_entries_from_path(surface, log_path, limit, query):
            entry_id = str(entry.get("id") or "")
            dedupe_key = f"{entry.get('source_path')}:{entry_id}"
            if dedupe_key in seen_ids:
                continue
            seen_ids.add(dedupe_key)
            combined.append(entry)

    combined.sort(key=_entry_sort_key, reverse=True)
    return combined[:limit]


@logs_router.get("/logs")
async def get_logs(
    surface: str = Query("audit"),
    query: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
    user=Depends(verify_api_key),
) -> Dict[str, Any]:
    """PS-40 log entries for the monitoring WebUI."""
    _ = db, user
    entries = _load_surface_entries(surface, limit, query)
    source_path = _source_relpath(_resolve_log_path(surface))

    return {
        "entries": entries,
        "count": len(entries),
        "surface": surface,
        "surface_label": _SURFACE_LABELS.get(surface, surface.upper()),
        "source_path": source_path,
        "available_surfaces": [
            {"id": "audit", "label": "Audit"},
            {"id": "api", "label": "API"},
            {"id": "web", "label": "Web"},
            {"id": "mcp", "label": "MCP"},
            {"id": "a2a", "label": "A2A"},
        ],
    }


def _parse_event_details(data: Optional[str]) -> Dict[str, Any]:
    """Best-effort parser for persisted audit payloads.

    Some historical rows may contain non-JSON payloads; those records should
    not break the entire audit listing endpoint.
    """
    if not data:
        return {}
    decrypted = decrypt_if_enabled(data)
    if not decrypted:
        return {}
    try:
        parsed = json.loads(decrypted)
    except (json.JSONDecodeError, TypeError, ValueError):
        return {"raw": str(decrypted)}
    return parsed if isinstance(parsed, dict) else {"value": parsed}


 # Covers: FR1.20
@router.get("")
async def get_audit_events(
    user_id: Optional[int] = Query(None),
    session_id: Optional[int] = Query(None),
    event_type: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user=Depends(verify_api_key),
) -> Dict[str, Any]:
    """Get audit events with filters."""
    api = AuditAPI(db)

    start = datetime.fromisoformat(start_date) if start_date else None
    end = datetime.fromisoformat(end_date) if end_date else None

    events = api.get_audit_events(
        user_id=user_id,
        session_id=session_id,
        event_type=event_type,
        start_date=start,
        end_date=end,
        limit=limit,
        offset=offset,
    )

    # Non-admin users can only view their own events.
    if getattr(user, "role", None) != "admin":
        events = [
            e
            for e in events
            if (e.actor and str(e.actor) == str(user.id))
            or (user_id is not None and int(user_id) == int(user.id))
        ]

    return {
        "events": [
            {
                "id": e.id,
                "timestamp": e.created_at.isoformat(),
                "event_type": e.kind,
                "user_id": int(e.actor) if e.actor and e.actor.isdigit() else None,
                "session_id": int(e.ref) if e.ref and e.ref.isdigit() else None,
                "details": _parse_event_details(e.data),
            }
            for e in events
        ],
        "count": len(events),
    }


@router.get("/{event_id}")
async def get_audit_event(
    event_id: int,
    db: Session = Depends(get_db),
    user=Depends(verify_api_key),
) -> Dict[str, Any]:
    """Get audit event by ID."""
    api = AuditAPI(db)
    event = api.get_audit_event(event_id)

    if not event:
        raise HTTPException(status_code=404, detail="Audit event not found")

    # Parse details from data field
    details = _parse_event_details(event.data)

    # Non-admin can only view their own events
    if getattr(user, "role", None) != "admin":
        if not (event.actor and str(event.actor) == str(user.id)):
            raise HTTPException(status_code=403, detail="Permission denied")

    return {
        "id": event.id,
        "timestamp": event.created_at.isoformat(),
        "event_type": event.kind,
        "user_id": int(event.actor) if event.actor and event.actor.isdigit() else None,
        "session_id": int(event.ref) if event.ref and event.ref.isdigit() else None,
        "channel_id": details.get("channel_id"),
        "expert_id": details.get("expert_id"),
        "ip_address": event.ip,
        "user_agent": event.user_agent,
        "details": details,
        "signature": event.signature,
    }


@router.get("/{event_id}/raw")
async def get_audit_event_raw(
    event_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(verify_admin),
) -> Dict[str, Any]:
    """Admin-only: return raw stored fields (for encryption-at-rest verification)."""
    api = AuditAPI(db)
    event = api.get_audit_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Audit event not found")
    return {
        "id": event.id,
        "event_type": event.kind,
        "actor": event.actor,
        "ref": event.ref,
        "created_at": event.created_at.isoformat(),
        "data_raw": event.data,
        "signature": event.signature,
    }


@router.get("/{event_id}/verify")
async def verify_audit_event_signature(
    event_id: int,
    db: Session = Depends(get_db),
    _admin=Depends(verify_admin),
) -> Dict[str, Any]:
    """Admin-only: verify audit event signature integrity."""
    from src.core.audit.logger import AuditLogger

    api = AuditAPI(db)
    event = api.get_audit_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Audit event not found")

    logger = AuditLogger()
    signature_data = (
        f"{event.kind}:{event.ref}:{event.actor}:{event.data}:{event.created_at.isoformat()}"
    )
    expected = logger._sign_event(signature_data)
    return {
        "id": event.id,
        "valid": bool(event.signature and event.signature == expected),
    }


 # Covers: FR1.20
@router.get("/export/{format}")
async def export_audit_logs(
    format: str,
    user_id: Optional[int] = Query(None),
    session_id: Optional[int] = Query(None),
    event_type: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    _admin=Depends(verify_admin),
) -> Response:
    """Export audit logs in specified format."""
    if format not in ["json", "csv"]:
        raise HTTPException(status_code=400, detail="Format must be 'json' or 'csv'")

    api = AuditAPI(db)

    filters = {"user_id": user_id, "session_id": session_id, "event_type": event_type}

    if start_date:
        filters["start_date"] = datetime.fromisoformat(start_date)
    if end_date:
        filters["end_date"] = datetime.fromisoformat(end_date)

    exported = api.export_audit_logs(format=format, **filters)

    media_type = "application/json" if format == "json" else "text/csv"

    return Response(
        content=exported,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename=audit_logs.{format}"},
    )
