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
API Key Management

License: Apache 2.0
Ownership: Cloud Dog
Description: API key generation, validation, and management

Related Requirements: FR1.11
Related Tasks: T055
Related Architecture: CC5.1.3
Related Tests: ST1.7

Recent Changes:
- Initial implementation
"""

import secrets
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from cloud_dog_idam.api_keys.hashing import hash_api_key

from src.core.auth.audit import log_api_key_event
from src.database.models import APIKey, Group, GroupMember
from src.database.connection import get_db
from src.utils.logger import get_logger

logger = get_logger(__name__)


def api_key_has_current_group_membership(api_key: APIKey, db: Session) -> bool:
    """Return whether a group-bound key is still backed by live membership.

    Group-scoped keys are deliberately revocable by membership removal. A key
    bound to a disabled/deleted group, a disabled/deleted user, or a user who is
    no longer a member of the bound group must fail closed.
    """
    if api_key.group_id is None:
        return True
    if api_key.user_id is None:
        return False

    group = db.query(Group).filter(Group.id == api_key.group_id).first()
    if not group or not group.enabled:
        return False

    membership = (
        db.query(GroupMember)
        .filter(
            GroupMember.group_id == api_key.group_id,
            GroupMember.user_id == api_key.user_id,
        )
        .first()
    )
    return membership is not None


class APIKeyManager:
    """Manages API keys."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize API key manager.

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

    def _hash_key(self, key: str) -> str:
        """Hash API key for storage."""
        return hash_api_key(key)

    def generate_key(
        self,
        user_id: Optional[int] = None,
        group_id: Optional[int] = None,
        name: Optional[str] = None,
        scopes: Optional[List[str]] = None,
        expires_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Generate a new API key.

        Args:
            user_id: User ID (optional)
            group_id: Group ID (optional)
            name: Key name (optional)
            scopes: List of scopes (optional)
            expires_days: Days until expiration (optional)

        Returns:
            Dict with 'key' (plain text) and 'api_key' (database object)
        """
        db = self._get_db()
        try:
            # Generate secure random key
            plain_key = f"ea_{secrets.token_urlsafe(32)}"
            key_hash = self._hash_key(plain_key)

            # Calculate expiration
            expires_at = None
            if expires_days:
                expires_at = datetime.utcnow() + timedelta(days=expires_days)

            # Create API key record
            api_key = APIKey(
                key_hash=key_hash,
                user_id=user_id,
                group_id=group_id,
                name=name,
                scopes_json=str(scopes) if scopes else None,
                expires_at=expires_at,
            )
            db.add(api_key)
            db.commit()
            db.refresh(api_key)

            log_api_key_event(
                "api_key_generate",
                "success",
                key_id=str(api_key.id),
                user_id=user_id,
                group_id=group_id,
                key_name=name,
            )

            return {"key": plain_key, "api_key": api_key}
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to generate API key: {e}", exc_info=True)
            raise

    def validate_key(self, key: str) -> Optional[APIKey]:
        """
        Validate API key.

        Args:
            key: Plain text API key

        Returns:
            APIKey object if valid, None otherwise
        """
        db = self._get_db()
        key_hash = self._hash_key(key)

        api_key = (
            db.query(APIKey)
            .filter(
                APIKey.key_hash == key_hash,
                APIKey.revoked.is_(False),
            )
            .first()
        )

        if not api_key:
            return None

        # Check expiration
        if api_key.expires_at and api_key.expires_at < datetime.utcnow():
            log_api_key_event(
                "api_key_validate",
                "failure",
                key_id=str(api_key.id),
                user_id=api_key.user_id,
                group_id=api_key.group_id,
                key_name=api_key.name,
                reason="expired",
            )
            return None

        if not api_key_has_current_group_membership(api_key, db):
            log_api_key_event(
                "api_key_validate",
                "failure",
                key_id=str(api_key.id),
                user_id=api_key.user_id,
                group_id=api_key.group_id,
                key_name=api_key.name,
                reason="group_membership_required",
            )
            return None

        # Update last used
        api_key.last_used_at = datetime.utcnow()
        db.commit()

        return api_key

    def revoke_key(self, key_id: int) -> bool:
        """Revoke an API key."""
        db = self._get_db()
        try:
            api_key = db.query(APIKey).filter(APIKey.id == key_id).first()
            if not api_key:
                return False

            api_key.revoked = True
            db.commit()

            log_api_key_event(
                "api_key_revoke",
                "success",
                key_id=str(key_id),
                user_id=api_key.user_id,
                group_id=api_key.group_id,
                key_name=api_key.name,
            )
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to revoke API key: {e}", exc_info=True)
            return False

    def get_user_keys(self, user_id: int) -> List[APIKey]:
        """Get all API keys for a user."""
        db = self._get_db()
        return db.query(APIKey).filter(APIKey.user_id == user_id).all()

    def get_group_keys(self, group_id: int) -> List[APIKey]:
        """Get all API keys for a group."""
        db = self._get_db()
        return db.query(APIKey).filter(APIKey.group_id == group_id).all()
