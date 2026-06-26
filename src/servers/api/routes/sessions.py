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
Session Management Routes

License: Apache 2.0
Ownership: Cloud Dog
Description: Session CRUD and management endpoints

Related Requirements: FR1.2, FR1.7
Related Tasks: T030, T022
Related Architecture: CC2.1, CC1.1.1
Related Tests: IT2.5, AT1.5

Recent Changes:
- Initial implementation
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from pydantic import BaseModel

from src.database.connection import get_db
from src.database.models import Session as SessionModel, User
from src.core.session.manager import SessionManager
from src.servers.api.auth import require_permission, verify_api_key

ROLE_ADMIN = "admin"
from src.core.session.key_manager import SessionKeyManager, HistoryKeyManager
from src.core.session.sharing_manager import HistorySharingManager
from src.core.session.summarization_manager import ContextSummarizationManager
from src.core.audit.logger import log_audit_event
from datetime import datetime, timedelta
from src.config.loader import get_config

router = APIRouter(prefix="/sessions", tags=["sessions"], dependencies=[Depends(require_permission("sessions:read"))])


def _expire_if_timed_out(db: Session, session: SessionModel) -> SessionModel:
    timeout_minutes = get_config("auth.session_timeout_minutes")
    if timeout_minutes is None:
        return session
    try:
        timeout_minutes = int(timeout_minutes)
    except Exception:
        return session
    if timeout_minutes <= 0:
        # Immediate expiry policy
        if session.status not in ("ended", "deleted"):
            session.status = "ended"
            db.commit()
            db.refresh(session)
        return session
    updated_at = session.updated_at or session.created_at
    if updated_at and session.status not in ("ended", "deleted"):
        age = datetime.utcnow() - updated_at.replace(tzinfo=None)
        if age > timedelta(minutes=timeout_minutes):
            session.status = "ended"
            db.commit()
            db.refresh(session)
    return session


def _require_owner_or_admin(current_user: User, session: SessionModel):
    if current_user.role == ROLE_ADMIN:
        return
    if int(session.user_id) != int(current_user.id):
        raise HTTPException(status_code=403, detail="Permission denied")


def _require_read_access(current_user: User, session: SessionModel, db: Session):
    """Read access for a session: owner, admin, or a party the session was
    shared with — directly (shared_with_user_ids) or via membership of a shared
    group (shared_with_group_ids). Mutations stay owner-or-admin.

    # req: FR-019  (Group Admin Role Management — shared session read access)
    """
    if current_user.role == ROLE_ADMIN:
        return
    if int(session.user_id) == int(current_user.id):
        return
    if HistorySharingManager(db).can_access_session(session, int(current_user.id)):
        return
    raise HTTPException(status_code=403, detail="Permission denied")


class CreateSessionRequest(BaseModel):
    user_id: int
    expert_config_id: int
    title: str = None
    channel_id: int = None
    context_window: int = 4096
    history_retention_days: int = 30


class AddMessageRequest(BaseModel):
    role: str
    content: str
    tokens_used: int = None
    metadata: Dict[str, Any] = None


