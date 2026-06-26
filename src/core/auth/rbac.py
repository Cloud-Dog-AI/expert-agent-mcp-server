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
Role-Based Access Control — cloud_dog_idam wrapper.

License: Apache 2.0
Ownership: Cloud Dog
Description: RBAC enforcement via cloud_dog_idam.rbac.RBACEngine (PS-70 compliant)

Related Requirements: FR1.6
Related Tasks: T006
Related Architecture: SE1.1
Related Tests: UT1.27

Recent Changes:
- W28A-697: Replaced bespoke RBACManager (191 LOC) with cloud_dog_idam.rbac.RBACEngine
"""

from typing import Any, Dict, List, Optional

from cloud_dog_idam.audit.emitter import AuditEmitter
from cloud_dog_idam.audit.models import AuditEvent
from cloud_dog_idam.rbac import RBACEngine
from src.database.models import User

ROLE_ADMIN = "admin"
from src.utils.logger import get_logger

logger = get_logger(__name__)

# PS-70 role-permission mappings for expert-agent.
_ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "expert:tool:execute", "expert:tool:list",
        "expert:config:write", "expert:config:read",
        "expert:admin:*",
        "users:create", "users:read", "users:update", "users:delete",
        "experts:create", "experts:read", "experts:update", "experts:delete",
        "sessions:create", "sessions:read", "sessions:update", "sessions:delete",
        "audit:read", "audit:export",
    },
    "user": {
        "expert:tool:execute", "expert:tool:list",
        "expert:config:read",
        "sessions:create", "sessions:read", "sessions:update",
        "experts:read",
    },
    "viewer": {
        "expert:tool:list", "expert:config:read",
        "sessions:read", "experts:read",
    },
}

# Singleton RBAC engine.
_rbac_engine = RBACEngine(role_permissions=_ROLE_PERMISSIONS)

# Singleton audit emitter for IDAM events (PS-70 UM7).
audit_emitter = AuditEmitter(also_log_to_memory=True)


class RBACManager:
    """RBAC enforcement backed by cloud_dog_idam.rbac.RBACEngine.

    This class preserves the original RBACManager interface for backward
    compatibility while delegating all permission logic to the platform package.
    """

    def __init__(self, *, fresh_engine: bool = False) -> None:
        """Bind to the shared cloud_dog_idam RBACEngine (or a fresh one when fresh_engine=True)."""
        self._engine = RBACEngine(role_permissions=_ROLE_PERMISSIONS) if fresh_engine else _rbac_engine

    def _ensure_role_assigned(self, user: User) -> str:
        """Ensure the user's role is registered with the RBAC engine."""
        role = user.role or "user"
        user_id = str(user.id)
        self._engine.assign_role_to_user(user_id, role)
        return user_id

    def has_permission(self, user: User, resource: str, action: str) -> bool:
        """Check if user has permission for resource:action."""
        if not user or not user.enabled:
            audit_emitter.emit(AuditEvent(
                actor_id="unknown", action=f"{resource}:{action}",
                target=f"{resource}:*", outcome="denied",
                details={"reason": "user_disabled_or_missing"},
            ))
            return False

        user_id = self._ensure_role_assigned(user)
        permission = f"{resource}:{action}"
        allowed = self._engine.has_permission(user_id, permission)

        if not allowed:
            audit_emitter.emit(AuditEvent(
                actor_id=user_id, action=permission,
                target=f"{resource}:*", outcome="denied",
                details={"role": user.role or "user"},
            ))

        return allowed

    def can_access_resource(
        self, user: User, resource_type: str, resource_id: int, owner_id: Optional[int] = None,
    ) -> bool:
        """Check if user can access a specific resource."""
        if not user or not user.enabled:
            return False
        if user.role == ROLE_ADMIN:
            return True
        if owner_id and user.id == owner_id:
            return True
        return False

    def has_group_permission(self, user: User, group_id: int, action: str) -> bool:
        """Check if user has permission in group."""
        if not user or not user.enabled:
            return False
        if user.role == ROLE_ADMIN:
            return True
        return user.enabled

    def get_user_permissions(self, user: User) -> List[str]:
        """Get all permissions for user."""
        if not user or not user.enabled:
            return []
        user_id = self._ensure_role_assigned(user)
        return sorted(self._engine.get_effective_permissions(user_id))

    def is_resource_owner(
        self, user_id: int, resource_type: str, resource_id: int, owner_id: Optional[int] = None,
    ) -> bool:
        """Check if user owns a resource."""
        return owner_id is not None and user_id == owner_id

    def has_permission_with_context(
        self, user: User, resource: str, action: str, context: Dict[str, Any],
    ) -> bool:
        """Check permission with additional context."""
        if not self.has_permission(user, resource, action):
            return False
        if resource == "sessions" and action == "create":
            context_user_id = context.get("user_id")
            if context_user_id and context_user_id != user.id:
                return False
        return True
