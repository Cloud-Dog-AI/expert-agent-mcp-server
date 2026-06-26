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
History Sharing Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Manages session sharing with users and groups for AT1.11

Related Requirements: FR1.27
Related Tasks: T065
Related Architecture: CC2.1.3
Related Tests: AT1.11
"""

import json
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from src.database.models import Session as SessionModel
from src.utils.logger import get_logger

logger = get_logger(__name__)


class HistorySharingManager:
    """Manages session sharing with users and groups."""

    def __init__(self, db: Session):
        """Initialize history sharing manager."""
        self.db = db

    def share_session(
        self,
        session_id: int,
        user_ids: Optional[List[int]] = None,
        group_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Share session with users and/or groups."""
        session = self.db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Update shared user IDs
        if user_ids:
            existing_user_ids = []
            if session.shared_with_user_ids:
                try:
                    existing_user_ids = json.loads(session.shared_with_user_ids)
                except Exception:
                    pass

            # Merge and deduplicate
            all_user_ids = list(set(existing_user_ids + user_ids))
            session.shared_with_user_ids = json.dumps(all_user_ids)

        # Update shared group IDs
        if group_ids:
            existing_group_ids = []
            if session.shared_with_group_ids:
                try:
                    existing_group_ids = json.loads(session.shared_with_group_ids)
                except Exception:
                    pass

            # Merge and deduplicate
            all_group_ids = list(set(existing_group_ids + group_ids))
            session.shared_with_group_ids = json.dumps(all_group_ids)

        self.db.commit()

        logger.info(f"Shared session {session_id} with users {user_ids} and groups {group_ids}")

        return {
            "session_id": session_id,
            "shared_with_user_ids": json.loads(session.shared_with_user_ids)
            if session.shared_with_user_ids
            else [],
            "shared_with_group_ids": json.loads(session.shared_with_group_ids)
            if session.shared_with_group_ids
            else [],
        }

    def unshare_session(
        self,
        session_id: int,
        user_ids: Optional[List[int]] = None,
        group_ids: Optional[List[int]] = None,
    ) -> Dict[str, Any]:
        """Unshare session with users and/or groups."""
        session = self.db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Remove user IDs
        if user_ids and session.shared_with_user_ids:
            try:
                existing_user_ids = json.loads(session.shared_with_user_ids)
                remaining_user_ids = [uid for uid in existing_user_ids if uid not in user_ids]
                session.shared_with_user_ids = (
                    json.dumps(remaining_user_ids) if remaining_user_ids else None
                )
            except Exception:
                pass

        # Remove group IDs
        if group_ids and session.shared_with_group_ids:
            try:
                existing_group_ids = json.loads(session.shared_with_group_ids)
                remaining_group_ids = [gid for gid in existing_group_ids if gid not in group_ids]
                session.shared_with_group_ids = (
                    json.dumps(remaining_group_ids) if remaining_group_ids else None
                )
            except Exception:
                pass

        self.db.commit()

        logger.info(f"Unshared session {session_id} from users {user_ids} and groups {group_ids}")

        return {
            "session_id": session_id,
            "shared_with_user_ids": json.loads(session.shared_with_user_ids)
            if session.shared_with_user_ids
            else [],
            "shared_with_group_ids": json.loads(session.shared_with_group_ids)
            if session.shared_with_group_ids
            else [],
        }

    def can_access_session(self, session: SessionModel, user_id: int) -> bool:
        """Check if user can access session.

        # req: FR-019  (Group Admin Role Management — group membership access + live revocation)

        Access is granted to the owner, to any user the session was explicitly
        shared with, and to any user that is a current member of a group the
        session was shared with (resolved live from the ``group_members`` join
        table, so a revoked membership immediately removes access).
        """
        # Owner can always access
        if session.user_id == user_id:
            return True

        # Check shared users
        if session.shared_with_user_ids:
            try:
                shared_user_ids = json.loads(session.shared_with_user_ids)
                if user_id in shared_user_ids:
                    return True
            except Exception:
                pass

        # Check shared groups via live group membership
        if session.shared_with_group_ids:
            try:
                shared_group_ids = json.loads(session.shared_with_group_ids)
            except Exception:
                shared_group_ids = []
            if shared_group_ids:
                from src.database.models import GroupMember

                is_member = (
                    self.db.query(GroupMember)
                    .filter(
                        GroupMember.user_id == user_id,
                        GroupMember.group_id.in_(shared_group_ids),
                    )
                    .first()
                    is not None
                )
                if is_member:
                    return True

        # Not owner, not in shared users, not a member of any shared group
        return False

    def get_sharing_info(self, session_id: int) -> Dict[str, Any]:
        """Get sharing information for a session."""
        session = self.db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise ValueError(f"Session {session_id} not found")

        return {
            "session_id": session_id,
            "owner_user_id": session.user_id,
            "shared_with_user_ids": json.loads(session.shared_with_user_ids)
            if session.shared_with_user_ids
            else [],
            "shared_with_group_ids": json.loads(session.shared_with_group_ids)
            if session.shared_with_group_ids
            else [],
            "session_key": session.session_key,
            "history_key": session.history_key,
        }
