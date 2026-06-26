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
API Key Routes

License: Apache 2.0
Ownership: Cloud Dog
Description: API key generation and management endpoints.

Related Requirements: FR1.11, CS1.1
Related Tasks: T055
Related Architecture: SE1.1
Related Tests: AT1.28, AT1.29, AT1.34
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session
from cloud_dog_cache.invalidation import CONFIG_CHANGE, invalidate_event

from src.database.connection import get_db
from src.database.models import User, APIKey
from src.common.a2a_client import publish_config_change_event
from src.core.auth.api_key_manager import APIKeyManager
from src.servers.api.auth import require_permission, verify_api_key, verify_admin


router = APIRouter(prefix="/api-keys", tags=["api-keys"], dependencies=[Depends(require_permission("users:read"))])


class CreateAPIKeyRequest(BaseModel):
    user_id: Optional[int] = None
    group_id: Optional[int] = None
    name: Optional[str] = None
    expires_days: Optional[int] = None

    # Optional explicit feature flags for logs/histories/channel access
    read_logs: bool = True
    read_histories: bool = True
    read_channels: bool = True


def _to_api_key_view(row: APIKey) -> Dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "group_id": row.group_id,
        "name": row.name,
        "read_channels": bool(row.read_channels),
        "write_channels": bool(row.write_channels),
        "read_logs": bool(row.read_logs),
        "write_logs": bool(row.write_logs),
        "read_histories": bool(row.read_histories),
        "write_histories": bool(row.write_histories),
        "revoked": bool(row.revoked),
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
    }


@router.post("")
async def create_api_key(
    request: CreateAPIKeyRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Admin-only: create an API key for a user (or unscoped)."""
    manager = APIKeyManager(db)
    result = manager.generate_key(
        user_id=request.user_id,
        group_id=request.group_id,
        name=request.name,
        expires_days=request.expires_days,
        scopes=None,
    )
    api_key_obj = result["api_key"]

    # Set capability flags (simple model fields)
    api_key_obj.read_logs = bool(request.read_logs)
    api_key_obj.read_histories = bool(request.read_histories)
    api_key_obj.read_channels = bool(request.read_channels)
    db.commit()
    db.refresh(api_key_obj)

    publish_config_change_event(
        action="create",
        resource_type="api_key",
        resource_id=int(api_key_obj.id),
        actor=_admin.username,
    )
    await invalidate_event(CONFIG_CHANGE)
    return {
        "id": api_key_obj.id,
        "key": result["key"],  # plaintext - caller must store securely
        "user_id": api_key_obj.user_id,
        "group_id": api_key_obj.group_id,
        "name": api_key_obj.name,
        "expires_at": api_key_obj.expires_at.isoformat() if api_key_obj.expires_at else None,
    }


@router.get("")
async def list_api_keys(
    user_id: Optional[int] = Query(default=None),
    group_id: Optional[int] = Query(default=None),
    include_revoked: bool = Query(default=False),
    limit: int = Query(default=200, ge=1, le=2000),
    db: Session = Depends(get_db),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Admin-only: list API keys (never returns plaintext keys)."""
    q = db.query(APIKey)
    if user_id is not None:
        q = q.filter(APIKey.user_id == user_id)
    if group_id is not None:
        q = q.filter(APIKey.group_id == group_id)
    if not include_revoked:
        q = q.filter(not APIKey.revoked)
    rows: List[APIKey] = q.order_by(APIKey.id.desc()).limit(limit).all()
    return {"total": len(rows), "api_keys": [_to_api_key_view(r) for r in rows]}


@router.delete("/{key_id}")
async def revoke_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Admin-only: revoke API key by id."""
    manager = APIKeyManager(db)
    ok = manager.revoke_key(key_id)
    if not ok:
        raise HTTPException(status_code=404, detail="API key not found")
    publish_config_change_event(
        action="delete",
        resource_type="api_key",
        resource_id=int(key_id),
        actor=_admin.username,
    )
    await invalidate_event(CONFIG_CHANGE)
    return {"success": True, "id": key_id, "revoked": True}


@router.post("/{key_id}/rotate")
async def rotate_api_key(
    key_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Admin-only: rotate key (revoke old, create replacement with same scope flags)."""
    current = db.query(APIKey).filter(APIKey.id == key_id).first()
    if current is None:
        raise HTTPException(status_code=404, detail="API key not found")
    if current.revoked:
        raise HTTPException(status_code=400, detail="Cannot rotate a revoked key")

    manager = APIKeyManager(db)
    remaining_days: Optional[int] = None
    if current.expires_at is not None:
        delta = current.expires_at - datetime.utcnow()
        remaining_days = max(0, int(delta.total_seconds() // 86400))

    created = manager.generate_key(
        user_id=current.user_id,
        group_id=current.group_id,
        name=(current.name or f"key_{current.id}") + "_rotated",
        scopes=None,
        expires_days=remaining_days,
    )
    new_key = created["api_key"]
    # Preserve capability flags on replacement key.
    new_key.read_channels = bool(current.read_channels)
    new_key.write_channels = bool(current.write_channels)
    new_key.read_logs = bool(current.read_logs)
    new_key.write_logs = bool(current.write_logs)
    new_key.read_histories = bool(current.read_histories)
    new_key.write_histories = bool(current.write_histories)
    db.commit()
    db.refresh(new_key)

    manager.revoke_key(key_id)

    return {
        "success": True,
        "old_key_id": key_id,
        "new_key": {
            "id": new_key.id,
            "key": created["key"],  # plaintext key shown once
            "user_id": new_key.user_id,
            "group_id": new_key.group_id,
            "name": new_key.name,
            "expires_at": new_key.expires_at.isoformat() if new_key.expires_at else None,
        },
    }


@router.get("/me")
async def get_my_api_key_permissions(
    db: Session = Depends(get_db),
    user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Return current user's API key-related flags (for debugging/testing)."""
    # NOTE: verify_api_key already validated the key and the associated user.
    return {
        "user_id": user.id,
        "role": user.role,
    }
