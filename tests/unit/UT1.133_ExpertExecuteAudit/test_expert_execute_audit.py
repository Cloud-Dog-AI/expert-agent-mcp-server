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
UT1.133 — expert.execute audit emission + actor.id stamping (EA3/EA8).

License: Apache 2.0
Ownership: Cloud-Dog, Viewdeck Engineering Limited
Description:
    Proves W28M-FIX-1614 (W28C-1704 EA3/EA8): the transactional executor emits
    a PS-40 ``expert.execute`` audit event on the success path (with
    ``output_sha256``, ``services_invoked``, ``token_usage``, ``outcome=success``,
    and the authenticated ``actor.id``) and on the failure path
    (``outcome=failure`` + ``error``, then re-raises). Also proves the EA8 actor
    backfill: when a caller does not pass ``user_id`` but a principal is present
    in the request-scoped context-var, the emitted event is attributed to that
    principal (never None / forged system identity for an authenticated caller).

Related Requirements: FR1.10 (audit), CS1.1 (attribution)
Related Tasks: W28M-FIX-1614 / W28C-1704 EA3/EA8
Related Architecture: SE1.3 (audit)
Related Tests: AT1.18 (audit log viewing)
"""

import asyncio
import json

import pytest

from src.core.audit.context import reset_current_principal, set_current_principal
from src.core.audit.manager import AuditManager
from src.core.auth.user_manager import UserManager
from src.core.execution.transactional import TransactionalExecutor
from src.database.models import AuditEvent, ExpertConfig


class StubLLMManager:
    async def initialize(self, **kwargs):
        return None

    async def generate(self, messages, temperature, max_tokens, **kwargs):
        return {"content": f"stubbed::{messages[-1]['content']}", "tokens_used": 23}


class FailingLLMManager:
    async def initialize(self, **kwargs):
        return None

    async def generate(self, messages, temperature, max_tokens, **kwargs):
        raise RuntimeError("llm boom")


def _make_user_and_expert(db_session):
    user = UserManager(db_session).create_user(
        username="audit_user",
        email="audit_user@example.com",
        password="Password123!",
        role="admin",
    )
    expert = ExpertConfig(
        name="audit_expert",
        title="Audit Expert",
        description="Expert with enough descriptive detail for audit-emission testing.",
        llm_provider="ollama",
        llm_model="granite4:tiny-h",
        enabled=True,
        prompt_template="You are {{ expert.title }}.",
    )
    db_session.add(expert)
    db_session.commit()
    db_session.refresh(expert)
    return user, expert
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_execute_success_emits_expert_execute_audit_with_sha_and_actor(db_session):
    user, expert = _make_user_and_expert(db_session)

    executor = TransactionalExecutor(db_session, llm_manager=StubLLMManager())
    result = asyncio.run(
        executor.execute(
            expert.id,
            "Summarise the report",
            auth_context={"user_id": user.id, "username": user.username, "role": user.role},
        )
    )
    assert result["output_text"] == "stubbed::Summarise the report"

    events = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.kind == "expert.execute")
        .order_by(AuditEvent.id.desc())
        .all()
    )
    assert events, "no expert.execute audit event was emitted"
    event = events[0]
    # EA8: actor.id is the authenticated principal, never None for an authed call.
    assert event.actor == str(user.id)
    data = json.loads(event.data)
    assert data["outcome"] == "success"
    assert data["output_sha256"] and len(data["output_sha256"]) == 64
    assert data["expert_id"] == expert.id
    assert "services_invoked" in data
    assert data["token_usage"] == 23
    assert data["llm_model"] == "granite4:tiny-h"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_execute_failure_emits_outcome_failure_and_reraises(db_session):
    user, expert = _make_user_and_expert(db_session)

    executor = TransactionalExecutor(db_session, llm_manager=FailingLLMManager())
    with pytest.raises(RuntimeError):
        asyncio.run(
            executor.execute(
                expert.id,
                "trigger failure",
                auth_context={"user_id": user.id, "username": user.username, "role": user.role},
            )
        )

    events = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.kind == "expert.execute")
        .order_by(AuditEvent.id.desc())
        .all()
    )
    assert events, "failure path did not emit an expert.execute audit event"
    data = json.loads(events[0].data)
    assert data["outcome"] == "failure"
    assert "llm boom" in str(data.get("error"))
    assert events[0].actor == str(user.id)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_log_event_backfills_actor_from_principal_context(db_session):
    """EA8: log_event with no explicit user_id is attributed to the context principal."""
    user, _expert = _make_user_and_expert(db_session)

    tokens = set_current_principal(user.id, user.username, user.role)
    try:
        AuditManager(db_session).log_event(event_type="ut1133.contextcheck", details={"x": 1})
    finally:
        reset_current_principal(tokens)

    event = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.kind == "ut1133.contextcheck")
        .order_by(AuditEvent.id.desc())
        .first()
    )
    assert event is not None
    assert event.actor == str(user.id)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_log_event_anonymous_stays_unattributed(db_session):
    """No principal in context => actor stays None (never a forged identity)."""
    AuditManager(db_session).log_event(event_type="ut1133.anoncheck", details={"x": 2})
    event = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.kind == "ut1133.anoncheck")
        .order_by(AuditEvent.id.desc())
        .first()
    )
    assert event is not None
    assert event.actor is None
