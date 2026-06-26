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
Group Management Routes

License: Apache 2.0
Ownership: Cloud Dog
Description: Group CRUD endpoints and group admin management

Related Requirements: FR1.5, FR1.27
Related Tasks: T006, T114
Related Architecture: CC5.1.2, SE1.1
Related Tests: AT1.7, AT1.84

Recent Changes:
- Initial implementation
- Added group admin management endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session
from typing import Dict, Any, Optional
from pydantic import BaseModel
from cloud_dog_cache.invalidation import CONFIG_CHANGE, invalidate_event

from src.database.connection import get_db
from src.core.auth.group_manager import GroupManager
from src.core.auth.user_manager import UserManager
from src.common.a2a_client import publish_config_change_event
from src.core.audit.logger import log_audit_event
from src.database.models import User
from src.servers.api.auth import require_permission, verify_admin, verify_api_key

router = APIRouter(prefix="/groups", tags=["groups"], dependencies=[Depends(require_permission("users:read"))])


class CreateGroupRequest(BaseModel):
    name: str
    description: Optional[str] = None
    enabled: bool = True


class UpdateGroupRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    enabled: Optional[bool] = None


class AssignGroupAdminRequest(BaseModel):
    user_id: int


class UpdateMemberRoleRequest(BaseModel):
    role: str  # "member" or "admin"


@router.post("")
async def create_group(
    request: CreateGroupRequest,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Create a new group."""
    manager = GroupManager(db)
    try:
        group = manager.create_group(
            name=request.name, description=request.description, enabled=request.enabled
        )
        try:
            log_audit_event(
                kind="group.created",
                ref=str(group.id),
                actor=str(current_user.id),
                data={"name": group.name, "enabled": group.enabled},
                db=db,
            )
        except Exception:
            pass
        publish_config_change_event(
            action="create",
            resource_type="group",
            resource_id=int(group.id),
            actor=current_user.username,
        )
        await invalidate_event(CONFIG_CHANGE)
        return {
            "id": group.id,
            "name": group.name,
            "description": group.description,
            "enabled": group.enabled,
            "created_at": group.created_at.isoformat(),
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create group: {str(e)}")


@router.get("")
async def list_groups(
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    _user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """List all groups."""
    manager = GroupManager(db)
    db_session = manager._get_db()
    from src.database.models import Group

    groups = db_session.query(Group).all()

    return {
        "total": len(groups),
        "items": [
            {
                "id": g.id,
                "name": g.name,
                "description": g.description,
                "enabled": g.enabled,
                "created_at": g.created_at.isoformat(),
            }
            for g in groups
        ],
    }


@router.get("/{group_id}")
async def get_group(
    group_id: int,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    _user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Get group by ID."""
    manager = GroupManager(db)
    group = manager.get_group(group_id=group_id)

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "enabled": group.enabled,
        "created_at": group.created_at.isoformat(),
        "updated_at": group.updated_at.isoformat(),
    }


