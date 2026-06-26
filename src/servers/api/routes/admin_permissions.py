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
Admin Permissions Catalogue Route (PS-71 §IW3A — permission catalog)

License: Apache 2.0
Ownership: Cloud Dog
Description:
    The shared ``@cloud-dog/idam`` Roles/RBAC pages fetch ``{apiBase}/v1/admin/permissions``
    (the assignable-permission catalogue used to populate the role editor and binding UI).
    The expert web proxy rewrites ``/v1/admin/<entity>`` -> ``/admin/<entity>``, so this
    router publishes the catalogue at ``/admin/permissions``. Previously this route did not
    exist and returned HTTP 404 (a console error on every authed IDAM page).

    The catalogue is the sorted union of every permission string defined across the PS-70
    baseline role map (``cloud_dog_idam`` RBACEngine config) AND the persistent role store
    (``SqlAlchemyRoleStore``), so custom roles' permissions are also offered.

Related Requirements: FR1.6, PS-71 IW3A
Related Tasks: W28A-891-R2 (W28F-903 backend-parity pattern)
Related Architecture: SE1.1, CC5.1.1
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from cloud_dog_idam.storage.sqlalchemy.role_store import SqlAlchemyRoleStore
from cloud_dog_logging import get_logger

from src.core.auth.rbac import _ROLE_PERMISSIONS
from src.database.connection import get_db
from src.database.models import User
from src.servers.api.auth import verify_admin

logger = get_logger(__name__)

router = APIRouter(prefix="/admin", tags=["admin-permissions"])


@router.get("/permissions")
async def list_permissions(
    db: Session = Depends(get_db),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Return the assignable-permission catalogue (union across baseline + persisted roles)."""
    perms: set[str] = set()
    # PS-70 baseline role -> permission map (cloud_dog_idam RBACEngine config).
    for plist in _ROLE_PERMISSIONS.values():
        perms.update(str(p) for p in plist)
    # Persisted roles (survive restart) — offer their permissions too.
    try:
        store = SqlAlchemyRoleStore(db)
        store.seed_baseline()
        for role in store.list_response():
            for p in (role.get("permissions") or []):
                perms.add(str(p))
    except Exception:  # pragma: no cover - catalogue degrades to baseline if store unavailable
        logger.debug("admin/permissions: role store unavailable; baseline catalogue only")
    catalogue = sorted(perms)
    return {"permissions": catalogue, "count": len(catalogue)}
