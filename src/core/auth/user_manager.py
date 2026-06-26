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
User Management

License: Apache 2.0
Ownership: Cloud Dog
Description: User CRUD operations and authentication

Related Requirements: FR1.5
Related Tasks: T005
Related Architecture: CC5.1.1
Related Tests: AT1.7

Recent Changes:
- Initial implementation
"""

from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from src.database.models import User
from src.database.connection import get_db
from src.core.auth.audit import log_authentication_event
from src.core.auth.password import hash_password, verify_password, validate_password_policy
from src.utils.logger import get_logger

logger = get_logger(__name__)


class UserManager:
    """Manages users."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize user manager.

        Args:
            db: Database session (if None, creates new)
        """
        self.db = db

    def _get_db(self) -> Session:
        """Get database session."""
        if self.db:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    def create_user(
        self,
        username: str,
        email: str,
        password: Optional[str] = None,
        display_name: Optional[str] = None,
        role: str = "user",
        enabled: bool = True,
        user_type: Optional[str] = None,
    ) -> User:
        """
        Create a new user.

        Args:
            username: Username
            email: Email address
            password: Password (optional, for local users)
            display_name: Display name (optional)
            role: User role (default: "user")
            enabled: Whether user is enabled

        Returns:
            Created user
        """
        db = self._get_db()
        try:
            # Check if user exists
            existing = (
                db.query(User).filter((User.username == username) | (User.email == email)).first()
            )
            if existing:
                raise ValueError(
                    f"User with username '{username}' or email '{email}' already exists"
                )

            # Enforce password policy for local users (config-driven)
            validate_password_policy(password)

            # Determine user_type: if user_type is provided, use it; otherwise infer from password
            if user_type is None:
                user_type = "external" if password is None else "local"

            user = User(
                username=username,
                email=email,
                display_name=display_name or username,
                pwd_hash=hash_password(password) if password else None,
                role=role,
                enabled=enabled,
                user_type=user_type,
            )
            db.add(user)
            db.commit()
            db.refresh(user)

            logger.info(f"Created user: {username}")
            return user
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create user: {e}", exc_info=True)
            raise

    def get_user(
        self, user_id: Optional[int] = None, username: Optional[str] = None
    ) -> Optional[User]:
        """Get user by ID or username."""
        db = self._get_db()
        if user_id:
            return db.query(User).filter(User.id == user_id).first()
        elif username:
            return db.query(User).filter(User.username == username).first()
        return None

    def authenticate(self, username: str, password: str) -> Optional[User]:
        """
        Authenticate user.

        Args:
            username: Username
            password: Password

        Returns:
            User if authenticated, None otherwise
        """
        user = self.get_user(username=username)
        if not user:
            log_authentication_event(username, "failure", reason="user_not_found")
            return None

        if not user.enabled:
            log_authentication_event(
                username,
                "failure",
                user_id=user.id,
                roles=[user.role],
                reason="user_disabled",
            )
            return None

        if not user.pwd_hash:
            # External user, cannot authenticate with password
            log_authentication_event(
                username,
                "failure",
                user_id=user.id,
                roles=[user.role],
                reason="password_auth_not_supported",
            )
            return None

        if verify_password(password, user.pwd_hash):
            log_authentication_event(username, "success", user_id=user.id, roles=[user.role])
            return user

        log_authentication_event(
            username,
            "failure",
            user_id=user.id,
            roles=[user.role],
            reason="invalid_password",
        )
        return None

    def update_user(self, user_id: int, **kwargs) -> Optional[User]:
        """Update user."""
        db = self._get_db()
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return None

            # Update allowed fields
            allowed_fields = [
                "username",
                "display_name",
                "email",
                "role",
                "enabled",
                "language",
                "timezone",
                "password",
            ]
            for field, value in kwargs.items():
                if field in allowed_fields and value is not None:
                    if field == "password":
                        validate_password_policy(value)
                        user.pwd_hash = hash_password(value)
                    else:
                        setattr(user, field, value)

            db.commit()
            db.refresh(user)

            logger.info(f"Updated user: {user_id}")
            return user
        except IntegrityError as e:
            db.rollback()
            logger.warning(f"User update integrity error: {e}", exc_info=True)
            # Most commonly: duplicate username/email constraint
            raise ValueError("User with that username or email already exists")
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update user: {e}", exc_info=True)
            raise
