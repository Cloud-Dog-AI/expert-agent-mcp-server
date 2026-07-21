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
Job Queue Management Routes

License: Apache 2.0
Ownership: Cloud Dog
Description: Job queue CRUD endpoints

Related Requirements: FR1.32, FR1.37, UC1.27
Related Tasks: T119
Related Architecture: CC2.1.2
Related Tests: AT1.89
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.config import get_config
from src.core.audit.logger import log_audit_event
from src.core.job.manager import JobManager
from src.core.queue.manager import QueueManager
from src.database.connection import get_db
from src.database.models import Job, User
from src.servers.api.auth import require_permission, verify_admin, verify_jobs_read, verify_jobs_write

router = APIRouter(prefix="/jobs", tags=["jobs"], dependencies=[Depends(require_permission("expert:read"))])

_CANCELLABLE = {
    "created",
    "validated",
    "queued",
    "scheduled",
    "dispatched",
    "running",
    "processing",
    "blocked",
    "paused",
    "pending",
    "retry_wait",
}
_RETRYABLE = {"failed", "cancelled", "timed_out", "timeout", "dead_lettered"}
_TERMINAL = {
    "completed",
    "succeeded",
    "failed",
    "cancelled",
    "timed_out",
    "timeout",
    "dead_lettered",
    "ttl_expired",
    "archived",
}
_ACTIVE = {"running", "processing", "dispatched"}
_QUEUED = {"created", "validated", "queued", "scheduled", "pending", "retry_wait"}


class ResubmitJobRequest(BaseModel):
    priority: Optional[int] = 0


class CreateJobRequest(BaseModel):
    job_type: str
    status: str = "queued"
    user_id: Optional[int] = None
    session_id: Optional[int] = None
    channel_id: Optional[int] = None
    prompt_sent: Optional[str] = None
    response_received: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    error_info: Optional[Dict[str, Any]] = None


def _safe_json(raw: Optional[str]) -> Dict[str, Any]:
    """Decode an optional JSON object, returning an empty object on invalid input."""
    if not raw:
        return {}
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _normalise_status(value: Optional[str]) -> str:
    """Return the canonical lowercase representation of a job status."""
    return str(value or "unknown").strip().lower()


def _is_admin(user: User) -> bool:
    """Return whether the supplied user has the administrator role."""
    return str(getattr(user, "role", "") or "").strip().lower() == "admin"


def _actor_identity(
    job: Job,
    metadata: Dict[str, Any],
    db: Optional[Session],
) -> Optional[str]:
    """Resolve the recorded job actor from metadata or the persisted user."""
    for key in ("actor", "request_auth_identity", "username", "user"):
        value = metadata.get(key)
        if value not in (None, ""):
            return str(value)
    if job.user_id is not None and db is not None:
        actor = db.query(User).filter(User.id == job.user_id).first()
        if actor:
            return actor.username
    return str(job.user_id) if job.user_id is not None else None


def _job_owned_by(job: Job, user: User) -> bool:
    """Return whether a job's persisted identifiers belong to a user."""
    if job.user_id is not None and int(job.user_id) == int(user.id):
        return True
    metadata = _safe_json(job.metadata_json)
    identities = {
        str(getattr(user, "id", "") or "").strip().lower(),
        str(getattr(user, "username", "") or "").strip().lower(),
        str(getattr(user, "email", "") or "").strip().lower(),
        str(getattr(user, "display_name", "") or "").strip().lower(),
    }
    identities.discard("")
    return any(
        str(metadata.get(key) or "").strip().lower() in identities
        for key in ("actor", "request_auth_identity", "username", "user", "user_id")
    )


def _ensure_job_access(job: Job, user: User) -> None:
    """Reject access unless the user is an administrator or owns the job."""
    if _is_admin(user) or _job_owned_by(job, user):
        return
    raise HTTPException(status_code=403, detail="Job access denied")


def _started_at(job: Job, metadata: Dict[str, Any], call_logs: list[dict[str, Any]]) -> Optional[str]:
    """Resolve a job start timestamp from metadata or its first call log."""
    started = metadata.get("started_at") or metadata.get("start_time")
    if started:
        return str(started)
    if call_logs:
        return str(call_logs[0].get("created_at") or "") or None
    return None


