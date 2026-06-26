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
Real-time Session State Synchronization

License: Apache 2.0
Ownership: Cloud Dog
Description: Real-time conversation state synchronization across servers

Related Requirements: FR1.2, FR1.7
Related Tasks: T025
Related Architecture: CC2.1.1, CC1.1.4
Related Tests: IT2.5

Recent Changes:
- Initial implementation
"""

from typing import Dict, Any, Optional, List, TYPE_CHECKING
from datetime import datetime
from sqlalchemy.orm import Session

from src.database.connection import get_db
from src.core.session.models import SessionState
from src.utils.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class SessionSynchronizer:
    """Manages real-time session state synchronization."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize session synchronizer.

        Args:
            db: Database session (if None, creates new)
        """
        self.db = db
        self._owned_db: Optional[Session] = None
        # SessionManager is not needed here - we use direct database access
        self._event_broadcaster = None

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

    def set_event_broadcaster(self, broadcaster):
        """
        Set event broadcaster for real-time updates.

        Args:
            broadcaster: Event broadcaster instance (e.g., A2A server ConnectionManager)
        """
        self._event_broadcaster = broadcaster

    async def synchronize_session_state(
        self, session_id: int, new_state: SessionState, metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Synchronize session state change across all servers.

        Args:
            session_id: Session ID
            new_state: New session state
            metadata: Additional metadata for the state change

        Returns:
            True if synchronized successfully
        """
        try:
            # Update session state in database directly
            from src.database.models import Session as SessionModel

            db = self._get_db()
            session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
            if not session:
                logger.warning(f"Session {session_id} not found")
                return False
            session.status = new_state.value
            session.updated_at = datetime.utcnow()
            db.commit()

            # Broadcast state change event
            await self._broadcast_session_state_change(
                session_id=session_id, new_state=new_state, metadata=metadata
            )

            logger.info(f"Synchronized session {session_id} state to {new_state.value}")
            return True
        except Exception as e:
            logger.error(f"Failed to synchronize session state: {e}", exc_info=True)
            return False

    async def synchronize_message_added(
        self,
        session_id: int,
        message_id: int,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Synchronize message addition across all servers.

        Args:
            session_id: Session ID
            message_id: Message ID
            role: Message role
            content: Message content (may be redacted)
            metadata: Additional metadata

        Returns:
            True if synchronized successfully
        """
        try:
            # Broadcast message added event
            await self._broadcast_message_added(
                session_id=session_id,
                message_id=message_id,
                role=role,
                content=content,
                metadata=metadata,
            )

            logger.debug(f"Synchronized message {message_id} addition for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to synchronize message addition: {e}", exc_info=True)
            return False

    async def synchronize_session_created(
        self,
        session_id: int,
        user_id: int,
        expert_config_id: int,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Synchronize session creation across all servers.

        Args:
            session_id: Session ID
            user_id: User ID
            expert_config_id: Expert configuration ID
            metadata: Additional metadata

        Returns:
            True if synchronized successfully
        """
        try:
            # Broadcast session created event
            await self._broadcast_session_created(
                session_id=session_id,
                user_id=user_id,
                expert_config_id=expert_config_id,
                metadata=metadata,
            )

            logger.info(f"Synchronized session {session_id} creation")
            return True
        except Exception as e:
            logger.error(f"Failed to synchronize session creation: {e}", exc_info=True)
            return False

    async def synchronize_session_ended(
        self,
        session_id: int,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Synchronize session end across all servers.

        Args:
            session_id: Session ID
            reason: Reason for ending session
            metadata: Additional metadata

        Returns:
            True if synchronized successfully
        """
        try:
            # Update session state to ENDED directly
            from src.database.models import Session as SessionModel

            db = self._get_db()
            session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
            if not session:
                logger.warning(f"Session {session_id} not found")
                return False
            session.status = SessionState.COMPLETED.value
            session.updated_at = datetime.utcnow()
            db.commit()

            # Broadcast session ended event
            await self._broadcast_session_ended(
                session_id=session_id, reason=reason, metadata=metadata
            )

            logger.info(f"Synchronized session {session_id} end")
            return True
        except Exception as e:
            logger.error(f"Failed to synchronize session end: {e}", exc_info=True)
            return False

    async def _broadcast_session_state_change(
        self, session_id: int, new_state: SessionState, metadata: Optional[Dict[str, Any]] = None
    ):
        """Broadcast session state change event."""
        if not self._event_broadcaster:
            logger.debug("No event broadcaster configured, skipping broadcast")
            return

        event_data = {
            "type": "session_state_change",
            "session_id": session_id,
            "state": new_state.value,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }

        try:
            await self._event_broadcaster.broadcast("sessions", event_data)
        except Exception as e:
            logger.warning(f"Failed to broadcast session state change: {e}")

    async def _broadcast_message_added(
        self,
        session_id: int,
        message_id: int,
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Broadcast message added event."""
        if not self._event_broadcaster:
            logger.debug("No event broadcaster configured, skipping broadcast")
            return

        event_data = {
            "type": "message_added",
            "session_id": session_id,
            "message_id": message_id,
            "role": role,
            "content": content,  # May be redacted for PII
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }

        try:
            await self._event_broadcaster.broadcast("conversations", event_data)
        except Exception as e:
            logger.warning(f"Failed to broadcast message added: {e}")

    async def _broadcast_session_created(
        self,
        session_id: int,
        user_id: int,
        expert_config_id: int,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Broadcast session created event."""
        if not self._event_broadcaster:
            logger.debug("No event broadcaster configured, skipping broadcast")
            return

        event_data = {
            "type": "session_created",
            "session_id": session_id,
            "user_id": user_id,
            "expert_config_id": expert_config_id,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }

        try:
            await self._event_broadcaster.broadcast("sessions", event_data)
        except Exception as e:
            logger.warning(f"Failed to broadcast session created: {e}")

    async def _broadcast_session_ended(
        self,
        session_id: int,
        reason: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Broadcast session ended event."""
        if not self._event_broadcaster:
            logger.debug("No event broadcaster configured, skipping broadcast")
            return

        event_data = {
            "type": "session_ended",
            "session_id": session_id,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat(),
            "metadata": metadata or {},
        }

        try:
            await self._event_broadcaster.broadcast("sessions", event_data)
        except Exception as e:
            logger.warning(f"Failed to broadcast session ended: {e}")

    def get_session_state_history(self, session_id: int, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get session state change history.

        # req: FR-013  (Conversation Management — real-time session state history)

        Reads the persisted audit/event store (``audit_events``) scoped to this
        session (``ref == str(session_id)``), newest first, and returns the
        decoded events. Returns an empty list only when the session has no
        recorded events.

        Args:
            session_id: Session ID
            limit: Maximum number of history entries

        Returns:
            List of state change / session events (most recent first)
        """
        import json

        from src.core.audit.api import AuditAPI

        db = self._get_db()
        events = AuditAPI(db).get_audit_events(session_id=session_id, limit=limit)

        history: List[Dict[str, Any]] = []
        for event in events:
            try:
                data = json.loads(event.data) if event.data else {}
            except Exception:
                data = {"raw": event.data}
            history.append(
                {
                    "event_id": event.id,
                    "kind": event.kind,
                    "session_id": session_id,
                    "actor": event.actor,
                    "data": data,
                    "timestamp": event.created_at.isoformat() if event.created_at else None,
                }
            )

        logger.debug(f"Loaded {len(history)} state history entries for session {session_id}")
        return history
