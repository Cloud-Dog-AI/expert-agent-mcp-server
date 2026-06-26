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
System Test: ST1.11 - Vector Store Metadata Synchronization

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for vector store metadata synchronization

Related Requirements: FR1.3
Related Tasks: T014
Related Architecture: CC4.1.1
Related Tests: ST1.11

Recent Changes:
- Initial implementation
"""

import json
import pytest
from src.core.vector.manager import VectorStoreManager
from src.database.models import VectorStore
from src.config.loader import get_config


def _require_qdrant_config() -> dict:
    qdrant_cfg = get_config("vector_stores_config.qdrant._DEFAULT_")
    if not isinstance(qdrant_cfg, dict):
        pytest.fail("Missing vector_stores_config.qdrant._DEFAULT_ config")
    host = qdrant_cfg.get("host")
    port = qdrant_cfg.get("port")
    collection = qdrant_cfg.get("collection_name")
    if not host or port is None or not collection:
        pytest.fail("Qdrant host/port/collection_name not configured")
    return {"host": host, "port": int(port), "collection_name": collection}


def _require_group_prefix() -> str:
    group_prefix = get_config("test.group.name_prefix")
    if not group_prefix:
        pytest.fail("test.group.name_prefix not configured")
    return str(group_prefix)


@pytest.fixture
def vector_manager(db_session):
    """Create vector store manager instance."""
    return VectorStoreManager(db_session)
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_vector_store_metadata_creation(vector_manager, db_session):
    """Test vector store metadata creation in database."""
    qdrant_cfg = _require_qdrant_config()
    # Create vector store record
    vector_store = VectorStore(
        name="test_store", type="qdrant", config_json=json.dumps(qdrant_cfg), enabled=True
    )
    db_session.add(vector_store)
    db_session.commit()

    assert vector_store.id is not None
    assert vector_store.name == "test_store"
    assert vector_store.type == "qdrant"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_vector_store_metadata_retrieval(vector_manager, db_session):
    """Test vector store metadata retrieval."""
    # Create vector store
    vector_store = VectorStore(name="test_store_2", type="chroma", enabled=True)
    db_session.add(vector_store)
    db_session.commit()

    # Retrieve metadata
    retrieved = db_session.query(VectorStore).filter(VectorStore.name == "test_store_2").first()

    assert retrieved is not None
    assert retrieved.name == "test_store_2"
    assert retrieved.type == "chroma"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_vector_store_metadata_update(vector_manager, db_session):
    """Test vector store metadata update."""
    qdrant_cfg = _require_qdrant_config()
    # Create vector store
    vector_store = VectorStore(name="test_store_3", type="qdrant", enabled=True)
    db_session.add(vector_store)
    db_session.commit()

    # Update metadata
    vector_store.enabled = False
    updated_cfg = {
        "host": qdrant_cfg["host"],
        "port": qdrant_cfg["port"] + 1,
        "collection_name": qdrant_cfg["collection_name"],
    }
    vector_store.config_json = json.dumps(updated_cfg)
    db_session.commit()

    # Verify update
    updated = db_session.query(VectorStore).filter(VectorStore.id == vector_store.id).first()

    assert updated.enabled is False
    assert str(updated_cfg["port"]) in updated.config_json
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_vector_store_synchronization(vector_manager, db_session):
    """Test synchronization between database and vector store."""
    qdrant_cfg = _require_qdrant_config()
    # Create vector store in database directly
    vector_store = VectorStore(
        name="sync_test", type="qdrant", config_json=json.dumps(qdrant_cfg), enabled=True
    )
    db_session.add(vector_store)
    db_session.commit()
    db_session.refresh(vector_store)

    # Verify it's in database
    db_store = db_session.query(VectorStore).filter(VectorStore.name == "sync_test").first()

    assert db_store is not None
    assert db_store.name == "sync_test"
    assert db_store.type == "qdrant"
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_vector_store_collection_mapping(vector_manager, db_session):
    """Test collection mapping in vector store metadata."""
    qdrant_cfg = _require_qdrant_config()
    # Vector store should track collections
    vector_store = VectorStore(
        name="collection_test",
        type="qdrant",
        config_json=json.dumps({"collection_name": qdrant_cfg["collection_name"]}),
        enabled=True,
    )
    db_session.add(vector_store)
    db_session.commit()

    # Verify collection mapping
    assert vector_store.config_json is not None
    assert "collection" in vector_store.config_json.lower()
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_vector_store_access_control_metadata(vector_manager, db_session):
    """Test access control metadata in vector store."""
    group_prefix = _require_group_prefix()
    # Create vector store with access control
    vector_store = VectorStore(
        name="acl_test",
        type="qdrant",
        access_control_json=json.dumps(
            {
                "read_groups": [f"{group_prefix}_read"],
                "write_groups": [f"{group_prefix}_write"],
            }
        ),
        enabled=True,
    )
    db_session.add(vector_store)
    db_session.commit()

    # Verify access control metadata
    assert vector_store.access_control_json is not None
    assert group_prefix in vector_store.access_control_json

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.system, pytest.mark.vdb, pytest.mark.db, pytest.mark.slow, pytest.mark.heavy]

