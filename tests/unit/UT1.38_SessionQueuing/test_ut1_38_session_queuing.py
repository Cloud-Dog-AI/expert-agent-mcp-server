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
Unit Test: UT1.38 - Session Queuing Functionality

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for session queuing

Related Requirements: FR1.11
Related Tasks: T028
Related Architecture: CC2.1.2
Related Tests: UT1.38

Recent Changes:
- Initial implementation
"""

import pytest
from src.core.session.concurrency import ConcurrencyManager, QueuePriority


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
        username=f"{base_username}_ut1_38_{unique}",
        email=f"ut1_38_{unique}@{domain}",
        password=password,
    )


@pytest.fixture
def concurrency_manager(db_session):
    """Create a concurrency manager with queue enabled."""
    manager = ConcurrencyManager(db_session)
    manager.queue_enabled = True
    return manager
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_queue_priority_levels():
    """Test queue priority levels."""
    assert QueuePriority.LOW == "low"
    assert QueuePriority.NORMAL == "normal"
    assert QueuePriority.HIGH == "high"
    assert QueuePriority.URGENT == "urgent"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_queue_session_basic(concurrency_manager, test_user):
    """Test basic session queuing."""
    queue_entry = concurrency_manager.queue_session(
        user_id=test_user.id, expert_config_id=1, priority=QueuePriority.NORMAL
    )

    assert queue_entry is not None
    assert queue_entry["user_id"] == test_user.id
    assert queue_entry["expert_config_id"] == 1
    assert queue_entry["priority"] == "normal"
    assert queue_entry["status"] == "queued"
    assert "queued_at" in queue_entry
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_queue_session_different_priorities(concurrency_manager, test_user):
    """Test queuing sessions with different priorities."""
    low = concurrency_manager.queue_session(test_user.id, 1, QueuePriority.LOW)
    normal = concurrency_manager.queue_session(test_user.id, 1, QueuePriority.NORMAL)
    high = concurrency_manager.queue_session(test_user.id, 1, QueuePriority.HIGH)
    urgent = concurrency_manager.queue_session(test_user.id, 1, QueuePriority.URGENT)

    assert low["priority"] == "low"
    assert normal["priority"] == "normal"
    assert high["priority"] == "high"
    assert urgent["priority"] == "urgent"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_queue_session_with_channel(concurrency_manager, test_user):
    """Test queuing session with channel ID."""
    queue_entry = concurrency_manager.queue_session(
        user_id=test_user.id, expert_config_id=1, channel_id=5, priority=QueuePriority.NORMAL
    )

    assert queue_entry["channel_id"] == 5
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_get_queue_position(concurrency_manager, test_user):
    """Test getting queue position."""
    queue_entry = concurrency_manager.queue_session(test_user.id, 1, QueuePriority.NORMAL)

    position = concurrency_manager.get_queue_position(test_user.id, queue_entry)

    assert isinstance(position, int)
    assert position >= 0
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_process_queue_empty(concurrency_manager):
    """Test processing empty queue."""
    processed = concurrency_manager.process_queue()

    assert isinstance(processed, list)
    assert len(processed) == 0
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_queue_disabled_error(concurrency_manager, test_user):
    """Test that queuing fails when disabled."""
    concurrency_manager.queue_enabled = False

    with pytest.raises(ValueError, match="disabled"):
        concurrency_manager.queue_session(test_user.id, 1, QueuePriority.NORMAL)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-006")


def test_queue_entry_structure(concurrency_manager, test_user):
    """Test queue entry structure."""
    queue_entry = concurrency_manager.queue_session(test_user.id, 1, QueuePriority.HIGH)

    required_fields = ["user_id", "expert_config_id", "priority", "queued_at", "status"]
    assert all(field in queue_entry for field in required_fields)
    assert queue_entry["status"] == "queued"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.db, pytest.mark.smtp, pytest.mark.fast]