@router.put("/{group_id}")
async def update_group(
    group_id: int,
    request: UpdateGroupRequest,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Update group."""
    manager = GroupManager(db)
    group = manager.get_group(group_id=group_id)

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Update fields
    if request.name is not None:
        group.name = request.name
    if request.description is not None:
        group.description = request.description
    if request.enabled is not None:
        group.enabled = request.enabled

    db.commit()
    db.refresh(group)
    try:
        log_audit_event(
            kind="group.updated",
            ref=str(group_id),
            actor=str(current_user.id),
            data={"updated_fields": [k for k, v in request.model_dump().items() if v is not None]},
            db=db,
        )
    except Exception:
        pass
    publish_config_change_event(
        action="update",
        resource_type="group",
        resource_id=int(group.id),
        actor=current_user.username,
    )
    await invalidate_event(CONFIG_CHANGE)

    return {
        "id": group.id,
        "name": group.name,
        "description": group.description,
        "enabled": group.enabled,
        "created_at": group.created_at.isoformat(),
        "updated_at": group.updated_at.isoformat(),
    }


@router.delete("/{group_id}")
async def delete_group(
    group_id: int,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    current_user: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Delete a group."""
    manager = GroupManager(db)
    group = manager.get_group(group_id=group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Delete group
    db.delete(group)
    db.commit()
    try:
        log_audit_event(
            kind="group.deleted",
            ref=str(group_id),
            actor=str(current_user.id),
            data={"name": group.name},
            db=db,
        )
    except Exception:
        pass
    publish_config_change_event(
        action="delete",
        resource_type="group",
        resource_id=int(group_id),
        actor=current_user.username,
    )
    await invalidate_event(CONFIG_CHANGE)

    return {"message": "Group deleted successfully", "id": group_id}


@router.get("/{group_id}/members")
async def get_group_members(
    group_id: int,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    _user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Get all members of a group."""
    manager = GroupManager(db)
    group = manager.get_group(group_id=group_id)

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    members = manager.get_group_members(group_id)
    db_session = manager._get_db()
    from src.database.models import GroupMember

    # Get member roles
    member_data = []
    for member in members:
        membership = (
            db_session.query(GroupMember)
            .filter(GroupMember.group_id == group_id, GroupMember.user_id == member.id)
            .first()
        )

        member_data.append(
            {
                "id": member.id,
                "username": member.username,
                "email": member.email,
                "display_name": member.display_name,
                "role": membership.role if membership else "member",
            }
        )

    return {"group_id": group_id, "total": len(member_data), "members": member_data}


@router.post("/{group_id}/members")
async def add_group_member(
    group_id: int,
    request: Dict[str, Any],
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Add member to group."""
    manager = GroupManager(db)
    group = manager.get_group(group_id=group_id)

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    user_id = request.get("user_id")
    role = request.get("role", "member")

    if not user_id:
        raise HTTPException(status_code=400, detail="user_id is required")

    # Verify user exists before adding to group
    user_manager = UserManager(db)
    user = user_manager.get_user(user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")

    success = manager.add_member(group_id=group_id, user_id=user_id, role=role)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to add member (may already exist)")

    return {"success": True, "group_id": group_id, "user_id": user_id, "role": role}


@router.post("/{group_id}/admins")
async def assign_group_admin(
    group_id: int,
    request: AssignGroupAdminRequest,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Assign a user as group admin."""
    manager = GroupManager(db)
    group = manager.get_group(group_id=group_id)

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Verify user exists
    user_manager = UserManager(db)
    user = user_manager.get_user(user_id=request.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    success = manager.assign_group_admin(group_id=group_id, user_id=request.user_id)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to assign group admin")

    return {
        "success": True,
        "group_id": group_id,
        "user_id": request.user_id,
        "message": f"User {request.user_id} assigned as admin for group {group_id}",
    }


@router.get("/{group_id}/admins")
async def get_group_admins(
    group_id: int,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    _user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Get all group admins."""
    manager = GroupManager(db)
    group = manager.get_group(group_id=group_id)

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    admins = manager.get_group_admins(group_id)

    return {
        "group_id": group_id,
        "total": len(admins),
        "admins": [
            {
                "id": admin.id,
                "username": admin.username,
                "email": admin.email,
                "display_name": admin.display_name,
            }
            for admin in admins
        ],
    }


@router.delete("/{group_id}/admins/{user_id}")
async def remove_group_admin(
    group_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Remove group admin role from user."""
    manager = GroupManager(db)
    group = manager.get_group(group_id=group_id)

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    success = manager.remove_group_admin(group_id=group_id, user_id=user_id)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to remove group admin")

    return {
        "success": True,
        "group_id": group_id,
        "user_id": user_id,
        "message": f"Admin role removed from user {user_id} in group {group_id}",
    }


@router.put("/{group_id}/members/{user_id}/role")
async def update_member_role(
    group_id: int,
    user_id: int,
    request: UpdateMemberRoleRequest,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Update member role in group."""
    manager = GroupManager(db)
    group = manager.get_group(group_id=group_id)

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    if request.role not in ["member", "admin"]:
        raise HTTPException(status_code=400, detail="Role must be 'member' or 'admin'")

    success = manager.update_member_role(group_id=group_id, user_id=user_id, role=request.role)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to update member role")

    return {"success": True, "group_id": group_id, "user_id": user_id, "role": request.role}


@router.delete("/{group_id}/members/{user_id}")
async def remove_group_member(
    group_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    x_api_key: Optional[str] = Header(None),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Remove member from group."""
    manager = GroupManager(db)
    group = manager.get_group(group_id=group_id)

    if not group:
        raise HTTPException(status_code=404, detail="Group not found")

    # Verify user exists
    user_manager = UserManager(db)
    user = user_manager.get_user(user_id=user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    success = manager.remove_member(group_id=group_id, user_id=user_id)

    if not success:
        raise HTTPException(status_code=400, detail="Failed to remove member (may not be in group)")

    return {
        "success": True,
        "group_id": group_id,
        "user_id": user_id,
        "message": f"User {user_id} removed from group {group_id}",
    }
