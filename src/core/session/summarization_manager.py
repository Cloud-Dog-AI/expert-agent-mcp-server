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
Context Summarization Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Manages context summarization with database storage for AT1.11

Related Requirements: FR1.28
Related Tasks: T066
Related Architecture: CC2.1.4
Related Tests: AT1.11
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from src.database.models import Session as SessionModel, Summary as SummaryModel
from src.core.session.summarizer import ContextSummarizer
from src.core.session.manager import SessionManager
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ContextSummarizationManager:
    """Manages context summarization with database storage."""

    def __init__(self, db: Session):
        """Initialize context summarization manager."""
        self.db = db
        self.summarizer = ContextSummarizer()
        self.session_manager = SessionManager(db)

    @staticmethod
    def _build_fallback_summary(
        older_messages: List[Dict[str, str]], preserve_recent: int, reason: str
    ) -> str:
        """Build deterministic fallback summary when LLM output is unavailable."""
        lines: List[str] = [
            f"Fallback summary generated because LLM summarization was unavailable ({reason}).",
            (
                f"Summarized {len(older_messages)} historical messages and preserved "
                f"{preserve_recent} recent messages."
            ),
            "Historical message excerpts:",
        ]

        max_items = 12
        for index, message in enumerate(older_messages[:max_items], start=1):
            role = (message.get("role") or "unknown").strip()
            content = (message.get("content") or "").strip().replace("\n", " ")
            if len(content) > 220:
                content = f"{content[:217]}..."
            lines.append(f"{index}. {role}: {content}")

        remaining = len(older_messages) - max_items
        if remaining > 0:
            lines.append(f"... {remaining} additional historical messages omitted.")

        return "\n".join(lines)

    def _store_summary(
        self,
        session_id: int,
        summary_text: str,
        original_message_count: int,
        preserved_message_count: int,
    ) -> SummaryModel:
        """Persist summary row and return refreshed model."""
        summary = SummaryModel(
            session_id=session_id,
            summary_text=summary_text,
            original_message_count=original_message_count,
            preserved_message_count=preserved_message_count,
        )
        self.db.add(summary)
        self.db.commit()
        self.db.refresh(summary)
        return summary

    async def summarize_session(
        self, session_id: int, preserve_recent: int = 5, max_tokens: Optional[int] = None
    ) -> Dict[str, Any]:
        """Summarize session history and store summary."""
        session = self.db.query(SessionModel).filter(SessionModel.id == session_id).first()
        if not session:
            raise ValueError(f"Session {session_id} not found")

        # Get messages
        messages = self.session_manager.get_messages(session_id=session_id)
        if len(messages) <= preserve_recent:
            return {
                "summary_id": None,
                "summary": None,
                "message": "Not enough messages to summarize",
                "original_message_count": len(messages),
                "preserved_message_count": len(messages),
            }

        # Convert messages to dict format
        message_dicts = [{"role": msg.role, "content": msg.content} for msg in messages]

        # Use context window if max_tokens not specified
        if max_tokens is None:
            max_tokens = session.context_window // 2

        original_message_count = len(messages) - preserve_recent
        older_message_dicts = message_dicts[:-preserve_recent] if preserve_recent > 0 else message_dicts

        # Summarize
        try:
            result = await self.summarizer.summarize_history(
                messages=message_dicts, max_tokens=max_tokens, preserve_recent=preserve_recent
            )

            summary_text = (result.get("summary") or "").strip()
            fallback_used = False
            if not summary_text:
                fallback_used = True
                logger.warning(
                    f"LLM summarization returned empty output for session {session_id}; "
                    "persisting fallback summary"
                )
                summary_text = self._build_fallback_summary(
                    older_messages=older_message_dicts,
                    preserve_recent=preserve_recent,
                    reason="empty_summary",
                )

            # Store summary in database
            summary = self._store_summary(
                session_id=session_id,
                summary_text=summary_text,
                original_message_count=original_message_count,
                preserved_message_count=preserve_recent,
            )

            logger.info(f"Created summary {summary.id} for session {session_id}")

            return {
                "summary_id": summary.id,
                "summary": summary_text,
                "original_message_count": summary.original_message_count,
                "preserved_message_count": summary.preserved_message_count,
                "total_tokens": result.get("total_tokens", 0),
                "message": (
                    "Summary generated using deterministic fallback"
                    if fallback_used
                    else "Summary generated"
                ),
            }
        except Exception as e:
            logger.error(f"Failed to summarize session {session_id}: {e}", exc_info=True)

            fallback_summary = self._build_fallback_summary(
                older_messages=older_message_dicts,
                preserve_recent=preserve_recent,
                reason=f"exception:{type(e).__name__}",
            )
            try:
                summary = self._store_summary(
                    session_id=session_id,
                    summary_text=fallback_summary,
                    original_message_count=original_message_count,
                    preserved_message_count=preserve_recent,
                )
            except Exception as db_error:
                self.db.rollback()
                logger.error(
                    f"Failed to persist fallback summary for session {session_id}: {db_error}",
                    exc_info=True,
                )
                return {
                    "summary_id": None,
                    "summary": None,
                    "message": f"Summarization failed: {str(e)}",
                    "original_message_count": original_message_count,
                    "preserved_message_count": preserve_recent,
                    "total_tokens": 0,
                }

            return {
                "summary_id": summary.id,
                "summary": fallback_summary,
                "message": "Summary generated using deterministic fallback after LLM failure",
                "original_message_count": original_message_count,
                "preserved_message_count": preserve_recent,
                "total_tokens": 0,
            }

    def get_summaries(self, session_id: int) -> List[Dict[str, Any]]:
        """Get all summaries for a session."""
        summaries = (
            self.db.query(SummaryModel)
            .filter(SummaryModel.session_id == session_id)
            .order_by(SummaryModel.created_at.desc())
            .all()
        )

        return [
            {
                "id": s.id,
                "summary_text": s.summary_text,
                "original_message_count": s.original_message_count,
                "preserved_message_count": s.preserved_message_count,
                "created_at": s.created_at.isoformat(),
            }
            for s in summaries
        ]

    def consolidate_summaries(self, session_id: int) -> Dict[str, Any]:
        """Consolidate multiple summaries for a session into a single summary.

        # req: FR-013  (Conversation Management — automatic context summarization/consolidation)

        All existing summaries (oldest first) are merged into one consolidated
        summary text, the superseded summary rows are removed, and a single new
        consolidated ``Summary`` row is persisted. Message counts are aggregated
        so the consolidated row reflects the full history it represents.
        """
        summaries = self.get_summaries(session_id)  # newest-first
        if len(summaries) <= 1:
            return {"consolidated": False, "message": "Not enough summaries to consolidate"}

        ordered = list(reversed(summaries))  # oldest -> newest for readable merge
        merged_text = "\n\n".join(
            s["summary_text"] for s in ordered if s.get("summary_text")
        )
        total_original = sum(int(s.get("original_message_count") or 0) for s in ordered)
        total_preserved = sum(int(s.get("preserved_message_count") or 0) for s in ordered)

        old_ids = [s["id"] for s in summaries]
        self.db.query(SummaryModel).filter(SummaryModel.id.in_(old_ids)).delete(
            synchronize_session=False
        )
        consolidated = SummaryModel(
            session_id=session_id,
            summary_text=merged_text,
            original_message_count=total_original,
            preserved_message_count=total_preserved,
        )
        self.db.add(consolidated)
        self.db.commit()
        self.db.refresh(consolidated)

        return {
            "consolidated": True,
            "summary_id": consolidated.id,
            "summary_text": consolidated.summary_text,
            "consolidated_count": len(summaries),
            "original_message_count": total_original,
            "preserved_message_count": total_preserved,
        }
