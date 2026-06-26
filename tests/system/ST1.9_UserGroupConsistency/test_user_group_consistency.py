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
System Test: ST1.9 - User and Group Data Consistency

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for user and group data consistency

Related Requirements: FR1.5
Related Tasks: T005
Related Architecture: CC5.1.1
Related Tests: ST1.9

Recent Changes:
- Initial implementation
"""

import pytest
from src.core.auth.user_manager import UserManager
from src.core.auth.group_manager import GroupManager
from src.database.models import GroupMember
from src.config.loader import get_config


def _require_test_user_config():
    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    password = get_config("test.user.password")
    group_prefix = get_config("test.group.name_prefix")
    if not base_username or not base_email or not password or not group_prefix:
        pytest.fail("Missing test.user.* or test.group.name_prefix in config")
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    domain = base_email.split("@", 1)[1]
    return base_username, domain, password, group_prefix


@pytest.fixture
def user_manager(db_session):
    """Create user manager instance."""
    return UserManager(db_session)


@pytest.fixture
def group_manager(db_session):
    """Create group manager instance."""
    return GroupManager(db_session)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_group_membership_consistency(user_manager, group_manager, db_session):
    """Test that user-group membership is consistent."""
    base_username, domain, password, group_prefix = _require_test_user_config()
    # Create user and group
    user = user_manager.create_user(
        username=f"{base_username}_consistency", email=f"consistency@{domain}", password=password
    )
    group = group_manager.create_group(f"{group_prefix}_consistency")

    # Add user to group
    group_manager.add_member(group.id, user.id)

    # Verify membership (get_group_members returns List[User])
    members = group_manager.get_group_members(group.id)
    assert len(members) == 1
    assert members[0].id == user.id
    assert members[0].username == user.username
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_group_data_synchronization(user_manager, group_manager, db_session):
    """Test that user and group data stay synchronized."""
    base_username, domain, password, group_prefix = _require_test_user_config()
    # Create user and group
    user = user_manager.create_user(
        username=f"{base_username}_sync", email=f"sync@{domain}", password=password
    )
    group = group_manager.create_group(f"{group_prefix}_sync")

    # Add user to group
    group_manager.add_member(group.id, user.id)

    # Verify from user side (query GroupMember directly)
    from src.database.models import GroupMember

    user_memberships = db_session.query(GroupMember).filter(GroupMember.user_id == user.id).all()
    assert len(user_memberships) == 1
    assert user_memberships[0].group_id == group.id

    # Verify from group side (get_group_members returns List[User])
    group_members = group_manager.get_group_members(group.id)
    assert len(group_members) == 1
    assert group_members[0].id == user.id
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_group_membership_cascade_deletion(user_manager, group_manager, db_session):
    """Test that group membership is handled on user/group deletion."""
    base_username, domain, password, group_prefix = _require_test_user_config()
    # Create user and group
    user = user_manager.create_user(
        username=f"{base_username}_cascade", email=f"cascade@{domain}", password=password
    )
    group = group_manager.create_group(f"{group_prefix}_cascade")

    # Add user to group
    group_manager.add_member(group.id, user.id)

    # Delete user - membership should be handled
    db_session.delete(user)
    db_session.commit()

    # Verify membership is cleaned up
    members = group_manager.get_group_members(group.id)
    assert len(members) == 0
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_group_role_consistency(user_manager, group_manager, db_session):
    """Test that user roles in groups are consistent."""
    base_username, domain, password, group_prefix = _require_test_user_config()
    # Create user and group
    user = user_manager.create_user(
        username=f"{base_username}_role", email=f"role@{domain}", password=password
    )
    group = group_manager.create_group(f"{group_prefix}_role")

    # Add user with specific role
    group_manager.add_member(group.id, user.id, role="admin")

    # Verify membership (get_group_members returns List[User], not GroupMember)
    members = group_manager.get_group_members(group.id)
    assert len(members) == 1
    assert members[0].id == user.id

    # Verify role via GroupMember query
    from src.database.models import GroupMember

    member_record = (
        db_session.query(GroupMember)
        .filter(GroupMember.group_id == group.id, GroupMember.user_id == user.id)
        .first()
    )
    assert member_record is not None
    assert member_record.role == "admin"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_multiple_users_group_consistency(user_manager, group_manager, db_session):
    """Test consistency with multiple users in a group."""
    base_username, domain, password, group_prefix = _require_test_user_config()
    # Create group
    group = group_manager.create_group(f"{group_prefix}_multi")

    # Create multiple users
    users = []
    for i in range(3):
        user = user_manager.create_user(
            username=f"{base_username}_multi_{i}", email=f"multi{i}@{domain}", password=password
        )
        group_manager.add_member(group.id, user.id)
        users.append(user)

    # Verify all members are in group (get_group_members returns List[User])
    members = group_manager.get_group_members(group.id)
    assert len(members) == 3
    member_user_ids = [m.id for m in members]
    assert all(uid in [u.id for u in users] for uid in member_user_ids)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-029")


def test_user_group_data_integrity(user_manager, group_manager, db_session):
    """Test data integrity between users and groups."""
    base_username, domain, password, group_prefix = _require_test_user_config()
    # Create user and group
    user = user_manager.create_user(
        username=f"{base_username}_integrity", email=f"integrity@{domain}", password=password
    )
    group = group_manager.create_group(f"{group_prefix}_integrity")

    # Add user to group
    group_manager.add_member(group.id, user.id)

    # Verify foreign key relationships
    member = (
        db_session.query(GroupMember)
        .filter(GroupMember.user_id == user.id, GroupMember.group_id == group.id)
        .first()
    )

    assert member is not None
    assert member.user_id == user.id
    assert member.group_id == group.id
    assert member.user.id == user.id
    assert member.group.id == group.id

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.db, pytest.mark.smtp, pytest.mark.slow, pytest.mark.heavy]

