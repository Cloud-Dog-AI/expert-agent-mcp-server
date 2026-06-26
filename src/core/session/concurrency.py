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
Session Concurrency Control

License: Apache 2.0
Ownership: Cloud Dog
Description: Manages session limits and concurrency control

Related Requirements: FR1.11, NF1.3, T027, T028, T029
Related Tasks: T027, T028, T029
Related Architecture: CP1.1.5, CC2.1.2, CC2.1.3
Related Tests: UT1.36, UT1.38, ST1.18, ST1.20, ST1.21

Recent Changes:
- Initial implementation
"""

from typing import Dict, List, Optional, Tuple, Any
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from enum import Enum

from src.database.models import Session as SessionModel, User, GroupMember
from src.database.connection import get_db
from src.core.session.models import SessionState
from src.utils.logger import get_logger
from src.config.loader import get_config

logger = get_logger(__name__)

from threading import Lock  # noqa: E402
import uuid  # noqa: E402

# In-memory queue (process-local) for session requests.
# This is intentionally simple but functional and testable.
_QUEUE_LOCK = Lock()
_SESSION_QUEUE: list[dict[str, Any]] = []


class QueuePriority(str, Enum):
    """Queue priority levels."""

    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class ConcurrencyManager:
    """Manages session concurrency limits and queuing."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize concurrency manager.

        Args:
            db: Database session (if None, creates new)
        """
        self.db = db
        self._owned_db: Optional[Session] = None
        raw_user_limit = get_config("session.max_sessions_per_user")
        raw_group_limit = get_config("session.max_sessions_per_group")
        raw_queue_enabled = get_config("session.queue_enabled")

        try:
            self.default_user_limit = int(raw_user_limit)
        except Exception:
            self.default_user_limit = None
        try:
            self.default_group_limit = int(raw_group_limit)
        except Exception:
            self.default_group_limit = None

        if isinstance(raw_queue_enabled, str):
            self.queue_enabled = raw_queue_enabled.strip().lower() in (
                "1",
                "true",
                "yes",
                "y",
                "on",
            )
        else:
            self.queue_enabled = bool(raw_queue_enabled)
        if self.default_user_limit is None:
            raise RuntimeError("session.max_sessions_per_user not configured")
        if self.default_group_limit is None:
            raise RuntimeError("session.max_sessions_per_group not configured")
        if self.queue_enabled is None:
            raise RuntimeError("session.queue_enabled not configured")

    def _get_db(self) -> Session:
        """Get database session."""
        if self.db:
            return self.db
        if self._owned_db is None:
            db_gen = get_db()
            self._owned_db = next(db_gen)
        return self._owned_db

    def close(self) -> None:
        """Close internally owned DB session (if any)."""
        if self._owned_db is not None:
            try:
                self._owned_db.close()
            finally:
                self._owned_db = None

    def __del__(self) -> None:
        """Best-effort cleanup for internally owned DB sessions."""
        try:
            self.close()
        except Exception:
            pass

    def _expire_timed_out_active_sessions(self, db: Session) -> None:
        """Expire timed-out active/created sessions before limit checks."""
        raw_timeout = get_config("auth.session_timeout_minutes")
        try:
            timeout_minutes = int(raw_timeout)
        except Exception:
            return

        now = datetime.utcnow()
        updated = False

        active_sessions = (
            db.query(SessionModel)
            .filter(
                SessionModel.status.in_([SessionState.ACTIVE.value, SessionState.CREATED.value])
            )
            .all()
        )

        for session in active_sessions:
            last_seen = session.updated_at or session.created_at
            if last_seen is None:
                continue
            last_seen_naive = last_seen.replace(tzinfo=None) if last_seen.tzinfo else last_seen

            should_expire = timeout_minutes <= 0 or (
                now - last_seen_naive > timedelta(minutes=timeout_minutes)
            )
            if should_expire:
                session.status = "ended"
                updated = True

        if updated:
            db.commit()

    def check_user_session_limit(
        self, user_id: int, group_id: Optional[int] = None
    ) -> Tuple[bool, Optional[str], int]:
        """
        Check if user can create a new session.

        Args:
            user_id: User ID
            group_id: Optional group ID for group-based limits

        Returns:
            Tuple of (allowed, reason, current_count)
        """
        db = self._get_db()
        self._expire_timed_out_active_sessions(db)

        # Get active sessions for user
        active_sessions = (
            db.query(SessionModel)
            .filter(
                SessionModel.user_id == user_id,
                SessionModel.status.in_([SessionState.ACTIVE.value, SessionState.CREATED.value]),
            )
            .count()
        )

        # Get user-specific limit (could be from user settings)
        user_limit = self.default_user_limit

        # Check group limit if group_id provided
        if group_id:
            group_sessions = (
                db.query(SessionModel)
                .join(User)
                .join(GroupMember)
                .filter(
                    GroupMember.group_id == group_id,
                    SessionModel.status.in_(
                        [SessionState.ACTIVE.value, SessionState.CREATED.value]
                    ),
                )
                .count()
            )

            group_limit = self.default_group_limit
            if group_sessions >= group_limit:
                return False, f"Group session limit ({group_limit}) reached", group_sessions

        if active_sessions >= user_limit:
            return False, f"User session limit ({user_limit}) reached", active_sessions

        return True, None, active_sessions

    def queue_session(
        self,
        user_id: int,
        expert_config_id: int,
        priority: QueuePriority = QueuePriority.NORMAL,
        channel_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Queue a session when limit is reached.

        Args:
            user_id: User ID
            expert_config_id: Expert configuration ID
            priority: Queue priority
            channel_id: Optional channel ID

        Returns:
            Queue information dict
        """
        if not self.queue_enabled:
            raise ValueError("Session queuing is disabled")

        with _QUEUE_LOCK:
            queue_entry = {
                "id": str(uuid.uuid4()),
                "user_id": user_id,
                "expert_config_id": expert_config_id,
                "channel_id": channel_id,
                "priority": priority.value,
                "queued_at": datetime.utcnow().isoformat(),
                "status": "queued",
            }
            _SESSION_QUEUE.append(queue_entry)
            logger.info(
                f"Queued session for user {user_id} with priority {priority.value} (queue size={len(_SESSION_QUEUE)})"
            )
            return queue_entry

    def get_queue_position(self, user_id: int, queue_entry: Dict[str, Any]) -> int:
        """
        Get position in queue.

        Args:
            user_id: User ID
            queue_entry: Queue entry dict

        Returns:
            Position in queue (0 = next, higher = further back)
        """
        with _QUEUE_LOCK:
            try:
                idx = next(
                    i for i, e in enumerate(_SESSION_QUEUE) if e.get("id") == queue_entry.get("id")
                )
                return idx
            except StopIteration:
                return -1

    def process_queue(self) -> List[Dict[str, Any]]:
        """
        Process queued sessions when slots become available.

        Returns:
            List of processed queue entries
        """
        # Minimal implementation: no automatic processing in-process.
        # This hook exists for future background/worker processing.
        return []

    def notify_user_limit_reached(
        self, user_id: int, reason: str, queue_entry: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Notify user that session limit was reached.

        Args:
            user_id: User ID
            reason: Reason for limit
            queue_entry: Optional queue entry if queued

        Returns:
            Notification dict
        """
        notification = {
            "user_id": user_id,
            "message": f"Session limit reached: {reason}",
            "queued": queue_entry is not None,
            "queue_position": None,
        }

        if queue_entry:
            notification["queue_position"] = self.get_queue_position(user_id, queue_entry)
            notification["message"] += (
                f". Your session has been queued (position: {notification['queue_position']})"
            )

        logger.info(f"Notified user {user_id}: {notification['message']}")
        return notification
