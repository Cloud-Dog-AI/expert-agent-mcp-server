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
Unit Test: UT1.17 - Weaviate Integration

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for Weaviate vector store provider integration

Related Requirements: FR1.3
Related Tasks: T016
Related Architecture: IP1.1.2
Related Tests: UT1.17

Recent Changes:
- Initial implementation
- Added precondition checks for Weaviate configuration
"""

import pytest
from unittest.mock import Mock, patch, AsyncMock
from src.core.vector.providers import WeaviateProvider
from src.config.loader import get_config


@pytest.fixture(autouse=True)
def check_weaviate_config():
    """Check if Weaviate configuration is available before running tests."""
    # Unit tests use mocks; we only ensure config system is initialised.
    # (No direct os.environ access; config comes via --env + src.config.loader.)
    _ = get_config("llm.base_url")


@pytest.fixture
def weaviate_provider():
    """Create a Weaviate provider instance."""
    return WeaviateProvider()


@pytest.fixture
def mock_weaviate_client():
    """Create a mock Weaviate client."""
    mock_client = Mock()
    mock_client.schema = Mock()
    mock_client.schema.exists = Mock(return_value=False)
    mock_client.schema.create_class = Mock()
    mock_client.data_object = Mock()
    mock_client.query = Mock()
    return mock_client


def _require_weaviate_test_config():
    url = get_config("test.vector_stores.weaviate.url")
    api_key = get_config("test.vector_stores.weaviate.api_key")
    collection_name = get_config("test.vector_stores.weaviate.collection_name")
    if not url or not collection_name:
        pytest.fail("Missing test.vector_stores.weaviate.url/collection_name in config")
    return url, api_key, collection_name
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_weaviate_initialization_success(weaviate_provider, mock_weaviate_client):
    """Test successful Weaviate initialization."""
    url, api_key, collection_name = _require_weaviate_test_config()
    config = {
        "url": str(url),
        "api_key": str(api_key) if api_key is not None else None,
        "collection_name": str(collection_name),
    }

    with patch("weaviate.Client", return_value=mock_weaviate_client):
        with patch("weaviate.auth.AuthApiKey"):
            with patch.object(
                weaviate_provider.embedding_manager, "initialize", new_callable=AsyncMock
            ) as mock_init:
                with patch.object(
                    weaviate_provider.embedding_manager,
                    "get_embedding_dimension",
                    return_value=1024,
                ):
                    mock_init.return_value = None
                    result = await weaviate_provider.initialize(config)

                    assert result is True
                    assert weaviate_provider._initialized is True
                    assert weaviate_provider.client is not None
                    assert await weaviate_provider.health_check() is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_weaviate_initialization_existing_collection(weaviate_provider, mock_weaviate_client):
    """Test Weaviate initialization with existing collection."""
    url, api_key, collection_name = _require_weaviate_test_config()
    config = {"url": str(url), "collection_name": str(collection_name)}

    mock_weaviate_client.schema.exists.return_value = True

    with patch("weaviate.Client", return_value=mock_weaviate_client):
        with patch.object(
            weaviate_provider.embedding_manager, "initialize", new_callable=AsyncMock
        ):
            with patch.object(
                weaviate_provider.embedding_manager, "get_embedding_dimension", return_value=1024
            ):
                result = await weaviate_provider.initialize(config)

                assert result is True
                assert weaviate_provider._initialized is True
                mock_weaviate_client.schema.create_class.assert_not_called()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_weaviate_initialization_no_api_key(weaviate_provider, mock_weaviate_client):
    """Test Weaviate initialization without API key."""
    url, _, collection_name = _require_weaviate_test_config()
    config = {"url": str(url), "collection_name": str(collection_name)}

    with patch("weaviate.Client", return_value=mock_weaviate_client):
        with patch.object(
            weaviate_provider.embedding_manager, "initialize", new_callable=AsyncMock
        ):
            with patch.object(
                weaviate_provider.embedding_manager, "get_embedding_dimension", return_value=1024
            ):
                result = await weaviate_provider.initialize(config)

                assert result is True
                assert weaviate_provider._initialized is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_weaviate_initialization_import_error(weaviate_provider):
    """Test Weaviate initialization when runtime client deps are unavailable."""
    url, _, collection_name = _require_weaviate_test_config()
    config = {"url": str(url), "collection_name": str(collection_name)}

    with patch.object(
        weaviate_provider.embedding_manager, "initialize", new_callable=AsyncMock
    ) as mock_init:
        mock_init.return_value = None
        with patch.object(weaviate_provider.__class__, "_shared_clients", {}):
            with patch(
                "src.core.vector.providers.build_runtime_client",
                side_effect=ImportError("No module named 'weaviate'"),
            ):
                result = await weaviate_provider.initialize(config)

                assert result is False
                assert weaviate_provider._initialized is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_weaviate_add_documents(weaviate_provider, mock_weaviate_client):
    """Test adding documents to Weaviate."""
    # Initialize provider
    weaviate_provider.client = mock_weaviate_client
    weaviate_provider._initialized = True

    documents = ["Document 1", "Document 2"]
    metadatas = [{"source": "test1"}, {"source": "test2"}]
    ids = ["id1", "id2"]

    mock_embeddings = [[0.1] * 1024, [0.2] * 1024]

    mock_batch = Mock()
    mock_batch.__enter__ = Mock(return_value=mock_batch)
    mock_batch.__exit__ = Mock(return_value=None)
    mock_batch.add_data_object = Mock()
    mock_weaviate_client.batch = mock_batch

    with patch.object(
        weaviate_provider.embedding_manager, "generate_batch_embeddings", new_callable=AsyncMock
    ) as mock_emb:
        mock_emb.return_value = mock_embeddings

        result = await weaviate_provider.add_documents(
            collection="test_collection", documents=documents, metadatas=metadatas, ids=ids
        )

        assert len(result) == 2
        assert result == ids
        assert mock_batch.add_data_object.call_count == 2
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_weaviate_add_documents_auto_ids(weaviate_provider, mock_weaviate_client):
    """Test adding documents with auto-generated IDs."""
    weaviate_provider.client = mock_weaviate_client
    weaviate_provider._initialized = True

    documents = ["Document 1"]
    mock_embeddings = [[0.1] * 1024]

    mock_batch = Mock()
    mock_batch.__enter__ = Mock(return_value=mock_batch)
    mock_batch.__exit__ = Mock(return_value=None)
    mock_batch.add_data_object = Mock()
    mock_weaviate_client.batch = mock_batch

    with patch.object(
        weaviate_provider.embedding_manager, "generate_batch_embeddings", new_callable=AsyncMock
    ) as mock_emb:
        mock_emb.return_value = mock_embeddings

        result = await weaviate_provider.add_documents(
            collection="test_collection", documents=documents
        )

        assert len(result) == 1
        assert isinstance(result[0], str)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_weaviate_add_documents_not_initialized(weaviate_provider):
    """Test adding documents when provider is not initialized."""
    weaviate_provider._initialized = False

    with pytest.raises(RuntimeError, match="Weaviate provider not initialized"):
        await weaviate_provider.add_documents(
            collection="test_collection", documents=["Document 1"]
        )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_weaviate_search(weaviate_provider, mock_weaviate_client):
    """Test searching Weaviate collection."""
    weaviate_provider.client = mock_weaviate_client
    weaviate_provider._initialized = True

    query = "test query"
    query_vector = [0.1] * 1024

    # Mock query builder chain
    mock_query_builder = Mock()
    mock_query_builder.with_near_vector = Mock(return_value=mock_query_builder)
    mock_query_builder.with_limit = Mock(return_value=mock_query_builder)
    mock_query_builder.with_where = Mock(return_value=mock_query_builder)
    mock_query_builder.do.return_value = {
        "data": {
            "Get": {
                "test_collection": [
                    {
                        "text": "Result 1",
                        "metadata": '{"source": "test1"}',
                        "_additional": {"id": "id1", "certainty": 0.9},
                    },
                    {
                        "text": "Result 2",
                        "metadata": '{"source": "test2"}',
                        "_additional": {"id": "id2", "certainty": 0.8},
                    },
                ]
            }
        }
    }
    mock_weaviate_client.query.get.return_value = mock_query_builder

    with patch.object(
        weaviate_provider.embedding_manager, "generate_embedding", new_callable=AsyncMock
    ) as mock_emb:
        mock_emb.return_value = query_vector

        results = await weaviate_provider.search(
            collection="test_collection", query=query, n_results=2
        )

        assert len(results) == 2
        assert results[0]["document"] == "Result 1"
        assert results[1]["document"] == "Result 2"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_weaviate_search_with_filter(weaviate_provider, mock_weaviate_client):
    """Test searching Weaviate with metadata filter."""
    weaviate_provider.client = mock_weaviate_client
    weaviate_provider._initialized = True

    query = "test query"
    query_vector = [0.1] * 1024
    filter_dict = {"source": "test1"}

    mock_query_builder = Mock()
    mock_query_builder.with_near_vector = Mock(return_value=mock_query_builder)
    mock_query_builder.with_limit = Mock(return_value=mock_query_builder)
    mock_query_builder.with_where = Mock(return_value=mock_query_builder)
    mock_query_builder.do.return_value = {
        "data": {
            "Get": {
                "test_collection": [
                    {
                        "text": "Result 1",
                        "metadata": '{"source": "test1"}',
                        "_additional": {"id": "id1", "certainty": 0.9},
                    }
                ]
            }
        }
    }
    mock_weaviate_client.query.get.return_value = mock_query_builder

    with patch.object(
        weaviate_provider.embedding_manager, "generate_embedding", new_callable=AsyncMock
    ) as mock_emb:
        mock_emb.return_value = query_vector

        results = await weaviate_provider.search(
            collection="test_collection", query=query, n_results=5, filter=filter_dict
        )

        assert len(results) == 1
        # Verify filter was applied (check that with_where was called)
        mock_query_builder.with_where.assert_called_once()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_weaviate_search_not_initialized(weaviate_provider):
    """Test searching when provider is not initialized."""
    weaviate_provider._initialized = False

    with pytest.raises(RuntimeError, match="Weaviate provider not initialized"):
        await weaviate_provider.search(collection="test_collection", query="test query")
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_weaviate_delete_document(weaviate_provider, mock_weaviate_client):
    """Test deleting a document from Weaviate."""
    weaviate_provider.client = mock_weaviate_client
    weaviate_provider._initialized = True

    mock_weaviate_client.data_object.delete = Mock()

    result = await weaviate_provider.delete_document(
        collection="test_collection", doc_id="doc_id_1"
    )

    assert result is True
    mock_weaviate_client.data_object.delete.assert_called_once_with(
        uuid="doc_id_1", class_name="test_collection"
    )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_weaviate_update_document(weaviate_provider, mock_weaviate_client):
    """Test updating a document in Weaviate."""
    weaviate_provider.client = mock_weaviate_client
    weaviate_provider._initialized = True

    document_id = "doc_id_1"
    new_text = "Updated document"
    new_metadata = {"source": "updated"}
    new_vector = [0.2] * 1024

    mock_weaviate_client.data_object.update = Mock()

    with patch.object(
        weaviate_provider.embedding_manager, "generate_embedding", new_callable=AsyncMock
    ) as mock_emb:
        mock_emb.return_value = new_vector

        result = await weaviate_provider.update_document(
            collection="test_collection",
            doc_id=document_id,
            content=new_text,
            metadata=new_metadata,
        )

        assert result is True
        mock_weaviate_client.data_object.update.assert_called_once()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_weaviate_count_documents(weaviate_provider, mock_weaviate_client):
    """Test counting documents in Weaviate collection."""
    weaviate_provider.client = mock_weaviate_client
    weaviate_provider._initialized = True

    # Mock aggregate query builder chain
    mock_aggregate = Mock()
    mock_aggregate.with_meta_count = Mock(return_value=mock_aggregate)
    mock_aggregate.with_where = Mock(return_value=mock_aggregate)
    mock_aggregate.do.return_value = {
        "data": {"Aggregate": {"test_collection": [{"meta": {"count": 42}}]}}
    }
    mock_weaviate_client.query.aggregate.return_value = mock_aggregate

    count = await weaviate_provider.count_documents("test_collection")

    assert count == 42
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_weaviate_health_check_healthy(weaviate_provider, mock_weaviate_client):
    """Test Weaviate health check when healthy."""
    weaviate_provider.client = mock_weaviate_client
    weaviate_provider._initialized = True

    mock_weaviate_client.is_ready.return_value = True

    result = await weaviate_provider.health_check()

    assert result is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_weaviate_health_check_unhealthy(weaviate_provider, mock_weaviate_client):
    """Test Weaviate health check when unhealthy."""
    weaviate_provider.client = mock_weaviate_client
    weaviate_provider._initialized = True

    mock_weaviate_client.is_ready.side_effect = Exception("Connection error")

    result = await weaviate_provider.health_check()

    assert result is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_weaviate_health_check_not_initialized(weaviate_provider):
    """Test Weaviate health check when not initialized."""
    weaviate_provider._initialized = False

    result = await weaviate_provider.health_check()

    assert result is False

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.vdb, pytest.mark.fast]

