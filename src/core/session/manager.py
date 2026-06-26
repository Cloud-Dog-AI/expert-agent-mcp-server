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
Session Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Manages sessions, messages, and context

Related Requirements: FR1.2, FR1.12
Related Tasks: T022, T023, T024
Related Architecture: CC2.1.1
Related Tests: IT2.5, AT1.5

Recent Changes:
- Initial implementation
"""

from typing import List, Dict, Any, Optional, Tuple
from queue import Queue
from threading import Thread
from sqlalchemy.orm import Session
from datetime import datetime, timedelta

import json

from src.database.models import (
    Session as SessionModel,
    Message as MessageModel,
    ExpertConfig,
    User,
    GroupMember,
)
from src.core.expert.access_control import is_authorized, normalise_access_control
from src.database.connection import get_db
from src.core.session.models import SessionState
from src.core.session.summarizer import ContextSummarizer
from src.core.session.concurrency import ConcurrencyManager, QueuePriority
from src.core.session.synchronization import SessionSynchronizer
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _run_async_in_thread(coroutine: Any, timeout_seconds: float) -> Any:
    """Execute an async coroutine in a dedicated thread when a loop is already running."""
    result_queue: Queue[tuple[bool, Any]] = Queue(maxsize=1)

    def _runner() -> None:
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result_queue.put((True, loop.run_until_complete(coroutine)))
        except Exception as exc:  # noqa: BLE001
            result_queue.put((False, exc))
        finally:
            loop.close()

    thread = Thread(target=_runner, daemon=True)
    thread.start()
    thread.join(timeout=timeout_seconds)
    if thread.is_alive():
        raise TimeoutError(f"Summarization timed out after {timeout_seconds}s")
    ok, value = result_queue.get()
    if ok:
        return value
    raise value


class SessionManager:
    """Manages sessions and message history."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize session manager.

        Args:
            db: Database session (if None, creates new)
        """
        self.db = db
        self._owned_db: Optional[Session] = None
        self.summarizer = ContextSummarizer()
        self.concurrency_manager = ConcurrencyManager(db)
        self.synchronizer = SessionSynchronizer(db)

    def _get_db(self) -> Session:
        """Get database session."""
        if self.db:
            return self.db
        if self._owned_db is None:
            db_gen = get_db()
            self._owned_db = next(db_gen)
        return self._owned_db

    def close(self) -> None:
        """Close internally owned database session (if any)."""
        for mgr_name in ("concurrency_manager", "synchronizer"):
            mgr = getattr(self, mgr_name, None)
            close_fn = getattr(mgr, "close", None)
            if callable(close_fn):
                try:
                    close_fn()
                except Exception:
                    pass
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

    def create_session(
        self,
        user_id: int,
        expert_config_id: int,
        title: Optional[str] = None,
        channel_id: Optional[int] = None,
        context_window: int = 4096,
        history_retention_days: int = 30,
        check_limits: bool = True,
        queue_if_full: bool = True,
    ) -> Tuple[SessionModel, Optional[Dict[str, Any]]]:
        """
        Create a new session with concurrency control.

        Args:
            user_id: User ID
            expert_config_id: Expert configuration ID
            title: Session title (optional)
            channel_id: Channel ID (optional)
            context_window: Context window size
            history_retention_days: History retention period
            check_limits: Whether to check session limits
            queue_if_full: Whether to queue if limit reached

        Returns:
            Tuple of (session, notification) where notification is None if created, or dict if queued/limited
        """
        db = self._get_db()

        # Validate user exists
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise ValueError("User not found")

        # Validate expert exists and is enabled
        expert = db.query(ExpertConfig).filter(ExpertConfig.id == expert_config_id).first()
        if not expert:
            raise ValueError("Expert configuration not found")
        if not expert.enabled:
            raise ValueError("Expert configuration is disabled")

        # Enforce expert access control via the unified schema (EA7 / W28M-FIX-1615).
        # normalise_access_control accepts the legacy {roles:[...]} and
        # {demo:true,collection,surface} shapes as well as the unified
        # {type, roles, demo_surface, demo_collection, allowed_groups} shape;
        # is_authorized dispatches on type while preserving the historical
        # allowed_groups membership gate (fail-closed on malformed JSON).
        if expert.access_control_json:
            try:
                ac = json.loads(expert.access_control_json) or {}
            except Exception:
                # If access_control_json is malformed, fail closed
                raise PermissionError("Access control configuration is invalid")

            if normalise_access_control(ac).get("allowed_groups"):
                user_row = db.query(User).filter(User.id == user_id).first()
                user_role = user_row.role if user_row else None
                user_group_ids = {
                    gm.group_id
                    for gm in db.query(GroupMember).filter(GroupMember.user_id == user_id).all()
                }
                if not is_authorized(ac, user_role=user_role, user_group_ids=user_group_ids):
                    raise PermissionError(
                        "User is not authorised to use this expert configuration"
                    )

        # Check concurrency limits
        if check_limits:
            allowed, reason, current_count = self.concurrency_manager.check_user_session_limit(
                user_id, channel_id
            )

            if not allowed:
                if queue_if_full:
                    # Queue the session
                    queue_entry = self.concurrency_manager.queue_session(
                        user_id, expert_config_id, QueuePriority.NORMAL, channel_id
                    )
                    notification = self.concurrency_manager.notify_user_limit_reached(
                        user_id, reason, queue_entry
                    )
                    return None, notification
                else:
                    raise ValueError(reason)

        try:
            # Generate session key and history key
            import uuid

            session_key = str(uuid.uuid4())
            history_key = str(uuid.uuid4())

            session = SessionModel(
                user_id=user_id,
                expert_config_id=expert_config_id,
                title=title or f"Session {datetime.utcnow().isoformat()}",
                status=SessionState.ACTIVE.value,
                context_window=context_window,
                history_retention_days=history_retention_days,
                session_key=session_key,
                history_key=history_key,
            )
            db.add(session)
            db.commit()
            db.refresh(session)

            logger.info(f"Created session {session.id} for user {user_id} with keys")
            return session, None
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create session: {e}", exc_info=True)
            raise

    def get_session(self, session_id: int) -> Optional[SessionModel]:
        """Get session by ID."""
        db = self._get_db()
        return db.query(SessionModel).filter(SessionModel.id == session_id).first()

    def update_session_state(self, session_id: int, state: SessionState) -> bool:
        """Update session state."""
        db = self._get_db()
        try:
            session = db.query(SessionModel).filter(SessionModel.id == session_id).first()
            if not session:
                return False

            session.status = state.value
            session.updated_at = datetime.utcnow()
            db.commit()

            # Synchronize state change (fire and forget)
            try:
                import asyncio

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(
                        self.synchronizer.synchronize_session_state(session_id, state)
                    )
                else:
                    loop.run_until_complete(
                        self.synchronizer.synchronize_session_state(session_id, state)
                    )
            except Exception as e:
                logger.warning(f"Failed to synchronize session state change: {e}")

            logger.debug(f"Updated session {session_id} state to {state.value}")
            return True
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to update session state: {e}", exc_info=True)
            return False

    def add_message(
        self,
        session_id: int,
        role: str,
        content: str,
        tokens_used: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> MessageModel:
        """
        Add message to session.

        Args:
            session_id: Session ID
            role: Message role (user, assistant, system)
            content: Message content
            tokens_used: Tokens used (optional)
            metadata: Additional metadata (optional)

        Returns:
            Created message
        """
        db = self._get_db()
        try:
            message = MessageModel(
                session_id=session_id,
                role=role,
                content=content,
                tokens_used=tokens_used,
                metadata_json=str(metadata) if metadata else None,
            )
            db.add(message)
            db.commit()
            db.refresh(message)

            # Synchronize message addition (fire and forget)
            try:
                import asyncio

                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.create_task(
                        self.synchronizer.synchronize_message_added(
                            session_id, message.id, role, content, metadata
                        )
                    )
                else:
                    loop.run_until_complete(
                        self.synchronizer.synchronize_message_added(
                            session_id, message.id, role, content, metadata
                        )
                    )
            except Exception as e:
                logger.warning(f"Failed to synchronize message addition: {e}")

            logger.debug(f"Added {role} message to session {session_id}")
            return message
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to add message: {e}", exc_info=True)
            raise

    def get_messages(
        self, session_id: int, limit: Optional[int] = None, offset: int = 0
    ) -> List[MessageModel]:
        """
        Get messages for session.

        Args:
            session_id: Session ID
            limit: Maximum number of messages
            offset: Offset for pagination

        Returns:
            List of messages
        """
        db = self._get_db()
        query = (
            db.query(MessageModel)
            .filter(MessageModel.session_id == session_id)
            .order_by(MessageModel.timestamp.asc())
        )

        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        return query.all()

    def get_message_history(
        self, session_id: int, max_tokens: Optional[int] = None, use_summarization: bool = True
    ) -> List[Dict[str, str]]:
        """
        Get message history in LLM format with context window management.

        Args:
            session_id: Session ID
            max_tokens: Maximum tokens to include (for context window management)
            use_summarization: Whether to use summarization for long conversations

        Returns:
            List of message dicts with 'role' and 'content'
        """
        messages = self.get_messages(session_id)

        # Convert to LLM format
        history = [{"role": msg.role, "content": msg.content} for msg in messages]

        # If max_tokens specified, manage context window
        if max_tokens:
            estimated_tokens = self._estimate_tokens(history)

            # If exceeds limit and summarization enabled, summarize
            if estimated_tokens > max_tokens and use_summarization and len(history) > 10:
                import asyncio

                try:
                    # Run async summarization
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        result = _run_async_in_thread(
                            self.summarizer.summarize_history(history, max_tokens),
                            timeout_seconds=30.0,
                        )
                    else:
                        result = loop.run_until_complete(
                            self.summarizer.summarize_history(history, max_tokens)
                        )

                    if result.get("summary"):
                        return result["preserved_messages"]
                except Exception as e:
                    logger.warning(f"Summarization failed, using truncation: {e}")

            # Fallback: truncate from beginning, keep recent messages
            total_tokens = 0
            truncated_history = []
            for msg in reversed(history):
                msg_tokens = self._estimate_message_tokens(msg)
                if total_tokens + msg_tokens > max_tokens:
                    break
                truncated_history.insert(0, msg)
                total_tokens += msg_tokens

            return truncated_history

        return history

    def _estimate_tokens(self, messages: List[Dict[str, str]]) -> int:
        """Estimate total tokens for messages."""
        return sum(self._estimate_message_tokens(msg) for msg in messages)

    def _estimate_message_tokens(self, message: Dict[str, str]) -> int:
        """Estimate tokens for a single message."""
        content = message.get("content", "")
        # Rough estimate: 4 characters per token, plus overhead for role
        return (len(content) // 4) + 5

    def cleanup_old_sessions(self, days: int = 90):
        """Clean up sessions older than specified days."""
        db = self._get_db()
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            deleted = (
                db.query(SessionModel)
                .filter(
                    SessionModel.created_at < cutoff,
                    SessionModel.status == SessionState.ARCHIVED.value,
                )
                .delete()
            )
            db.commit()

            logger.info(f"Cleaned up {deleted} old sessions")
            return deleted
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to cleanup old sessions: {e}", exc_info=True)
            return 0
