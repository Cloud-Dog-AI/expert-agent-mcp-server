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
Unit Test: UT1.19 - OpenSearch/Elastic Integration

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for OpenSearch/Elasticsearch vector store provider integration

Related Requirements: FR1.3
Related Tasks: T016
Related Architecture: IP1.1.2
Related Tests: UT1.19

Recent Changes:
- Initial implementation
"""

import importlib.util
from unittest.mock import AsyncMock, Mock, patch

import pytest
from src.core.vector.providers import OpenSearchProvider
from src.config.loader import get_config


@pytest.fixture
def opensearch_provider():
    """Create an OpenSearch provider instance."""
    return OpenSearchProvider()


@pytest.fixture
def mock_opensearch_client():
    """Create a mock OpenSearch client."""
    mock_client = Mock()
    mock_client.indices = Mock()
    mock_client.indices.exists = Mock(return_value=False)
    mock_client.indices.create = Mock()
    mock_client.indices.refresh = Mock()
    mock_client.index = Mock()
    mock_client.search = Mock()
    mock_client.delete = Mock()
    return mock_client


def _require_opensearch_test_config():
    host = get_config("test.vector_stores.opensearch.host")
    port = get_config("test.vector_stores.opensearch.port")
    username = get_config("test.vector_stores.opensearch.username")
    password = get_config("test.vector_stores.opensearch.password")
    collection_name = get_config("test.vector_stores.opensearch.collection_name")
    if not host or port is None or not collection_name:
        pytest.fail("Missing test.vector_stores.opensearch.host/port/collection_name in config")
    return host, port, username, password, collection_name
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_opensearch_initialization_success(opensearch_provider, mock_opensearch_client):
    """Test successful OpenSearch initialization."""
    if importlib.util.find_spec("opensearchpy") is None:
        pytest.fail("opensearchpy not installed")

    host, port, _, _, collection_name = _require_opensearch_test_config()
    config = {"host": str(host), "port": int(port), "collection_name": str(collection_name)}

    with patch("opensearchpy.OpenSearch", return_value=mock_opensearch_client):
        with patch.object(
            opensearch_provider.embedding_manager, "initialize", new_callable=AsyncMock
        ) as mock_init:
            with patch.object(
                opensearch_provider.embedding_manager, "get_embedding_dimension", return_value=1024
            ):
                mock_init.return_value = None

                result = await opensearch_provider.initialize(config)

                assert result is True
                assert opensearch_provider._initialized is True
                assert opensearch_provider.client is not None
                assert await opensearch_provider.health_check() is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_opensearch_initialization_existing_index(
    opensearch_provider, mock_opensearch_client
):
    """Test OpenSearch initialization with existing index."""
    if importlib.util.find_spec("opensearchpy") is None:
        pytest.fail("opensearchpy not installed")

    host, port, _, _, collection_name = _require_opensearch_test_config()
    config = {"host": str(host), "port": int(port), "collection_name": str(collection_name)}

    mock_opensearch_client.indices.exists.return_value = True

    with patch("opensearchpy.OpenSearch", return_value=mock_opensearch_client):
        with patch.object(
            opensearch_provider.embedding_manager, "initialize", new_callable=AsyncMock
        ) as mock_init:
            with patch.object(
                opensearch_provider.embedding_manager, "get_embedding_dimension", return_value=1024
            ):
                mock_init.return_value = None

                result = await opensearch_provider.initialize(config)

                assert result is True
                assert opensearch_provider._initialized is True
                mock_opensearch_client.indices.create.assert_not_called()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_opensearch_initialization_with_auth(opensearch_provider, mock_opensearch_client):
    """Test OpenSearch initialization with authentication."""
    if importlib.util.find_spec("opensearchpy") is None:
        pytest.fail("opensearchpy not installed")

    host, port, username, password, collection_name = _require_opensearch_test_config()
    config = {
        "host": str(host),
        "port": int(port),
        "username": str(username) if username is not None else None,
        "password": str(password) if password is not None else None,
        "collection_name": str(collection_name),
    }

    with patch("opensearchpy.OpenSearch", return_value=mock_opensearch_client):
        with patch.object(
            opensearch_provider.embedding_manager, "initialize", new_callable=AsyncMock
        ) as mock_init:
            with patch.object(
                opensearch_provider.embedding_manager, "get_embedding_dimension", return_value=1024
            ):
                mock_init.return_value = None

                result = await opensearch_provider.initialize(config)

                assert result is True
                assert opensearch_provider._initialized is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_opensearch_initialization_import_error(opensearch_provider):
    """Test OpenSearch initialization when runtime client deps are unavailable."""
    host, port, _, _, collection_name = _require_opensearch_test_config()
    config = {"host": str(host), "port": int(port), "collection_name": str(collection_name)}

    with patch.object(
        opensearch_provider.embedding_manager, "initialize", new_callable=AsyncMock
    ) as mock_init:
        mock_init.return_value = None
        with patch.object(opensearch_provider.__class__, "_shared_clients", {}):
            with patch(
                "src.core.vector.providers.build_runtime_client",
                side_effect=ImportError("No module named 'opensearchpy'"),
            ):
                result = await opensearch_provider.initialize(config)

                assert result is False
                assert opensearch_provider._initialized is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_opensearch_add_documents(opensearch_provider, mock_opensearch_client):
    """Test adding documents to OpenSearch index."""
    _, _, _, _, collection_name = _require_opensearch_test_config()
    opensearch_provider.client = mock_opensearch_client
    opensearch_provider._initialized = True
    opensearch_provider.index_name = str(collection_name)

    documents = ["Document 1", "Document 2"]
    metadatas = [{"source": "test1"}, {"source": "test2"}]
    ids = ["id1", "id2"]

    mock_embeddings = [[0.1] * 1024, [0.2] * 1024]

    with patch.object(
        opensearch_provider.embedding_manager, "generate_batch_embeddings", new_callable=AsyncMock
    ) as mock_emb:
        mock_emb.return_value = mock_embeddings
        mock_opensearch_client.index.return_value = {"_id": "id1"}

        result = await opensearch_provider.add_documents(
            collection=str(collection_name), documents=documents, metadatas=metadatas, ids=ids
        )

        assert len(result) == 2
        assert result == ids
        assert mock_opensearch_client.index.call_count == 2
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_opensearch_add_documents_auto_ids(opensearch_provider, mock_opensearch_client):
    """Test adding documents with auto-generated IDs."""
    _, _, _, _, collection_name = _require_opensearch_test_config()
    opensearch_provider.client = mock_opensearch_client
    opensearch_provider._initialized = True
    opensearch_provider.index_name = str(collection_name)

    documents = ["Document 1"]
    mock_embeddings = [[0.1] * 1024]

    with patch.object(
        opensearch_provider.embedding_manager, "generate_batch_embeddings", new_callable=AsyncMock
    ) as mock_emb:
        mock_emb.return_value = mock_embeddings
        mock_opensearch_client.index.return_value = {"_id": "auto_id"}

        result = await opensearch_provider.add_documents(
            collection=str(collection_name), documents=documents
        )

        assert len(result) == 1
        assert isinstance(result[0], str)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_opensearch_add_documents_not_initialized(opensearch_provider):
    """Test adding documents when provider is not initialized."""
    _, _, _, _, collection_name = _require_opensearch_test_config()
    opensearch_provider._initialized = False

    with pytest.raises(RuntimeError, match="OpenSearch provider not initialized"):
        await opensearch_provider.add_documents(
            collection=str(collection_name), documents=["Document 1"]
        )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_opensearch_search(opensearch_provider, mock_opensearch_client):
    """Test searching OpenSearch index."""
    _, _, _, _, collection_name = _require_opensearch_test_config()
    opensearch_provider.client = mock_opensearch_client
    opensearch_provider._initialized = True
    opensearch_provider.index_name = str(collection_name)

    query = "test query"
    query_vector = [0.1] * 1024

    # Mock search results
    mock_opensearch_client.search.return_value = {
        "hits": {
            "hits": [
                {
                    "_id": "id1",
                    "_source": {"text": "Result 1", "metadata": {"source": "test1"}},
                    "_score": 0.9,
                },
                {
                    "_id": "id2",
                    "_source": {"text": "Result 2", "metadata": {"source": "test2"}},
                    "_score": 0.8,
                },
            ]
        }
    }

    with patch.object(
        opensearch_provider.embedding_manager, "generate_embedding", new_callable=AsyncMock
    ) as mock_emb:
        mock_emb.return_value = query_vector

        results = await opensearch_provider.search(
            collection=str(collection_name), query=query, n_results=2
        )

        assert len(results) == 2
        assert results[0]["document"] == "Result 1"
        assert results[1]["document"] == "Result 2"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_opensearch_search_with_filter(opensearch_provider, mock_opensearch_client):
    """Test searching OpenSearch with metadata filter."""
    _, _, _, _, collection_name = _require_opensearch_test_config()
    opensearch_provider.client = mock_opensearch_client
    opensearch_provider._initialized = True
    opensearch_provider.index_name = str(collection_name)

    query = "test query"
    query_vector = [0.1] * 1024
    filter_dict = {"source": "test1"}

    mock_opensearch_client.search.return_value = {
        "hits": {
            "hits": [
                {
                    "_id": "id1",
                    "_source": {"text": "Result 1", "metadata": {"source": "test1"}},
                    "_score": 0.9,
                }
            ]
        }
    }

    with patch.object(
        opensearch_provider.embedding_manager, "generate_embedding", new_callable=AsyncMock
    ) as mock_emb:
        mock_emb.return_value = query_vector

        results = await opensearch_provider.search(
            collection=str(collection_name), query=query, n_results=5, filter=filter_dict
        )

        assert len(results) == 1
        # Verify filter was applied (check that search was called)
        mock_opensearch_client.search.assert_called_once()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_opensearch_search_not_initialized(opensearch_provider):
    """Test searching when provider is not initialized."""
    _, _, _, _, collection_name = _require_opensearch_test_config()
    opensearch_provider._initialized = False

    with pytest.raises(RuntimeError, match="OpenSearch provider not initialized"):
        await opensearch_provider.search(collection=str(collection_name), query="test query")
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_opensearch_delete_document(opensearch_provider, mock_opensearch_client):
    """Test deleting a document from OpenSearch index."""
    _, _, _, _, collection_name = _require_opensearch_test_config()
    opensearch_provider.client = mock_opensearch_client
    opensearch_provider._initialized = True

    mock_opensearch_client.delete.return_value = {"result": "deleted"}

    result = await opensearch_provider.delete_document(
        collection=str(collection_name), doc_id="doc_id_1"
    )

    assert result is True
    mock_opensearch_client.delete.assert_called_once_with(index=str(collection_name), id="doc_id_1")
    mock_opensearch_client.indices.refresh.assert_called_once_with(index=str(collection_name))
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_opensearch_update_document(opensearch_provider, mock_opensearch_client):
    """Test updating a document in OpenSearch index."""
    _, _, _, _, collection_name = _require_opensearch_test_config()
    opensearch_provider.client = mock_opensearch_client
    opensearch_provider._initialized = True

    document_id = "doc_id_1"
    new_text = "Updated document"
    new_metadata = {"source": "updated"}
    new_vector = [0.2] * 1024

    mock_opensearch_client.index.return_value = {"result": "updated"}

    with patch.object(
        opensearch_provider.embedding_manager, "generate_embedding", new_callable=AsyncMock
    ) as mock_emb:
        mock_emb.return_value = new_vector

        result = await opensearch_provider.update_document(
            collection=str(collection_name),
            doc_id=document_id,
            content=new_text,
            metadata=new_metadata,
        )

        assert result is True
        mock_opensearch_client.index.assert_called_once()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_opensearch_count_documents(opensearch_provider, mock_opensearch_client):
    """Test counting documents in OpenSearch index."""
    _, _, _, _, collection_name = _require_opensearch_test_config()
    opensearch_provider.client = mock_opensearch_client
    opensearch_provider._initialized = True

    mock_opensearch_client.count.return_value = {"count": 42}

    count = await opensearch_provider.count_documents(str(collection_name))

    assert count == 42
    # Verify count was called with correct parameters
    assert mock_opensearch_client.count.called
    call_args = mock_opensearch_client.count.call_args
    assert call_args[1]["index"] == str(collection_name)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_opensearch_health_check_healthy(opensearch_provider, mock_opensearch_client):
    """Test OpenSearch health check when healthy."""
    opensearch_provider.client = mock_opensearch_client
    opensearch_provider._initialized = True

    mock_opensearch_client.ping.return_value = True

    result = await opensearch_provider.health_check()

    assert result is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_opensearch_health_check_unhealthy(opensearch_provider, mock_opensearch_client):
    """Test OpenSearch health check when unhealthy."""
    opensearch_provider.client = mock_opensearch_client
    opensearch_provider._initialized = True

    mock_opensearch_client.ping.side_effect = Exception("Connection error")

    result = await opensearch_provider.health_check()

    assert result is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_opensearch_health_check_not_initialized(opensearch_provider):
    """Test OpenSearch health check when not initialized."""
    opensearch_provider._initialized = False

    result = await opensearch_provider.health_check()

    assert result is False

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.vdb, pytest.mark.fast]

