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
User Management Routes

License: Apache 2.0
Ownership: Cloud Dog
Description: User CRUD endpoints

Related Requirements: FR1.5
Related Tasks: T005
Related Architecture: CC5.1.1
Related Tests: AT1.7

Recent Changes:
- Initial implementation
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from pydantic import BaseModel
from cloud_dog_cache.invalidation import CONFIG_CHANGE, invalidate_event

from src.database.connection import get_db
from src.core.auth.user_manager import UserManager
from src.common.a2a_client import publish_config_change_event
from src.core.audit.logger import log_audit_event
from src.database.models import (
    APIKey,
    Job,
    KnowledgeVersion,
    Message,
    MultimediaFile,
    Session as SessionModel,
    User,
)
from src.servers.api.auth import require_permission, verify_api_key, verify_admin

router = APIRouter(prefix="/users", tags=["users"])


class CreateUserRequest(BaseModel):
    username: str
    email: str
    password: Optional[str] = None
    display_name: Optional[str] = None
    role: str = "user"


@router.get("")
async def list_users(
    enabled_only: bool = False,
    role: Optional[str] = None,
    db: Session = Depends(get_db),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """List all users."""
    from src.database.models import User

    query = db.query(User)
    if enabled_only:
        query = query.filter(User.enabled)
    if role:
        query = query.filter(User.role == role)

    users = query.all()
    return {
        "users": [
            {
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "display_name": u.display_name,
                "role": u.role,
                "enabled": u.enabled,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "updated_at": u.updated_at.isoformat() if u.updated_at else None,
            }
            for u in users
        ],
        "count": len(users),
    }


@router.post("")
async def create_user(
    request: CreateUserRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Create a new user."""
    manager = UserManager(db)
    try:
        user = manager.create_user(
            username=request.username,
            email=request.email,
            password=request.password,
            display_name=request.display_name,
            role=request.role,
        )
        try:
            log_audit_event(
                kind="user.created",
                ref=str(user.id),
                actor=_admin.username,
                data={
                    "target": {"type": "user", "id": str(user.id), "name": user.username},
                    "username": user.username,
                    "email": user.email,
                    "display_name": user.display_name,
                    "role": user.role,
                    "outcome": "success",
                },
                ip=http_request.client.host if http_request.client else None,
                user_agent=http_request.headers.get("user-agent"),
                db=db,
            )
        except Exception:
            pass
        publish_config_change_event(
            action="create",
            resource_type="user",
            resource_id=int(user.id),
            actor=_admin.username,
        )
        await invalidate_event(CONFIG_CHANGE)
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "enabled": user.enabled,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{user_id}")
async def get_user(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Get user by ID."""
    manager = UserManager(db)
    user = manager.get_user(user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    # Admin can view any user; normal users can only view themselves
    if current_user.role != "admin" and int(current_user.id) != int(user_id):
        raise HTTPException(status_code=403, detail="Permission denied")
    return {
        "id": user.id,
        "username": user.username,
        "email": user.email,
        "display_name": user.display_name,
        "role": user.role,
        "enabled": user.enabled,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "updated_at": user.updated_at.isoformat() if user.updated_at else None,
    }


class UpdateUserRequest(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    display_name: Optional[str] = None
    role: Optional[str] = None
    enabled: Optional[bool] = None


@router.put("/{user_id}")
async def update_user(
    user_id: int,
    request: UpdateUserRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Update a user."""
    manager = UserManager(db)
    try:
        if current_user.role != "admin" and int(current_user.id) != int(user_id):
            raise HTTPException(status_code=403, detail="Permission denied")
        # Non-admin users cannot change role/enabled flags
        if current_user.role != "admin":
            if request.role is not None or request.enabled is not None:
                raise HTTPException(status_code=403, detail="Permission denied")

        # Validate email format if provided
        if request.email is not None and request.email:
            import re

            email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            if not re.match(email_pattern, request.email):
                raise HTTPException(status_code=400, detail="Invalid email format")

        # Validate username if provided
        if request.username is not None and not request.username.strip():
            raise HTTPException(status_code=400, detail="Username cannot be empty")

        # W28A-285: Prevent demoting the last admin user.
        if request.role is not None and request.role != "admin":
            target_user = manager.get_user(user_id=user_id)
            if target_user and target_user.role == "admin":
                admin_count = db.query(User).filter(User.role == "admin", User.enabled == True).count()
                if admin_count <= 1:
                    raise HTTPException(
                        status_code=400,
                        detail="Cannot demote the last admin user",
                    )

        update_data = {}
        if request.username is not None:
            update_data["username"] = request.username
        if request.email is not None:
            update_data["email"] = request.email
        if request.password is not None:
            update_data["password"] = request.password
        if request.display_name is not None:
            update_data["display_name"] = request.display_name
        if request.role is not None:
            update_data["role"] = request.role
        if request.enabled is not None:
            update_data["enabled"] = request.enabled

        user = manager.update_user(user_id, **update_data)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        try:
            log_audit_event(
                kind="user.updated",
                ref=str(user.id),
                actor=current_user.username,
                data={
                    "target": {"type": "user", "id": str(user.id), "name": user.username},
                    "username": user.username,
                    "email": user.email,
                    "display_name": user.display_name,
                    "role": user.role,
                    "updated_fields": [key for key, value in update_data.items() if value is not None],
                    "outcome": "success",
                },
                ip=http_request.client.host if http_request.client else None,
                user_agent=http_request.headers.get("user-agent"),
                db=db,
            )
        except Exception:
            pass

        publish_config_change_event(
            action="update",
            resource_type="user",
            resource_id=int(user.id),
            actor=current_user.username,
        )
        await invalidate_event(CONFIG_CHANGE)
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "enabled": user.enabled,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/{user_id}")
async def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Delete a user."""
    manager = UserManager(db)
    user = manager.get_user(user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    deleted_username = user.username
    deleted_email = user.email
    deleted_display_name = user.display_name
    deleted_role = user.role

    # Delete user
    db.delete(user)
    db.commit()
    try:
        log_audit_event(
            kind="user.deleted",
            ref=str(user_id),
            actor=_admin.username,
            data={
                "target": {"type": "user", "id": str(user_id), "name": deleted_username},
                "username": deleted_username,
                "email": deleted_email,
                "display_name": deleted_display_name,
                "role": deleted_role,
                "outcome": "success",
            },
            ip=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            db=db,
        )
    except Exception:
        pass
    publish_config_change_event(
        action="delete",
        resource_type="user",
        resource_id=int(user_id),
        actor=_admin.username,
    )
    await invalidate_event(CONFIG_CHANGE)

    return {"message": "User deleted successfully", "id": user_id}


 # Covers: NF1.4
@router.get("/{user_id}/gdpr/export")
async def export_user_gdpr_data(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Export user-linked data for GDPR portability requests."""
    manager = UserManager(db)
    user = manager.get_user(user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if current_user.role != "admin" and int(current_user.id) != int(user_id):
        raise HTTPException(status_code=403, detail="Permission denied")

    sessions = db.query(SessionModel).filter(SessionModel.user_id == user_id).all()
    session_ids = [int(s.id) for s in sessions]

    messages = (
        db.query(Message).filter(Message.session_id.in_(session_ids)).all() if session_ids else []
    )
    jobs = db.query(Job).filter(Job.user_id == user_id).all()
    api_keys = db.query(APIKey).filter(APIKey.user_id == user_id).all()
    knowledge_versions = (
        db.query(KnowledgeVersion).filter(KnowledgeVersion.created_by_user_id == user_id).all()
    )
    files = (
        db.query(MultimediaFile).filter(MultimediaFile.session_id.in_(session_ids)).all()
        if session_ids
        else []
    )

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "enabled": user.enabled,
        },
        "data": {
            "sessions": [
                {
                    "id": s.id,
                    "title": s.title,
                    "status": s.status,
                    "expert_config_id": s.expert_config_id,
                }
                for s in sessions
            ],
            "messages": [
                {
                    "id": m.id,
                    "session_id": m.session_id,
                    "role": m.role,
                    "content": m.content,
                }
                for m in messages
            ],
            "jobs": [
                {
                    "id": j.id,
                    "session_id": j.session_id,
                    "channel_id": j.channel_id,
                    "status": j.status,
                    "job_type": j.job_type,
                }
                for j in jobs
            ],
            "api_keys": [
                {
                    "id": key.id,
                    "name": key.name,
                    "revoked": key.revoked,
                    "expires_at": key.expires_at.isoformat() if key.expires_at else None,
                }
                for key in api_keys
            ],
            "files": [
                {
                    "id": f.id,
                    "session_id": f.session_id,
                    "file_type": f.file_type,
                    "file_path": f.file_path,
                }
                for f in files
            ],
            "knowledge_versions": [
                {
                    "id": kv.id,
                    "knowledge_type": kv.knowledge_type,
                    "knowledge_id": kv.knowledge_id,
                    "version": kv.version,
                    "is_current": kv.is_current,
                }
                for kv in knowledge_versions
            ],
        },
        "counts": {
            "sessions": len(sessions),
            "messages": len(messages),
            "jobs": len(jobs),
            "api_keys": len(api_keys),
            "files": len(files),
            "knowledge_versions": len(knowledge_versions),
        },
    }


 # Covers: NF1.4
@router.delete("/{user_id}/gdpr/delete")
async def gdpr_delete_user_data(
    user_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Delete user and linked records for GDPR erasure requests."""
    manager = UserManager(db)
    user = manager.get_user(user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sessions = db.query(SessionModel).filter(SessionModel.user_id == user_id).all()
    session_ids = [int(s.id) for s in sessions]

    deleted_counts = {
        "messages": 0,
        "jobs": 0,
        "files": 0,
        "api_keys": 0,
        "knowledge_versions": 0,
        "sessions": 0,
        "users": 0,
    }

    try:
        if session_ids:
            deleted_counts["messages"] = (
                db.query(Message).filter(Message.session_id.in_(session_ids)).delete()
            )
            deleted_counts["files"] = (
                db.query(MultimediaFile).filter(MultimediaFile.session_id.in_(session_ids)).delete()
            )

        deleted_counts["jobs"] = db.query(Job).filter(Job.user_id == user_id).delete()
        deleted_counts["api_keys"] = db.query(APIKey).filter(APIKey.user_id == user_id).delete()
        deleted_counts["knowledge_versions"] = (
            db.query(KnowledgeVersion).filter(KnowledgeVersion.created_by_user_id == user_id).delete()
        )

        for session in sessions:
            db.delete(session)
            deleted_counts["sessions"] += 1

        db.delete(user)
        deleted_counts["users"] = 1
        db.commit()
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed GDPR deletion: {e}")

    return {
        "message": "GDPR deletion completed",
        "user_id": user_id,
        "deleted": deleted_counts,
    }
