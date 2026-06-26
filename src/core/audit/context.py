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
Request-scoped principal context for audit attribution.

License: Apache 2.0
Ownership: Cloud Dog
Description:
    W28M-FIX-1614 (EA8). The authenticated principal is resolved once per
    request by ``AuthStateMiddleware`` and published into a ``ContextVar`` so
    that the audit emitters (``AuditLogger.log`` and ``AuditManager.log_event``)
    can stamp ``actor.id`` from the real caller WITHOUT threading the principal
    through every function signature. Anonymous requests leave the default
    (``None``), so an unauthenticated caller is NEVER attributed an
    admin/system identity (COMMON-FINAL-EVIDENCE-CLOSEOUT-CONTROLS §0C).

Related Requirements: FR1.10 (audit), CS1.1 (attribution)
Related Tasks: W28M-FIX-1614 / W28C-1704 EA8
Related Architecture: SE1.3 (audit)
Related Tests: UT1.133 (expert.execute audit emission)
"""

from __future__ import annotations

import contextvars
from typing import Optional, Tuple

_principal_id: contextvars.ContextVar[Optional[int]] = contextvars.ContextVar(
    "audit_principal_id", default=None
)
_principal_username: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "audit_principal_username", default=None
)
_principal_role: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "audit_principal_role", default=None
)

# Opaque token bundle returned by ``set_current_principal`` and consumed by
# ``reset_current_principal`` (one Token per ContextVar).
PrincipalTokens = Tuple[object, object, object]


def set_current_principal(
    user_id: Optional[int],
    username: Optional[str] = None,
    role: Optional[str] = None,
) -> PrincipalTokens:
    """Publish the authenticated principal for the current request context.

    Returns a token bundle that MUST be passed to ``reset_current_principal``
    in a ``finally`` block so the context does not leak across requests.
    """
    return (
        _principal_id.set(int(user_id) if user_id is not None else None),
        _principal_username.set(str(username) if username is not None else None),
        _principal_role.set(str(role) if role is not None else None),
    )


def reset_current_principal(tokens: PrincipalTokens) -> None:
    """Restore the principal context to its prior state."""
    id_tok, name_tok, role_tok = tokens
    _principal_id.reset(id_tok)
    _principal_username.reset(name_tok)
    _principal_role.reset(role_tok)


def get_current_principal_id() -> Optional[int]:
    """Return the authenticated principal id for the current context, or None."""
    return _principal_id.get()


def get_current_principal_username() -> Optional[str]:
    """Return the authenticated principal username for the current context, or None."""
    return _principal_username.get()


def get_current_principal_role() -> Optional[str]:
    """Return the authenticated principal role for the current context, or None."""
    return _principal_role.get()
