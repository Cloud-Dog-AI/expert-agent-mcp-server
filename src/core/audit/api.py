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
Audit Logging APIs

License: Apache 2.0
Ownership: Cloud Dog
Description: API endpoints for audit log access

Related Requirements: FR1.10, T034
Related Tasks: T034
Related Architecture: SE1.3
Related Tests: AT1.6

Recent Changes:
- Initial implementation
"""

from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from src.database.models import AuditEvent
from src.database.connection import get_db
from src.utils.logger import get_logger
from src.core.security.crypto import decrypt_if_enabled

logger = get_logger(__name__)


class AuditAPI:
    """API for audit log access."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize audit API.

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

    def get_audit_events(
        self,
        user_id: Optional[int] = None,
        session_id: Optional[int] = None,
        event_type: Optional[str] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[AuditEvent]:
        """
        Get audit events with filters.

        Args:
            user_id: Filter by user ID (stored in actor field as string)
            session_id: Filter by session ID (stored in ref field as string)
            event_type: Filter by event type (stored in kind field)
            start_date: Filter by start date
            end_date: Filter by end date
            limit: Maximum number of events
            offset: Offset for pagination

        Returns:
            List of audit events
        """
        db = self._get_db()
        query = db.query(AuditEvent)

        if user_id:
            query = query.filter(AuditEvent.actor == str(user_id))
        if session_id:
            query = query.filter(AuditEvent.ref == str(session_id))
        if event_type:
            query = query.filter(AuditEvent.kind == event_type)
        if start_date:
            query = query.filter(AuditEvent.created_at >= start_date)
        if end_date:
            query = query.filter(AuditEvent.created_at <= end_date)

        return query.order_by(AuditEvent.created_at.desc()).offset(offset).limit(limit).all()

    def get_audit_event(self, event_id: int) -> Optional[AuditEvent]:
        """Get audit event by ID."""
        db = self._get_db()
        return db.query(AuditEvent).filter(AuditEvent.id == event_id).first()

    def export_audit_logs(self, format: str = "json", **filters) -> str:
        """
        Export audit logs in specified format.

        Args:
            format: Export format (json, csv)
            **filters: Filter parameters

        Returns:
            Exported audit logs as string
        """
        events = self.get_audit_events(**filters)

        def _details_payload(raw_data: Optional[str]) -> Dict[str, Any]:
            """Decode audit data (decrypt if enabled, parse JSON safely)."""
            if not raw_data:
                return {}
            decrypted = decrypt_if_enabled(raw_data) or ""
            try:
                return json.loads(decrypted)
            except Exception:
                logger.warning("Audit event data was not valid JSON; returning raw payload.")
                return {"raw": decrypted}

        if format == "json":
            import json

            return json.dumps(
                [
                    {
                        "id": e.id,
                        "timestamp": e.created_at.isoformat(),
                        "event_type": e.kind,
                        "user_id": int(e.actor) if e.actor and e.actor.isdigit() else None,
                        "session_id": int(e.ref) if e.ref and e.ref.isdigit() else None,
                        "details": _details_payload(e.data),
                    }
                    for e in events
                ],
                indent=2,
            )
        elif format == "csv":
            import csv
            import io
            import json

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["id", "timestamp", "event_type", "user_id", "session_id", "details"])
            for e in events:
                details = _details_payload(e.data)
                writer.writerow(
                    [
                        e.id,
                        e.created_at.isoformat(),
                        e.kind,
                        int(e.actor) if e.actor and e.actor.isdigit() else None,
                        int(e.ref) if e.ref and e.ref.isdigit() else None,
                        json.dumps(details),
                    ]
                )
            return output.getvalue()
        else:
            raise ValueError(f"Unsupported format: {format}")
