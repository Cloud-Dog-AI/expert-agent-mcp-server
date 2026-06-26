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
Vector Store Isolation and Cross-talk Prevention

License: Apache 2.0
Ownership: Cloud Dog
Description: Ensures no cross-talk/data leakage between different groups/databases

Related Requirements: FR1.3
Related Tasks: T020
Related Architecture: CC4.1.1
Related Tests: UT1.24

Recent Changes:
- Initial implementation
"""

from typing import List, Dict, Any, Optional, TYPE_CHECKING
from sqlalchemy.orm import Session

from src.database.models import GroupMember
from src.database.connection import get_db
from src.utils.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class VectorIsolationManager:
    """Manages vector store isolation to prevent cross-talk between groups."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize isolation manager.

        Args:
            db: Database session (if None, creates new)
        """
        self.db = db
        self._vector_manager = None

    @property
    def vector_manager(self):
        """Lazy import to avoid circular dependency."""
        if self._vector_manager is None:
            from src.core.vector.manager import VectorStoreManager

            self._vector_manager = VectorStoreManager(self.db)
        return self._vector_manager

    def _get_db(self) -> Session:
        """Get database session."""
        if self.db:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    def get_group_collection_name(
        self, group_id: int, base_collection: str = "expert_agent"
    ) -> str:
        """
        Generate collection name for a group to ensure isolation.

        Args:
            group_id: Group ID
            base_collection: Base collection name

        Returns:
            Group-specific collection name
        """
        return f"{base_collection}_group_{group_id}"

    def get_user_collection_name(self, user_id: int, base_collection: str = "expert_agent") -> str:
        """
        Generate collection name for a user to ensure isolation.

        Args:
            user_id: User ID
            base_collection: Base collection name

        Returns:
            User-specific collection name
        """
        return f"{base_collection}_user_{user_id}"

    def validate_group_access(self, user_id: int, group_id: int, vector_store_name: str) -> bool:
        """
        Validate that user has access to group's vector store.

        Args:
            user_id: User ID
            group_id: Group ID
            vector_store_name: Vector store name

        Returns:
            True if user has access, False otherwise
        """
        db = self._get_db()

        # Check if user is member of group
        membership = (
            db.query(GroupMember)
            .filter(GroupMember.user_id == user_id, GroupMember.group_id == group_id)
            .first()
        )

        if not membership:
            logger.warning(f"User {user_id} is not a member of group {group_id}")
            return False

        # Check vector store access control
        vector_store = self.vector_manager.get_vector_store(name=vector_store_name)
        if not vector_store:
            return False

        # Check access control
        if vector_store.access_control_json:
            import json

            access_control = json.loads(vector_store.access_control_json)
            read_groups = access_control.get("read_groups", [])
            write_groups = access_control.get("write_groups", [])

            # User must be in read or write groups
            if group_id not in read_groups and group_id not in write_groups:
                logger.warning(
                    f"Group {group_id} does not have access to vector store {vector_store_name}"
                )
                return False

        return True

    def ensure_collection_isolation(
        self,
        group_id: Optional[int] = None,
        user_id: Optional[int] = None,
        base_collection: str = "expert_agent_default",
    ) -> str:
        """
        Ensure collection name is isolated for group/user.

        Args:
            group_id: Group ID (takes precedence over user_id)
            user_id: User ID (used if group_id not provided)
            base_collection: Base collection name

        Returns:
            Isolated collection name
        """
        if group_id:
            return self.get_group_collection_name(group_id, base_collection)
        elif user_id:
            return self.get_user_collection_name(user_id, base_collection)
        else:
            # No isolation - use base collection (not recommended for production)
            logger.warning(
                "No group_id or user_id provided - using base collection without isolation"
            )
            return base_collection

    def validate_collection_access(
        self, user_id: int, collection_name: str, operation: str = "read"
    ) -> bool:
        """
        Validate that user has access to collection.

        Args:
            user_id: User ID
            collection_name: Collection name
            operation: Operation type (read, write)

        Returns:
            True if user has access, False otherwise
        """
        # Extract group_id or user_id from collection name
        if "_group_" in collection_name:
            try:
                group_id = int(collection_name.split("_group_")[1])
                return self.validate_group_access(user_id, group_id, "default")
            except (ValueError, IndexError):
                logger.error(f"Invalid group collection name format: {collection_name}")
                return False
        elif "_user_" in collection_name:
            try:
                collection_user_id = int(collection_name.split("_user_")[1])
                # User can only access their own collection
                return user_id == collection_user_id
            except (ValueError, IndexError):
                logger.error(f"Invalid user collection name format: {collection_name}")
                return False
        else:
            # Base collection - check if user has admin access
            # For now, allow access (should be restricted in production)
            logger.warning(f"Accessing base collection {collection_name} without isolation")
            return True

    def get_accessible_collections(
        self, user_id: int, base_collection: str = "expert_agent_default"
    ) -> List[str]:
        """
        Get list of collections accessible to user.

        Args:
            user_id: User ID
            base_collection: Base collection name

        Returns:
            List of accessible collection names
        """
        db = self._get_db()
        accessible = []

        # Add user's own collection
        user_collection = self.get_user_collection_name(user_id, base_collection)
        accessible.append(user_collection)

        # Add collections for groups user is member of
        memberships = db.query(GroupMember).filter(GroupMember.user_id == user_id).all()

        for membership in memberships:
            group_collection = self.get_group_collection_name(membership.group_id, base_collection)
            accessible.append(group_collection)

        return accessible

    def enforce_isolation_filter(
        self, user_id: int, base_filter: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Enforce isolation by adding filter criteria.

        Args:
            user_id: User ID
            base_filter: Base filter criteria

        Returns:
            Enhanced filter with isolation constraints
        """
        accessible_collections = self.get_accessible_collections(user_id)

        isolation_filter = base_filter or {}

        # Add collection filter (if provider supports it)
        # This would need to be handled at the provider level
        isolation_filter["_accessible_collections"] = accessible_collections

        return isolation_filter

    def verify_no_cross_talk(
        self, user_id: int, collection_name: str, operation: str = "read"
    ) -> bool:
        """
        Verify that operation won't cause cross-talk.

        Args:
            user_id: User ID
            collection_name: Collection name
            operation: Operation type

        Returns:
            True if safe, False if cross-talk risk detected
        """
        # Validate access
        if not self.validate_collection_access(user_id, collection_name, operation):
            logger.warning(
                f"Cross-talk prevention: User {user_id} denied access to {collection_name}"
            )
            return False

        # Additional checks
        if "_group_" in collection_name:
            # Verify user is still member of group
            try:
                group_id = int(collection_name.split("_group_")[1])
                db = self._get_db()
                membership = (
                    db.query(GroupMember)
                    .filter(GroupMember.user_id == user_id, GroupMember.group_id == group_id)
                    .first()
                )

                if not membership:
                    logger.warning(
                        f"Cross-talk prevention: User {user_id} no longer member of group {group_id}"
                    )
                    return False
            except (ValueError, IndexError):
                return False

        return True

    def create_isolated_collection(
        self,
        group_id: Optional[int] = None,
        user_id: Optional[int] = None,
        base_collection: str = "expert_agent_default",
        store_type: str = "qdrant",
    ) -> str:
        """
        Create an isolated collection for group or user.

        Args:
            group_id: Group ID
            user_id: User ID
            base_collection: Base collection name
            store_type: Vector store type

        Returns:
            Created collection name
        """
        collection_name = self.ensure_collection_isolation(
            group_id=group_id, user_id=user_id, base_collection=base_collection
        )

        # Collection will be created automatically when first document is added
        logger.info(
            f"Created isolated collection: {collection_name} for group={group_id}, user={user_id}"
        )

        return collection_name
