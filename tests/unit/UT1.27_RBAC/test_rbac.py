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
Unit Test: UT1.27 - Role-Based Access Control Enforcement

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for role-based access control enforcement

Related Requirements: FR1.6
Related Tasks: T006
Related Architecture: SE1.1
Related Tests: UT1.27

Recent Changes:
- Initial implementation
"""

import pytest
from src.core.auth.rbac import RBACManager
from src.config.loader import get_config


@pytest.fixture
def rbac_manager():
    """Create RBAC manager instance with fresh engine to avoid cross-test state leaks."""
    return RBACManager(fresh_engine=True)


@pytest.fixture
def test_user_admin(db_session):
    """Create test admin user."""
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
        username=f"{base_username}_admin", email=f"admin@{domain}", password=password, role="admin"
    )


@pytest.fixture
def test_user_regular(db_session):
    """Create test regular user."""
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
        username=f"{base_username}_regular", email=f"user@{domain}", password=password, role="user"
    )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-030")


def test_admin_can_access_all_resources(rbac_manager, test_user_admin):
    """Test that admin users can access all resources."""
    # Admin should have access to all operations
    assert rbac_manager.has_permission(test_user_admin, "users", "create") is True
    assert rbac_manager.has_permission(test_user_admin, "users", "read") is True
    assert rbac_manager.has_permission(test_user_admin, "users", "update") is True
    assert rbac_manager.has_permission(test_user_admin, "users", "delete") is True
    assert rbac_manager.has_permission(test_user_admin, "experts", "create") is True
    assert rbac_manager.has_permission(test_user_admin, "sessions", "create") is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-030")


def test_regular_user_limited_access(rbac_manager, test_user_regular):
    """Test that regular users have limited access."""
    # Regular users can read and create their own resources
    assert rbac_manager.has_permission(test_user_regular, "sessions", "create") is True
    assert rbac_manager.has_permission(test_user_regular, "sessions", "read") is True

    # But cannot manage users or experts
    assert rbac_manager.has_permission(test_user_regular, "users", "create") is False
    assert rbac_manager.has_permission(test_user_regular, "users", "delete") is False
    assert rbac_manager.has_permission(test_user_regular, "experts", "create") is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-030")


def test_user_can_access_own_resources(rbac_manager, test_user_regular):
    """Test that users can access their own resources."""
    # User can read their own sessions
    assert (
        rbac_manager.can_access_resource(
            test_user_regular, "session", 1, owner_id=test_user_regular.id
        )
        is True
    )

    # User cannot access other users' sessions
    assert rbac_manager.can_access_resource(test_user_regular, "session", 2, owner_id=999) is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-030")


def test_group_based_permissions(rbac_manager, db_session, test_user_regular):
    """Test group-based permissions."""
    from src.core.auth.group_manager import GroupManager

    group_manager = GroupManager(db_session)
    group_prefix = get_config("test.group.name_prefix")
    if not group_prefix:
        pytest.fail("Missing test.group.name_prefix in config")

    # Create group
    group = group_manager.create_group(f"{group_prefix}_rbac", "Test group")

    # Add user to group
    group_manager.add_member(group.id, test_user_regular.id, role="member")

    # User should have group permissions
    assert rbac_manager.has_group_permission(test_user_regular, group.id, "read") is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-030")


def test_role_hierarchy(rbac_manager, test_user_admin, test_user_regular):
    """Test role hierarchy (admin > user)."""
    # Admin role should have higher privileges
    admin_permissions = rbac_manager.get_user_permissions(test_user_admin)
    user_permissions = rbac_manager.get_user_permissions(test_user_regular)

    # Admin should have more permissions
    assert len(admin_permissions) >= len(user_permissions)

    # Admin permissions should dominate all user permissions. Admin holds the
    # "*" wildcard grant (PS-82 baseline: admin == all permissions), which
    # subsumes every concrete user permission even when not enumerated literally.
    admin_has_wildcard = "*" in admin_permissions
    for perm in user_permissions:
        assert admin_has_wildcard or perm in admin_permissions, (
            f"admin role must dominate user permission {perm!r}"
        )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-030")


def test_permission_denied_for_unauthorized_action(rbac_manager, test_user_regular):
    """Test that unauthorized actions are denied."""
    # Regular user cannot delete users
    assert rbac_manager.has_permission(test_user_regular, "users", "delete") is False

    # Regular user cannot create experts
    assert rbac_manager.has_permission(test_user_regular, "experts", "create") is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-030")


def test_resource_ownership_check(rbac_manager, test_user_regular):
    """Test resource ownership verification."""
    # User owns resource
    assert (
        rbac_manager.is_resource_owner(
            test_user_regular.id, "session", 1, owner_id=test_user_regular.id
        )
        is True
    )

    # User does not own resource
    assert rbac_manager.is_resource_owner(test_user_regular.id, "session", 2, owner_id=999) is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-030")


def test_permission_check_with_context(rbac_manager, test_user_regular):
    """Test permission check with additional context."""
    # User can create session for themselves
    assert (
        rbac_manager.has_permission_with_context(
            test_user_regular, "sessions", "create", {"user_id": test_user_regular.id}
        )
        is True
    )

    # User cannot create session for another user
    assert (
        rbac_manager.has_permission_with_context(
            test_user_regular, "sessions", "create", {"user_id": 999}
        )
        is False
    )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.db, pytest.mark.smtp, pytest.mark.fast]

