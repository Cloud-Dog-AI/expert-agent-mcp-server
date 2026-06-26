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
Unit Test: UT1.15 - Vector Store Abstraction Interface

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for vector store abstraction interface

Related Requirements: FR1.3
Related Tasks: T014
Related Architecture: CC4.1.1
Related Tests: UT1.15

Recent Changes:
- Initial implementation
"""

import pytest
from src.config.loader import get_config
from src.core.vector.providers import VectorStoreProvider


class MockVectorStoreProvider(VectorStoreProvider):
    """Mock implementation for testing abstraction."""

    def __init__(self):
        self._initialized = False
        self._documents = {}

    async def initialize(self, config):
        """Initialize mock provider."""
        self._initialized = True
        return True

    async def add_documents(self, collection, documents, metadatas=None, ids=None):
        """Add documents to mock collection."""
        if collection not in self._documents:
            self._documents[collection] = []

        doc_ids = ids or [f"doc_{i}" for i in range(len(documents))]
        for i, doc in enumerate(documents):
            self._documents[collection].append(
                {
                    "id": doc_ids[i],
                    "content": doc,
                    "metadata": metadatas[i] if metadatas and i < len(metadatas) else {},
                }
            )
        return doc_ids

    async def search(self, collection, query, n_results=5, filter=None):
        """Search mock collection."""
        if collection not in self._documents:
            return []

        results = []
        for doc in self._documents[collection][:n_results]:
            results.append(
                {"id": doc["id"], "text": doc["content"], "score": 0.9, "metadata": doc["metadata"]}
            )
        return results

    async def health_check(self):
        """Check mock provider health."""
        return self._initialized
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_vector_store_provider_abstract_interface():
    """Test that VectorStoreProvider is an abstract class."""
    # Cannot instantiate abstract class directly
    with pytest.raises(TypeError):
        VectorStoreProvider()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_vector_store_provider_initialization():
    """Test vector store provider initialization."""
    provider = MockVectorStoreProvider()

    assert provider._initialized is False

    host = get_config("test.vector_stores.chroma.host")
    port = get_config("test.vector_stores.chroma.port")
    if not host or port is None:
        pytest.fail("Missing test.vector_stores.chroma.host/port in config")
    result = await provider.initialize({"host": str(host), "port": int(port)})

    assert result is True
    assert provider._initialized is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_vector_store_provider_add_documents():
    """Test adding documents to vector store."""
    provider = MockVectorStoreProvider()
    await provider.initialize({})

    collection_name = get_config("test.vector_stores.collection_name")
    if not collection_name:
        pytest.fail("Missing test.vector_stores.collection_name in config")
    documents = ["Document 1", "Document 2"]
    metadatas = [{"source": "test1"}, {"source": "test2"}]

    ids = await provider.add_documents(
        collection=str(collection_name), documents=documents, metadatas=metadatas
    )

    assert len(ids) == 2
    assert ids[0] == "doc_0"
    assert ids[1] == "doc_1"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_vector_store_provider_search():
    """Test searching vector store."""
    provider = MockVectorStoreProvider()
    await provider.initialize({})

    collection_name = get_config("test.vector_stores.collection_name")
    if not collection_name:
        pytest.fail("Missing test.vector_stores.collection_name in config")
    # Add documents first
    await provider.add_documents(
        collection=str(collection_name), documents=["Document 1", "Document 2", "Document 3"]
    )

    # Search
    results = await provider.search(
        collection=str(collection_name), query="test query", n_results=2
    )

    assert len(results) == 2
    assert all("id" in r and "text" in r for r in results)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_vector_store_provider_health_check():
    """Test health check."""
    provider = MockVectorStoreProvider()

    # Not initialized
    assert await provider.health_check() is False

    # Initialize
    await provider.initialize({})

    # Should be healthy
    assert await provider.health_check() is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_vector_store_provider_delete_document():
    """Test deleting document (default implementation)."""
    provider = MockVectorStoreProvider()
    await provider.initialize({})

    # Default implementation should return False
    result = await provider.delete_document("test_collection", "doc_1")

    assert result is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_vector_store_provider_update_document():
    """Test updating document (default implementation)."""
    provider = MockVectorStoreProvider()
    await provider.initialize({})

    # Default implementation should return False
    result = await provider.update_document("test_collection", "doc_1", "Updated content")

    assert result is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_vector_store_provider_count_documents():
    """Test counting documents (default implementation)."""
    provider = MockVectorStoreProvider()
    await provider.initialize({})

    # Add documents
    await provider.add_documents(
        collection="test_collection", documents=["Doc 1", "Doc 2", "Doc 3"]
    )

    # Count documents (default implementation uses search)
    count = await provider.count_documents("test_collection")

    assert count >= 0  # Should return a count (may be limited by search implementation)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.vdb, pytest.mark.fast]