def _priority(metadata: Dict[str, Any]) -> int:
    """Parse the optional numeric job priority with a safe default."""
    try:
        return int(metadata.get("priority", 0))
    except (TypeError, ValueError):
        return 0


def _attempt(metadata: Dict[str, Any]) -> int:
    """Parse the current one-based retry attempt from job metadata."""
    try:
        return max(1, int(metadata.get("attempt", metadata.get("retry_attempt", 1))))
    except (TypeError, ValueError):
        return 1


def _max_attempts(metadata: Dict[str, Any]) -> int:
    """Resolve the positive retry limit from metadata and platform config."""
    try:
        config_default = int(get_config("queue.max_retries") or 3)
    except (TypeError, ValueError):
        config_default = 3
    try:
        return max(1, int(metadata.get("max_attempts", config_default)))
    except (TypeError, ValueError):
        return config_default


def _duration_seconds(job: Job, metadata: Dict[str, Any], performance_metrics: Dict[str, Any], started_at: Optional[str]) -> Optional[float]:
    """Calculate job duration from latency metrics or persisted timestamps."""
    latency_ms = performance_metrics.get("latency_ms")
    try:
        latency_ms_float = float(latency_ms)
        if latency_ms_float > 0:
            return latency_ms_float / 1000.0
    except (TypeError, ValueError):
        pass

    started_raw = started_at or metadata.get("started_at")
    if not started_raw:
        return None
    if not job.completed_at:
        return None
    try:
        start_ts = datetime.fromisoformat(str(started_raw).replace("Z", "+00:00"))
        end_ts = job.completed_at
        if end_ts.tzinfo is None:
            end_ts = end_ts.replace(tzinfo=start_ts.tzinfo)
        if end_ts >= start_ts:
            return (end_ts - start_ts).total_seconds()
    except (TypeError, ValueError):
        return None
    return None


def _outcome_text(job: Job, error_info: Dict[str, Any]) -> Optional[str]:
    """Build a concise outcome summary from error details or response text."""
    for key in ("message", "detail", "error", "reason"):
        value = error_info.get(key)
        if value not in (None, ""):
            return str(value)
    if job.response_received:
        return str(job.response_received)[:240]
    return None


def _lifecycle_log(
    job: Job,
    metadata: Dict[str, Any],
    started_at: Optional[str],
    actor: Optional[str],
) -> list[Dict[str, Any]]:
    """Return an explicit or derived chronological job lifecycle log."""
    explicit_log = metadata.get("lifecycle_log")
    if isinstance(explicit_log, list):
        return [entry for entry in explicit_log if isinstance(entry, dict)]
    entries = [
        {
            "timestamp": job.created_at.isoformat() if job.created_at else None,
            "from_state": None,
            "to_state": "created",
            "actor": actor,
            "message": "Job record created",
        },
        {
            "timestamp": started_at,
            "from_state": "queued",
            "to_state": "running",
            "actor": actor,
            "message": "Job dispatch started",
        },
        {
            "timestamp": job.updated_at.isoformat() if job.updated_at else None,
            "from_state": None,
            "to_state": job.status,
            "actor": actor,
            "message": "Latest state update",
        },
    ]
    return [entry for entry in entries if entry["timestamp"]]


