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
API Authentication Utilities

License: Apache 2.0
Ownership: Cloud Dog
Description: Authentication and authorization utilities for API routes

Related Requirements: FR1.5, FR1.11
Related Tasks: T055
Related Architecture: CC5.1.3
Related Tests: ST1.7

Recent Changes:
- Initial implementation
"""

from datetime import datetime
from typing import List, Optional

from cloud_dog_idam.api_keys.hashing import hash_api_key, key_matches
from cloud_dog_idam.domain.errors import TokenError
from cloud_dog_idam.tokens.jwt import JWTTokenService
from fastapi import Depends, Header, HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from sqlalchemy.orm import Session

from src.config.loader import get_config
from src.core.auth.api_key_manager import api_key_has_current_group_membership
from src.core.auth.expert_flat_roles import (
    READ_ONLY_ROLE,
    is_write_gated_data_path,
    role_can_write,
)
from src.core.audit.context import reset_current_principal, set_current_principal
from src.database.connection import get_db
from src.database.models import APIKey, User
from src.utils.logger import get_logger

logger = get_logger(__name__)


def job_permissions_for_role(role: Optional[str]) -> List[str]:
    """Return the PS-76 job-control permissions granted to a role.

    W28A-729-R5: flat-role aware — ``admin`` and ``read-write`` may write jobs;
    ``read-only`` (and any unknown role, fail-closed) gets read-only job access.
    """
    from src.core.auth.expert_flat_roles import (
        normalise_flat_role,
        role_can_write,
        role_is_admin,
    )

    flat = normalise_flat_role(role)
    perms: List[str] = ["read_jobs"]
    if role_can_write(flat):
        perms.append("write_jobs")
    if role_is_admin(flat):
        perms.insert(0, "admin")
    return perms


def _build_token_service() -> JWTTokenService:
    auth_config = get_config("auth")
    if not isinstance(auth_config, dict):
        auth_config = {}
    return JWTTokenService(
        secret=str(auth_config.get("jwt_secret") or ""),
        issuer=str(auth_config.get("issuer") or "expert-agent"),
        audience=str(auth_config.get("audience") or "expert-agent-users"),
        algorithm=str(auth_config.get("algorithm") or "HS256"),
        access_ttl=int(auth_config.get("session_timeout_minutes") or 60) * 60,
    )


_TOKEN_SERVICE = _build_token_service()


def _resolve_db_argument(
    authorization: Optional[str], db: Session
) -> tuple[Optional[str], Session]:
    """Support direct calls like verify_api_key(x_api_key, db) in legacy routes."""
    if isinstance(authorization, Session) and not isinstance(db, Session):
        return None, authorization
    return authorization, db


def _validate_api_key_user(x_api_key: str, db: Session) -> Optional[User]:
    now = datetime.utcnow()
    key_hash = hash_api_key(x_api_key)
    api_key = (
        db.query(APIKey).filter(APIKey.key_hash == key_hash, APIKey.revoked.is_(False)).first()
    )

    # Compatibility fallback: legacy rows may have been hashed outside idam hash helper.
    if not api_key:
        for candidate in db.query(APIKey).filter(APIKey.revoked.is_(False)).all():
            if key_matches(x_api_key, str(candidate.key_hash)):
                api_key = candidate
                break

    if not api_key:
        return None
    if api_key.expires_at and api_key.expires_at < now:
        return None

    user = db.query(User).filter(User.id == api_key.user_id).first() if api_key.user_id else None
    if not user or not user.enabled:
        return None
    if not api_key_has_current_group_membership(api_key, db):
        return None

    api_key.last_used_at = now
    db.commit()
    return user


async def verify_api_key(
    x_api_key: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    """
    Verify API key and return associated user.

    Args:
        x_api_key: API key from header
        db: Database session

    Returns:
        User object if valid

    Raises:
        HTTPException: If API key is missing or invalid
    """
    authorization, db = _resolve_db_argument(authorization, db)

    # Prefer API key when provided; otherwise accept Bearer JWT.
    if x_api_key:
        user = _validate_api_key_user(x_api_key, db)
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
        return user

    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            claims = _TOKEN_SERVICE.verify(token)
        except TokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
            )
        user_id = claims.get("user_id", claims.get("sub"))
        try:
            user_id_int = int(user_id)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token"
            )
        user = db.query(User).filter(User.id == user_id_int).first()
        if user and user.enabled:
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token not associated with an active user",
        )

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Missing authentication (X-API-Key or Authorization: Bearer <token>)",
    )


async def verify_admin(user: User = Depends(verify_api_key)) -> User:
    """
    Verify user is an admin.

    Args:
        user: User from verify_api_key dependency

    Returns:
        User object if admin

    Raises:
        HTTPException: If user is not an admin
    """
    if user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")

    return user


# W28A-729-R5: the read-write (DB role "user") and read-only (DB role "viewer")
# flat WebUI roles must be able to VIEW the data surfaces the WebUI exposes. The
# data routers gate reads on "expert:read" (channels/knowledge/services/jobs/
# files/vector-stores/api-docs), "experts:read" (experts/prompts), or
# "sessions:read" (sessions). Grant the read perms for those named surfaces —
# READ ONLY: no create/update/delete. Writes remain gated (route-level
# verify_admin) and the WebUI read-only write-gate returns 403 before the proxy.
# Admin/IDAM surfaces (users/groups/rbac/api-keys -> users:read; audit ->
# audit:read) deliberately stay admin-only and are NOT granted here.
_DATA_READ_PERMISSIONS = {
    "expert:read",
    "experts:read",
    "sessions:read",
    "channels:read",
    "knowledge:read",
    "prompts:read",
    "services:read",
}

_RBAC_ROLE_PERMISSIONS = {
    "admin": {"*"},
    "owner": {"expert:*", "users:read", "sessions:*"},
    # read-write: data reads + use/execute + own-session create (no admin CRUD).
    "user": {"expert:execute", "sessions:create"} | _DATA_READ_PERMISSIONS,
    # read-only: data reads ONLY (view); every write resolves to 403.
    "viewer": set(_DATA_READ_PERMISSIONS),
}


def require_permission(permission: str):
    """RBAC permission guard backed by cloud_dog_idam.rbac.RBACEngine.

    Usage: ``Depends(require_permission("sessions:read"))``
    """
    async def _guard(user: User = Depends(verify_api_key)) -> User:
        from cloud_dog_idam.rbac import RBACEngine
        engine = RBACEngine(role_permissions=_RBAC_ROLE_PERMISSIONS)
        principal = f"user:{user.id}"
        engine.assign_role_to_user(principal, user.role or "user")
        parts = permission.split(":")
        resource = parts[0] if parts else permission
        action = parts[1] if len(parts) > 1 else "*"
        perm_str = f"{resource}:{action}"
        if not engine.has_permission(principal, perm_str):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission}",
            )
        return user
    return _guard


async def verify_jobs_read(user: User = Depends(verify_api_key)) -> User:
    """Allow any authenticated active user to view job data."""
    if not user.enabled:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Job read access required")
    return user


async def verify_jobs_write(user: User = Depends(verify_api_key)) -> User:
    """Allow only job-control writers to mutate jobs."""
    if "write_jobs" not in job_permissions_for_role(user.role):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Job write access required")
    return user


class AuthStateMiddleware(BaseHTTPMiddleware):
    """Store authenticated user identity in request.state for audit logging.

    Runs early in the middleware stack so that AuditMiddleware (from
    cloud_dog_logging) can read request.state.user and attribute audit
    events to the actual caller instead of 'anonymous'.
    """

    async def dispatch(self, request: Request, call_next):
        # Try to identify user from API key or JWT without blocking
        # unauthenticated requests (health, docs, etc.).
        x_api_key = request.headers.get("x-api-key")
        authorization = request.headers.get("authorization")
        user = None

        if x_api_key or (authorization and authorization.lower().startswith("bearer ")):
            try:
                db = next(get_db())
                try:
                    if x_api_key:
                        user = _validate_api_key_user(x_api_key, db)
                    elif authorization:
                        token = authorization.split(" ", 1)[1].strip()
                        claims = _TOKEN_SERVICE.verify(token)
                        user_id = claims.get("user_id", claims.get("sub"))
                        user = db.query(User).filter(User.id == int(user_id)).first()
                finally:
                    db.close()
            except Exception:
                pass  # Don't block the request — auth errors handled by route-level Depends

        principal_tokens = None
        if user:
            request.state.user = user
            # EA8 (W28M-FIX-1614): publish the authenticated principal so audit
            # emitters can stamp actor.id without function-signature plumbing.
            principal_tokens = set_current_principal(user.id, user.username, user.role)

        try:
            return await call_next(request)
        finally:
            if principal_tokens is not None:
                reset_current_principal(principal_tokens)


_WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class ReadOnlyApiWriteGateMiddleware(BaseHTTPMiddleware):
    """W28A-729-R5 — API-tier read-only write-gate (closes the direct-/api hole).

    The WebUI write-gate lives in the web proxy (``web_api_proxy``), but a
    read-only session can also reach the API server DIRECTLY (Traefik routes
    ``/api`` → API server, bypassing the web proxy). Several data routers gate
    only on a router-level ``require_permission("…:read")`` + ``verify_api_key``
    on their write routes, so a read-capable role (``viewer`` = the read-only
    flat role) would otherwise pass straight through to writes.

    This enforces the same flat-role write-gate at the API tier: a read-only
    caller is denied 403 on write methods to data paths. It reuses the user
    already resolved by ``AuthStateMiddleware`` (``request.state.user``) — no
    re-auth. read-write / admin pass through to the route's own auth; anonymous
    / invalid callers are left untouched so the route returns its normal 401.
    Auth (login/logout) and health paths are never gated.
    """

    async def dispatch(self, request: Request, call_next):
        """Deny a read-only caller (403) on write methods to gated data paths; pass others through."""
        if request.method in _WRITE_METHODS:
            path = request.url.path
            if (
                is_write_gated_data_path(path)
                and "/auth/" not in path
                and not path.rstrip("/").endswith("/auth")
            ):
                user = getattr(request.state, "user", None)
                if user is not None and not role_can_write(getattr(user, "role", None)):
                    return JSONResponse(
                        status_code=status.HTTP_403_FORBIDDEN,
                        content={
                            "detail": "read-only role: write operations are not permitted",
                            "role": READ_ONLY_ROLE,
                        },
                    )
        return await call_next(request)
