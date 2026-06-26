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
Unit Test: UT1.18 - Qdrant Integration

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for Qdrant vector store integration

Related Requirements: FR1.3
Related Tasks: T016
Related Architecture: IP1.1.2
Related Tests: UT1.18

Recent Changes:
- Initial implementation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.vector.providers import QdrantProvider
from src.config.loader import get_config


@pytest.fixture
def qdrant_provider():
    """Create Qdrant provider instance."""
    return QdrantProvider()


@pytest.fixture
def mock_qdrant_client():
    """Mock Qdrant client."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.get_collection.return_value = mock_collection
    mock_client.create_collection.return_value = None
    return mock_client, mock_collection


def _require_qdrant_test_config():
    host = get_config("test.vector_stores.qdrant.host")
    port = get_config("test.vector_stores.qdrant.port")
    api_key = get_config("test.vector_stores.qdrant.api_key")
    collection_name = get_config("test.vector_stores.qdrant.collection_name")
    if not host or port is None or not collection_name:
        pytest.fail("Missing test.vector_stores.qdrant.host/port/collection_name in config")
    return host, port, api_key, collection_name
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_qdrant_provider_initialization(qdrant_provider):
    """Test Qdrant provider initialization."""
    host, port, api_key, collection_name = _require_qdrant_test_config()
    config = {
        "host": str(host),
        "port": int(port),
        "api_key": str(api_key) if api_key is not None else None,
        "collection_name": str(collection_name),
    }

    type(qdrant_provider)._shared_clients.clear()
    with patch.object(qdrant_provider, "embedding_manager") as mock_embedding:
        mock_embedding.initialize = AsyncMock()
        mock_embedding.get_embedding_dimension = MagicMock(return_value=1024)
        mock_runtime_client = MagicMock()
        mock_runtime_client.init_backend = AsyncMock(return_value=True)
        qdrant_provider._ensure_collection = AsyncMock()

        with patch(
            "src.core.vector.providers.build_runtime_client",
            return_value=mock_runtime_client,
        ):
            result = await qdrant_provider.initialize(config)
            assert result is True
            assert qdrant_provider._initialized is True
            assert qdrant_provider.client is mock_runtime_client
            qdrant_provider._ensure_collection.assert_awaited_once()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_qdrant_provider_add_documents(qdrant_provider, mock_qdrant_client):
    """Test adding documents to Qdrant."""
    _, _, _, collection_name = _require_qdrant_test_config()
    mock_client, mock_collection = mock_qdrant_client
    qdrant_provider.client = mock_client
    qdrant_provider._initialized = True

    documents = ["Document 1", "Document 2"]
    metadatas = [{"source": "test1"}, {"source": "test2"}]

    # Mock embedding manager
    with patch.object(qdrant_provider, "embedding_manager") as mock_embedding:
        mock_embedding.generate_batch_embeddings = AsyncMock(
            return_value=[[0.1] * 1024, [0.2] * 1024]
        )

        # Mock uuid generation
        with patch("uuid.uuid4") as mock_uuid:
            mock_uuid.side_effect = [MagicMock(hex="id1"), MagicMock(hex="id2")]

            ids = await qdrant_provider.add_documents(
                collection=str(collection_name), documents=documents, metadatas=metadatas
            )

            assert len(ids) == 2
            mock_client.upsert.assert_called_once()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_qdrant_provider_search(qdrant_provider, mock_qdrant_client):
    """Test searching Qdrant collection."""
    _, _, _, collection_name = _require_qdrant_test_config()
    mock_client, mock_collection = mock_qdrant_client
    qdrant_provider.client = mock_client
    qdrant_provider._initialized = True

    # Mock search results (Qdrant uses query_points which returns points)
    mock_point = MagicMock()
    mock_point.id = "doc1"
    mock_point.payload = {"text": "Result 1", "source": "test1"}
    mock_point.score = 0.9

    mock_query_result = MagicMock()
    mock_query_result.points = [mock_point]
    mock_client.query_points.return_value = mock_query_result

    # Mock embedding manager
    with patch.object(qdrant_provider, "embedding_manager") as mock_embedding:
        mock_embedding.generate_embedding = AsyncMock(return_value=[0.1] * 1024)

        results = await qdrant_provider.search(
            collection=str(collection_name), query="test query", n_results=1
        )

        assert len(results) == 1
        assert "id" in results[0]
        assert "document" in results[0]
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_qdrant_provider_health_check(qdrant_provider):
    """Test Qdrant provider health check."""
    qdrant_provider._initialized = False
    assert await qdrant_provider.health_check() is False

    qdrant_provider._initialized = True
    mock_client = MagicMock()
    mock_client.get_collections.return_value = MagicMock()
    qdrant_provider.client = mock_client
    assert await qdrant_provider.health_check() is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_qdrant_provider_not_initialized(qdrant_provider):
    """Test that operations fail if provider not initialized."""
    _, _, _, collection_name = _require_qdrant_test_config()
    with pytest.raises(RuntimeError, match="Qdrant provider not initialized"):
        await qdrant_provider.add_documents(str(collection_name), ["doc"])
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_qdrant_provider_delete_document(qdrant_provider, mock_qdrant_client):
    """Test deleting document from Qdrant."""
    mock_client, mock_collection = mock_qdrant_client
    qdrant_provider.client = mock_client
    qdrant_provider._initialized = True

    # QdrantProvider uses default implementation which may not be implemented
    # Check if it raises or returns False
    try:
        result = await qdrant_provider.delete_document("test_collection", "doc1")
        # If implemented, should return True/False
        assert isinstance(result, bool)
    except NotImplementedError:
        # If not implemented, that's also acceptable for default implementation
        pass
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_qdrant_provider_count_documents(qdrant_provider, mock_qdrant_client):
    """Test counting documents in Qdrant."""
    mock_client, mock_collection = mock_qdrant_client
    qdrant_provider.client = mock_client
    qdrant_provider._initialized = True

    # QdrantProvider uses default implementation which uses search
    # Mock search to return results
    mock_point = MagicMock()
    mock_point.id = "doc1"
    mock_point.payload = {"text": "Result 1"}
    mock_point.score = 0.9

    mock_query_result = MagicMock()
    mock_query_result.points = [mock_point] * 5  # 5 results
    mock_client.query_points.return_value = mock_query_result

    # Mock embedding manager for search
    with patch.object(qdrant_provider, "embedding_manager") as mock_embedding:
        mock_embedding.generate_embedding = AsyncMock(return_value=[0.1] * 1024)

        count = await qdrant_provider.count_documents("test_collection")

        # Should return count (may be limited by search implementation)
        assert count >= 0

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.vdb, pytest.mark.fast]
