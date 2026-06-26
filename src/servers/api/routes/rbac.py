# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
# SPDX-License-Identifier: Apache-2.0
"""RBAC binding CRUD API — W28A-276B."""
from __future__ import annotations
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from cloud_dog_idam.rbac import RBACEngine
from src.core.auth.rbac import _rbac_engine, _ROLE_PERMISSIONS
from src.servers.api.auth import require_permission
from cloud_dog_logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/rbac", tags=["rbac"], dependencies=[Depends(require_permission("users:read"))])

# In-memory binding store (same lifecycle as RBACEngine singleton).
_bindings: list[dict] = []
_next_id = 1


class BindingCreate(BaseModel):
    entity_type: str  # "user" or "group"
    entity_id: str
    role: str
    resource_type: Optional[str] = None  # "expert", "channel", "knowledge", or None (global)
    resource_id: Optional[str] = None


@router.get("/roles")
async def list_roles():
    """Return defined roles and their permissions."""
    return {
        "roles": [
            {"name": name, "permissions": sorted(perms)}
            for name, perms in _ROLE_PERMISSIONS.items()
        ]
    }


@router.get("/bindings")
async def list_bindings():
    """Return all RBAC bindings."""
    return {"bindings": _bindings, "total": len(_bindings)}


@router.post("/bindings")
async def create_binding(req: BindingCreate):
    """Create an RBAC binding."""
    global _next_id
    if req.role not in _ROLE_PERMISSIONS:
        return {"ok": False, "error": f"Unknown role: {req.role}. Valid: {sorted(_ROLE_PERMISSIONS.keys())}"}

    binding = {
        "id": _next_id,
        "entity_type": req.entity_type,
        "entity_id": req.entity_id,
        "role": req.role,
        "resource_type": req.resource_type,
        "resource_id": req.resource_id,
    }
    _next_id += 1

    # Apply to engine
    if req.entity_type == "user":
        _rbac_engine.assign_role_to_user(req.entity_id, req.role)
    elif req.entity_type == "group":
        _rbac_engine.assign_role_to_group(req.entity_id, req.role)

    _bindings.append(binding)
    logger.info(f"RBAC binding created: {binding}")
    return {"ok": True, "binding": binding}


@router.delete("/bindings/{binding_id}")
async def delete_binding(binding_id: int):
    """Delete an RBAC binding."""
    global _bindings
    found = [b for b in _bindings if b["id"] == binding_id]
    if not found:
        return {"ok": False, "error": f"Binding {binding_id} not found"}
    _bindings = [b for b in _bindings if b["id"] != binding_id]
    logger.info(f"RBAC binding deleted: {found[0]}")
    return {"ok": True, "deleted": found[0]}
