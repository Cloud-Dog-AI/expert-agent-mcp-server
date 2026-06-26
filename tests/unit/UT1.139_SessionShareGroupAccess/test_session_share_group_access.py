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
Unit Test: UT1.139 — Session sharing group access, summary consolidation, state history.

License: Apache 2.0
Ownership: Cloud-Dog, Viewdeck Engineering Limited
Description:
    W28E-1809B Stream-B functional-gap closure unit coverage:
      * HistorySharingManager.can_access_session — group-shared access via live
        group membership (FR-019: group membership + live revocation).
      * ContextSummarizationManager.consolidate_summaries — real merge + persist
        (FR-013: conversation management / context summarization).
      * SessionSynchronizer.get_session_state_history — real audit-event query
        (FR-013: real-time session state history).

Related Requirements: FR-019, FR-013
Related Tests: UT1.139
"""

from __future__ import annotations

import json
import uuid

import pytest

from src.core.auth.group_manager import GroupManager
from src.core.auth.user_manager import UserManager
from src.core.session.sharing_manager import HistorySharingManager
from src.core.session.summarization_manager import ContextSummarizationManager
from src.core.session.synchronization import SessionSynchronizer
from src.database.models import AuditEvent
from src.database.models import Session as SessionModel
from src.database.models import Summary as SummaryModel
from tests.helpers_orchestration import seed_expert


def _make_user(db_session, role: str = "user"):
    unique = uuid.uuid4().hex[:8]
    return UserManager(db_session).create_user(
        username=f"ut139_{role}_{unique}",
        email=f"ut139_{role}_{unique}@example.com",
        password="Password123!",
        role=role,
        enabled=True,
    )


def _make_session(db_session, owner_id: int) -> SessionModel:
    expert = seed_expert(
        db_session,
        name=f"ut139_expert_{uuid.uuid4().hex[:8]}",
        title="UT1.139 Expert",
        description="UT1.139 session sharing coverage expert.",
    )
    session = SessionModel(user_id=owner_id, expert_config_id=expert.id, title="UT1.139 Session")
    db_session.add(session)
    db_session.commit()
    db_session.refresh(session)
    return session


@pytest.mark.UT
@pytest.mark.internal
@pytest.mark.req("FR-019")
def test_owner_can_access_session(db_session):
    owner = _make_user(db_session)
    session = _make_session(db_session, owner.id)
    mgr = HistorySharingManager(db_session)
    assert mgr.can_access_session(session, owner.id) is True


@pytest.mark.UT
@pytest.mark.internal
@pytest.mark.req("FR-019")
def test_shared_user_access_and_unshared_denied(db_session):
    owner = _make_user(db_session)
    shared = _make_user(db_session)
    stranger = _make_user(db_session)
    session = _make_session(db_session, owner.id)

    mgr = HistorySharingManager(db_session)
    mgr.share_session(session.id, user_ids=[shared.id])
    db_session.refresh(session)

    assert mgr.can_access_session(session, shared.id) is True
    assert mgr.can_access_session(session, stranger.id) is False


@pytest.mark.UT
@pytest.mark.internal
@pytest.mark.negative
@pytest.mark.req("FR-019")
def test_group_member_access_and_live_revocation(db_session):
    owner = _make_user(db_session)
    member = _make_user(db_session)
    outsider = _make_user(db_session)
    session = _make_session(db_session, owner.id)

    groups = GroupManager(db_session)
    group = groups.create_group(name=f"ut139_group_{uuid.uuid4().hex[:8]}")
    groups.add_member(group.id, member.id)

    mgr = HistorySharingManager(db_session)
    mgr.share_session(session.id, group_ids=[group.id])
    db_session.refresh(session)

    # Member of a shared group has access; a non-member does not.
    assert mgr.can_access_session(session, member.id) is True
    assert mgr.can_access_session(session, outsider.id) is False

    # Live revocation: removing the membership immediately removes access.
    groups.remove_member(group.id, member.id)
    db_session.refresh(session)
    assert mgr.can_access_session(session, member.id) is False


@pytest.mark.UT
@pytest.mark.internal
@pytest.mark.req("FR-013")
def test_consolidate_summaries_merges_and_persists(db_session):
    owner = _make_user(db_session)
    session = _make_session(db_session, owner.id)

    for idx, text in enumerate(["first summary", "second summary", "third summary"]):
        db_session.add(
            SummaryModel(
                session_id=session.id,
                summary_text=text,
                original_message_count=10 + idx,
                preserved_message_count=2,
            )
        )
    db_session.commit()

    mgr = ContextSummarizationManager(db_session)
    result = mgr.consolidate_summaries(session.id)

    assert result["consolidated"] is True
    assert result["consolidated_count"] == 3
    # Merged text carries every source summary, oldest first.
    assert "first summary" in result["summary_text"]
    assert "third summary" in result["summary_text"]
    assert result["original_message_count"] == (10 + 11 + 12)
    # Exactly one consolidated row remains (the superseded rows were removed).
    remaining = db_session.query(SummaryModel).filter(SummaryModel.session_id == session.id).all()
    assert len(remaining) == 1
    assert remaining[0].id == result["summary_id"]


@pytest.mark.UT
@pytest.mark.internal
@pytest.mark.req("FR-013")
def test_consolidate_summaries_noop_when_single(db_session):
    owner = _make_user(db_session)
    session = _make_session(db_session, owner.id)
    db_session.add(
        SummaryModel(
            session_id=session.id,
            summary_text="only one",
            original_message_count=5,
            preserved_message_count=1,
        )
    )
    db_session.commit()

    result = ContextSummarizationManager(db_session).consolidate_summaries(session.id)
    assert result["consolidated"] is False


@pytest.mark.UT
@pytest.mark.internal
@pytest.mark.req("FR-013")
def test_get_session_state_history_returns_audit_events(db_session):
    owner = _make_user(db_session)
    session = _make_session(db_session, owner.id)

    db_session.add(
        AuditEvent(
            kind="session.state_changed",
            ref=str(session.id),
            actor=str(owner.id),
            data=json.dumps({"new_state": "active"}),
        )
    )
    db_session.commit()

    history = SessionSynchronizer(db_session).get_session_state_history(session.id)
    assert len(history) == 1
    assert history[0]["kind"] == "session.state_changed"
    assert history[0]["data"]["new_state"] == "active"
    assert history[0]["session_id"] == session.id


@pytest.mark.UT
@pytest.mark.internal
@pytest.mark.req("FR-013")
def test_get_session_state_history_empty_when_none(db_session):
    owner = _make_user(db_session)
    session = _make_session(db_session, owner.id)
    history = SessionSynchronizer(db_session).get_session_state_history(session.id)
    assert history == []