def _serialise_job(
    job_manager: JobManager,
    job: Job,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """Serialize a persisted job and its related runtime metadata for the API."""
    metadata = _safe_json(job.metadata_json)
    performance_metrics = _safe_json(job.performance_metrics_json)
    vector_context = _safe_json(job.vector_context_json)
    tool_calls = _safe_json(job.tool_calls_json)
    error_info = _safe_json(job.error_info_json)
    call_logs = [
        {
            "id": log.id,
            "llm_provider": log.llm_provider,
            "llm_model": log.llm_model,
            "input_tokens": log.input_tokens,
            "output_tokens": log.output_tokens,
            "latency_ms": log.latency_ms,
            "cost_usd": log.cost_usd,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in job_manager.get_job_call_logs(job.id)
    ]
    started_at = _started_at(job, metadata, call_logs)
    duration_seconds = _duration_seconds(job, metadata, performance_metrics, started_at)
    actor = _actor_identity(job, metadata, db)
    result_ref = (
        metadata.get("result_ref")
        or metadata.get("result_url")
        or metadata.get("output_ref")
        or metadata.get("queue_job_id")
        or metadata.get("mcp_platform_job_id")
    )
    trace_id = (
        metadata.get("trace_id")
        or metadata.get("traceparent")
        or metadata.get("correlation_id")
    )
    request_arguments = metadata.get("request_arguments")
    if not isinstance(request_arguments, dict):
        request_arguments = {}

    return {
        "id": job.id,
        "job_id": job.id,
        "type": job.job_type,
        "job_type": job.job_type,
        "status": job.status,
        "priority": _priority(metadata),
        "attempt": _attempt(metadata),
        "max_attempts": _max_attempts(metadata),
        "request_auth_identity": metadata.get("request_auth_identity"),
        "request_source": metadata.get("request_source"),
        "auth_method": metadata.get("auth_method"),
        "correlation_id": metadata.get("correlation_id"),
        "trace_id": trace_id,
        "actor": actor,
        "session_id": job.session_id,
        "channel_id": job.channel_id,
        "user_id": job.user_id,
        "prompt_sent": job.prompt_sent,
        "response_received": job.response_received,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": started_at,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
        "completed_at": job.completed_at.isoformat() if job.completed_at else None,
        "finished_at": job.completed_at.isoformat() if job.completed_at else None,
        "duration_seconds": duration_seconds,
        "outcome": _outcome_text(job, error_info),
        "outcome_summary": _outcome_text(job, error_info),
        "result_ref": result_ref,
        "last_error": error_info or None,
        "input_ref": {
            "session_id": job.session_id,
            "channel_id": job.channel_id,
            "request_source": metadata.get("request_source"),
            "auth_method": metadata.get("auth_method"),
            "correlation_id": metadata.get("correlation_id"),
            "trace_id": trace_id,
        },
        "parameters": request_arguments,
        "thinking": metadata.get("thinking") or metadata.get("reasoning_trace"),
        "lifecycle_log": _lifecycle_log(job, metadata, started_at, actor),
        "metadata": metadata,
        "performance_metrics": performance_metrics,
        "vector_context": vector_context,
        "tool_calls": tool_calls,
        "error_info": error_info,
        "call_logs": call_logs,
    }


def _log_job_mutation(
    *,
    request: Request,
    current_user: User,
    job: Job,
    action: str,
    outcome: str,
    db: Session,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Persist a structured audit record for a job mutation."""
    log_audit_event(
        kind=f"job.{action}",
        ref=str(job.id),
        actor=current_user.username,
        data={
            "target": {"type": "job", "id": str(job.id), "name": job.job_type},
            "job_id": job.id,
            "job_type": job.job_type,
            "status": job.status,
            "user_id": job.user_id,
            "session_id": job.session_id,
            "channel_id": job.channel_id,
            "outcome": outcome,
            **(extra or {}),
        },
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        db=db,
    )


async def _cancel_job(job_manager: JobManager, queue_manager: QueueManager, job: Job) -> bool:
    """Cancel a queued job and persist its terminal status."""
    removed = await queue_manager.cancel_job(job.id)
    job_manager.update_job(job.id, status="cancelled")
    return removed


def _actor_for_user_id(db: Session, user_id: Optional[int], fallback: User) -> str:
    """Resolve a requested actor username or use the authenticated fallback."""
    if user_id is not None:
        actor = db.query(User).filter(User.id == user_id).first()
        if actor:
            return actor.username
    return fallback.username


@router.post("")
async def create_job(
    payload: CreateJobRequest,
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_jobs_write),
) -> Dict[str, Any]:
    """Create a source-backed job record for authenticated job workflows."""
    status_value = _normalise_status(payload.status)
    allowed_statuses = _TERMINAL | _ACTIVE | _QUEUED | {
        "blocked",
        "paused",
        "validated",
    }
    if status_value not in allowed_statuses:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported job status '{payload.status}'.",
        )

    target_user_id = payload.user_id if _is_admin(current_user) else int(current_user.id)
    actor = _actor_for_user_id(db, target_user_id, current_user)
    metadata = dict(payload.metadata or {})
    metadata.update(
        {
            "actor": actor,
            "request_auth_identity": actor,
            "request_source": metadata.get("request_source") or "api.jobs.create",
            "created_by": current_user.username,
        }
    )
    if status_value in _ACTIVE or status_value in _TERMINAL:
        metadata.setdefault("started_at", datetime.utcnow().isoformat())

    job_manager = JobManager(db)
    job = job_manager.create_job(
        job_type=payload.job_type,
        session_id=payload.session_id,
        channel_id=payload.channel_id,
        user_id=target_user_id,
        prompt_sent=payload.prompt_sent,
        metadata=metadata,
    )
    job_manager.update_job(
        job.id,
        status=status_value,
        response_received=payload.response_received,
        error_info=payload.error_info,
    )
    refreshed = job_manager.get_job(job.id) or job
    _log_job_mutation(
        request=request,
        current_user=current_user,
        job=refreshed,
        action="created",
        outcome="success",
        db=db,
        extra={"source": "api.jobs.create"},
    )
    response.status_code = 201
    return _serialise_job(job_manager, refreshed, db)


@router.get("")
async def list_jobs(
    session_id: Optional[int] = Query(None),
    channel_id: Optional[int] = Query(None),
    user_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_jobs_read),
) -> Dict[str, Any]:
    """List jobs with filters."""
    job_manager = JobManager(db)
    effective_user_id = user_id
    if not _is_admin(current_user):
        if user_id is not None and int(user_id) != int(current_user.id):
            raise HTTPException(status_code=403, detail="Job access denied")
        effective_user_id = int(current_user.id)
    jobs = job_manager.list_jobs(
        session_id=session_id,
        channel_id=channel_id,
        user_id=effective_user_id,
        status=status,
        limit=limit,
        offset=offset,
    )
    job_list = [_serialise_job(job_manager, job, db) for job in jobs]
    return {"total": len(job_list), "limit": limit, "offset": offset, "jobs": job_list}


@router.get("/{job_id:int}")
async def get_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_jobs_read),
) -> Dict[str, Any]:
    """Get job details."""
    job_manager = JobManager(db)
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    _ensure_job_access(job, current_user)
    return _serialise_job(job_manager, job, db)


@router.post("/{job_id:int}/cancel")
async def cancel_job(
    job_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_jobs_write),
) -> Dict[str, Any]:
    """Cancel a queued or active job."""
    job_manager = JobManager(db)
    queue_manager = QueueManager(db)
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    _ensure_job_access(job, current_user)

    status = _normalise_status(job.status)
    if status not in _CANCELLABLE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot cancel job with status '{job.status}'.",
        )

    removed = await _cancel_job(job_manager, queue_manager, job)
    refreshed = job_manager.get_job(job_id) or job
    _log_job_mutation(
        request=request,
        current_user=current_user,
        job=refreshed,
        action="cancelled",
        outcome="success",
        db=db,
        extra={"removed_from_queue": removed},
    )
    return {
        "success": True,
        "job_id": job_id,
        "removed_from_queue": removed,
        "message": f"Job {job_id} cancelled",
    }


@router.delete("/{job_id:int}")
async def remove_job(
    job_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Delete a terminal job or cancel an active one."""
    job_manager = JobManager(db)
    queue_manager = QueueManager(db)
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    status = _normalise_status(job.status)
    if status in _TERMINAL:
        snapshot = _serialise_job(job_manager, job, db)
        db.delete(job)
        db.commit()
        _log_job_mutation(
            request=request,
            current_user=current_user,
            job=job,
            action="deleted",
            outcome="success",
            db=db,
            extra={"deleted_snapshot": snapshot},
        )
        return {"success": True, "job_id": job_id, "message": f"Job {job_id} deleted"}

    if status in _CANCELLABLE:
        removed = await _cancel_job(job_manager, queue_manager, job)
        refreshed = job_manager.get_job(job_id) or job
        _log_job_mutation(
            request=request,
            current_user=current_user,
            job=refreshed,
            action="cancelled",
            outcome="success",
            db=db,
            extra={"removed_from_queue": removed, "delete_requested": True},
        )
        return {
            "success": True,
            "job_id": job_id,
            "removed_from_queue": removed,
            "message": f"Job {job_id} cancelled",
        }

    raise HTTPException(status_code=400, detail=f"Cannot delete job with status '{job.status}'.")


@router.post("/{job_id:int}/resubmit")
async def resubmit_job(
    job_id: int,
    request: ResubmitJobRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_jobs_write),
) -> Dict[str, Any]:
    """Resubmit a failed or cancelled job."""
    job_manager = JobManager(db)
    queue_manager = QueueManager(db)
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=400, detail="Cannot resubmit job that no longer exists.")
    _ensure_job_access(job, current_user)

    status = _normalise_status(job.status)
    if status not in _RETRYABLE:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot resubmit job with status '{job.status}'.",
        )

    metadata = _safe_json(job.metadata_json)
    priority = request.priority if request.priority is not None else _priority(metadata)
    new_attempt = _attempt(metadata) + 1
    configured_max = _max_attempts(metadata)
    metadata.update({"priority": priority, "attempt": new_attempt, "max_attempts": configured_max})

    new_job = job_manager.create_job(
        job_type=job.job_type,
        session_id=job.session_id,
        channel_id=job.channel_id,
        user_id=job.user_id,
        prompt_sent=job.prompt_sent,
        metadata=metadata,
    )
    await queue_manager.enqueue(
        job_type=new_job.job_type,
        session_id=new_job.session_id,
        channel_id=new_job.channel_id,
        user_id=new_job.user_id,
        priority=priority,
        metadata=metadata,
    )
    _log_job_mutation(
        request=http_request,
        current_user=current_user,
        job=new_job,
        action="retried",
        outcome="success",
        db=db,
        extra={"original_job_id": job_id, "priority": priority},
    )
    return {
        "success": True,
        "original_job_id": job_id,
        "new_job_id": new_job.id,
        "message": f"Job {job_id} resubmitted as job {new_job.id}",
    }


