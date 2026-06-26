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
Admin Roles Routes (PS-71 §IW3A — persistent role store)

License: Apache 2.0
Ownership: Cloud Dog
Description: Persistent admin role CRUD backed by cloud_dog_idam SqlAlchemyRoleStore.

The PS-71 §IW3A Roles page is backed by the shared ``SqlAlchemyRoleStore`` so that
roles AND their permissions survive a process/engine restart (the legacy ``/rbac/roles``
endpoint exposed only an in-memory permission catalogue). Baseline ``admin``/``user``
roles are seeded and are undeletable (IW3A.4 -> HTTP 403).

Related Requirements: FR1.5, PS-71 IW3A
Related Tasks: W28A-876 (Gate 4b)
Related Architecture: CC5.1.1
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from cloud_dog_idam.domain.models import Role
from cloud_dog_idam.storage.sqlalchemy.role_store import (
    BaselineRoleProtected,
    SqlAlchemyRoleStore,
)
from cloud_dog_logging import get_logger

from src.common.a2a_client import publish_config_change_event
from src.core.audit.logger import log_audit_event
from src.database.connection import get_db
from src.database.models import User
from src.servers.api.auth import verify_admin, verify_api_key

logger = get_logger(__name__)

router = APIRouter(prefix="/admin/roles", tags=["admin-roles"])


class CreateRoleRequest(BaseModel):
    name: str
    description: Optional[str] = ""
    permissions: Optional[List[str]] = None


class UpdateRoleRequest(BaseModel):
    description: Optional[str] = None
    permissions: Optional[List[str]] = None


def _store(db: Session) -> SqlAlchemyRoleStore:
    return SqlAlchemyRoleStore(db)


def _role_payload(role: Role, *, baseline: bool) -> Dict[str, Any]:
    """Return a single role in the PS-71 §IW3A.1 column shape."""
    return {
        "role_id": role.role_id,
        "name": role.name,
        "description": role.description,
        "permissions": sorted(role.permissions),
        "baseline": baseline,
    }


@router.get("")
async def list_roles(
    db: Session = Depends(get_db),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """List all roles (IW3A.1 shape) — baseline roles are seeded on read."""
    store = _store(db)
    store.seed_baseline()
    roles = store.list_response()
    return {"roles": roles, "count": len(roles)}


@router.post("")
async def create_role(
    request: CreateRoleRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Create a new role with its permission set."""
    store = _store(db)
    store.seed_baseline()
    name = (request.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    if store.get_by_name(name) is not None:
        raise HTTPException(status_code=409, detail=f"role already exists: {name}")

    permissions = {
        str(p).strip() for p in (request.permissions or []) if str(p).strip()
    }
    role = store.save(
        Role(
            name=name,
            description=str(request.description or ""),
            permissions=permissions,
        )
    )

    try:
        log_audit_event(
            kind="role.created",
            ref=str(role.role_id),
            actor=_admin.username,
            data={
                "target": {"type": "role", "id": role.role_id, "name": role.name},
                "name": role.name,
                "permissions": sorted(role.permissions),
                "outcome": "success",
            },
            ip=http_request.client.host if http_request.client else None,
            user_agent=http_request.headers.get("user-agent"),
            db=db,
        )
    except Exception:
        pass
    try:
        publish_config_change_event(
            action="create",
            resource_type="role",
            resource_id=role.role_id,
            actor=_admin.username,
        )
    except Exception:
        pass

    return {"role": _role_payload(role, baseline=False)}


@router.get("/{role_id}")
async def get_role(
    role_id: str,
    db: Session = Depends(get_db),
    _user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Get a single role by id."""
    store = _store(db)
    store.seed_baseline()
    role = store.get(role_id)
    if role is None:
        raise HTTPException(status_code=404, detail=f"unknown role: {role_id}")
    from cloud_dog_idam.rbac.role_catalog import BASELINE_ROLE_NAMES

    return {"role": _role_payload(role, baseline=role.name in BASELINE_ROLE_NAMES)}


async def _update_role(
    role_id: str,
    request: UpdateRoleRequest,
    http_request: Request,
    db: Session,
    admin: User,
) -> Dict[str, Any]:
    store = _store(db)
    store.seed_baseline()
    if store.get(role_id) is None:
        raise HTTPException(status_code=404, detail=f"unknown role: {role_id}")

    permissions = (
        {str(p).strip() for p in request.permissions if str(p).strip()}
        if request.permissions is not None
        else None
    )
    role = store.update(
        role_id,
        description=request.description,
        permissions=permissions,
    )

    try:
        log_audit_event(
            kind="role.updated",
            ref=str(role.role_id),
            actor=admin.username,
            data={
                "target": {"type": "role", "id": role.role_id, "name": role.name},
                "name": role.name,
                "permissions": sorted(role.permissions),
                "outcome": "success",
            },
            ip=http_request.client.host if http_request.client else None,
            user_agent=http_request.headers.get("user-agent"),
            db=db,
        )
    except Exception:
        pass
    try:
        publish_config_change_event(
            action="update",
            resource_type="role",
            resource_id=role.role_id,
            actor=admin.username,
        )
    except Exception:
        pass

    from cloud_dog_idam.rbac.role_catalog import BASELINE_ROLE_NAMES

    return {"role": _role_payload(role, baseline=role.name in BASELINE_ROLE_NAMES)}


@router.put("/{role_id}")
async def update_role_put(
    role_id: str,
    request: UpdateRoleRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Replace a role's description/permissions."""
    return await _update_role(role_id, request, http_request, db, _admin)


@router.patch("/{role_id}")
async def update_role_patch(
    role_id: str,
    request: UpdateRoleRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Partially update a role's description/permissions."""
    return await _update_role(role_id, request, http_request, db, _admin)


@router.delete("/{role_id}")
async def delete_role(
    role_id: str,
    http_request: Request,
    db: Session = Depends(get_db),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Delete a role. Baseline (admin/user) roles are undeletable -> HTTP 403."""
    store = _store(db)
    store.seed_baseline()
    try:
        removed = store.delete(role_id)
    except BaselineRoleProtected as exc:
        raise HTTPException(
            status_code=403,
            detail=f"baseline role cannot be deleted: {exc}",
        )
    if not removed:
        raise HTTPException(status_code=404, detail=f"unknown role: {role_id}")

    try:
        log_audit_event(
            kind="role.deleted",
            ref=str(role_id),
            actor=_admin.username,
            data={
                "target": {"type": "role", "id": role_id, "name": role_id},
                "outcome": "success",
            },
            ip=http_request.client.host if http_request.client else None,
            user_agent=http_request.headers.get("user-agent"),
            db=db,
        )
    except Exception:
        pass
    try:
        publish_config_change_event(
            action="delete",
            resource_type="role",
            resource_id=role_id,
            actor=_admin.username,
        )
    except Exception:
        pass

    return {"message": "Role deleted successfully", "id": role_id}
