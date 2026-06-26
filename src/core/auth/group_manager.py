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
Group Management

License: Apache 2.0
Ownership: Cloud Dog
Description: Group CRUD operations and membership management

Related Requirements: FR1.5
Related Tasks: T006
Related Architecture: CC5.1.2
Related Tests: AT1.7

Recent Changes:
- Initial implementation
"""

from typing import List, Optional
from sqlalchemy.orm import Session

from src.database.models import Group, GroupMember, User

ROLE_ADMIN = "admin"
from src.database.connection import get_db
from src.utils.logger import get_logger

logger = get_logger(__name__)


class GroupManager:
    """Manages groups."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize group manager.

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

    def create_group(
        self, name: str, description: Optional[str] = None, enabled: bool = True
    ) -> Group:
        """
        Create a new group.

        Args:
            name: Group name
            description: Group description (optional)
            enabled: Whether group is enabled

        Returns:
            Created group
        """
        db = self._get_db()
        try:
            # Check if group exists
            existing = db.query(Group).filter(Group.name == name).first()
            if existing:
                raise ValueError(f"Group '{name}' already exists")

            group = Group(name=name, description=description, enabled=enabled)
            db.add(group)
            db.commit()
            db.refresh(group)

            logger.info(f"Created group: {name}")
            return group
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create group: {e}", exc_info=True)
            raise

    def get_group(
        self, group_id: Optional[int] = None, name: Optional[str] = None
    ) -> Optional[Group]:
        """Get group by ID or name."""
        db = self._get_db()
        if group_id:
            return db.query(Group).filter(Group.id == group_id).first()
        elif name:
            return db.query(Group).filter(Group.name == name).first()
        return None

    def add_member(self, group_id: int, user_id: int, role: str = "member") -> bool:
        """
        Add user to group.

        Args:
            group_id: Group ID
            user_id: User ID
            role: Member role (default: "member")

        Returns:
            True if successful
        """
        db = self._get_db()
        try:
            # Check if membership exists
            existing = (
                db.query(GroupMember)
                .filter(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
                .first()
            )
            if existing:
                return False

            membership = GroupMember(group_id=group_id, user_id=user_id, role=role)
            db.add(membership)
            db.commit()

            logger.info(f"Added user {user_id} to group {group_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to add member: {e}", exc_info=True)
            return False

    def remove_member(self, group_id: int, user_id: int) -> bool:
        """
        Remove user from group.

        Args:
            group_id: Group ID
            user_id: User ID

        Returns:
            True if successful, False if member not found or error
        """
        db = self._get_db()
        try:
            # Find and delete membership
            membership = (
                db.query(GroupMember)
                .filter(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
                .first()
            )

            if not membership:
                logger.warning(f"Member not found: user {user_id} in group {group_id}")
                return False

            db.delete(membership)
            db.commit()

            logger.info(f"Removed user {user_id} from group {group_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to remove member: {e}", exc_info=True)
            return False

    def get_group_members(self, group_id: int) -> List[User]:
        """Get all members of a group."""
        db = self._get_db()
        members = db.query(User).join(GroupMember).filter(GroupMember.group_id == group_id).all()
        return members

    def assign_group_admin(self, group_id: int, user_id: int) -> bool:
        """
        Assign a user as group admin.

        Args:
            group_id: Group ID
            user_id: User ID to assign as admin

        Returns:
            True if successful
        """
        db = self._get_db()
        try:
            # Check if membership exists
            membership = (
                db.query(GroupMember)
                .filter(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
                .first()
            )

            if membership:
                # Update existing membership to admin
                membership.role = "admin"
            else:
                # Create new membership with admin role
                membership = GroupMember(group_id=group_id, user_id=user_id, role="admin")
                db.add(membership)

            db.commit()
            logger.info(f"Assigned user {user_id} as admin for group {group_id}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to assign group admin: {e}", exc_info=True)
            return False

    def is_group_admin(self, user_id: int, group_id: int) -> bool:
        """
        Check if user is a group admin.

        Args:
            user_id: User ID
            group_id: Group ID

        Returns:
            True if user is group admin
        """
        db = self._get_db()
        membership = (
            db.query(GroupMember)
            .filter(
                GroupMember.group_id == group_id,
                GroupMember.user_id == user_id,
                GroupMember.role == ROLE_ADMIN,
            )
            .first()
        )
        return membership is not None

    def get_group_admins(self, group_id: int) -> List[User]:
        """Get all group admins."""
        db = self._get_db()
        admins = (
            db.query(User)
            .join(GroupMember)
            .filter(GroupMember.group_id == group_id, GroupMember.role == ROLE_ADMIN)
            .all()
        )
        return admins

    def remove_group_admin(self, group_id: int, user_id: int) -> bool:
        """
        Remove group admin role from user (downgrade to member).

        Args:
            group_id: Group ID
            user_id: User ID

        Returns:
            True if successful
        """
        db = self._get_db()
        try:
            membership = (
                db.query(GroupMember)
                .filter(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
                .first()
            )

            if not membership:
                return False

            if membership.role == ROLE_ADMIN:
                membership.role = "member"
                db.commit()
                logger.info(f"Removed admin role from user {user_id} in group {group_id}")
                return True

            return False
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to remove group admin: {e}", exc_info=True)
            return False

    def update_member_role(self, group_id: int, user_id: int, role: str) -> bool:
        """
        Update member role in group.

        Args:
            group_id: Group ID
            user_id: User ID
            role: New role (member, admin)

        Returns:
            True if successful
        """
        db = self._get_db()
        try:
            membership = (
                db.query(GroupMember)
                .filter(GroupMember.group_id == group_id, GroupMember.user_id == user_id)
                .first()
            )

            if not membership:
                return False

            membership.role = role
            db.commit()
            logger.info(f"Updated role for user {user_id} in group {group_id} to {role}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update member role: {e}", exc_info=True)
            return False
