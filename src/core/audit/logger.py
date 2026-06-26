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
Audit Logger

License: Apache 2.0
Ownership: Cloud Dog
Description: Audit event logging with cryptographic signing

Related Requirements: FR1.10, CS1.3
Related Tasks: T041
Related Architecture: SE1.3
Related Tests: ST1.4

Recent Changes:
- Initial implementation
"""

import json
import hashlib
import hmac
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session

from cloud_dog_logging import Actor, Target, get_audit_logger
from src.database.models import AuditEvent as AuditEventModel
from src.database.connection import get_db
from src.config.loader import get_config
from src.core.audit.context import get_current_principal_id
from src.core.security.crypto import encrypt_if_enabled
from src.utils.logger import get_logger

logger = get_logger(__name__)
_VALID_OUTCOMES = {"success", "failure", "error", "denied", "partial"}


def _normalise_outcome(value: Any) -> str:
    raw = str(value or "success").strip().lower()
    if raw in _VALID_OUTCOMES:
        return raw
    aliases = {
        "ok": "success",
        "passed": "success",
        "complete": "success",
        "completed": "success",
        "failed": "failure",
        "forbidden": "denied",
    }
    return aliases.get(raw, "success")


class AuditLogger:
    """Audit event logger with cryptographic signing."""

    def __init__(self):
        secret = get_config("auth.jwt_secret")
        if not secret:
            raise RuntimeError(
                "auth.jwt_secret not configured. "
                "Set via config hierarchy (environment -> env file -> config.yaml -> defaults.yaml)."
            )
        self.secret_key = str(secret).encode()

    def _sign_event(self, data: str) -> str:
        """Cryptographically sign audit event."""
        return hmac.new(self.secret_key, data.encode(), hashlib.sha256).hexdigest()

    def _emit_platform_event(
        self,
        *,
        kind: str,
        ref: Optional[str],
        actor: Optional[str],
        data: Optional[Dict[str, Any]],
        ip: Optional[str],
        user_agent: Optional[str],
    ) -> None:
        """Mirror legacy audit writes into the platform PS-40 audit stream."""
        payload = dict(data or {})
        duration_ms = payload.pop("duration_ms", None)
        outcome = _normalise_outcome(payload.pop("outcome", "success"))
        if ip:
            payload.setdefault("client_ip", ip)
        if user_agent:
            payload.setdefault("user_agent", user_agent)

        action = kind.rsplit(".", 1)[-1] if "." in kind else kind
        target = self._build_target(kind=kind, ref=ref, actor=actor, payload=payload)
        payload.pop("target", None)

        audit_logger = get_audit_logger()
        event = audit_logger._build_event(
            event_type=kind,
            actor=Actor(
                type="user" if actor else "system",
                id=str(actor or "system"),
                ip=ip,
                user_agent=user_agent,
            ),
            action=action,
            outcome=outcome,
            target=target,
            duration_ms=duration_ms if isinstance(duration_ms, int) else None,
            **payload,
        )
        audit_logger.emit(event)

    @staticmethod
    def _build_target(
        *,
        kind: str,
        ref: Optional[str],
        actor: Optional[str],
        payload: Dict[str, Any],
    ) -> Target:
        """Build a PS-40 target object for mirrored platform audit events."""
        if isinstance(payload.get("target"), dict):
            raw_target = payload["target"]
            target_type = str(raw_target.get("type") or kind.split(".", 1)[0] or "resource")
            target_id = str(raw_target.get("id") or ref or actor or kind)
            target_name = raw_target.get("name")
            return Target(type=target_type, id=target_id, name=str(target_name) if target_name else kind)

        target_type = kind.split(".", 1)[0] if "." in kind else "resource"
        target_id = ref
        target_name: Optional[str] = kind

        candidate_keys = (
            f"{target_type}_id",
            "target_id",
            "user_id",
            "session_id",
            "channel_id",
            "expert_id",
            "group_id",
            "key_id",
            "subject",
            "username",
        )
        for key in candidate_keys:
            value = payload.get(key)
            if value not in (None, ""):
                target_id = str(value)
                break

        if target_type == "user" and target_id in (None, ""):
            target_id = str(actor or payload.get("username") or "anonymous")
        elif target_id in (None, ""):
            target_id = str(actor or kind)

        if target_type == "user":
            username = payload.get("username")
            if username not in (None, ""):
                target_name = str(username)

        return Target(type=target_type, id=str(target_id), name=target_name)

    def log(
        self,
        kind: str,
        ref: Optional[str] = None,
        actor: Optional[str] = None,
        data: Optional[Dict[str, Any]] = None,
        ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        db: Optional[Session] = None,
    ):
        """
        Log an audit event.

        Args:
            kind: Event kind (e.g., 'session.created', 'user.login')
            ref: Reference ID (e.g., session_id, user_id)
            actor: Actor identifier (user_id, api_key, etc.)
            data: Additional event data
            ip: Client IP address
            user_agent: Client user agent
            db: Database session (if None, creates new)
        """
        # EA8 (W28M-FIX-1614): when a route did not pass the actor explicitly,
        # source it from the authenticated principal context so audit events are
        # attributed to the real caller instead of None. Anonymous requests keep
        # actor=None (no principal in context) — never a forged system identity.
        if actor is None:
            ctx_principal = get_current_principal_id()
            if ctx_principal is not None:
                actor = str(ctx_principal)

        try:
            self._emit_platform_event(
                kind=kind,
                ref=ref,
                actor=actor,
                data=data,
                ip=ip,
                user_agent=user_agent,
            )
        except Exception as exc:
            logger.warning(f"Failed to emit platform audit event for {kind}: {exc}")

        # Store data as JSON (and encrypt at rest if configured)
        event_data_plain = json.dumps(data) if data else None
        event_data = encrypt_if_enabled(event_data_plain) if event_data_plain else None

        # Use an explicit timestamp we can later verify (do NOT rely on DB server_default).
        # MariaDB stores DateTime without microseconds by default, so normalise here.
        created_at = datetime.utcnow().replace(microsecond=0)

        # Create signature
        signature_data = f"{kind}:{ref}:{actor}:{event_data}:{created_at.isoformat()}"
        signature = self._sign_event(signature_data)

        # Store in database
        if db is None:
            db_gen = get_db()
            db = next(db_gen)
            close_db = True
        else:
            close_db = False

        try:
            audit_event = AuditEventModel(
                kind=kind,
                ref=ref,
                actor=actor,
                data=event_data,
                ip=ip,
                user_agent=user_agent,
                created_at=created_at,
                signature=signature,
            )
            db.add(audit_event)
            db.commit()
            logger.debug(f"Audit event logged: {kind} (ref: {ref})")
        except Exception as e:
            logger.error(f"Failed to log audit event: {e}", exc_info=True)
            db.rollback()
        finally:
            if close_db:
                db.close()


# Global audit logger instance
_audit_logger = AuditLogger()


def log_audit_event(
    kind: str,
    ref: Optional[str] = None,
    actor: Optional[str] = None,
    data: Optional[Dict[str, Any]] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    db: Optional[Session] = None,
):
    """Log an audit event (convenience function)."""
    _audit_logger.log(kind, ref, actor, data, ip, user_agent, db)
