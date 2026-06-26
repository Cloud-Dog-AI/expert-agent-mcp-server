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
Unit Test: UT1.4 - User Manager Authentication and Authorization

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for user manager authentication and authorization

Related Requirements: CS1.1, FR1.5
Related Tasks: T005, T006
Related Architecture: SE1.1, CC5.1.1
Related Tests: UT1.4

Recent Changes:
- Initial implementation
"""

import pytest
from src.core.auth.user_manager import UserManager

# Prefer config system over direct os.getenv defaults
from src.config.loader import get_config
# Removed unused import


def _required_test_user_config():
    username = get_config("test.user.username")
    email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not username or not email or not password:
        pytest.fail(
            "Missing test.user.username/test.user.email/test.user.password in config (--env)"
        )
    if "@" not in email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    return username, email, password
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_manager_creation(db_session):
    """Test user manager can be created."""
    manager = UserManager(db_session)
    assert manager is not None
    assert isinstance(manager, UserManager)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_create_user(db_session):
    """Test user creation."""
    manager = UserManager(db_session)
    username, email, password = _required_test_user_config()

    user = manager.create_user(
        username=username, email=email, password=password, display_name="Test User"
    )

    assert user is not None
    assert user.id > 0
    assert user.username == username
    assert user.email == email
    assert user.display_name == "Test User"
    assert user.pwd_hash is not None
    assert user.role == "user"
    assert user.enabled is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_create_user_duplicate_username(db_session):
    """Test user creation with duplicate username fails."""
    manager = UserManager(db_session)
    base_username, base_email, base_password = _required_test_user_config()
    domain = base_email.split("@", 1)[1]

    manager.create_user(
        username=base_username, email=f"ut1_4_dupe1@{domain}", password=base_password
    )

    # Try to create duplicate
    with pytest.raises(ValueError, match="already exists"):
        manager.create_user(
            username=base_username, email=f"ut1_4_dupe2@{domain}", password=base_password
        )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_create_user_duplicate_email(db_session):
    """Test user creation with duplicate email fails."""
    manager = UserManager(db_session)
    _, email, password = _required_test_user_config()

    manager.create_user(username="user1", email=email, password=password)

    # Try to create duplicate
    with pytest.raises(ValueError, match="already exists"):
        manager.create_user(username="user2", email=email, password=password)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_get_user_by_id(db_session):
    """Test getting user by ID."""
    manager = UserManager(db_session)
    username, email, password = _required_test_user_config()

    created = manager.create_user(username=username, email=email, password=password)

    retrieved = manager.get_user(user_id=created.id)

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.username == username
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_get_user_by_username(db_session):
    """Test getting user by username."""
    manager = UserManager(db_session)
    username, email, password = _required_test_user_config()

    created = manager.create_user(username=username, email=email, password=password)

    retrieved = manager.get_user(username=username)

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.username == username
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_authenticate_success(db_session):
    """Test successful authentication."""
    manager = UserManager(db_session)
    username, email, password = _required_test_user_config()

    manager.create_user(username=username, email=email, password=password)

    user = manager.authenticate(username, password)

    assert user is not None
    assert user.username == username
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_authenticate_success_emits_structured_audit(db_session, monkeypatch):
    """Successful auth emits a structured audit event."""
    manager = UserManager(db_session)
    username, email, password = _required_test_user_config()
    captured = []

    monkeypatch.setattr(
        "src.core.auth.user_manager.log_authentication_event",
        lambda *args, **kwargs: captured.append((args, kwargs)),
    )

    manager.create_user(username=username, email=email, password=password)
    user = manager.authenticate(username, password)

    assert user is not None
    assert captured
    assert captured[-1][0][0] == username
    assert captured[-1][0][1] == "success"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_authenticate_wrong_password(db_session):
    """Test authentication with wrong password fails."""
    manager = UserManager(db_session)
    username, email, password = _required_test_user_config()

    manager.create_user(username=username, email=email, password=password)

    user = manager.authenticate(username, f"{password}_wrong")

    assert user is None
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_authenticate_failure_emits_structured_audit(db_session, monkeypatch):
    """Failed auth emits a structured audit event."""
    manager = UserManager(db_session)
    username, email, password = _required_test_user_config()
    captured = []

    monkeypatch.setattr(
        "src.core.auth.user_manager.log_authentication_event",
        lambda *args, **kwargs: captured.append((args, kwargs)),
    )

    manager.create_user(username=username, email=email, password=password)
    user = manager.authenticate(username, f"{password}_wrong")

    assert user is None
    assert captured
    assert captured[-1][0][0] == username
    assert captured[-1][0][1] == "failure"
    assert captured[-1][1]["reason"] == "invalid_password"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_authenticate_nonexistent_user(db_session):
    """Test authentication with nonexistent user fails."""
    manager = UserManager(db_session)
    _, _, password = _required_test_user_config()

    user = manager.authenticate("nonexistent", password)

    assert user is None
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_authenticate_disabled_user(db_session):
    """Test authentication with disabled user fails."""
    manager = UserManager(db_session)
    username, email, password = _required_test_user_config()

    manager.create_user(username=username, email=email, password=password, enabled=False)

    authenticated = manager.authenticate(username, password)

    assert authenticated is None
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_update_user(db_session):
    """Test user update."""
    manager = UserManager(db_session)
    username, email, password = _required_test_user_config()

    user = manager.create_user(username=username, email=email, password=password)

    updated = manager.update_user(user.id, display_name="Updated Name", role="admin")

    assert updated is not None
    assert updated.display_name == "Updated Name"
    assert updated.role == "admin"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_update_nonexistent_user(db_session):
    """Test updating nonexistent user returns None."""
    manager = UserManager(db_session)

    updated = manager.update_user(99999, display_name="Test")

    assert updated is None

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.db, pytest.mark.smtp, pytest.mark.fast]
