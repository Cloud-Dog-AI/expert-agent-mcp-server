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
Session Key and History Key Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Manages session keys and history keys for AT1.11

Related Requirements: FR1.26
Related Tasks: T064
Related Architecture: CC2.1.2
Related Tests: AT1.11
"""

import uuid
from typing import Optional, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session
from src.database.models import Session as SessionModel
from src.utils.logger import get_logger

logger = get_logger(__name__)


class SessionKeyManager:
    """Manages session keys for session access."""

    def __init__(self, db: Session):
        """Initialize session key manager."""
        self.db = db

    def generate_session_key(self) -> str:
        """Generate a unique session key (UUID)."""
        return str(uuid.uuid4())

    def generate_history_key(self) -> str:
        """Generate a unique history key (UUID)."""
        return str(uuid.uuid4())

    def set_session_key(
        self,
        session_id: int,
        session_key: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> str:
        """Set session key for a session."""
        session = self.db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if session_key is None:
            session_key = self.generate_session_key()

        session.session_key = session_key
        session.session_key_expires_at = expires_at
        self.db.commit()

        logger.debug(f"Set session key for session {session_id}")
        return session_key

    def set_history_key(self, session_id: int, history_key: Optional[str] = None) -> str:
        """Set history key for a session."""
        session = self.db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise ValueError(f"Session {session_id} not found")

        if history_key is None:
            history_key = self.generate_history_key()

        session.history_key = history_key
        self.db.commit()

        logger.debug(f"Set history key for session {session_id}")
        return history_key

    def get_session_by_key(self, session_key: str) -> Optional[SessionModel]:
        """Get session by session key."""
        session = (
            self.db.query(SessionModel).filter(SessionModel.session_key == session_key).first()
        )

        if not session:
            return None

        # Check expiration
        if session.session_key_expires_at and session.session_key_expires_at < datetime.utcnow():
            logger.warning(f"Session key {session_key} has expired")
            return None

        return session

    def get_session_by_history_key(self, history_key: str) -> Optional[SessionModel]:
        """Get session by history key."""
        session = (
            self.db.query(SessionModel).filter(SessionModel.history_key == history_key).first()
        )

        return session

    def rotate_session_key(self, session_id: int) -> str:
        """Rotate session key for a session."""
        new_key = self.generate_session_key()
        return self.set_session_key(session_id, session_key=new_key)

    def validate_key_access(self, session: SessionModel, user_id: int) -> bool:
        """Validate if user can access session via key."""
        # Owner can always access
        if session.user_id == user_id:
            return True

        # Check shared users
        if session.shared_with_user_ids:
            import json

            try:
                shared_user_ids = json.loads(session.shared_with_user_ids)
                if user_id in shared_user_ids:
                    return True
            except Exception:
                pass

        # Check shared groups (would need group membership check)
        # For now, return False if not owner and not in shared users
        return False


class HistoryKeyManager:
    """Manages history keys for history access."""

    def __init__(self, db: Session):
        """Initialize history key manager."""
        self.db = db
        self.session_key_manager = SessionKeyManager(db)

    def get_history_by_key(self, history_key: str) -> Optional[Dict[str, Any]]:
        """Get history by history key."""
        session = self.session_key_manager.get_session_by_history_key(history_key)
        if not session:
            return None

        from src.core.session.manager import SessionManager

        session_manager = SessionManager(self.db)
        messages = session_manager.get_messages(session_id=session.id)

        return {
            "session_id": session.id,
            "history_key": history_key,
            "messages": [
                {
                    "id": msg.id,
                    "role": msg.role,
                    "content": msg.content,
                    "timestamp": msg.timestamp.isoformat(),
                    "user_id": getattr(msg, "user_id", None),
                }
                for msg in messages
            ],
            "count": len(messages),
        }