@router.get("")
async def list_sessions(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """List sessions."""
    q = db.query(SessionModel)
    if current_user.role != "admin":
        q = q.filter(SessionModel.user_id == current_user.id)
    q = q.order_by(SessionModel.id.desc())
    sessions = q.offset(skip).limit(limit).all()
    sessions = [_expire_if_timed_out(db, s) for s in sessions]
    return {
        "sessions": [
            {
                "id": s.id,
                "title": s.title,
                "status": s.status,
                "user_id": s.user_id,
                "expert_config_id": s.expert_config_id,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
            }
            for s in sessions
        ],
        "total": q.count(),
    }


@router.post("", response_model=None)
async def create_session(
    request: CreateSessionRequest,
    db: Session = Depends(get_db),
    check_limits: bool = True,
    queue_if_full: bool = True,
    current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Create a new session with concurrency control."""
    if current_user.role != "admin" and int(request.user_id) != int(current_user.id):
        raise HTTPException(status_code=403, detail="Permission denied")
    manager = SessionManager(db)
    try:
        result = manager.create_session(
            user_id=request.user_id,
            expert_config_id=request.expert_config_id,
            title=request.title,
            channel_id=request.channel_id,
            context_window=request.context_window,
            history_retention_days=request.history_retention_days,
            check_limits=check_limits,
            queue_if_full=queue_if_full,
        )
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    session, notification = result

    if notification:
        # Session was queued or limited
        return {
            "status": "queued" if notification.get("queued") else "limited",
            "message": notification.get("message"),
            "queue_position": notification.get("queue_position"),
        }

    # Emit audit event for session creation
    try:
        log_audit_event(
            kind="session.created",
            ref=str(session.id),
            actor=str(session.user_id),
            data={
                "expert_config_id": session.expert_config_id,
                "status": session.status,
                "title": session.title,
            },
            db=db,
        )
    except Exception:
        # Do not block session creation on audit logging failure
        pass

    return {
        "id": session.id,
        "title": session.title,
        "status": session.status,
        "user_id": session.user_id,
        "expert_config_id": session.expert_config_id,
        "session_key": session.session_key,
        "history_key": session.history_key,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
    }


@router.get("/{session_id}")
async def get_session(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Get session by ID."""
    manager = SessionManager(db)
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session = _expire_if_timed_out(db, session)
    _require_read_access(current_user, session, db)
    return {
        "id": session.id,
        "title": session.title,
        "status": session.status,
        "user_id": session.user_id,
        "expert_config_id": session.expert_config_id,
        "session_key": session.session_key,
        "history_key": session.history_key,
    }


@router.post("/{session_id}/messages")
async def add_message(
    session_id: int,
    request: AddMessageRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Add message to session."""
    manager = SessionManager(db)
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session = _expire_if_timed_out(db, session)
    _require_owner_or_admin(current_user, session)
    if session.status != "active":
        raise HTTPException(status_code=400, detail="Session is not active")
    message = manager.add_message(
        session_id=session_id,
        role=request.role,
        content=request.content,
        tokens_used=request.tokens_used,
        metadata=request.metadata,
    )
    return {
        "id": message.id,
        "role": message.role,
        "content": message.content,
        "timestamp": message.timestamp.isoformat(),
    }


@router.get("/{session_id}/messages")
async def get_messages(
    session_id: int,
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Get messages for session."""
    manager = SessionManager(db)
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    session = _expire_if_timed_out(db, session)
    _require_read_access(current_user, session, db)
    messages = manager.get_messages(session_id, limit=limit, offset=offset)
    return {
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "timestamp": m.timestamp.isoformat()}
            for m in messages
        ],
        "count": len(messages),
    }


# AT1.11: Session Key and History Key endpoints


@router.get("/key/{session_key}")
async def get_session_by_key(
    session_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Get session by session key."""
    key_manager = SessionKeyManager(db)
    session = key_manager.get_session_by_key(session_key)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or key expired")
    session = _expire_if_timed_out(db, session)
    _require_owner_or_admin(current_user, session)
    return {
        "id": session.id,
        "title": session.title,
        "status": session.status,
        "user_id": session.user_id,
        "expert_config_id": session.expert_config_id,
        "session_key": session.session_key,
        "history_key": session.history_key,
    }


@router.get("/history/{history_key}")
async def get_history_by_key(
    history_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Get history by history key."""
    history_manager = HistoryKeyManager(db)
    history = history_manager.get_history_by_key(history_key)
    if not history:
        raise HTTPException(status_code=404, detail="History not found")
    # History key access is restricted to the session owner/admin for now.
    # (Shared history access is enforced via the sharing manager APIs.)
    session = db.query(SessionModel).filter(SessionModel.history_key == history_key).first()
    if session:
        session = _expire_if_timed_out(db, session)
        _require_owner_or_admin(current_user, session)
    return history


class ShareSessionRequest(BaseModel):
    user_ids: Optional[List[int]] = None
    group_ids: Optional[List[int]] = None


@router.post("/{session_id}/share")
async def share_session(
    session_id: int,
    request: ShareSessionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Share session with users and/or groups."""
    sharing_manager = HistorySharingManager(db)
    try:
        # Only owner/admin can share
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        session = _expire_if_timed_out(db, session)
        _require_owner_or_admin(current_user, session)
        result = sharing_manager.share_session(
            session_id=session_id, user_ids=request.user_ids, group_ids=request.group_ids
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/rotate-key")
async def rotate_session_key(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Rotate session key."""
    key_manager = SessionKeyManager(db)
    try:
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        session = _expire_if_timed_out(db, session)
        _require_owner_or_admin(current_user, session)
        new_key = key_manager.rotate_session_key(session_id)
        return {
            "session_id": session_id,
            "session_key": new_key,
            "message": "Session key rotated successfully",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{session_id}/summarize")
async def summarize_session(
    session_id: int,
    preserve_recent: int = 5,
    max_tokens: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Trigger session summarization."""
    summarization_manager = ContextSummarizationManager(db)
    try:
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        session = _expire_if_timed_out(db, session)
        _require_owner_or_admin(current_user, session)
        # Use await directly since we're in an async function
        result = await summarization_manager.summarize_session(
            session_id=session_id, preserve_recent=preserve_recent, max_tokens=max_tokens
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to summarize: {str(e)}")


@router.get("/{session_id}/summaries")
async def get_summaries(
    session_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Get all summaries for a session."""
    summarization_manager = ContextSummarizationManager(db)
    try:
        session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        session = _expire_if_timed_out(db, session)
        _require_read_access(current_user, session, db)
        summaries = summarization_manager.get_summaries(session_id)
        return {"session_id": session_id, "summaries": summaries, "count": len(summaries)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get summaries: {str(e)}")


@router.delete("/{session_id}")
async def delete_session(
    session_id: int,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Delete a session."""
    manager = SessionManager(db)
    session = manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    _require_owner_or_admin(current_user, session)

    # Delete session (cascade will handle messages, summaries, etc.)
    db.delete(session)
    db.commit()

    return {"message": "Session deleted successfully", "id": session_id}
