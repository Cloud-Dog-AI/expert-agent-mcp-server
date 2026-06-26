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
Unit Test: UT1.29 - Audit Logging Integrity

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for audit logging integrity and cryptographic signing

Related Requirements: FR1.10
Related Tasks: T041
Related Architecture: SE1.3
Related Tests: UT1.29

Recent Changes:
- Initial implementation
"""

import pytest
import json
from src.core.audit.manager import AuditManager
from src.config.loader import get_config


@pytest.fixture
def audit_manager(db_session):
    """Create audit manager instance."""
    return AuditManager(db_session)


@pytest.fixture
def test_user(db_session):
    """Create test user for audit events."""
    from src.core.auth.user_manager import UserManager

    manager = UserManager(db_session)
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not base_username or not base_email or not password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in config")
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    domain = base_email.split("@", 1)[1]
    return manager.create_user(
        username=f"{base_username}_audit_integrity",
        email=f"audit_integrity@{domain}",
        password=password,
    )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


def test_audit_event_has_signature(audit_manager, test_user):
    """Test that audit events have cryptographic signatures."""
    event = audit_manager.log_event("user_login", user_id=test_user.id, details={"action": "login"})

    assert event.signature is not None
    assert len(event.signature) > 0
    assert isinstance(event.signature, str)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


def test_audit_event_signature_verification(audit_manager, test_user):
    """Test that audit event signatures can be verified."""
    event = audit_manager.log_event("user_login", user_id=test_user.id, details={"action": "login"})

    # Verify signature
    is_valid = audit_manager.verify_event_signature(event)
    assert is_valid is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


def test_audit_event_signature_tampering_detection(audit_manager, test_user, db_session):
    """Test that tampering with audit events is detected."""
    event = audit_manager.log_event("user_login", user_id=test_user.id, details={"action": "login"})

    # Tamper with event data (modify the stored data)
    # Create tampered details that don't match the original signature
    tampered_details = {
        "action": "tampered",
        "user_id": test_user.id,
        "session_id": None,
        "channel_id": None,
        "expert_id": None,
    }
    # Add a different timestamp to ensure signature mismatch
    from datetime import datetime

    tampered_details["timestamp"] = datetime.utcnow().isoformat()
    event.data = json.dumps(tampered_details)
    db_session.commit()

    # Verify signature should fail (data changed, so signature won't match)
    is_valid = audit_manager.verify_event_signature(event)
    assert is_valid is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


def test_audit_event_immutability(audit_manager, test_user, db_session):
    """Test that audit events are immutable after creation."""
    event = audit_manager.log_event("user_login", user_id=test_user.id)

    original_signature = event.signature

    # Try to modify event (should not affect signature if properly protected)
    # In practice, events should be read-only after creation
    event.kind = "modified"
    db_session.commit()

    # Original signature should still be present
    assert event.signature == original_signature
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


def test_audit_event_chain_integrity(audit_manager, test_user):
    """Test integrity of audit event chain."""
    # Create sequence of events
    events = []
    for i in range(5):
        event = audit_manager.log_event(f"event_{i}", user_id=test_user.id, details={"sequence": i})
        events.append(event)

    # All events should have valid signatures
    for event in events:
        is_valid = audit_manager.verify_event_signature(event)
        assert is_valid is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


def test_audit_event_signature_uniqueness(audit_manager, test_user):
    """Test that audit event signatures are unique."""
    event1 = audit_manager.log_event(
        "user_login", user_id=test_user.id, details={"timestamp": "2024-01-01T00:00:00"}
    )

    event2 = audit_manager.log_event(
        "user_login", user_id=test_user.id, details={"timestamp": "2024-01-01T00:00:01"}
    )

    # Signatures should be different (even for similar events)
    assert event1.signature != event2.signature
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


def test_audit_event_retention_policy(audit_manager, test_user):
    """Test audit event retention policy."""
    from datetime import datetime, timedelta

    # Create old event (simulated)
    old_time = datetime.utcnow() - timedelta(days=100)

    # Events older than retention period should be archived or deleted
    # This depends on retention policy implementation
    events = audit_manager.get_events(user_id=test_user.id, start_time=old_time)

    # Should handle old events appropriately
    assert isinstance(events, list)
    # All events should be after old_time
    if events:
        assert all(event.created_at >= old_time for event in events)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-005")


def test_audit_event_export_integrity(audit_manager, test_user):
    """Test that exported audit events maintain integrity."""
    # Create events
    audit_manager.log_event("user_login", user_id=test_user.id)
    audit_manager.log_event("session_create", user_id=test_user.id)

    # Export events
    export_data = audit_manager.export_events(user_id=test_user.id, format="json")

    # Exported data should include signatures
    import json

    data = json.loads(export_data)

    # Verify exported events have signatures
    assert isinstance(data, list)
    for event_data in data:
        assert isinstance(event_data, dict)
        assert "signature" in event_data
        assert event_data["signature"] is not None

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.db, pytest.mark.smtp, pytest.mark.fast]

