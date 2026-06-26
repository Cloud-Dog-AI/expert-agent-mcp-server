"""
Authentication Audit Helpers

License: Apache 2.0
Ownership: Cloud Dog
Description: Structured audit helpers for auth, token, and API-key security events
"""

from __future__ import annotations

from typing import Optional

from cloud_dog_logging import Actor, Target, get_audit_logger

from src.utils.logger import get_server_id


def _system_actor() -> Actor:
    """Return the service principal Actor used for system-originated audit events."""
    server_id = get_server_id()
    return Actor(type="system", id=server_id, roles=["service"])


def log_authentication_event(
    username: str,
    outcome: str,
    *,
    user_id: Optional[int] = None,
    roles: Optional[list[str]] = None,
    reason: Optional[str] = None,
    auth_method: str = "password",
) -> None:
    """Emit a structured NIST-style security audit event for a login attempt."""
    actor_id = str(user_id) if user_id is not None else str(username or "unknown")
    details = {
        "username": str(username or "unknown"),
        "auth_method": auth_method,
        "server_id": get_server_id(),
    }
    if reason:
        details["reason"] = reason
    get_audit_logger().log_security(
        actor=Actor(type="user", id=actor_id, roles=roles),
        action="login",
        target=Target(type="user", id=actor_id, name=str(username or actor_id)),
        outcome=outcome,
        **details,
    )


def log_api_key_event(
    action: str,
    outcome: str,
    *,
    key_id: str,
    user_id: Optional[int] = None,
    group_id: Optional[int] = None,
    reason: Optional[str] = None,
    key_name: Optional[str] = None,
) -> None:
    """Emit a structured security audit event for an API-key lifecycle/usage action."""
    details = {"server_id": get_server_id()}
    if user_id is not None:
        details["user_id"] = user_id
    if group_id is not None:
        details["group_id"] = group_id
    if reason:
        details["reason"] = reason
    if key_name:
        details["name"] = key_name
    get_audit_logger().log_security(
        actor=_system_actor(),
        action=action,
        target=Target(type="api_key", id=str(key_id), name=key_name),
        outcome=outcome,
        **details,
    )


def log_token_event(
    action: str,
    outcome: str,
    *,
    subject: Optional[str] = None,
    reason: Optional[str] = None,
) -> None:
    """Emit a structured security audit event for a JWT token action (issue/verify/revoke)."""
    details = {"server_id": get_server_id()}
    if reason:
        details["reason"] = reason
    if subject:
        details["subject"] = subject
    get_audit_logger().log_security(
        actor=_system_actor(),
        action=action,
        target=Target(type="auth_token", id=str(subject or "jwt")),
        outcome=outcome,
        **details,
    )
