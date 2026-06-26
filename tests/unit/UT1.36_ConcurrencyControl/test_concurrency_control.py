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
Unit Test: UT1.36 - Session Limit Enforcement per User/Group

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for concurrency control

Related Requirements: FR1.11
Related Tasks: T027
Related Architecture: CP1.1.5
Related Tests: UT1.36

Recent Changes:
- Initial implementation
"""

import pytest
from datetime import datetime, timedelta
from src.core.session.concurrency import ConcurrencyManager, QueuePriority
from src.database.models import Session as SessionModel, ExpertConfig
from src.core.session.models import SessionState


@pytest.fixture
def test_user(db_session):
    """Create a test user."""
    import uuid
    from src.core.auth.user_manager import UserManager
    from src.config.loader import get_config

    manager = UserManager(db_session)
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail(
            "Missing test.user.username/test.user.email/test.user.password in config (--env)"
        )
    unique = uuid.uuid4().hex[:8]
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    domain = base_email.split("@", 1)[1]
    return manager.create_user(
        username=f"{base_username}_ut1_36_{unique}",
        email=f"ut1_36_{unique}@{domain}",
        password=password,
    )


@pytest.fixture
def concurrency_manager(db_session):
    """Create a concurrency manager."""
    return ConcurrencyManager(db_session)


@pytest.fixture
def test_expert(db_session):
    """Create a test expert configuration."""
    from src.config.loader import get_config

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    if not llm_provider or not llm_model:
        pytest.fail("Missing llm.provider/llm.model in config (--env)")
    expert = ExpertConfig(
        name="ut1_36_expert",
        title="UT1.36 Expert",
        description="UT1.36 expert configuration for concurrency tests.",
        llm_provider=llm_provider,
        llm_model=llm_model,
        enabled=True,
    )
    db_session.add(expert)
    db_session.commit()
    db_session.refresh(expert)
    return expert
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_concurrency_manager_initialization(concurrency_manager):
    """Test concurrency manager can be initialized."""
    assert concurrency_manager is not None
    assert concurrency_manager.default_user_limit > 0
    assert concurrency_manager.default_group_limit > 0
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_check_user_session_limit_allowed(concurrency_manager, test_user):
    """Test checking user session limit when allowed."""
    allowed, reason, count = concurrency_manager.check_user_session_limit(test_user.id)

    assert allowed is True
    assert reason is None
    assert count >= 0
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_check_user_session_limit_exceeded(concurrency_manager, test_user, test_expert, db_session):
    """Test checking user session limit when exceeded."""
    # Set a very low limit for testing
    concurrency_manager.default_user_limit = 1

    # Create a session to reach the limit
    from src.core.session.manager import SessionManager

    session_manager = SessionManager(db_session)
    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    session, _ = result
    session_manager.update_session_state(session.id, SessionState.ACTIVE)

    # Now check limit - should be exceeded
    allowed, reason, count = concurrency_manager.check_user_session_limit(test_user.id)

    assert allowed is False
    assert reason is not None
    assert "limit" in reason.lower()
    assert count >= 1
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_check_user_session_limit_ignores_timed_out_sessions(
    concurrency_manager, test_user, test_expert, db_session
):
    """Timed-out active sessions must be expired before limit checks."""
    concurrency_manager.default_user_limit = 1

    from src.core.session.manager import SessionManager

    session_manager = SessionManager(db_session)
    session, _ = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    session_manager.update_session_state(session.id, SessionState.ACTIVE)

    stale_session = db_session.query(SessionModel).filter(SessionModel.id == session.id).first()
    assert stale_session is not None
    stale_session.updated_at = datetime.utcnow() - timedelta(days=365)
    db_session.commit()

    allowed, reason, count = concurrency_manager.check_user_session_limit(test_user.id)
    assert allowed is True
    assert reason is None
    assert count == 0

    refreshed = db_session.query(SessionModel).filter(SessionModel.id == session.id).first()
    assert refreshed is not None
    assert refreshed.status == "ended"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_queue_session(concurrency_manager, test_user, test_expert):
    """Test queueing a session."""
    if not concurrency_manager.queue_enabled:
        pytest.skip("Queue not enabled")

    queue_entry = concurrency_manager.queue_session(
        user_id=test_user.id, expert_config_id=test_expert.id, priority=QueuePriority.NORMAL
    )

    assert queue_entry is not None
    assert queue_entry["user_id"] == test_user.id
    assert queue_entry["status"] == "queued"
    assert "queued_at" in queue_entry
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_queue_session_with_priority(concurrency_manager, test_user, test_expert):
    """Test queueing a session with different priorities."""
    if not concurrency_manager.queue_enabled:
        pytest.skip("Queue not enabled")

    high_priority = concurrency_manager.queue_session(
        user_id=test_user.id, expert_config_id=test_expert.id, priority=QueuePriority.HIGH
    )

    low_priority = concurrency_manager.queue_session(
        user_id=test_user.id, expert_config_id=test_expert.id, priority=QueuePriority.LOW
    )

    assert high_priority["priority"] == "high"
    assert low_priority["priority"] == "low"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_notify_user_limit_reached(concurrency_manager, test_user):
    """Test user notification when limit reached."""
    reason = "User session limit (10) reached"
    notification = concurrency_manager.notify_user_limit_reached(test_user.id, reason)

    assert notification is not None
    assert notification["user_id"] == test_user.id
    assert "limit" in notification["message"].lower()
    assert notification["queued"] is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_notify_user_limit_reached_with_queue(concurrency_manager, test_user, test_expert):
    """Test user notification when limit reached with queue."""
    if not concurrency_manager.queue_enabled:
        pytest.skip("Queue not enabled")

    queue_entry = concurrency_manager.queue_session(
        user_id=test_user.id, expert_config_id=test_expert.id, priority=QueuePriority.NORMAL
    )

    reason = "User session limit (10) reached"
    notification = concurrency_manager.notify_user_limit_reached(test_user.id, reason, queue_entry)

    assert notification["queued"] is True
    assert "queue" in notification["message"].lower()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_get_queue_position(concurrency_manager, test_user, test_expert):
    """Test getting queue position."""
    if not concurrency_manager.queue_enabled:
        pytest.skip("Queue not enabled")

    queue_entry = concurrency_manager.queue_session(
        user_id=test_user.id, expert_config_id=test_expert.id
    )

    position = concurrency_manager.get_queue_position(test_user.id, queue_entry)

    assert isinstance(position, int)
    assert position >= 0
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_process_queue(concurrency_manager):
    """Test processing queue."""
    if not concurrency_manager.queue_enabled:
        pytest.skip("Queue not enabled")

    processed = concurrency_manager.process_queue()

    assert isinstance(processed, list)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_check_user_session_limit_with_group(concurrency_manager, test_user, db_session):
    """Test checking user session limit with group."""
    # Create a group and add user
    from src.core.auth.group_manager import GroupManager
    from src.config.loader import get_config

    group_manager = GroupManager(db_session)
    group_prefix = get_config("test.group.name_prefix")
    if not group_prefix:
        pytest.fail("Missing test.group.name_prefix in config (--env)")
    group = group_manager.create_group(f"{group_prefix}_ut1_36_group")
    group_manager.add_member(group.id, test_user.id)

    # Check limit with group
    allowed, reason, count = concurrency_manager.check_user_session_limit(
        test_user.id, group_id=group.id
    )

    assert isinstance(allowed, bool)
    assert count >= 0

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.db, pytest.mark.smtp, pytest.mark.fast]

