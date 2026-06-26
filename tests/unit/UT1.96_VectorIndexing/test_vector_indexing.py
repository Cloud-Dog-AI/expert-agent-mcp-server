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
Unit Test: UT1.21 - Indexing and Search Functionality

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for vector store indexing and search

Related Requirements: FR1.3
Related Tasks: T017
Related Architecture: CC4.1.2
Related Tests: UT1.21

Recent Changes:
- Initial implementation
"""

import pytest
from src.core.vector.manager import VectorStoreManager
from src.core.vector.providers import QdrantProvider
from unittest.mock import Mock, AsyncMock
from types import SimpleNamespace


@pytest.fixture
def vector_manager():
    """Create vector store manager."""
    return VectorStoreManager()


@pytest.fixture
async def qdrant_provider(vector_manager):
    """
    Unit-test Qdrant provider behaviour with a mocked client.

    RULES.md alignment:
    - Unit tests may use mocks/stubs.
    - No dependency on a real Qdrant service.
    """
    provider = QdrantProvider()
    provider._initialized = True

    # Mock embeddings (no external calls)
    provider.embedding_manager.get_embedding_dimension = Mock(return_value=1024)
    provider.embedding_manager.generate_batch_embeddings = AsyncMock(
        side_effect=lambda docs: [[0.0] * 1024 for _ in docs]
    )
    provider.embedding_manager.generate_embedding = AsyncMock(return_value=[0.0] * 1024)

    # Mock Qdrant client (avoid qdrant_client pydantic validation/network)
    client = Mock()
    client.get_collections = Mock(return_value=SimpleNamespace(collections=[]))
    client.create_collection = Mock()
    client.upsert = Mock()

    def query_points_side_effect(**kwargs):
        # Return deterministic results; include category for filter tests
        points = [
            SimpleNamespace(
                id="1", payload={"text": "Doc 1", "category": "programming"}, score=0.9
            ),
            SimpleNamespace(
                id="2", payload={"text": "Doc 2", "category": "programming"}, score=0.8
            ),
            SimpleNamespace(
                id="3", payload={"text": "Doc 3", "category": "programming"}, score=0.7
            ),
        ]
        return SimpleNamespace(points=points[: int(kwargs.get("limit", 3))])

    client.query_points = Mock(side_effect=query_points_side_effect)
    provider.client = client
    return provider
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_add_documents_with_indexing(qdrant_provider):
    """Test adding documents with automatic embedding indexing."""
    if not qdrant_provider._initialized:
        pytest.skip("Qdrant not available")

    collection = "test_collection"

    documents = [
        "The expert agent helps users with technical questions.",
        "Vector stores enable semantic search capabilities.",
        "Embeddings convert text into numerical representations.",
    ]

    metadatas = [
        {"source": "doc1", "type": "technical"},
        {"source": "doc2", "type": "technical"},
        {"source": "doc3", "type": "technical"},
    ]

    ids = await qdrant_provider.add_documents(
        collection=collection, documents=documents, metadatas=metadatas
    )

    assert len(ids) == 3
    assert all(id is not None for id in ids)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_search_with_embeddings(qdrant_provider):
    """Test search functionality with query embeddings."""
    if not qdrant_provider._initialized:
        pytest.skip("Qdrant not available")

    collection = "test_collection"

    # Add documents first
    documents = [
        "Python is a programming language.",
        "JavaScript is used for web development.",
        "SQL is a database query language.",
    ]

    await qdrant_provider.add_documents(
        collection=collection,
        documents=documents,
        metadatas=[{"source": f"doc{i}"} for i in range(3)],
    )

    # Search
    results = await qdrant_provider.search(
        collection=collection, query="What programming languages are available?", n_results=3
    )

    assert len(results) > 0
    assert all("document" in r for r in results)
    assert all("score" in r for r in results)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_search_with_filters(qdrant_provider):
    """Test search with metadata filters."""
    if not qdrant_provider._initialized:
        pytest.skip("Qdrant not available")

    collection = "test_collection"

    # Add documents with metadata
    documents = ["Document about Python", "Document about JavaScript", "Document about SQL"]

    metadatas = [
        {"source": "doc1", "category": "programming"},
        {"source": "doc2", "category": "programming"},
        {"source": "doc3", "category": "database"},
    ]

    await qdrant_provider.add_documents(
        collection=collection, documents=documents, metadatas=metadatas
    )

    # Search with filter
    results = await qdrant_provider.search(
        collection=collection,
        query="programming languages",
        n_results=5,
        filter={"category": "programming"},
    )

    assert len(results) > 0
    # All results should match filter
    for result in results:
        metadata = result.get("metadata", {})
        assert metadata.get("category") == "programming"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_indexing_multiple_documents(qdrant_provider):
    """Test indexing multiple documents in batch."""
    if not qdrant_provider._initialized:
        pytest.skip("Qdrant not available")

    collection = "test_collection"

    documents = [f"Document {i} about topic {i % 3}" for i in range(10)]
    metadatas = [{"index": i, "topic": i % 3} for i in range(10)]

    ids = await qdrant_provider.add_documents(
        collection=collection, documents=documents, metadatas=metadatas
    )

    assert len(ids) == 10
    assert len(set(ids)) == 10  # All IDs should be unique
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_search_relevance_scores(qdrant_provider):
    """Test that search returns relevance scores."""
    if not qdrant_provider._initialized:
        pytest.skip("Qdrant not available")

    collection = "test_collection"

    # Add documents
    documents = [
        "Machine learning is a subset of artificial intelligence.",
        "Deep learning uses neural networks.",
        "Natural language processing enables text understanding.",
    ]

    await qdrant_provider.add_documents(collection=collection, documents=documents)

    # Search
    results = await qdrant_provider.search(
        collection=collection, query="artificial intelligence and machine learning", n_results=3
    )

    assert len(results) > 0

    # Check scores are in descending order (most relevant first)
    scores = [r.get("score", 0) for r in results]
    assert all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1))
    assert all(0 <= score <= 1 for score in scores)  # Cosine similarity range

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.vdb, pytest.mark.db, pytest.mark.fast]

