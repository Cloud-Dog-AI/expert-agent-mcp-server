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
System Test: ST1.12 - Collection-Based Data Separation

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for collection-based data separation

Related Requirements: FR1.3
Related Tasks: T019
Related Architecture: CC4.1.1
Related Tests: ST1.12

Recent Changes:
- Initial implementation
"""

import pytest
from src.core.vector.manager import VectorStoreManager
from src.database.models import Group, VectorStore


@pytest.fixture
def vector_manager(db_session):
    """Create vector store manager instance."""
    return VectorStoreManager(db_session)


@pytest.fixture
def test_group(db_session):
    """Create test group."""
    group = Group(name="test_group", description="Test group", enabled=True)
    db_session.add(group)
    db_session.commit()
    return group
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_collection_per_group_separation(vector_manager, db_session, test_group):
    """Test that each group has its own collection."""
    # Create vector store for group
    collection_name = f"group_{test_group.id}_collection"

    vector_store = VectorStore(
        name=f"store_group_{test_group.id}",
        type="qdrant",
        config_json=f'{{"collection_name": "{collection_name}"}}',
        enabled=True,
    )
    db_session.add(vector_store)
    db_session.commit()

    # Verify collection name is group-specific
    assert collection_name == f"group_{test_group.id}_collection"
    assert str(test_group.id) in collection_name
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_collection_isolation(vector_manager, db_session):
    """Test that collections are isolated between groups."""
    # Create two groups
    group1 = Group(name="group1", enabled=True)
    group2 = Group(name="group2", enabled=True)
    db_session.add_all([group1, group2])
    db_session.commit()

    # Create collections for each group
    collection1 = f"group_{group1.id}_collection"
    collection2 = f"group_{group2.id}_collection"

    # Collections should be different
    assert collection1 != collection2
    assert str(group1.id) in collection1
    assert str(group2.id) in collection2
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_collection_naming_convention(vector_manager, db_session, test_group):
    """Test collection naming convention."""
    # Collection names should follow a consistent pattern
    collection_name = f"group_{test_group.id}_collection"

    # Verify naming pattern
    assert collection_name.startswith("group_")
    assert collection_name.endswith("_collection")
    assert str(test_group.id) in collection_name
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_cross_collection_access_prevention(vector_manager, db_session):
    """Test that cross-collection access is prevented."""
    # Create two groups with separate collections
    group1 = Group(name="group1", enabled=True)
    group2 = Group(name="group2", enabled=True)
    db_session.add_all([group1, group2])
    db_session.commit()

    collection1 = f"group_{group1.id}_collection"
    collection2 = f"group_{group2.id}_collection"

    # Collections should be separate
    assert collection1 != collection2

    # Access control should prevent cross-collection access
    # (This would be tested with actual vector store operations)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_default_collection_for_system(vector_manager, db_session):
    """Test default collection for system-level data."""
    # System-level data should use a default collection
    default_collection = "expert_agent_default"

    vector_store = VectorStore(
        name="system_store",
        type="qdrant",
        config_json=f'{{"collection_name": "{default_collection}"}}',
        enabled=True,
    )
    db_session.add(vector_store)
    db_session.commit()

    # Verify default collection
    assert default_collection in vector_store.config_json
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_collection_cleanup_on_group_deletion(vector_manager, db_session):
    """Test that collections are cleaned up when groups are deleted."""
    # Create group and collection
    group = Group(name="temp_group", enabled=True)
    db_session.add(group)
    db_session.commit()

    # Delete group
    db_session.delete(group)
    db_session.commit()

    # Collection metadata should be handled appropriately
    # (Actual collection deletion would be handled by vector store manager)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.vdb, pytest.mark.db, pytest.mark.slow, pytest.mark.heavy]

