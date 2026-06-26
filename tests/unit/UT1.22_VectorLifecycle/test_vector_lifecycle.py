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
Unit Test: UT1.22 - Vector Lifecycle Management

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for vector store lifecycle management (purge, compress, consolidate)

Related Requirements: FR1.3
Related Tasks: T018
Related Architecture: CC4.1.3
Related Tests: UT1.22

Recent Changes:
- Initial implementation
"""

import pytest
import json
from unittest.mock import Mock, AsyncMock
from src.core.vector.lifecycle import VectorLifecycleManager
from src.database.models import VectorStore as VectorStoreModel
from src.config.loader import get_config


@pytest.fixture
def lifecycle_manager(db_session):
    """Create a VectorLifecycleManager instance."""
    return VectorLifecycleManager(db=db_session)


def _require_vector_store_test_config():
    store_name = get_config("test.vector_stores.store_name")
    collection_name = get_config("test.vector_stores.collection_name")
    qdrant_host = get_config("test.vector_stores.qdrant.host")
    qdrant_port = get_config("test.vector_stores.qdrant.port")
    if not store_name or not collection_name or not qdrant_host or qdrant_port is None:
        pytest.fail("Missing test.vector_stores.* config for lifecycle tests")
    return store_name, collection_name, qdrant_host, qdrant_port


@pytest.fixture
def mock_vector_store(db_session):
    """Create a mock vector store."""
    store_name, _, qdrant_host, qdrant_port = _require_vector_store_test_config()
    store = VectorStoreModel(
        name=str(store_name),
        type="qdrant",
        enabled=True,
        config_json=json.dumps({"host": str(qdrant_host), "port": int(qdrant_port)}),
    )
    db_session.add(store)
    db_session.commit()
    db_session.refresh(store)
    return store


@pytest.fixture
def mock_provider():
    """Create a mock vector store provider."""
    provider = Mock()
    provider._initialized = True
    provider.count_documents = AsyncMock(return_value=10)
    provider.delete_document = AsyncMock(return_value=True)
    provider.search = AsyncMock(
        return_value=[
            {"id": "doc1", "document": "Test 1", "metadata": {}},
            {"id": "doc2", "document": "Test 2", "metadata": {}},
        ]
    )
    return provider
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_lifecycle_purge_by_age(lifecycle_manager, mock_vector_store, mock_provider):
    """Test purging documents older than specified days."""
    store_name, collection_name, _, _ = _require_vector_store_test_config()
    # Patch the _vector_manager attribute directly
    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = mock_vector_store
    mock_vm._get_provider.return_value = mock_provider
    lifecycle_manager._vector_manager = mock_vm

    result = await lifecycle_manager.purge(
        store_name=str(store_name), collection=str(collection_name), older_than_days=30
    )

    assert "purged_count" in result
    assert "count_before" in result
    assert "count_after" in result
    assert result["count_before"] == 10
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_lifecycle_purge_by_filter(lifecycle_manager, mock_vector_store, mock_provider):
    """Test purging documents by filter criteria."""
    store_name, collection_name, _, _ = _require_vector_store_test_config()
    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = mock_vector_store
    mock_vm._get_provider.return_value = mock_provider
    lifecycle_manager._vector_manager = mock_vm

    filter_criteria = {"source": "test", "status": "archived"}

    result = await lifecycle_manager.purge(
        store_name=str(store_name), collection=str(collection_name), filter_criteria=filter_criteria
    )

    assert "purged_count" in result
    assert result["count_before"] == 10
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_lifecycle_purge_store_not_found(lifecycle_manager):
    """Test purge when vector store is not found."""
    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = None
    lifecycle_manager._vector_manager = mock_vm

    with pytest.raises(ValueError, match="not found or disabled"):
        await lifecycle_manager.purge(
            store_name="nonexistent_store", collection=str(_require_vector_store_test_config()[1])
        )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_lifecycle_compress_duplicates(lifecycle_manager, mock_vector_store, mock_provider):
    """Test compressing collection by removing duplicates."""
    store_name, collection_name, _, _ = _require_vector_store_test_config()
    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = mock_vector_store
    mock_vm._get_provider.return_value = mock_provider
    lifecycle_manager._vector_manager = mock_vm

    # Mock search to return duplicate documents
    duplicate_results = [
        {"id": "doc1", "document": "Duplicate text", "metadata": {"source": "test"}},
        {"id": "doc2", "document": "Duplicate text", "metadata": {"source": "test"}},
        {"id": "doc3", "document": "Unique text", "metadata": {"source": "test"}},
    ]
    mock_provider.search.return_value = duplicate_results
    mock_provider.delete_document = AsyncMock(return_value=True)

    result = await lifecycle_manager.compress(
        store_name=str(store_name), collection=str(collection_name), target_ratio=0.5
    )

    assert "compressed_count" in result
    assert "count_before" in result
    assert "count_after" in result
    assert "compression_ratio" in result
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_lifecycle_compress_no_duplicates(
    lifecycle_manager, mock_vector_store, mock_provider
):
    """Test compress when no duplicates are found."""
    store_name, collection_name, _, _ = _require_vector_store_test_config()
    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = mock_vector_store
    mock_vm._get_provider.return_value = mock_provider
    lifecycle_manager._vector_manager = mock_vm

    # Mock search to return unique documents
    unique_results = [
        {"id": "doc1", "document": "Unique 1", "metadata": {}},
        {"id": "doc2", "document": "Unique 2", "metadata": {}},
    ]
    mock_provider.search.return_value = unique_results

    result = await lifecycle_manager.compress(
        store_name=str(store_name), collection=str(collection_name)
    )

    assert result["compressed_count"] == 0
    assert result["compression_ratio"] == 1.0  # No compression
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_lifecycle_consolidate_similar(lifecycle_manager, mock_vector_store, mock_provider):
    """Test consolidating similar documents."""
    store_name, collection_name, _, _ = _require_vector_store_test_config()
    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = mock_vector_store
    mock_vm._get_provider.return_value = mock_provider
    lifecycle_manager._vector_manager = mock_vm

    # Mock search to return similar documents
    similar_results = [
        {"id": "doc1", "document": "Similar content A", "metadata": {"source": "test"}},
        {"id": "doc2", "document": "Similar content B", "metadata": {"source": "test"}},
    ]
    mock_provider.search.return_value = similar_results
    mock_provider.update_document = AsyncMock(return_value=True)
    mock_provider.delete_document = AsyncMock(return_value=True)

    result = await lifecycle_manager.consolidate(
        store_name=str(store_name), collection=str(collection_name), similarity_threshold=0.85
    )

    assert "consolidated_count" in result
    assert "count_before" in result
    assert "count_after" in result
    assert "similarity_threshold" in result
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_lifecycle_consolidate_no_similar(
    lifecycle_manager, mock_vector_store, mock_provider
):
    """Test consolidate when no similar documents are found."""
    store_name, collection_name, _, _ = _require_vector_store_test_config()
    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = mock_vector_store
    mock_vm._get_provider.return_value = mock_provider
    lifecycle_manager._vector_manager = mock_vm

    # Mock search to return dissimilar documents
    dissimilar_results = [
        {"id": "doc1", "document": "Completely different A", "metadata": {}},
        {"id": "doc2", "document": "Completely different B", "metadata": {}},
    ]
    mock_provider.search.return_value = dissimilar_results

    result = await lifecycle_manager.consolidate(
        store_name=str(store_name), collection=str(collection_name)
    )

    assert result["consolidated_count"] == 0
    assert result["count_before"] == result["count_after"]  # No consolidation
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_lifecycle_purge_initializes_provider(
    lifecycle_manager, mock_vector_store, mock_provider
):
    """Test that purge initializes provider if not already initialized."""
    store_name, collection_name, _, _ = _require_vector_store_test_config()
    mock_provider._initialized = False
    mock_provider.initialize = AsyncMock(return_value=True)

    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = mock_vector_store
    mock_vm._get_provider.return_value = mock_provider
    lifecycle_manager._vector_manager = mock_vm

    await lifecycle_manager.purge(store_name=str(store_name), collection=str(collection_name))

    mock_provider.initialize.assert_called_once()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_lifecycle_compress_handles_errors(
    lifecycle_manager, mock_vector_store, mock_provider
):
    """Test that compress handles errors gracefully."""
    store_name, collection_name, _, _ = _require_vector_store_test_config()
    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = mock_vector_store
    mock_vm._get_provider.return_value = mock_provider
    lifecycle_manager._vector_manager = mock_vm

    mock_provider.search.side_effect = Exception("Search failed")

    # Compress catches exceptions and returns 0 compressed_count
    result = await lifecycle_manager.compress(
        store_name=str(store_name), collection=str(collection_name)
    )

    # Should return result with 0 compressed_count (error handled)
    assert result["compressed_count"] == 0
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_lifecycle_consolidate_handles_errors(
    lifecycle_manager, mock_vector_store, mock_provider
):
    """Test that consolidate handles errors gracefully."""
    store_name, collection_name, _, _ = _require_vector_store_test_config()
    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = mock_vector_store
    mock_vm._get_provider.return_value = mock_provider
    lifecycle_manager._vector_manager = mock_vm

    mock_provider.search.side_effect = Exception("Search failed")

    # Consolidate catches exceptions and returns 0 consolidated_count
    result = await lifecycle_manager.consolidate(
        store_name=str(store_name), collection=str(collection_name)
    )

    # Should return result with 0 consolidated_count (error handled)
    assert result["consolidated_count"] == 0
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_lifecycle_purge_empty_collection(
    lifecycle_manager, mock_vector_store, mock_provider
):
    """Test purging an empty collection."""
    store_name, collection_name, _, _ = _require_vector_store_test_config()
    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = mock_vector_store
    mock_vm._get_provider.return_value = mock_provider
    lifecycle_manager._vector_manager = mock_vm

    mock_provider.count_documents.return_value = 0
    mock_provider.search.return_value = []  # Empty search results

    result = await lifecycle_manager.purge(
        store_name=str(store_name), collection=str(collection_name)
    )

    assert result["purged_count"] == 0
    assert result["count_before"] == 0
    assert result["count_after"] == 0
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_lifecycle_compress_with_custom_threshold(
    lifecycle_manager, mock_vector_store, mock_provider
):
    """Test compress with custom similarity threshold."""
    store_name, collection_name, _, _ = _require_vector_store_test_config()
    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = mock_vector_store
    mock_vm._get_provider.return_value = mock_provider
    lifecycle_manager._vector_manager = mock_vm

    result = await lifecycle_manager.compress(
        store_name=str(store_name), collection=str(collection_name), target_ratio=0.90
    )

    assert "compressed_count" in result
    # Verify search was called
    assert mock_provider.search.called
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_lifecycle_consolidate_with_custom_threshold(
    lifecycle_manager, mock_vector_store, mock_provider
):
    """Test consolidate with custom similarity threshold."""
    store_name, collection_name, _, _ = _require_vector_store_test_config()
    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = mock_vector_store
    mock_vm._get_provider.return_value = mock_provider
    lifecycle_manager._vector_manager = mock_vm

    result = await lifecycle_manager.consolidate(
        store_name=str(store_name), collection=str(collection_name), similarity_threshold=0.80
    )

    assert "consolidated_count" in result
    # Verify search was called
    assert mock_provider.search.called

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.vdb, pytest.mark.db, pytest.mark.fast]

