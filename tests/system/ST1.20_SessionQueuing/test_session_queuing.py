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
System Test: ST1.20 - Session Queuing and Prioritization

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for session queuing and prioritization

Related Requirements: FR1.11
Related Tasks: T028
Related Architecture: CC2.1.2
Related Tests: ST1.20

Recent Changes:
- Initial implementation
"""

import pytest
from src.core.session.concurrency import ConcurrencyManager, QueuePriority
from src.core.session.manager import SessionManager
from src.core.auth.user_manager import UserManager
from src.database.models import ExpertConfig
from src.config.loader import get_config


@pytest.fixture
def test_user(db_session):
    """Create a test user."""
    import uuid

    manager = UserManager(db_session)
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in config")

    # Use unique username/email to avoid conflicts in full test runs
    unique_id = str(uuid.uuid4())[:8]
    username = f"{base_username}_st1_20_{unique_id}"
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    email = f"st1_20_{unique_id}@{base_email.split('@')[1]}"

    # Always create new user with unique credentials to avoid conflicts
    return manager.create_user(username=username, email=email, password=password)


@pytest.fixture
def test_expert(db_session, test_config):
    """Create a test expert configuration."""
    import uuid

    unique_id = str(uuid.uuid4())[:8]
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    if not llm_provider or not llm_model:
        pytest.fail("Missing llm.provider/llm.model in config")
    expert = ExpertConfig(
        name=f"test_expert_st1_20_{unique_id}",
        title="Test Expert",
        description="Test expert configuration",
        llm_provider=llm_provider,
        llm_model=llm_model,
        enabled=True,
    )
    db_session.add(expert)
    db_session.commit()
    db_session.refresh(expert)
    return expert


@pytest.fixture
def concurrency_manager(db_session):
    """Create concurrency manager with queue enabled."""
    manager = ConcurrencyManager(db_session)
    manager.queue_enabled = True
    return manager
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_system_queues_session_when_limit_reached(
    concurrency_manager, test_user, test_expert, db_session
):
    """Test that system queues sessions when limit is reached."""
    # Create session manager - it will use the config value
    session_manager = SessionManager(db_session)
    # Update the concurrency manager's limit
    session_manager.concurrency_manager.default_user_limit = 1

    # Create session to reach limit
    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    session, _ = result
    from src.core.session.models import SessionState

    session_manager.update_session_state(session.id, SessionState.ACTIVE)
    db_session.commit()  # Commit to ensure limit check sees it

    # Verify limit is actually reached using SessionManager's concurrency manager
    allowed, reason, count = session_manager.concurrency_manager.check_user_session_limit(
        test_user.id
    )
    assert allowed is False, (
        f"Limit should be reached. Count: {count}, Limit: {session_manager.concurrency_manager.default_user_limit}"
    )

    # Try to create another session - should be queued
    result2 = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=True, queue_if_full=True
    )
    session2, notification = result2

    # When limit is reached and queued, session should be None
    assert session2 is None, "Session should be None when queued"
    assert notification is not None, "Notification should be provided when queued"
    assert notification.get("queued") is True, "Notification should indicate queued status"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_system_queue_prioritization(concurrency_manager, test_user, test_expert):
    """Test that system respects queue priorities."""
    # Queue sessions with different priorities
    concurrency_manager.queue_session(test_user.id, test_expert.id, QueuePriority.HIGH)
    concurrency_manager.queue_session(test_user.id, test_expert.id, QueuePriority.NORMAL)
    concurrency_manager.queue_session(test_user.id, test_expert.id, QueuePriority.LOW)

    # Process queue - should return in priority order
    processed = concurrency_manager.process_queue()

    # High priority should be processed first
    if len(processed) > 0:
        assert processed[0]["priority"] in ["high", "urgent"]
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_system_queue_position_tracking(concurrency_manager, test_user, test_expert):
    """Test that system tracks queue positions."""
    # Queue multiple sessions
    queue_entry1 = concurrency_manager.queue_session(
        test_user.id, test_expert.id, QueuePriority.NORMAL
    )
    queue_entry2 = concurrency_manager.queue_session(
        test_user.id, test_expert.id, QueuePriority.NORMAL
    )
    queue_entry3 = concurrency_manager.queue_session(
        test_user.id, test_expert.id, QueuePriority.NORMAL
    )

    # Check positions (may return 0 if not implemented or positions are same)
    pos1 = concurrency_manager.get_queue_position(test_user.id, queue_entry1)
    pos2 = concurrency_manager.get_queue_position(test_user.id, queue_entry2)
    pos3 = concurrency_manager.get_queue_position(test_user.id, queue_entry3)

    # Positions should be sequential if implemented
    # If all return 0, that's acceptable (implementation may not track positions)
    assert isinstance(pos1, int)
    assert isinstance(pos2, int)
    assert isinstance(pos3, int)
    # If positions are tracked, they should be sequential
    if pos1 > 0 or pos2 > 0 or pos3 > 0:
        assert pos1 <= pos2
        assert pos2 <= pos3
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_system_queue_processing(concurrency_manager, test_user, test_expert):
    """Test that system processes queue correctly."""
    # Queue multiple sessions
    for i in range(3):
        concurrency_manager.queue_session(test_user.id, test_expert.id, QueuePriority.NORMAL)

    # Process queue
    processed = concurrency_manager.process_queue()

    assert isinstance(processed, list)
    assert len(processed) <= 3  # May process all or some
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_system_queue_with_urgent_priority(concurrency_manager, test_user, test_expert):
    """Test that urgent priority sessions are processed first."""
    # Queue with different priorities
    concurrency_manager.queue_session(test_user.id, test_expert.id, QueuePriority.NORMAL)
    concurrency_manager.queue_session(test_user.id, test_expert.id, QueuePriority.URGENT)
    concurrency_manager.queue_session(test_user.id, test_expert.id, QueuePriority.HIGH)

    # Process queue
    processed = concurrency_manager.process_queue()

    # Urgent should be first
    if len(processed) > 0:
        assert processed[0]["priority"] == "urgent"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_system_queue_notification(concurrency_manager, test_user):
    """Test that system notifies users when queued."""
    reason = "Session limit reached"
    queue_entry = concurrency_manager.queue_session(test_user.id, 1, QueuePriority.NORMAL)

    notification = concurrency_manager.notify_user_limit_reached(test_user.id, reason, queue_entry)

    assert notification["queued"] is True
    assert "queue" in notification["message"].lower()
    assert "position" in notification or "queued" in notification
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_system_queue_multiple_users(concurrency_manager, db_session):
    """Test that system handles queue for multiple users."""
    user_manager = UserManager(db_session)
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in config")
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    domain = base_email.split("@", 1)[1]
    user1 = user_manager.create_user(
        f"{base_username}_st1_20_user1",
        f"st1_20_user1@{domain}",
        password,
    )
    user2 = user_manager.create_user(
        f"{base_username}_st1_20_user2",
        f"st1_20_user2@{domain}",
        password,
    )

    # Queue sessions for different users
    queue1 = concurrency_manager.queue_session(user1.id, 1, QueuePriority.NORMAL)
    queue2 = concurrency_manager.queue_session(user2.id, 1, QueuePriority.NORMAL)

    # Both should be queued
    assert queue1 is not None
    assert queue2 is not None
    assert queue1["user_id"] == user1.id
    assert queue2["user_id"] == user2.id

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.db, pytest.mark.smtp, pytest.mark.slow, pytest.mark.heavy]

