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
Unit Test: UT1.24 - Cross-talk Prevention Between Groups/Databases

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests to ensure no cross-talk/data leakage between different groups/databases

Related Requirements: FR1.3
Related Tasks: T020
Related Architecture: CC4.1.1
Related Tests: UT1.24

Recent Changes:
- Initial implementation
"""

import pytest
import json
from src.core.vector.isolation import VectorIsolationManager
from src.database.models import Group, User, GroupMember, VectorStore as VectorStoreModel
from src.config.loader import get_config


@pytest.fixture
def isolation_manager(db_session):
    """Create a VectorIsolationManager instance."""
    return VectorIsolationManager(db=db_session)


@pytest.fixture
def test_groups(db_session):
    """Create test groups."""
    group1 = Group(name="group1", description="Test Group 1")
    group2 = Group(name="group2", description="Test Group 2")
    db_session.add(group1)
    db_session.add(group2)
    db_session.commit()
    db_session.refresh(group1)
    db_session.refresh(group2)
    return group1, group2


@pytest.fixture
def test_users(db_session):
    """Create test users."""
    from src.config.loader import get_config

    base_email = get_config("test.user.email")
    if not base_email:
        pytest.fail("Missing test.user.email in config (--env)")
    # Use different emails for each user to avoid constraint violations
    user1_email = base_email.replace("@", "+user1@") if "@" in base_email else "user1@test.com"
    user2_email = base_email.replace("@", "+user2@") if "@" in base_email else "user2@test.com"
    user1 = User(username="user1", email=user1_email, pwd_hash="hash1")
    user2 = User(username="user2", email=user2_email, pwd_hash="hash2")
    db_session.add(user1)
    db_session.add(user2)
    db_session.commit()
    db_session.refresh(user1)
    db_session.refresh(user2)
    return user1, user2


@pytest.fixture
def test_group_members(db_session, test_users, test_groups):
    """Create group memberships."""
    user1, user2 = test_users
    group1, group2 = test_groups

    member1 = GroupMember(user_id=user1.id, group_id=group1.id, role="admin")
    member2 = GroupMember(user_id=user2.id, group_id=group2.id, role="member")
    db_session.add(member1)
    db_session.add(member2)
    db_session.commit()
    return member1, member2
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_get_group_collection_name(isolation_manager):
    """Test generating group-specific collection names."""
    collection_name = isolation_manager.get_group_collection_name(
        group_id=1, base_collection="expert_agent"
    )

    assert collection_name == "expert_agent_group_1"
    assert "group_1" in collection_name
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_get_user_collection_name(isolation_manager):
    """Test generating user-specific collection names."""
    collection_name = isolation_manager.get_user_collection_name(
        user_id=1, base_collection="expert_agent"
    )

    assert collection_name == "expert_agent_user_1"
    assert "user_1" in collection_name
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_validate_group_access_allowed(
    isolation_manager, test_users, test_groups, test_group_members, db_session
):
    """Test validating group access when user is a member."""
    user1, _ = test_users
    group1, _ = test_groups

    # Create a vector store (required for validation)
    vector_store = VectorStoreModel(
        name="test_store",
        type="qdrant",
        enabled=True,
        config_json=json.dumps({"host": get_config("vector_stores_config.qdrant._DEFAULT_.host")}),
    )
    db_session.add(vector_store)
    db_session.commit()

    result = isolation_manager.validate_group_access(
        user_id=user1.id, group_id=group1.id, vector_store_name="test_store"
    )

    assert result is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_validate_group_access_denied(isolation_manager, test_users, test_groups):
    """Test validating group access when user is not a member."""
    user1, _ = test_users
    _, group2 = test_groups

    result = isolation_manager.validate_group_access(
        user_id=user1.id, group_id=group2.id, vector_store_name="test_store"
    )

    assert result is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_validate_group_access_nonexistent_user(isolation_manager, test_groups):
    """Test validating group access with nonexistent user."""
    group1, _ = test_groups

    result = isolation_manager.validate_group_access(
        user_id=99999, group_id=group1.id, vector_store_name="test_store"
    )

    assert result is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_validate_group_access_nonexistent_group(isolation_manager, test_users):
    """Test validating group access with nonexistent group."""
    user1, _ = test_users

    result = isolation_manager.validate_group_access(
        user_id=user1.id, group_id=99999, vector_store_name="test_store"
    )

    assert result is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_isolate_collection_by_group(isolation_manager, test_groups):
    """Test isolating collections by group ID."""
    group1, group2 = test_groups

    collection1 = isolation_manager.get_group_collection_name(group1.id, "test_collection")
    collection2 = isolation_manager.get_group_collection_name(group2.id, "test_collection")

    # Collections should be different
    assert collection1 != collection2
    assert f"group_{group1.id}" in collection1
    assert f"group_{group2.id}" in collection2
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_isolate_collection_by_user(isolation_manager, test_users):
    """Test isolating collections by user ID."""
    user1, user2 = test_users

    collection1 = isolation_manager.get_user_collection_name(user1.id, "test_collection")
    collection2 = isolation_manager.get_user_collection_name(user2.id, "test_collection")

    # Collections should be different
    assert collection1 != collection2
    assert f"user_{user1.id}" in collection1
    assert f"user_{user2.id}" in collection2
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_no_cross_talk_between_groups(isolation_manager, test_groups):
    """Test that different groups get different collection names."""
    group1, group2 = test_groups

    coll1 = isolation_manager.get_group_collection_name(group1.id)
    coll2 = isolation_manager.get_group_collection_name(group2.id)

    assert coll1 != coll2
    # Verify they contain different group IDs
    assert str(group1.id) in coll1
    assert str(group2.id) in coll2
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_no_cross_talk_between_users(isolation_manager, test_users):
    """Test that different users get different collection names."""
    user1, user2 = test_users

    coll1 = isolation_manager.get_user_collection_name(user1.id)
    coll2 = isolation_manager.get_user_collection_name(user2.id)

    assert coll1 != coll2
    # Verify they contain different user IDs
    assert str(user1.id) in coll1
    assert str(user2.id) in coll2
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_collection_name_stability(isolation_manager):
    """Test that collection names are stable (same input = same output)."""
    group_id = 42
    base = "test_collection"

    coll1 = isolation_manager.get_group_collection_name(group_id, base)
    coll2 = isolation_manager.get_group_collection_name(group_id, base)

    assert coll1 == coll2
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_collection_name_uniqueness(isolation_manager):
    """Test that collection names are unique for different groups."""
    collections = set()
    for group_id in range(1, 11):
        coll = isolation_manager.get_group_collection_name(group_id, "base")
        collections.add(coll)

    # All 10 collections should be unique
    assert len(collections) == 10
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_validate_vector_store_access_allowed(
    isolation_manager, test_users, test_groups, test_group_members, db_session
):
    """Test validating vector store access when user has group access."""
    user1, _ = test_users
    group1, _ = test_groups

    # Create a vector store
    vector_store = VectorStoreModel(
        name="test_store",
        type="qdrant",
        enabled=True,
        config_json=json.dumps({"host": get_config("vector_stores_config.qdrant._DEFAULT_.host")}),
    )
    db_session.add(vector_store)
    db_session.commit()

    # validate_group_access is synchronous, not async
    result = isolation_manager.validate_group_access(
        user_id=user1.id, group_id=group1.id, vector_store_name="test_store"
    )

    assert result is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_validate_vector_store_access_denied(
    isolation_manager, test_users, test_groups, db_session
):
    """Test validating vector store access when user does not have group access."""
    user1, _ = test_users
    _, group2 = test_groups

    # Create a vector store
    vector_store = VectorStoreModel(
        name="test_store",
        type="qdrant",
        enabled=True,
        config_json=json.dumps({"host": get_config("vector_stores_config.qdrant._DEFAULT_.host")}),
    )
    db_session.add(vector_store)
    db_session.commit()

    # validate_group_access is synchronous, not async
    result = isolation_manager.validate_group_access(
        user_id=user1.id, group_id=group2.id, vector_store_name="test_store"
    )

    assert result is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_collection_name_format(isolation_manager):
    """Test that collection names follow expected format."""
    group_id = 123
    base = "expert_agent"

    collection = isolation_manager.get_group_collection_name(group_id, base)

    # Should be: base_group_<id>
    assert collection.startswith(base)
    assert f"_group_{group_id}" in collection
    assert collection == f"{base}_group_{group_id}"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_user_collection_name_format(isolation_manager):
    """Test that user collection names follow expected format."""
    user_id = 456
    base = "expert_agent"

    collection = isolation_manager.get_user_collection_name(user_id, base)

    # Should be: base_user_<id>
    assert collection.startswith(base)
    assert f"_user_{user_id}" in collection
    assert collection == f"{base}_user_{user_id}"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.vdb, pytest.mark.db, pytest.mark.smtp, pytest.mark.fast]

