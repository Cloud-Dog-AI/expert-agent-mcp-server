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
Authentication Routes

License: Apache 2.0
Ownership: Cloud Dog
Description: Authentication endpoints (login/logout/token validation)
"""

from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from src.core.auth.user_manager import UserManager
from src.core.auth.password import verify_password
from src.core.auth.token import TokenManager
from src.core.auth.lockout import LockoutManager
from src.database.models import User
from src.servers.api.auth import verify_api_key, verify_admin
from src.database.connection import get_db


router = APIRouter(prefix="/auth", tags=["auth"])

# Token revocation must persist across requests for tests; keep a module-level manager.
_token_manager = TokenManager()
_lockout = LockoutManager()


class RegisterRequest(BaseModel):
    username: str
    email: str
    password: Optional[str] = None
    display_name: Optional[str] = None


@router.post("/register")
async def register(request: RegisterRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Public user registration endpoint (no authentication required)."""
    manager = UserManager(db)
    try:
        user = manager.create_user(
            username=request.username,
            email=request.email,
            password=request.password,  # Can be None for external users
            display_name=request.display_name or request.username,
            role="user",
        )
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
            "enabled": user.enabled,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


class LoginRequest(BaseModel):
    username: str
    password: str
    # Optional test hook: request a custom short expiry (seconds)
    expires_in_seconds: Optional[int] = None


@router.post("/login")
async def login(request: LoginRequest, db: Session = Depends(get_db)) -> Dict[str, Any]:
    """Authenticate user and return a JWT token."""
    subject = str(request.username or "").strip()
    if _lockout.is_locked(subject):
        raise HTTPException(
            status_code=429, detail="Too many failed login attempts. Try again later."
        )

    manager = UserManager(db)
    user = manager.authenticate(subject, request.password)
    if not user:
        _lockout.register_failure(subject)
        raise HTTPException(status_code=401, detail="Invalid username or password")

    _lockout.register_success(subject)

    token = _token_manager.generate_token(user_id=user.id, expires_in=request.expires_in_seconds)
    return {"token": token, "user_id": user.id}


class LogoutRequest(BaseModel):
    token: str


@router.post("/logout")
async def logout(request: LogoutRequest) -> Dict[str, Any]:
    """Revoke a JWT token."""
    _token_manager.revoke_token(request.token)
    return {"revoked": True}


@router.get("/validate")
async def validate(token: str) -> Dict[str, Any]:
    """Validate a JWT token."""
    is_valid, user_id = _token_manager.validate_token(token)
    return {"valid": is_valid, "user_id": user_id}


class RefreshRequest(BaseModel):
    token: str


@router.post("/refresh")
async def refresh(request: RefreshRequest) -> Dict[str, Any]:
    """Refresh a JWT token (returns a new token if current token is valid)."""
    new_token = _token_manager.refresh_token(request.token)
    if not new_token:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return {"token": new_token}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    request: ChangePasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(verify_api_key),
) -> Dict[str, Any]:
    """Change password for the authenticated local user."""
    manager = UserManager(db)
    user = manager.get_user(user_id=current_user.id)
    if not user or not user.enabled:
        raise HTTPException(status_code=401, detail="Invalid user")
    if not user.pwd_hash:
        raise HTTPException(
            status_code=400, detail="Password change not available for external users"
        )
    if not verify_password(request.current_password, user.pwd_hash):
        raise HTTPException(status_code=401, detail="Invalid current password")

    manager.update_user(user.id, password=request.new_password)
    return {"changed": True}


class AdminResetPasswordRequest(BaseModel):
    user_id: int
    new_password: str


@router.post("/admin-reset-password")
async def admin_reset_password(
    request: AdminResetPasswordRequest,
    db: Session = Depends(get_db),
    _admin: User = Depends(verify_admin),
) -> Dict[str, Any]:
    """Admin-only: reset a user's password (local auth only)."""
    manager = UserManager(db)
    user = manager.get_user(user_id=request.user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    manager.update_user(user.id, password=request.new_password)
    return {"reset": True, "user_id": user.id}
