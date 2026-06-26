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
Unit Test: UT1.5 - Group Manager Membership and Permissions

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for group manager membership and permissions

Related Requirements: FR1.5
Related Tasks: T005
Related Architecture: CC5.1.1
Related Tests: UT1.5

Recent Changes:
- Initial implementation
"""

import pytest
from src.core.auth.group_manager import GroupManager
from src.core.auth.user_manager import UserManager
# Removed unused import


@pytest.fixture
def test_user(db_session):
    """Create a test user."""
    import uuid
    from src.config.loader import get_config

    manager = UserManager(db_session)
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    group_prefix = get_config("test.group.name_prefix")
    if not base_username or not base_email or not password:
        pytest.fail(
            "Missing test.user.username/test.user.email/test.user.password in config (--env)"
        )
    if not group_prefix:
        pytest.fail("Missing test.group.name_prefix in config (--env)")
    unique = uuid.uuid4().hex[:8]
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    domain = base_email.split("@", 1)[1]
    return manager.create_user(
        username=f"{base_username}_ut1_5_{unique}",
        email=f"ut1_5_{unique}@{domain}",
        password=password,
    )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_group_manager_creation(db_session):
    """Test group manager can be created."""
    manager = GroupManager(db_session)
    assert manager is not None
    assert isinstance(manager, GroupManager)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_create_group(db_session):
    """Test group creation."""
    from src.config.loader import get_config

    manager = GroupManager(db_session)
    group_prefix = get_config("test.group.name_prefix")
    if not group_prefix:
        pytest.fail("Missing test.group.name_prefix in config (--env)")

    group = manager.create_group(name=f"{group_prefix}_ut1_5", description="Test group")

    assert group is not None
    assert group.id > 0
    assert group.name == f"{group_prefix}_ut1_5"
    assert group.description == "Test group"
    assert group.enabled is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_create_group_duplicate(db_session):
    """Test group creation with duplicate name fails."""
    from src.config.loader import get_config

    manager = GroupManager(db_session)
    group_prefix = get_config("test.group.name_prefix")
    if not group_prefix:
        pytest.fail("Missing test.group.name_prefix in config (--env)")
    group_name = f"{group_prefix}_ut1_5_dup"

    manager.create_group(name=group_name)

    # Try to create duplicate
    with pytest.raises(ValueError, match="already exists"):
        manager.create_group(name=group_name)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_get_group_by_id(db_session):
    """Test getting group by ID."""
    from src.config.loader import get_config

    manager = GroupManager(db_session)
    group_prefix = get_config("test.group.name_prefix")
    if not group_prefix:
        pytest.fail("Missing test.group.name_prefix in config (--env)")

    created = manager.create_group(name=f"{group_prefix}_ut1_5_get")

    retrieved = manager.get_group(group_id=created.id)

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.name == f"{group_prefix}_ut1_5_get"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_get_group_by_name(db_session):
    """Test getting group by name."""
    from src.config.loader import get_config

    manager = GroupManager(db_session)
    group_prefix = get_config("test.group.name_prefix")
    if not group_prefix:
        pytest.fail("Missing test.group.name_prefix in config (--env)")

    created = manager.create_group(name=f"{group_prefix}_ut1_5_name")

    retrieved = manager.get_group(name=f"{group_prefix}_ut1_5_name")

    assert retrieved is not None
    assert retrieved.id == created.id
    assert retrieved.name == f"{group_prefix}_ut1_5_name"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_add_member(db_session, test_user):
    """Test adding member to group."""
    from src.config.loader import get_config

    group_manager = GroupManager(db_session)
    group_prefix = get_config("test.group.name_prefix")
    if not group_prefix:
        pytest.fail("Missing test.group.name_prefix in config (--env)")

    group = group_manager.create_group(name=f"{group_prefix}_ut1_5_member")

    result = group_manager.add_member(group.id, test_user.id, role="member")

    assert result is True

    # Verify membership
    members = group_manager.get_group_members(group.id)
    assert len(members) == 1
    assert members[0].id == test_user.id
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_add_member_duplicate(db_session, test_user):
    """Test adding duplicate member returns False."""
    from src.config.loader import get_config

    group_manager = GroupManager(db_session)
    group_prefix = get_config("test.group.name_prefix")
    if not group_prefix:
        pytest.fail("Missing test.group.name_prefix in config (--env)")

    group = group_manager.create_group(name=f"{group_prefix}_ut1_5_dup_member")

    # Add member first time
    result1 = group_manager.add_member(group.id, test_user.id)
    assert result1 is True

    # Try to add again
    result2 = group_manager.add_member(group.id, test_user.id)
    assert result2 is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_add_member_with_role(db_session, test_user):
    """Test adding member with specific role."""
    from src.config.loader import get_config

    group_manager = GroupManager(db_session)
    group_prefix = get_config("test.group.name_prefix")
    if not group_prefix:
        pytest.fail("Missing test.group.name_prefix in config (--env)")

    group = group_manager.create_group(name=f"{group_prefix}_ut1_5_role")

    result = group_manager.add_member(group.id, test_user.id, role="admin")

    assert result is True

    # Verify role (would need to check GroupMember table directly)
    members = group_manager.get_group_members(group.id)
    assert len(members) == 1
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_get_group_members(db_session, test_user):
    """Test getting all group members."""
    group_manager = GroupManager(db_session)
    user_manager = UserManager(db_session)
    from src.config.loader import get_config

    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    base_password = get_config("test.user.password")
    group_prefix = get_config("test.group.name_prefix")
    if not base_username or not base_email or not base_password or not group_prefix:
        pytest.fail("Missing test.user.* or test.group.name_prefix in config (--env)")
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    domain = base_email.split("@", 1)[1]

    # Create group
    group = group_manager.create_group(name=f"{group_prefix}_ut1_5_multi")

    # Create additional users
    user2 = user_manager.create_user(
        username=f"{base_username}_ut1_5_user2",
        email=f"ut1_5_user2@{domain}",
        password=base_password,
    )
    user3 = user_manager.create_user(
        username=f"{base_username}_ut1_5_user3",
        email=f"ut1_5_user3@{domain}",
        password=base_password,
    )

    # Add members
    group_manager.add_member(group.id, test_user.id)
    group_manager.add_member(group.id, user2.id)
    group_manager.add_member(group.id, user3.id)

    # Get members
    members = group_manager.get_group_members(group.id)

    assert len(members) == 3
    user_ids = [m.id for m in members]
    assert test_user.id in user_ids
    assert user2.id in user_ids
    assert user3.id in user_ids

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.db, pytest.mark.smtp, pytest.mark.fast]

