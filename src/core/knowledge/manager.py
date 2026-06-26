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
Knowledge History Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Manages knowledge history with permission-based access control

Related Requirements: FR1.31, FR1.39, UC1.26
Related Tasks: T118
Related Architecture: CC4.1
Related Tests: AT1.88

Recent Changes:
- Initial implementation
"""

import json
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.core.auth.group_manager import GroupManager

ROLE_ADMIN = "admin"
from src.core.auth.user_manager import UserManager
from src.utils.logger import get_logger

logger = get_logger(__name__)


class KnowledgeHistoryManager:
    """Manages knowledge history with permission-based access control."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize knowledge history manager.

        Args:
            db: Database session (if None, creates new)
        """
        self.db = db
        self.group_manager = GroupManager(db)
        self.user_manager = UserManager(db)
        # NOTE: We intentionally store knowledge history in SQL for versioning/rollback.

    def _get_db(self) -> Session:
        """Get database session."""
        if self.db:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    def _check_permission(
        self, user_id: int, knowledge_type: str, knowledge_id: int, operation: str = "read"
    ) -> bool:
        """
        Check if user has permission to perform operation on knowledge.

        Args:
            user_id: User ID
            knowledge_type: Type of knowledge (user, group, session)
            knowledge_id: Knowledge ID (user_id, group_id, or session_id)
            operation: Operation type (read, write, delete)

        Returns:
            True if user has permission
        """
        db = self._get_db()
        from src.database.models import User

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return False

        # System admin can do everything
        if user.role == ROLE_ADMIN:
            return True

        if knowledge_type == "user":
            # Users can manage their own knowledge
            if knowledge_id == user_id:
                return True
            # Group admins can manage group members' knowledge
            # Check if user is group admin and knowledge_id is a member of their group
            # This is simplified - in production, check group membership
            return False

        elif knowledge_type == "group":
            # Group admins can manage their group's knowledge
            if self.group_manager.is_group_admin(user_id, knowledge_id):
                return True
            # Group members can read their group's knowledge
            if operation == "read":
                # Check if user is member of group
                db = self._get_db()
                from src.database.models import GroupMember

                membership = (
                    db.query(GroupMember)
                    .filter(GroupMember.group_id == knowledge_id, GroupMember.user_id == user_id)
                    .first()
                )
                return membership is not None
            return False

        elif knowledge_type == "session":
            # Session participants can manage session knowledge
            # Check if user is participant in session
            db = self._get_db()
            from src.database.models import Session as SessionModel

            session = db.query(SessionModel).filter(SessionModel.id == knowledge_id).first()
            if session and session.user_id == user_id:
                return True
            # Group admins can manage sessions in their groups
            if session:
                # Get expert config to find group
                from src.database.models import ExpertConfig

                expert = (
                    db.query(ExpertConfig)
                    .filter(ExpertConfig.id == session.expert_config_id)
                    .first()
                )
                if expert:
                    # Check if user is group admin of expert's group
                    # This is simplified - in production, check expert-group mapping
                    pass
            return False

        return False

    def _get_current_version(self, knowledge_type: str, knowledge_id: int):
        db = self._get_db()
        from src.database.models import KnowledgeVersion

        return (
            db.query(KnowledgeVersion)
            .filter(
                KnowledgeVersion.knowledge_type == knowledge_type,
                KnowledgeVersion.knowledge_id == knowledge_id,
                KnowledgeVersion.is_current,
            )
            .order_by(KnowledgeVersion.version.desc())
            .first()
        )

    def _ensure_initial_version(
        self, knowledge_type: str, knowledge_id: int, created_by_user_id: int
    ):
        db = self._get_db()
        from src.database.models import KnowledgeVersion

        current = self._get_current_version(knowledge_type, knowledge_id)
        if current:
            return current
        v = KnowledgeVersion(
            knowledge_type=knowledge_type,
            knowledge_id=knowledge_id,
            version=1,
            is_current=True,
            note="initial",
            created_by_user_id=created_by_user_id,
        )
        db.add(v)
        db.commit()
        db.refresh(v)
        return v

    def _create_new_version_from_current(
        self,
        knowledge_type: str,
        knowledge_id: int,
        created_by_user_id: int,
        note: Optional[str] = None,
        keep_entries: Optional[List[Dict[str, Any]]] = None,
    ):
        db = self._get_db()
        from src.database.models import KnowledgeVersion, KnowledgeEntry

        current = self._ensure_initial_version(knowledge_type, knowledge_id, created_by_user_id)
        # Mark old current false
        current.is_current = False
        new_v = KnowledgeVersion(
            knowledge_type=knowledge_type,
            knowledge_id=knowledge_id,
            version=int(current.version) + 1,
            is_current=True,
            note=note,
            created_by_user_id=created_by_user_id,
        )
        db.add(new_v)
        db.flush()

        # Copy entries
        entries_to_copy: List[KnowledgeEntry] = []
        if keep_entries is None:
            # Copy from current version rows
            for e in current.entries:
                entries_to_copy.append(
                    KnowledgeEntry(
                        knowledge_version_id=new_v.id,
                        content=e.content,
                        metadata_json=e.metadata_json,
                    )
                )
        else:
            for e in keep_entries:
                entries_to_copy.append(
                    KnowledgeEntry(
                        knowledge_version_id=new_v.id,
                        content=e["content"],
                        metadata_json=json.dumps(e.get("metadata", {}))
                        if e.get("metadata") is not None
                        else None,
                    )
                )
        for e in entries_to_copy:
            db.add(e)
        db.commit()
        db.refresh(new_v)
        return new_v

    def get_knowledge_history(
        self,
        user_id: int,
        knowledge_type: str,
        knowledge_id: int,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """
        Get knowledge history.

        Args:
            user_id: User ID requesting access
            knowledge_type: Type of knowledge (user, group, session)
            knowledge_id: Knowledge ID
            limit: Maximum number of entries
            offset: Offset for pagination

        Returns:
            List of knowledge history entries
        """
        if not self._check_permission(user_id, knowledge_type, knowledge_id, "read"):
            raise PermissionError(
                f"User {user_id} does not have read permission for {knowledge_type} {knowledge_id}"
            )

        db = self._get_db()
        from src.database.models import KnowledgeEntry

        current = self._ensure_initial_version(knowledge_type, knowledge_id, user_id)
        query = (
            db.query(KnowledgeEntry)
            .filter(KnowledgeEntry.knowledge_version_id == current.id)
            .order_by(KnowledgeEntry.created_at.asc())
        )
        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)
        rows = query.all()
        return [
            {
                "id": r.id,
                "content": r.content,
                "metadata": json.loads(r.metadata_json) if r.metadata_json else {},
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "version": current.version,
            }
            for r in rows
        ]

    def add_knowledge(
        self,
        user_id: int,
        knowledge_type: str,
        knowledge_id: int,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Add knowledge entry.

        Args:
            user_id: User ID adding knowledge
            knowledge_type: Type of knowledge (user, group, session)
            knowledge_id: Knowledge ID
            content: Knowledge content
            metadata: Additional metadata

        Returns:
            Created knowledge entry
        """
        if not self._check_permission(user_id, knowledge_type, knowledge_id, "write"):
            raise PermissionError(
                f"User {user_id} does not have write permission for {knowledge_type} {knowledge_id}"
            )

        db = self._get_db()
        from src.database.models import KnowledgeEntry

        self._ensure_initial_version(knowledge_type, knowledge_id, user_id)
        # Create a new version for the write (immutable history)
        new_v = self._create_new_version_from_current(
            knowledge_type,
            knowledge_id,
            created_by_user_id=user_id,
            note="add",
        )
        # Append new entry to new version
        entry = KnowledgeEntry(
            knowledge_version_id=new_v.id,
            content=content,
            metadata_json=json.dumps(metadata or {}),
        )
        db.add(entry)
        db.commit()
        db.refresh(entry)
        logger.info(
            f"Added knowledge entry for {knowledge_type} {knowledge_id} v{new_v.version} by user {user_id}"
        )
        return {
            "id": entry.id,
            "content": entry.content,
            "metadata": metadata or {},
            "created_at": entry.created_at.isoformat() if entry.created_at else None,
            "version": new_v.version,
        }

    def update_knowledge(
        self,
        user_id: int,
        knowledge_type: str,
        knowledge_id: int,
        entry_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Update knowledge entry.

        Args:
            user_id: User ID updating knowledge
            knowledge_type: Type of knowledge
            knowledge_id: Knowledge ID
            entry_id: Entry ID
            content: Updated content (optional)
            metadata: Updated metadata (optional)

        Returns:
            Updated knowledge entry
        """
        if not self._check_permission(user_id, knowledge_type, knowledge_id, "write"):
            raise PermissionError(
                f"User {user_id} does not have write permission for {knowledge_type} {knowledge_id}"
            )

        self._get_db()

        current = self._ensure_initial_version(knowledge_type, knowledge_id, user_id)
        # Load current entries, update the matching one, create new version
        current_entries = [
            {
                "content": e.content,
                "metadata": json.loads(e.metadata_json) if e.metadata_json else {},
                "id": e.id,
            }
            for e in current.entries
        ]
        updated = False
        for e in current_entries:
            if str(e["id"]) == str(entry_id):
                if content is not None:
                    e["content"] = content
                if metadata is not None:
                    e["metadata"] = metadata
                updated = True
        if not updated:
            raise ValueError("Entry not found")

        new_v = self._create_new_version_from_current(
            knowledge_type,
            knowledge_id,
            created_by_user_id=user_id,
            note="update",
            keep_entries=[
                {"content": e["content"], "metadata": e["metadata"]} for e in current_entries
            ],
        )
        # Return the updated entry (by content match; sufficient for API contract)
        return {
            "type": knowledge_type,
            "knowledge_id": knowledge_id,
            "version": new_v.version,
            "updated": True,
        }

    def delete_knowledge(
        self, user_id: int, knowledge_type: str, knowledge_id: int, entry_id: Optional[str] = None
    ) -> bool:
        """
        Delete knowledge entry or all knowledge.

        Args:
            user_id: User ID deleting knowledge
            knowledge_type: Type of knowledge
            knowledge_id: Knowledge ID
            entry_id: Entry ID (if None, delete all)

        Returns:
            True if successful
        """
        if not self._check_permission(user_id, knowledge_type, knowledge_id, "delete"):
            raise PermissionError(
                f"User {user_id} does not have delete permission for {knowledge_type} {knowledge_id}"
            )

        self._get_db()
        current = self._ensure_initial_version(knowledge_type, knowledge_id, user_id)
        if entry_id:
            keep = [
                {
                    "content": e.content,
                    "metadata": json.loads(e.metadata_json) if e.metadata_json else {},
                    "id": e.id,
                }
                for e in current.entries
                if str(e.id) != str(entry_id)
            ]
        else:
            keep = []
        self._create_new_version_from_current(
            knowledge_type,
            knowledge_id,
            created_by_user_id=user_id,
            note="delete",
            keep_entries=[{"content": e["content"], "metadata": e["metadata"]} for e in keep],
        )
        return True

    def list_versions(
        self, user_id: int, knowledge_type: str, knowledge_id: int
    ) -> List[Dict[str, Any]]:
        if not self._check_permission(user_id, knowledge_type, knowledge_id, "read"):
            raise PermissionError("Permission denied")
        db = self._get_db()
        from src.database.models import KnowledgeVersion

        rows = (
            db.query(KnowledgeVersion)
            .filter(
                KnowledgeVersion.knowledge_type == knowledge_type,
                KnowledgeVersion.knowledge_id == knowledge_id,
            )
            .order_by(KnowledgeVersion.version.asc())
            .all()
        )
        return [
            {
                "version": r.version,
                "is_current": bool(r.is_current),
                "note": r.note,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ]

    def rollback(self, user_id: int, knowledge_type: str, knowledge_id: int, version: int) -> bool:
        if not self._check_permission(user_id, knowledge_type, knowledge_id, "write"):
            raise PermissionError("Permission denied")
        db = self._get_db()
        from src.database.models import KnowledgeVersion

        rows = (
            db.query(KnowledgeVersion)
            .filter(
                KnowledgeVersion.knowledge_type == knowledge_type,
                KnowledgeVersion.knowledge_id == knowledge_id,
            )
            .all()
        )
        target = next((r for r in rows if int(r.version) == int(version)), None)
        if not target:
            raise ValueError("Version not found")
        for r in rows:
            r.is_current = r.id == target.id
        db.commit()
        return True

    def remove_by_filter(
        self,
        user_id: int,
        knowledge_type: str,
        knowledge_id: int,
        keyword: Optional[str] = None,
        channel_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        if not self._check_permission(user_id, knowledge_type, knowledge_id, "delete"):
            raise PermissionError("Permission denied")
        current = self._ensure_initial_version(knowledge_type, knowledge_id, user_id)
        kept: List[Dict[str, Any]] = []
        removed = 0
        for e in current.entries:
            meta = json.loads(e.metadata_json) if e.metadata_json else {}
            if keyword and keyword.lower() in (e.content or "").lower():
                removed += 1
                continue
            if channel_id is not None and int(meta.get("channel_id", -1)) == int(channel_id):
                removed += 1
                continue
            kept.append({"content": e.content, "metadata": meta})

        new_v = self._create_new_version_from_current(
            knowledge_type,
            knowledge_id,
            created_by_user_id=user_id,
            note="remove",
            keep_entries=kept,
        )
        return {"removed": removed, "version": new_v.version}

    def list_knowledge(
        self, user_id: int, knowledge_type: Optional[str] = None, knowledge_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        List knowledge entries accessible to user.

        Args:
            user_id: User ID
            knowledge_type: Filter by type (optional)
            knowledge_id: Filter by ID (optional)

        Returns:
            List of knowledge entries
        """
        db = self._get_db()
        from src.database.models import (
            User,
            GroupMember,
            Session as SessionModel,
            KnowledgeVersion,
            KnowledgeEntry,
        )

        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            return []

        # Build accessible scope map.
        allowed: Dict[str, set[int]] = {
            "user": set(),
            "group": set(),
            "session": set(),
        }

        if user.role == ROLE_ADMIN:
            # Admin access is unrestricted; keep empty allow-lists and skip scoped filtering.
            pass
        else:
            allowed["user"].add(int(user_id))

            memberships = db.query(GroupMember).filter(GroupMember.user_id == user_id).all()
            for membership in memberships:
                allowed["group"].add(int(membership.group_id))

            sessions = db.query(SessionModel.id).filter(SessionModel.user_id == user_id).all()
            for (sid,) in sessions:
                allowed["session"].add(int(sid))

        versions_q = db.query(KnowledgeVersion).filter(KnowledgeVersion.is_current)
        if knowledge_type:
            versions_q = versions_q.filter(KnowledgeVersion.knowledge_type == knowledge_type)
        if knowledge_id is not None:
            versions_q = versions_q.filter(KnowledgeVersion.knowledge_id == int(knowledge_id))

        if user.role != "admin":
            visible_pairs = []
            for k_type in ("user", "group", "session"):
                ids = allowed[k_type]
                if ids:
                    visible_pairs.append((k_type, ids))
            if not visible_pairs:
                return []

            # Apply scoped visibility per knowledge type.
            scoped_conditions = []
            from sqlalchemy import and_, or_

            for k_type, ids in visible_pairs:
                scoped_conditions.append(
                    and_(
                        KnowledgeVersion.knowledge_type == k_type,
                        KnowledgeVersion.knowledge_id.in_(list(ids)),
                    )
                )
            versions_q = versions_q.filter(or_(*scoped_conditions))

        versions = versions_q.order_by(
            KnowledgeVersion.knowledge_type.asc(),
            KnowledgeVersion.knowledge_id.asc(),
            KnowledgeVersion.version.desc(),
        ).all()

        if not versions:
            return []

        version_ids = [int(v.id) for v in versions]
        entries = (
            db.query(KnowledgeEntry)
            .filter(KnowledgeEntry.knowledge_version_id.in_(version_ids))
            .order_by(KnowledgeEntry.created_at.desc())
            .all()
        )

        version_by_id = {int(v.id): v for v in versions}
        results: List[Dict[str, Any]] = []
        for entry in entries:
            version = version_by_id.get(int(entry.knowledge_version_id))
            if not version:
                continue
            metadata: Dict[str, Any] = {}
            if entry.metadata_json:
                try:
                    metadata = json.loads(entry.metadata_json)
                except Exception:
                    metadata = {}
            results.append(
                {
                    "id": int(entry.id),
                    "knowledge_type": version.knowledge_type,
                    "knowledge_id": int(version.knowledge_id),
                    "knowledge_version_id": int(version.id),
                    "version": int(version.version),
                    "content": entry.content,
                    "metadata": metadata,
                    "created_at": entry.created_at.isoformat() if entry.created_at else None,
                    "version_created_at": version.created_at.isoformat()
                    if version.created_at
                    else None,
                }
            )
        return results
