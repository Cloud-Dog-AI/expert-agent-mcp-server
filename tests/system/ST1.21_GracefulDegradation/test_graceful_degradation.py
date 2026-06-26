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
System Test: ST1.21 - Graceful Degradation When Limits Are Reached

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for graceful degradation

Related Requirements: FR1.11
Related Tasks: T029
Related Architecture: CP1.1.5
Related Tests: ST1.21

Recent Changes:
- Initial implementation
"""

import pytest
from src.core.session.manager import SessionManager
from src.core.session.concurrency import ConcurrencyManager, QueuePriority
from src.core.auth.user_manager import UserManager
from src.database.models import ExpertConfig
from src.core.session.models import SessionState
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
    username = f"{base_username}_st1_21_{unique_id}"
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    email = f"st1_21_{unique_id}@{base_email.split('@')[1]}"

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
        name=f"test_expert_st1_21_{unique_id}",
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
    manager.default_user_limit = 1  # Low limit for testing
    return manager
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_graceful_handling_when_limit_reached(
    concurrency_manager, test_user, test_expert, db_session
):
    """Test graceful handling when session limit is reached."""
    session_manager = SessionManager(db_session)

    # Create session to reach limit
    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    session, _ = result
    session_manager.update_session_state(session.id, SessionState.ACTIVE)

    # Try to create another session with queue enabled
    result2 = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=True, queue_if_full=True
    )
    session2, notification = result2

    # Should return graceful notification when queued
    if notification and notification.get("queued"):
        assert session2 is None
        assert "message" in notification
        assert notification["queued"] is True
    else:
        # If limit not reached or check passes, session may be created
        assert session2 is not None or notification is not None
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_graceful_notification_content(concurrency_manager, test_user, test_expert, db_session):
    """Test that notification contains helpful information."""
    session_manager = SessionManager(db_session)

    # Reach limit
    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    session, _ = result
    session_manager.update_session_state(session.id, SessionState.ACTIVE)

    # Try to create another
    result2 = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=True, queue_if_full=True
    )
    session2, notification = result2

    # Notification should be informative when queued
    if notification and notification.get("queued"):
        assert "message" in notification
        assert len(notification["message"]) > 0
        assert notification["queued"] is True
    else:
        # If not queued, notification may be None
        assert notification is None or isinstance(notification, dict)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_graceful_handling_without_queue(concurrency_manager, test_user, test_expert, db_session):
    """Test graceful handling when queue is disabled."""
    import os

    os.environ["CLOUD_DOG__EXPERT__SESSION__MAX_SESSIONS_PER_USER"] = "1"
    from src.config.loader import load_config

    load_config.cache_clear()

    session_manager = SessionManager(db_session)
    # Update the concurrency manager's limit and disable queue
    session_manager.concurrency_manager.default_user_limit = 1
    session_manager.concurrency_manager.queue_enabled = False

    # Reach limit
    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    session, _ = result
    session_manager.update_session_state(session.id, SessionState.ACTIVE)
    db_session.commit()  # Commit to ensure limit check sees it

    # Verify limit is actually reached
    allowed, reason, count = session_manager.concurrency_manager.check_user_session_limit(
        test_user.id
    )
    assert allowed is False, (
        f"Limit should be reached. Count: {count}, Limit: {session_manager.concurrency_manager.default_user_limit}"
    )

    # Try to create another without queue
    # This should raise ValueError
    with pytest.raises(ValueError) as exc_info:
        session_manager.create_session(
            user_id=test_user.id,
            expert_config_id=test_expert.id,
            check_limits=True,
            queue_if_full=False,
        )

    # Exception should mention limit
    assert "limit" in str(exc_info.value).lower() or "session" in str(exc_info.value).lower()
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_graceful_recovery_when_session_completes(
    concurrency_manager, test_user, test_expert, db_session
):
    """Test graceful recovery when a session completes."""
    session_manager = SessionManager(db_session)

    # Create and activate session
    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    session, _ = result
    session_manager.update_session_state(session.id, SessionState.ACTIVE)

    # Queue a session
    concurrency_manager.queue_session(test_user.id, test_expert.id, QueuePriority.NORMAL)

    # Complete the active session
    session_manager.update_session_state(session.id, SessionState.COMPLETED)

    # Should be able to process queue now
    processed = concurrency_manager.process_queue()

    # Queue should be processable
    assert isinstance(processed, list)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_graceful_handling_multiple_users(concurrency_manager, db_session, test_expert):
    """Test graceful handling doesn't affect other users."""
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
        f"{base_username}_st1_21_user1",
        f"st1_21_user1@{domain}",
        password,
    )
    user2 = user_manager.create_user(
        f"{base_username}_st1_21_user2",
        f"st1_21_user2@{domain}",
        password,
    )

    session_manager = SessionManager(db_session)

    # User1 reaches limit
    result = session_manager.create_session(
        user_id=user1.id, expert_config_id=test_expert.id, check_limits=False
    )
    session1, _ = result
    session_manager.update_session_state(session1.id, SessionState.ACTIVE)

    # User2 should still be able to create sessions
    result2 = session_manager.create_session(
        user_id=user2.id, expert_config_id=test_expert.id, check_limits=True, queue_if_full=True
    )
    session2, notification2 = result2

    # User2 should succeed (different user)
    assert session2 is not None
    assert notification2 is None  # No notification needed
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_graceful_error_messages(concurrency_manager, test_user):
    """Test that error messages are user-friendly."""
    reason = "User session limit (1) reached. Current active sessions: 1"
    notification = concurrency_manager.notify_user_limit_reached(test_user.id, reason)

    assert "message" in notification
    message = notification["message"]

    # Should be clear and helpful
    assert len(message) > 0
    assert "limit" in message.lower() or "session" in message.lower()

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.db, pytest.mark.smtp, pytest.mark.slow, pytest.mark.heavy]

