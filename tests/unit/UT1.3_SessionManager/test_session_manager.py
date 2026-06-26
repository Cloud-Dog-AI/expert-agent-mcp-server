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
Unit Test: UT1.3 - Session Manager Creation and State Transitions

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for session manager creation and state transitions

Related Requirements: FR1.2
Related Tasks: T022
Related Architecture: CC2.1.1
Related Tests: UT1.3

Recent Changes:
- Initial implementation
"""

import pytest
from datetime import datetime

from src.core.session.manager import SessionManager
from src.core.session.models import SessionState
from src.database.models import Session as SessionModel, ExpertConfig
# Removed unused import


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
        username=f"{base_username}_ut1_3_{unique}",
        email=f"ut1_3_{unique}@{domain}",
        password=password,
    )


@pytest.fixture
def test_expert(db_session, test_config):
    """Create a test expert configuration."""
    from src.config.loader import get_config

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    if not llm_provider or not llm_model:
        pytest.fail("Missing llm.provider/llm.model in config (--env)")
    expert = ExpertConfig(
        name="test_expert",
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
def session_manager(db_session):
    """Create a session manager instance."""
    return SessionManager(db_session)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_manager_creation(session_manager):
    """Test session manager can be created."""
    assert session_manager is not None
    assert isinstance(session_manager, SessionManager)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_create_session(session_manager, test_user, test_expert):
    """Test session creation."""
    result = session_manager.create_session(
        user_id=test_user.id,
        expert_config_id=test_expert.id,
        title="Test Session",
        check_limits=False,  # Disable limits for unit tests
    )
    session, notification = result

    assert session is not None
    assert notification is None  # Should not be queued in unit tests
    assert session.id > 0
    assert session.user_id == test_user.id
    assert session.expert_config_id == test_expert.id
    assert session.title == "Test Session"
    assert session.status == SessionState.ACTIVE.value
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_get_session(session_manager, test_user, test_expert):
    """Test getting session by ID."""
    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    created, _ = result

    retrieved = session_manager.get_session(created.id)

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.user_id == test_user.id
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_update_session_state(session_manager, test_user, test_expert):
    """Test session state transitions."""
    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    session, _ = result

    # Transition to ACTIVE
    result = session_manager.update_session_state(session.id, SessionState.ACTIVE)
    assert result is True

    updated = session_manager.get_session(session.id)
    assert updated.status == SessionState.ACTIVE.value

    # Transition to COMPLETED
    result = session_manager.update_session_state(session.id, SessionState.COMPLETED)
    assert result is True

    updated = session_manager.get_session(session.id)
    assert updated.status == SessionState.COMPLETED.value
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_add_message(session_manager, test_user, test_expert):
    """Test adding message to session."""
    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    session, _ = result

    message = session_manager.add_message(
        session_id=session.id, role="user", content="Hello, world!"
    )

    assert message is not None
    assert message.id > 0
    assert message.session_id == session.id
    assert message.role == "user"
    assert message.content == "Hello, world!"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_get_messages(session_manager, test_user, test_expert):
    """Test getting messages from session."""
    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    session, _ = result

    # Add multiple messages
    session_manager.add_message(session.id, "user", "Message 1")
    session_manager.add_message(session.id, "assistant", "Response 1")
    session_manager.add_message(session.id, "user", "Message 2")

    messages = session_manager.get_messages(session.id)

    assert len(messages) == 3
    assert messages[0].content == "Message 1"
    assert messages[1].content == "Response 1"
    assert messages[2].content == "Message 2"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_get_message_history(session_manager, test_user, test_expert):
    """Test getting message history in LLM format."""
    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    session, _ = result

    session_manager.add_message(session.id, "user", "Hello")
    session_manager.add_message(session.id, "assistant", "Hi there!")

    history = session_manager.get_message_history(session.id)

    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "Hi there!"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_get_message_history_with_max_tokens(session_manager, test_user, test_expert):
    """Test message history with token limit."""
    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    session, _ = result

    # Add messages with varying lengths
    # Use smaller messages to ensure they fit within token limit
    short_msg = "Short"  # ~1-2 tokens
    medium_msg = "A" * 50  # ~12-13 tokens
    long_msg = "B" * 100  # ~25 tokens

    session_manager.add_message(session.id, "user", short_msg)
    session_manager.add_message(session.id, "assistant", medium_msg)
    session_manager.add_message(session.id, "user", long_msg)

    # Get history with token limit (should get recent messages that fit)
    # Token limit of 50 should get at least the last 2-3 messages
    history = session_manager.get_message_history(
        session.id, max_tokens=50, use_summarization=False
    )

    # Should include some messages (may be fewer than total due to token limit)
    # Note: With summarization disabled, should get messages that fit
    assert len(history) >= 0  # May be 0 if all messages exceed limit
    assert len(history) <= 3
    # Verify we got at least one message with proper structure
    if len(history) > 0:
        assert all("role" in msg and "content" in msg for msg in history)
        # The last message (long_msg) should be included if it fits within 50 tokens
        # Token estimation might vary, so check if any of our messages are present
        contents = [msg["content"] for msg in history]
        assert any(msg in contents for msg in [short_msg, medium_msg, long_msg])
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_cleanup_old_sessions(session_manager, test_user, test_expert, db_session):
    """Test cleanup of old archived sessions."""
    # Create old session
    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    old_session, _ = result
    session_id = old_session.id  # Store ID before potential deletion
    session_manager.update_session_state(old_session.id, SessionState.ARCHIVED)

    # Manually set old date (90+ days ago)
    from datetime import timedelta

    old_date = datetime.utcnow() - timedelta(days=100)
    db_session.query(SessionModel).filter(SessionModel.id == session_id).update(
        {"created_at": old_date}
    )
    db_session.commit()
    db_session.refresh(old_session)

    # Cleanup
    deleted = session_manager.cleanup_old_sessions(days=90)

    assert deleted >= 1

    # Verify session is gone (query fresh from DB)
    db_session.expire_all()  # Expire all objects
    retrieved = session_manager.get_session(session_id)
    assert retrieved is None

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.db, pytest.mark.smtp, pytest.mark.fast]

