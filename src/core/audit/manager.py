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
Audit Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Audit logging with cryptographic signing

Related Requirements: FR1.10
Related Tasks: T041
Related Architecture: SE1.3
Related Tests: AT1.6, UT1.29

Recent Changes:
- Initial implementation
"""

import hashlib
import hmac
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from cloud_dog_logging import Actor, Target, get_audit_logger

from src.database.models import AuditEvent as AuditEventModel
from src.database.connection import get_db
from src.config.loader import get_config
from src.core.audit.context import get_current_principal_id
from src.utils.logger import get_logger

logger = get_logger(__name__)


class AuditManager:
    """Manages audit logging with integrity verification."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize audit manager.

        Args:
            db: Database session (if None, creates new)
        """
        self.db = db
        self.secret_key = get_config("security.audit_secret_key")
        if not self.secret_key:
            raise RuntimeError(
                "security.audit_secret_key not configured. "
                "Set via config hierarchy (environment -> env file -> config.yaml -> defaults.yaml)."
            )

    def _get_db(self) -> Session:
        """Get database session."""
        if self.db:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    def _generate_signature(self, event_data: Dict[str, Any]) -> str:
        """
        Generate cryptographic signature for audit event.

        Args:
            event_data: Event data dictionary

        Returns:
            Hexadecimal signature string
        """
        # Create canonical representation
        canonical = json.dumps(event_data, sort_keys=True)

        # Generate HMAC signature
        signature = hmac.new(
            self.secret_key.encode(), canonical.encode(), hashlib.sha256
        ).hexdigest()

        return signature

    @staticmethod
    def _build_target(
        event_type: str,
        *,
        user_id: Optional[int],
        session_id: Optional[int],
        channel_id: Optional[int],
        expert_id: Optional[int],
        details: Optional[Dict[str, Any]],
    ) -> Target:
        """Resolve a PS-40-compliant target for platform audit emission."""
        event_prefix = event_type.split(".", 1)[0] if "." in event_type else "resource"
        details = details or {}

        if session_id is not None:
            return Target(type="session", id=str(session_id), name=event_type)
        if channel_id is not None:
            return Target(type="channel", id=str(channel_id), name=event_type)
        if expert_id is not None:
            return Target(type="expert", id=str(expert_id), name=event_type)
        if user_id is not None:
            return Target(type="user", id=str(user_id), name=event_type)

        explicit_target = details.get("target")
        if isinstance(explicit_target, dict):
            return Target(
                type=str(explicit_target.get("type") or event_prefix),
                id=str(explicit_target.get("id") or event_type),
                name=str(explicit_target.get("name") or event_type),
            )

        for key, target_type in (
            ("target_id", event_prefix),
            ("user_id", "user"),
            ("session_id", "session"),
            ("channel_id", "channel"),
            ("expert_id", "expert"),
            ("username", "user"),
        ):
            value = details.get(key)
            if value not in (None, ""):
                return Target(type=target_type, id=str(value), name=event_type)

        return Target(type=event_prefix, id=event_type, name=event_type)

    def _emit_platform_event(
        self,
        *,
        event_type: str,
        user_id: Optional[int],
        session_id: Optional[int],
        channel_id: Optional[int],
        expert_id: Optional[int],
        ip_address: Optional[str],
        user_agent: Optional[str],
        details: Optional[Dict[str, Any]],
    ) -> None:
        """Mirror database audit writes into the platform audit stream."""
        target = self._build_target(
            event_type,
            user_id=user_id,
            session_id=session_id,
            channel_id=channel_id,
            expert_id=expert_id,
            details=details,
        )
        actor_id = str(user_id) if user_id is not None else "system"
        actor_type = "user" if user_id is not None else "system"
        payload = dict(details or {})
        action = str(payload.pop("action", event_type.rsplit(".", 1)[-1] if "." in event_type else event_type) or event_type)
        outcome = str(payload.pop("outcome", "success") or "success")
        severity = str(payload.pop("severity", "INFO") or "INFO").upper()
        duration_ms = payload.pop("duration_ms", None)
        payload.pop("target", None)
        audit_logger = get_audit_logger()
        audit_logger.emit(
            audit_logger._build_event(
                event_type=event_type,
                actor=Actor(type=actor_type, id=actor_id, ip=ip_address, user_agent=user_agent),
                action=action,
                outcome=outcome,
                target=target,
                duration_ms=duration_ms,
                severity=severity,
                **payload,
            )
        )

    def log_event(
        self,
        event_type: str,
        user_id: Optional[int] = None,
        session_id: Optional[int] = None,
        channel_id: Optional[int] = None,
        expert_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> AuditEventModel:
        """
        Log an audit event.

        Args:
            event_type: Type of event
            user_id: User ID (optional)
            session_id: Session ID (optional)
            channel_id: Channel ID (optional)
            expert_id: Expert ID (optional)
            ip_address: IP address (optional)
            user_agent: User agent (optional)
            details: Additional details (optional)

        Returns:
            Created audit event
        """
        # EA8 (W28M-FIX-1614): backfill actor.id from the authenticated principal
        # context when the caller did not pass user_id explicitly. Anonymous
        # callers (no principal in context) keep user_id=None.
        if user_id is None:
            ctx_principal = get_current_principal_id()
            if ctx_principal is not None:
                user_id = int(ctx_principal)

        db = self._get_db()

        # Prepare event data for signature
        # Store all relevant fields in a combined details dict for signature verification
        timestamp = datetime.utcnow().isoformat()
        combined_details = details.copy() if details else {}
        # Only include non-None values to avoid JSON null issues
        if user_id is not None:
            combined_details["user_id"] = user_id
        if session_id is not None:
            combined_details["session_id"] = session_id
        if channel_id is not None:
            combined_details["channel_id"] = channel_id
        if expert_id is not None:
            combined_details["expert_id"] = expert_id

        # Store timestamp in details for signature verification
        combined_details["timestamp"] = timestamp

        event_data = {"event_type": event_type, "timestamp": timestamp, "details": combined_details}

        # Generate signature
        signature = self._generate_signature(event_data)

        self._emit_platform_event(
            event_type=event_type,
            user_id=user_id,
            session_id=session_id,
            channel_id=channel_id,
            expert_id=expert_id,
            ip_address=ip_address,
            user_agent=user_agent,
            details=combined_details,
        )

        # Create audit event (using 'kind' field as per model)
        # Store combined_details (including timestamp) in data field for signature verification
        event = AuditEventModel(
            kind=event_type,
            ref=str(session_id) if session_id else None,
            actor=str(user_id) if user_id else None,
            data=json.dumps(
                combined_details
            ),  # Store full details including user_id, session_id, timestamp, etc.
            ip=ip_address,
            user_agent=user_agent,
            signature=signature,
        )

        db.add(event)
        db.commit()
        db.refresh(event)

        logger.info(f"Audit event logged: {event_type} (ID: {event.id})")
        return event

    def get_events(
        self,
        user_id: Optional[int] = None,
        session_id: Optional[int] = None,
        event_type: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        limit: Optional[int] = None,
        offset: int = 0,
    ) -> List[AuditEventModel]:
        """
        Get audit events with filtering.

        Args:
            user_id: Filter by user ID (via actor field)
            session_id: Filter by session ID (via ref field)
            event_type: Filter by event type (via kind field)
            start_time: Start time filter
            end_time: End time filter
            limit: Maximum number of events
            offset: Offset for pagination

        Returns:
            List of audit events
        """
        db = self._get_db()
        query = db.query(AuditEventModel)

        if user_id:
            query = query.filter(AuditEventModel.actor == str(user_id))
        if session_id:
            query = query.filter(AuditEventModel.ref == str(session_id))
        if event_type:
            query = query.filter(AuditEventModel.kind == event_type)
        if start_time:
            query = query.filter(AuditEventModel.created_at >= start_time)
        if end_time:
            query = query.filter(AuditEventModel.created_at <= end_time)

        query = query.order_by(AuditEventModel.created_at.desc())

        if offset:
            query = query.offset(offset)
        if limit:
            query = query.limit(limit)

        return query.all()

    def verify_event_signature(self, event: AuditEventModel) -> bool:
        """
        Verify audit event signature.

        Args:
            event: Audit event

        Returns:
            True if signature is valid
        """
        # Reconstruct event data (using model fields)
        # Parse data to extract original details (which includes timestamp)
        try:
            details = json.loads(event.data) if event.data else {}
        except (json.JSONDecodeError, TypeError):
            details = {}

        # Extract timestamp from details (stored during creation) or fall back to created_at
        # Make a copy to avoid modifying the original
        details_copy = details.copy()
        timestamp = details_copy.pop("timestamp", event.created_at.isoformat())

        # Reconstruct event_data exactly as it was when signed
        # Note: timestamp is both at top level AND in details in the original
        event_data = {
            "event_type": event.kind,
            "timestamp": timestamp,  # Use timestamp from details, not created_at
            "details": details,  # Should contain user_id, session_id, etc. AND timestamp (as stored)
        }

        # Generate expected signature
        expected_signature = self._generate_signature(event_data)

        # Compare signatures
        return hmac.compare_digest(event.signature, expected_signature)

    def export_events(self, user_id: Optional[int] = None, format: str = "json") -> Any:
        """
        Export audit events.

        Args:
            user_id: Filter by user ID
            format: Export format ("json", "csv")

        Returns:
            Exported data
        """
        events = self.get_events(user_id=user_id)

        if format == "json":
            return json.dumps(
                [
                    {
                        "id": event.id,
                        "timestamp": event.created_at.isoformat(),
                        "event_type": event.kind,
                        "user_id": int(event.actor)
                        if event.actor and event.actor.isdigit()
                        else None,
                        "session_id": int(event.ref) if event.ref and event.ref.isdigit() else None,
                        "details": json.loads(event.data) if event.data else {},
                        "signature": event.signature,
                    }
                    for event in events
                ],
                indent=2,
            )
        else:
            # CSV format
            import csv
            import io

            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["ID", "Timestamp", "Event Type", "User ID", "Session ID", "Details"])
            for event in events:
                writer.writerow(
                    [
                        event.id,
                        event.created_at.isoformat(),
                        event.kind,
                        event.actor or "",
                        event.ref or "",
                        event.data or "",
                    ]
                )
            return output.getvalue()
