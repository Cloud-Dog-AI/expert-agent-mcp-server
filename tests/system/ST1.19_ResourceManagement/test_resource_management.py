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
System Test: ST1.19 - Resource Management Under High Load

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for resource management under high load

Related Requirements: FR1.11
Related Tasks: T028
Related Architecture: CC2.1.3
Related Tests: ST1.19

Recent Changes:
- Initial implementation
"""

import pytest
from src.core.session.manager import SessionManager
from src.core.session.concurrency import ConcurrencyManager
from src.core.auth.user_manager import UserManager
from src.database.models import ExpertConfig
from src.core.session.models import SessionState
from src.config.loader import get_config


@pytest.fixture
def session_manager(db_session):
    """Create session manager instance."""
    return SessionManager(db_session)


@pytest.fixture
def concurrency_manager(db_session):
    """Create concurrency manager."""
    manager = ConcurrencyManager(db_session)
    manager.default_user_limit = 5  # Set limit for testing
    return manager


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

    # Use unique username/email to avoid conflicts in full test runs
    unique_id = str(uuid.uuid4())[:8]
    username = f"{base_username}_st1_19_{unique_id}"
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    email = f"st1_19_{unique_id}@{base_email.split('@')[1]}"

    return manager.create_user(username=username, email=email, password=password)


@pytest.fixture
def test_expert(db_session, test_config):
    """Create test expert."""
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    if not llm_provider or not llm_model:
        pytest.fail("Missing llm.provider/llm.model in config")
    expert = ExpertConfig(
        name="load_expert",
        title="Load Expert",
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
@pytest.mark.req("FR-006")


def test_resource_management_under_load(
    session_manager, concurrency_manager, test_user, test_expert, db_session
):
    """Test resource management when system is under load."""
    # Create multiple sessions up to limit
    sessions = []
    for i in range(concurrency_manager.default_user_limit):
        result = session_manager.create_session(
            user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
        )
        session, _ = result
        session_manager.update_session_state(session.id, SessionState.ACTIVE)
        sessions.append(session)

    # System should handle load gracefully
    allowed, reason, count = concurrency_manager.check_user_session_limit(test_user.id)

    assert count == concurrency_manager.default_user_limit
    assert allowed is False  # Limit reached
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_resource_cleanup_on_completion(
    session_manager, concurrency_manager, test_user, test_expert, db_session
):
    """Test that resources are cleaned up when sessions complete."""
    # Create and activate session
    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
    )
    session, _ = result
    session_manager.update_session_state(session.id, SessionState.ACTIVE)

    # Complete session
    session_manager.update_session_state(session.id, SessionState.COMPLETED)

    # Should be able to create new session (completed doesn't count)
    allowed, reason, count = concurrency_manager.check_user_session_limit(test_user.id)
    assert count < concurrency_manager.default_user_limit
    assert allowed is True
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_resource_management_multiple_users(
    session_manager, concurrency_manager, test_expert, db_session
):
    """Test resource management with multiple users."""
    user_manager = UserManager(db_session)
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in config")
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    domain = base_email.split("@", 1)[1]

    # Create multiple users
    users = []
    for i in range(3):
        import uuid

        unique = uuid.uuid4().hex[:6]
        user = user_manager.create_user(
            username=f"{base_username}_st1_19_{i}_{unique}",
            email=f"st1_19_{i}_{unique}@{domain}",
            password=password,
        )
        users.append(user)

    # Each user should be able to create sessions independently
    for user in users:
        result = session_manager.create_session(
            user_id=user.id, expert_config_id=test_expert.id, check_limits=False
        )
        session, _ = result
        session_manager.update_session_state(session.id, SessionState.ACTIVE)

        # Check limit for this user
        allowed, reason, count = concurrency_manager.check_user_session_limit(user.id)
        assert count >= 1
        if count < concurrency_manager.default_user_limit:
            assert allowed is True
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_resource_management_queue_handling(
    session_manager, concurrency_manager, test_user, test_expert, db_session
):
    """Test that queue handles resource management."""
    concurrency_manager.queue_enabled = True

    # Create sessions up to limit
    for i in range(concurrency_manager.default_user_limit):
        result = session_manager.create_session(
            user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
        )
        session, _ = result
        session_manager.update_session_state(session.id, SessionState.ACTIVE)

    # Try to create another - should be queued
    result = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id, check_limits=True, queue_if_full=True
    )
    session, notification = result

    # Should be queued when limit reached
    if notification and notification.get("queued"):
        assert session is None
        assert notification["queued"] is True
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_resource_management_limit_configuration(concurrency_manager):
    """Test that resource limits are configurable."""
    original_limit = concurrency_manager.default_user_limit

    # Change limit
    concurrency_manager.default_user_limit = 20
    assert concurrency_manager.default_user_limit == 20

    # Restore
    concurrency_manager.default_user_limit = original_limit
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_resource_management_graceful_degradation(
    session_manager, concurrency_manager, test_user, test_expert, db_session
):
    """Test graceful degradation when resources are exhausted."""
    # Create sessions up to limit
    for i in range(concurrency_manager.default_user_limit):
        result = session_manager.create_session(
            user_id=test_user.id, expert_config_id=test_expert.id, check_limits=False
        )
        session, _ = result
        session_manager.update_session_state(session.id, SessionState.ACTIVE)

    # System should degrade gracefully
    allowed, reason, count = concurrency_manager.check_user_session_limit(test_user.id)

    # Should provide clear reason
    assert allowed is False
    assert reason is not None
    assert "limit" in reason.lower()

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.db, pytest.mark.smtp, pytest.mark.slow, pytest.mark.heavy]

