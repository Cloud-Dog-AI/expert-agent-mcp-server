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
Unit Test: UT1.16 - Chroma Integration

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for Chroma vector store integration

Related Requirements: FR1.3
Related Tasks: T015
Related Architecture: IP1.1.2
Related Tests: UT1.16

Recent Changes:
- Initial implementation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from src.core.vector.providers import ChromaProvider
from src.config.loader import get_config


@pytest.fixture
def chroma_provider():
    """Create Chroma provider instance."""
    return ChromaProvider()


@pytest.fixture
def mock_chroma_client():
    """Mock Chroma client."""
    mock_client = MagicMock()
    mock_collection = MagicMock()
    mock_client.get_collection.return_value = mock_collection
    mock_client.create_collection.return_value = mock_collection
    return mock_client, mock_collection
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_chroma_provider_initialization(chroma_provider):
    """Test Chroma provider initialization."""
    host = get_config("test.vector_stores.chroma.host")
    port = get_config("test.vector_stores.chroma.port")
    collection_name = get_config("test.vector_stores.chroma.collection_name")
    if not host or port is None or not collection_name:
        pytest.fail("Missing test.vector_stores.chroma.host/port/collection_name in config")
    config = {"host": str(host), "port": int(port), "collection_name": str(collection_name)}

    type(chroma_provider)._shared_clients.clear()
    mock_runtime_client = MagicMock()
    mock_runtime_client.init_backend = AsyncMock(return_value=True)
    chroma_provider._ensure_collection = AsyncMock()

    with patch("src.core.vector.providers.build_runtime_client", return_value=mock_runtime_client):
        result = await chroma_provider.initialize(config)
        assert result is True
        assert chroma_provider._initialized is True
        assert chroma_provider.client is mock_runtime_client
        chroma_provider._ensure_collection.assert_awaited_once()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_chroma_provider_add_documents(chroma_provider, mock_chroma_client):
    """Test adding documents to Chroma."""
    mock_client, mock_collection = mock_chroma_client
    chroma_provider.client = mock_client
    chroma_provider.collection = mock_collection
    chroma_provider._initialized = True

    mock_collection.add.return_value = None

    documents = ["Document 1", "Document 2"]
    metadatas = [{"source": "test1"}, {"source": "test2"}]

    # ChromaProvider.add_documents generates UUIDs if ids not provided
    with patch("uuid.uuid4") as mock_uuid:
        mock_uuid.return_value.hex = "test-id"
        mock_uuid.side_effect = [MagicMock(hex="id1"), MagicMock(hex="id2")]

        ids = await chroma_provider.add_documents(
            collection="test_collection", documents=documents, metadatas=metadatas
        )

        assert len(ids) == 2
        mock_collection.add.assert_called_once()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_chroma_provider_search(chroma_provider, mock_chroma_client):
    """Test searching Chroma collection."""
    mock_client, mock_collection = mock_chroma_client
    chroma_provider.client = mock_client
    chroma_provider.collection = mock_collection
    chroma_provider._initialized = True

    # Mock search results (Chroma returns "document" not "text")
    mock_results = {
        "ids": [["doc1", "doc2"]],
        "documents": [["Result 1", "Result 2"]],
        "metadatas": [[{"source": "test1"}, {"source": "test2"}]],
        "distances": [[0.1, 0.2]],
    }
    mock_collection.query.return_value = mock_results

    results = await chroma_provider.search(
        collection="test_collection", query="test query", n_results=2
    )

    assert len(results) == 2
    assert all("id" in r and "document" in r for r in results)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_chroma_provider_health_check(chroma_provider):
    """Test Chroma provider health check."""
    chroma_provider._initialized = False
    assert await chroma_provider.health_check() is False

    chroma_provider._initialized = True
    mock_client = MagicMock()
    mock_client.list_collections.return_value = []
    chroma_provider.client = mock_client
    assert await chroma_provider.health_check() is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_chroma_provider_not_initialized(chroma_provider):
    """Test that operations fail if provider not initialized."""
    with pytest.raises(RuntimeError, match="Chroma provider not initialized"):
        await chroma_provider.add_documents("test_collection", ["doc"])

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.vdb, pytest.mark.fast]
