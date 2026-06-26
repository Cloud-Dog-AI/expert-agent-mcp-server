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
import os
System Test: ST1.8 - Session Persistence and Retrieval

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for session persistence and retrieval

Related Requirements: FR1.2
Related Tasks: T022
Related Architecture: CC2.1.1
Related Tests: ST1.8

Recent Changes:
- Initial implementation
"""

import pytest
from src.core.session.manager import SessionManager
from src.core.auth.user_manager import UserManager
from src.database.models import ExpertConfig, Session as SessionModel
from src.core.session.models import SessionState
from src.config.loader import get_config


@pytest.fixture
def session_manager(db_session):
    """Create session manager instance."""
    return SessionManager(db_session)


@pytest.fixture
def test_user(db_session):
    """Create test user."""
    import uuid

    manager = UserManager(db_session)
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in config")

    unique = uuid.uuid4().hex[:8]
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    domain = base_email.split("@", 1)[1]
    return manager.create_user(
        username=f"{base_username}_st1_8_{unique}",
        email=f"st1_8_{unique}@{domain}",
        password=password,
    )


@pytest.fixture
def test_expert(db_session, test_config):
    """Create test expert."""
    import uuid

    unique = uuid.uuid4().hex[:8]
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    if not llm_provider or not llm_model:
        pytest.fail("Missing llm.provider/llm.model in config")
    expert = ExpertConfig(
        name=f"persist_expert_{unique}",
        title="Persistence Expert",
        llm_provider=llm_provider,
        llm_model=llm_model,
        enabled=True,
    )
    db_session.add(expert)
    db_session.commit()
    db_session.refresh(expert)
    return expert
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_persistence_creation(session_manager, test_user, test_expert):
    """Test that sessions are persisted to database."""
    result = session_manager.create_session(
        user_id=test_user.id,
        expert_config_id=test_expert.id,
        title="Test Session",
        check_limits=False,
    )
    session, _ = result

    assert session.id is not None
    assert session.user_id == test_user.id
    assert session.expert_config_id == test_expert.id
    assert session.title == "Test Session"
    assert session.created_at is not None
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_retrieval_by_id(session_manager, test_user, test_expert):
    """Test retrieving session by ID."""
    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    session, _ = result
    session_id = session.id

    # Retrieve session
    retrieved = session_manager.get_session(session_id)

    assert retrieved is not None
    assert retrieved.id == session_id
    assert retrieved.user_id == test_user.id
    assert retrieved.expert_config_id == test_expert.id
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_persistence_across_restarts(session_manager, test_user, test_expert, db_session):
    """Test that sessions persist across database connections."""
    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    session, _ = result
    session_id = session.id

    # Simulate new connection by creating new manager
    new_manager = SessionManager(db_session)

    # Should still be able to retrieve
    retrieved = new_manager.get_session(session_id)

    assert retrieved is not None
    assert retrieved.id == session_id
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_state_persistence(session_manager, test_user, test_expert):
    """Test that session state changes are persisted."""
    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    session, _ = result

    # Update state
    session_manager.update_session_state(session.id, SessionState.ACTIVE)

    # Retrieve and verify
    retrieved = session_manager.get_session(session.id)
    assert retrieved.status == SessionState.ACTIVE.value
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_metadata_persistence(session_manager, test_user, test_expert, db_session):
    """Test that session metadata is persisted."""
    result = session_manager.create_session(
        user_id=test_user.id,
        expert_config_id=test_expert.id,
        context_window=8192,
        history_retention_days=60,
        check_limits=False,
    )
    session, _ = result

    # Verify metadata persisted
    assert session.context_window == 8192
    assert session.history_retention_days == 60

    # Retrieve and verify
    retrieved = session_manager.get_session(session.id)
    assert retrieved.context_window == 8192
    assert retrieved.history_retention_days == 60
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_list_retrieval(session_manager, test_user, test_expert, db_session):
    """Test retrieving list of sessions."""
    # Create multiple sessions
    sessions = []
    for i in range(3):
        result = session_manager.create_session(
            user_id=test_user.id,
            expert_config_id=test_expert.id,
            title=f"Session {i}",
            check_limits=False,
        )
        session, _ = result
        sessions.append(session)

    # Query sessions for user
    user_sessions = (
        db_session.query(SessionModel).filter(SessionModel.user_id == test_user.id).all()
    )

    assert len(user_sessions) >= 3
    assert all(s.user_id == test_user.id for s in user_sessions)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_timestamp_persistence(session_manager, test_user, test_expert):
    """Test that session timestamps are persisted correctly."""
    from datetime import datetime

    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    session, _ = result

    assert session.created_at is not None
    assert isinstance(session.created_at, datetime)
    assert session.updated_at is not None
    assert isinstance(session.updated_at, datetime)

    # Update and verify updated_at changes
    initial_updated = session.updated_at
    session_manager.update_session_state(session.id, SessionState.ACTIVE)

    retrieved = session_manager.get_session(session.id)
    assert retrieved.updated_at >= initial_updated

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.db, pytest.mark.smtp, pytest.mark.slow, pytest.mark.heavy]

