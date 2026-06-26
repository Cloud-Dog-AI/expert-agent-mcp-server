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
Integration Test: IT2.5 - Real-time Session State Updates

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for real-time session state synchronization across components

Related Requirements: FR1.2
Related Tasks: T024
Related Architecture: CC2.1.1
Related Tests: IT2.5

Recent Changes:
- Initial implementation
"""

import asyncio
import uuid

import pytest

from src.core.session.synchronization import SessionSynchronizer
from src.core.session.manager import SessionManager
from src.database.models import ExpertConfig
from src.core.session.models import SessionState
from src.config.loader import get_config, load_config


pytestmark = pytest.mark.integration


def _get_timeout() -> float:
    timeout = get_config("test.http_timeout_seconds")
    if timeout is None:
        pytest.fail("test.http_timeout_seconds not configured")
    return float(timeout)


class RecordingBroadcaster:
    """Capture broadcast events for validation."""

    def __init__(self):
        self.events = []

    async def broadcast(self, topic: str, data: dict):
        self.events.append({"topic": topic, "data": data})


@pytest.fixture
def session_manager(db_session):
    """Create session manager."""
    return SessionManager(db=db_session)


@pytest.fixture
def recording_broadcaster():
    return RecordingBroadcaster()


@pytest.fixture
def synchronizer(db_session, recording_broadcaster):
    """Create session synchronizer."""
    sync = SessionSynchronizer(db=db_session)
    sync.set_event_broadcaster(recording_broadcaster)
    return sync


@pytest.fixture
def test_expert(db_session, test_config):
    """Create test expert configuration."""
    load_config.cache_clear()
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    if not llm_provider or not llm_model:
        pytest.fail("Missing llm.provider/llm.model in config (--env)")
    unique = uuid.uuid4().hex[:8]
    expert = ExpertConfig(
        name=f"test_expert_realtime_{unique}",
        title=f"Realtime Session Expert Alpha Beta {unique}",
        description=f"Validates session state sync behaviour for integration tests ({unique}).",
        llm_provider=llm_provider,
        llm_model=llm_model,
        enabled=True,
    )
    db_session.add(expert)
    db_session.commit()
    db_session.refresh(expert)
    return expert


@pytest.fixture
def test_user(db_session, test_env_file):
    """Create test user."""
    from src.core.auth.user_manager import UserManager
    import uuid

    manager = UserManager(db_session)
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    base_username = get_config("test.user.username")
    if not base_email or not password or not base_username:
        pytest.fail(
            "Missing test.user.username/test.user.email/test.user.password in config (--env)"
        )
    unique = uuid.uuid4().hex[:8]
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    domain = base_email.split("@", 1)[1]
    return manager.create_user(
        username=f"{base_username}_it2_5_{unique}",
        email=f"it2_5_{unique}@{domain}",
        password=password,
    )
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_session_state_synchronization(
    session_manager,
    synchronizer,
    recording_broadcaster,
    test_user,
    test_expert,
    check_llm_available,
):
    """Test that session state changes are synchronized."""
    # Create session
    session, _ = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )

    # Update session state via synchronizer (captures event)
    timeout = _get_timeout()
    result = await asyncio.wait_for(
        synchronizer.synchronize_session_state(session.id, SessionState.ACTIVE),
        timeout=timeout,
    )
    assert result is True

    # Verify state was updated
    updated_session = session_manager.get_session(session.id)
    assert updated_session.status == SessionState.ACTIVE.value
    assert any(
        event["topic"] == "sessions" and event["data"].get("type") == "session_state_change"
        for event in recording_broadcaster.events
    )
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_session_state_broadcast(
    synchronizer,
    session_manager,
    recording_broadcaster,
    test_user,
    test_expert,
    check_llm_available,
):
    """Test broadcasting session state to multiple clients."""
    session, _ = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )

    session_manager.synchronizer = synchronizer
    session_manager.update_session_state(session.id, SessionState.ACTIVE)
    await asyncio.sleep(0.1)

    # Verify state was updated
    updated_session = session_manager.get_session(session.id)
    assert updated_session.status == SessionState.ACTIVE.value
    assert any(
        event["topic"] == "sessions" and event["data"].get("type") == "session_state_change"
        for event in recording_broadcaster.events
    )
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_state_persistence(session_manager, test_user, test_expert):
    """Test that session state changes are persisted to database."""
    # Create session
    session, _ = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )

    initial_state = session.status

    # Update state to a different value
    session_manager.update_session_state(session.id, SessionState.PAUSED)

    # Retrieve from database
    updated_session = session_manager.get_session(session.id)
    assert updated_session.status == SessionState.PAUSED.value
    assert updated_session.status != initial_state
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_concurrent_session_state_updates(session_manager, test_user, test_expert):
    """Test handling concurrent session state updates."""
    # Create session
    session, _ = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )

    # Simulate concurrent updates
    session_manager.update_session_state(session.id, SessionState.ACTIVE)
    session_manager.update_session_state(session.id, SessionState.PAUSED)
    session_manager.update_session_state(session.id, SessionState.ACTIVE)

    # Final state should be consistent
    final_session = session_manager.get_session(session.id)
    assert final_session.status == SessionState.ACTIVE.value
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_session_state_notification(
    synchronizer,
    session_manager,
    recording_broadcaster,
    test_user,
    test_expert,
    check_llm_available,
):
    """Test that session state changes trigger notifications."""
    session, _ = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )

    timeout = _get_timeout()
    await asyncio.wait_for(
        synchronizer.synchronize_session_state(session.id, SessionState.ACTIVE),
        timeout=timeout,
    )

    # Verify state was updated
    updated_session = session_manager.get_session(session.id)
    assert updated_session.status == SessionState.ACTIVE.value
    assert any(
        event["topic"] == "sessions" and event["data"].get("type") == "session_state_change"
        for event in recording_broadcaster.events
    )
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_state_transitions(session_manager, test_user, test_expert):
    """Test valid session state transitions."""
    # Create session
    session, _ = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )

    # Test state transitions
    transitions = [
        (SessionState.CREATED, SessionState.ACTIVE),
        (SessionState.ACTIVE, SessionState.PAUSED),
        (SessionState.PAUSED, SessionState.ACTIVE),
        (SessionState.ACTIVE, SessionState.COMPLETED),
    ]

    for from_state, to_state in transitions:
        session_manager.update_session_state(session.id, from_state)
        session_manager.update_session_state(session.id, to_state)

        updated = session_manager.get_session(session.id)
        assert updated.status == to_state.value
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-013")


def test_session_state_consistency(session_manager, test_user, test_expert):
    """Test that session state remains consistent across operations."""
    # Create session
    session, _ = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )

    # Perform multiple operations
    session_manager.update_session_state(session.id, SessionState.ACTIVE)

    # Add message (should maintain state)
    session_manager.add_message(
        session_id=session.id,
        role="user",
        content="Test message",
        tokens_used=5,
    )

    # Verify state is still consistent
    updated_session = session_manager.get_session(session.id)
    assert updated_session.status == SessionState.ACTIVE.value

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.db, pytest.mark.smtp, pytest.mark.heavy]