@router.post("/{job_id:int}/retry")
async def retry_job(
    job_id: int,
    request: ResubmitJobRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_jobs_write),
) -> Dict[str, Any]:
    """Alias for PS-76 Retry semantics."""
    return await resubmit_job(job_id, request, http_request, db, current_user)


@router.post("/{job_id:int}/stop")
async def stop_job(
    job_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_jobs_write),
) -> Dict[str, Any]:
    """Backward-compatible alias for cancel."""
    return await cancel_job(job_id, request, db, current_user)


@router.get("/queue/status")
async def get_queue_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_jobs_read),
) -> Dict[str, Any]:
    """Get queue status."""
    job_manager = JobManager(db)
    jobs = job_manager.list_jobs(
        user_id=None if _is_admin(current_user) else int(current_user.id),
        limit=1000,
    )
    status_counts: Dict[str, int] = {}
    failed_24h = 0
    cutoff = datetime.utcnow() - timedelta(hours=24)

    for job in jobs:
        status = _normalise_status(job.status)
        status_counts[status] = status_counts.get(status, 0) + 1
        if status == "failed" and job.created_at and job.created_at.replace(tzinfo=None) >= cutoff:
            failed_24h += 1

    queue_depth = sum(status_counts.get(status, 0) for status in _QUEUED)
    active_jobs = sum(status_counts.get(status, 0) for status in _ACTIVE)
    return {
        "status": "ok",
        "queue_depth": queue_depth,
        "active_jobs": active_jobs,
        "failed_24h": failed_24h,
        "status_counts": status_counts,
        "total": sum(status_counts.values()),
    }
