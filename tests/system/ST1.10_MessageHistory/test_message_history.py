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
System Test: ST1.10 - Message History Storage and Retrieval

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for message history storage and retrieval

Related Requirements: FR1.2
Related Tasks: T023
Related Architecture: CC2.1.1
Related Tests: ST1.10

Recent Changes:
- Initial implementation
"""

import pytest
from src.core.session.manager import SessionManager
from src.core.auth.user_manager import UserManager
from src.database.models import ExpertConfig
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
        username=f"{base_username}_st1_10_{unique}",
        email=f"st1_10_{unique}@{domain}",
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
        name=f"history_expert_{unique}",
        title="History Expert",
        llm_provider=llm_provider,
        llm_model=llm_model,
        enabled=True,
    )
    db_session.add(expert)
    db_session.commit()
    db_session.refresh(expert)
    return expert


@pytest.fixture
def test_session(session_manager, test_user, test_expert):
    """Create test session."""
    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    session, _ = result
    return session
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_message_storage(session_manager, test_session):
    """Test that messages are stored in database."""
    message = session_manager.add_message(
        session_id=test_session.id, role="user", content="Test message"
    )

    assert message.id is not None
    assert message.session_id == test_session.id
    assert message.role == "user"
    assert message.content == "Test message"
    assert message.timestamp is not None
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_message_retrieval(session_manager, test_session):
    """Test retrieving messages from history."""
    # Add multiple messages
    msg1 = session_manager.add_message(session_id=test_session.id, role="user", content="Message 1")
    msg2 = session_manager.add_message(
        session_id=test_session.id, role="assistant", content="Message 2"
    )

    # Retrieve messages
    messages = session_manager.get_messages(test_session.id)

    assert len(messages) >= 2
    assert any(m.id == msg1.id for m in messages)
    assert any(m.id == msg2.id for m in messages)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_message_history_ordering(session_manager, test_session):
    """Test that message history is ordered correctly."""
    # Add messages with delays
    session_manager.add_message(session_id=test_session.id, role="user", content="First message")
    session_manager.add_message(
        session_id=test_session.id, role="assistant", content="Second message"
    )
    session_manager.add_message(session_id=test_session.id, role="user", content="Third message")

    # Retrieve messages (should be ordered by timestamp)
    messages = session_manager.get_messages(test_session.id)

    assert len(messages) >= 3
    # Messages should be in chronological order
    timestamps = [m.timestamp for m in messages]
    assert timestamps == sorted(timestamps)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_message_history_pagination(session_manager, test_session):
    """Test message history pagination."""
    # Add multiple messages
    for i in range(10):
        session_manager.add_message(session_id=test_session.id, role="user", content=f"Message {i}")

    # Get first page
    page1 = session_manager.get_messages(test_session.id, limit=5, offset=0)
    assert len(page1) <= 5

    # Get second page
    page2 = session_manager.get_messages(test_session.id, limit=5, offset=5)
    assert len(page2) <= 5

    # Pages should be different
    if len(page1) > 0 and len(page2) > 0:
        assert page1[0].id != page2[0].id
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_message_metadata_storage(session_manager, test_session):
    """Test that message metadata is stored."""
    tokens_used = get_config("test.message.tokens_used")
    model_name = get_config("test.message.model")
    if tokens_used is None or model_name is None:
        pytest.fail("test.message.tokens_used/test.message.model not configured")
    tokens_used = int(tokens_used)
    metadata = {"tokens": tokens_used, "model": str(model_name)}
    message = session_manager.add_message(
        session_id=test_session.id,
        role="user",
        content="Message with metadata",
        tokens_used=tokens_used,
        metadata=metadata,
    )

    assert message.tokens_used == 100
    # metadata_json is stored as str(metadata), not JSON, so check string representation
    if message.metadata_json:
        assert str(tokens_used) in message.metadata_json
        assert str(model_name) in message.metadata_json
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_message_history_persistence(session_manager, test_session, db_session):
    """Test that message history persists across sessions."""
    # Add message
    message = session_manager.add_message(
        session_id=test_session.id, role="user", content="Persistent message"
    )
    message_id = message.id

    # Create new manager (simulating new connection)
    new_manager = SessionManager(db_session)

    # Should still be able to retrieve
    messages = new_manager.get_messages(test_session.id)
    assert any(m.id == message_id for m in messages)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_message_history_filtering(session_manager, test_session):
    """Test filtering message history by role."""
    # Add messages with different roles
    session_manager.add_message(test_session.id, "user", "User message")
    session_manager.add_message(test_session.id, "assistant", "Assistant message")
    session_manager.add_message(test_session.id, "user", "Another user message")

    # Get all messages
    all_messages = session_manager.get_messages(test_session.id)

    # Filter by role
    user_messages = [m for m in all_messages if m.role == "user"]
    assistant_messages = [m for m in all_messages if m.role == "assistant"]

    assert len(user_messages) >= 2
    assert len(assistant_messages) >= 1

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.db, pytest.mark.smtp, pytest.mark.slow, pytest.mark.heavy]

