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
Unit Test: UT1.20 - PGVector Integration

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for PGVector (PostgreSQL extension) vector store provider integration

Related Requirements: FR1.3
Related Tasks: T016
Related Architecture: IP1.1.2
Related Tests: UT1.20

Recent Changes:
- Initial implementation
"""

import importlib.util
from unittest.mock import AsyncMock, patch

import pytest
from src.core.vector.providers import PGVectorProvider
from src.config.loader import get_config


@pytest.fixture
def pgvector_provider():
    """Create a PGVector provider instance."""
    return PGVectorProvider()


@pytest.fixture
def mock_asyncpg_connection():
    """Create a mock asyncpg connection."""
    mock_conn = AsyncMock()
    mock_conn.execute = AsyncMock()
    mock_conn.fetch = AsyncMock()
    mock_conn.fetchval = AsyncMock(return_value=1)
    return mock_conn


def _require_pgvector_test_config():
    host = get_config("test.vector_stores.pgvector.host")
    port = get_config("test.vector_stores.pgvector.port")
    database = get_config("test.vector_stores.pgvector.database")
    username = get_config("test.vector_stores.pgvector.username")
    password = get_config("test.vector_stores.pgvector.password")
    collection_name = get_config("test.vector_stores.pgvector.collection_name")
    database_uri = get_config("test.vector_stores.pgvector.database_uri")
    if not host or port is None or not database or not username or not collection_name:
        pytest.fail("Missing test.vector_stores.pgvector.* in config")
    return host, port, database, username, password, collection_name, database_uri
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_pgvector_initialization_success(pgvector_provider, mock_asyncpg_connection):
    """Test successful PGVector initialization."""
    if importlib.util.find_spec("asyncpg") is None or importlib.util.find_spec("pgvector") is None:
        pytest.fail("asyncpg or pgvector not installed")

    host, port, database, username, password, collection_name, _ = _require_pgvector_test_config()
    config = {
        "host": str(host),
        "port": int(port),
        "database": str(database),
        "username": str(username),
        "password": str(password) if password is not None else None,
        "collection_name": str(collection_name),
    }

    with patch("asyncpg.connect", return_value=mock_asyncpg_connection):
        with patch("pgvector.asyncpg.register_vector", new_callable=AsyncMock):
            with patch.object(
                pgvector_provider.embedding_manager, "initialize", new_callable=AsyncMock
            ) as mock_init:
                with patch.object(
                    pgvector_provider.embedding_manager,
                    "get_embedding_dimension",
                    return_value=1024,
                ):
                    mock_init.return_value = None

                    result = await pgvector_provider.initialize(config)

                    assert result is True
                    assert pgvector_provider._initialized is True
                    assert pgvector_provider.client is not None
                    assert await pgvector_provider.health_check() is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_pgvector_initialization_with_uri(pgvector_provider, mock_asyncpg_connection):
    """Test PGVector initialization with database URI."""
    if importlib.util.find_spec("asyncpg") is None or importlib.util.find_spec("pgvector") is None:
        pytest.fail("asyncpg or pgvector not installed")

    _, _, _, _, _, collection_name, database_uri = _require_pgvector_test_config()
    if not database_uri:
        pytest.fail("Missing test.vector_stores.pgvector.database_uri in config")
    config = {"database_uri": str(database_uri), "collection_name": str(collection_name)}

    with patch("asyncpg.connect", return_value=mock_asyncpg_connection):
        with patch("pgvector.asyncpg.register_vector", new_callable=AsyncMock):
            with patch.object(
                pgvector_provider.embedding_manager, "initialize", new_callable=AsyncMock
            ) as mock_init:
                with patch.object(
                    pgvector_provider.embedding_manager,
                    "get_embedding_dimension",
                    return_value=1024,
                ):
                    mock_init.return_value = None

                    result = await pgvector_provider.initialize(config)

                    assert result is True
                    assert pgvector_provider._initialized is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_pgvector_initialization_import_error(pgvector_provider):
    """Test PGVector initialization when dependencies are not installed."""
    host, port, database, _, _, collection_name, _ = _require_pgvector_test_config()
    config = {
        "host": str(host),
        "port": int(port),
        "database": str(database),
        "collection_name": str(collection_name),
    }

    with patch("builtins.__import__", side_effect=ImportError("No module named 'asyncpg'")):
        result = await pgvector_provider.initialize(config)

        assert result is False
        assert pgvector_provider._initialized is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_pgvector_add_documents(pgvector_provider, mock_asyncpg_connection):
    """Test adding documents to PGVector table."""
    _, _, _, _, _, collection_name, _ = _require_pgvector_test_config()
    pgvector_provider.client = mock_asyncpg_connection
    pgvector_provider._initialized = True

    documents = ["Document 1", "Document 2"]
    metadatas = [{"source": "test1"}, {"source": "test2"}]
    ids = ["id1", "id2"]

    mock_embeddings = [[0.1] * 1024, [0.2] * 1024]

    with patch.object(
        pgvector_provider.embedding_manager, "generate_batch_embeddings", new_callable=AsyncMock
    ) as mock_emb:
        mock_emb.return_value = mock_embeddings

        result = await pgvector_provider.add_documents(
            collection=str(collection_name), documents=documents, metadatas=metadatas, ids=ids
        )

        assert len(result) == 2
        assert result == ids
        assert mock_asyncpg_connection.execute.call_count == 2
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_pgvector_add_documents_auto_ids(pgvector_provider, mock_asyncpg_connection):
    """Test adding documents with auto-generated IDs."""
    _, _, _, _, _, collection_name, _ = _require_pgvector_test_config()
    pgvector_provider.client = mock_asyncpg_connection
    pgvector_provider._initialized = True

    documents = ["Document 1"]
    mock_embeddings = [[0.1] * 1024]

    with patch.object(
        pgvector_provider.embedding_manager, "generate_batch_embeddings", new_callable=AsyncMock
    ) as mock_emb:
        mock_emb.return_value = mock_embeddings

        result = await pgvector_provider.add_documents(
            collection=str(collection_name), documents=documents
        )

        assert len(result) == 1
        assert isinstance(result[0], str)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_pgvector_add_documents_not_initialized(pgvector_provider):
    """Test adding documents when provider is not initialized."""
    _, _, _, _, _, collection_name, _ = _require_pgvector_test_config()
    pgvector_provider._initialized = False

    with pytest.raises(RuntimeError, match="PGVector provider not initialized"):
        await pgvector_provider.add_documents(
            collection=str(collection_name), documents=["Document 1"]
        )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_pgvector_search(pgvector_provider, mock_asyncpg_connection):
    """Test searching PGVector table."""
    _, _, _, _, _, collection_name, _ = _require_pgvector_test_config()
    pgvector_provider.client = mock_asyncpg_connection
    pgvector_provider._initialized = True

    query = "test query"
    query_vector = [0.1] * 1024

    # Mock fetch results - use dict-like access
    mock_row1 = {
        "id": "id1",
        "text": "Result 1",
        "metadata": '{"source": "test1"}',
        "similarity": 0.9,
    }

    mock_row2 = {
        "id": "id2",
        "text": "Result 2",
        "metadata": '{"source": "test2"}',
        "similarity": 0.8,
    }

    mock_asyncpg_connection.fetch.return_value = [mock_row1, mock_row2]

    with patch.object(
        pgvector_provider.embedding_manager, "generate_embedding", new_callable=AsyncMock
    ) as mock_emb:
        mock_emb.return_value = query_vector

        results = await pgvector_provider.search(
            collection=str(collection_name), query=query, n_results=2
        )

        assert len(results) == 2
        assert results[0]["document"] == "Result 1"
        assert results[1]["document"] == "Result 2"
        assert results[0]["score"] == 0.9
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_pgvector_search_with_filter(pgvector_provider, mock_asyncpg_connection):
    """Test searching PGVector with metadata filter."""
    _, _, _, _, _, collection_name, _ = _require_pgvector_test_config()
    pgvector_provider.client = mock_asyncpg_connection
    pgvector_provider._initialized = True

    query = "test query"
    query_vector = [0.1] * 1024
    filter_dict = {"source": "test1"}

    mock_row = {
        "id": "id1",
        "text": "Result 1",
        "metadata": '{"source": "test1"}',
        "similarity": 0.9,
    }

    mock_asyncpg_connection.fetch.return_value = [mock_row]

    with patch.object(
        pgvector_provider.embedding_manager, "generate_embedding", new_callable=AsyncMock
    ) as mock_emb:
        mock_emb.return_value = query_vector

        results = await pgvector_provider.search(
            collection=str(collection_name), query=query, n_results=5, filter=filter_dict
        )

        assert len(results) == 1
        # Verify filter was applied (check that fetch was called)
        assert mock_asyncpg_connection.fetch.called
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_pgvector_search_not_initialized(pgvector_provider):
    """Test searching when provider is not initialized."""
    _, _, _, _, _, collection_name, _ = _require_pgvector_test_config()
    pgvector_provider._initialized = False

    with pytest.raises(RuntimeError, match="PGVector provider not initialized"):
        await pgvector_provider.search(collection=str(collection_name), query="test query")
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_pgvector_delete_document(pgvector_provider, mock_asyncpg_connection):
    """Test deleting a document from PGVector table."""
    _, _, _, _, _, collection_name, _ = _require_pgvector_test_config()
    pgvector_provider.client = mock_asyncpg_connection
    pgvector_provider._initialized = True

    result = await pgvector_provider.delete_document(
        collection=str(collection_name), doc_id="doc_id_1"
    )

    assert result is True
    assert mock_asyncpg_connection.execute.called
    # Verify DELETE query was executed
    call_args = str(mock_asyncpg_connection.execute.call_args)
    assert "DELETE" in call_args or "delete" in call_args.lower()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_pgvector_update_document(pgvector_provider, mock_asyncpg_connection):
    """Test updating a document in PGVector table."""
    _, _, _, _, _, collection_name, _ = _require_pgvector_test_config()
    pgvector_provider.client = mock_asyncpg_connection
    pgvector_provider._initialized = True

    document_id = "doc_id_1"
    new_text = "Updated document"
    new_metadata = {"source": "updated"}
    new_vector = [0.2] * 1024

    with patch.object(
        pgvector_provider.embedding_manager, "generate_embedding", new_callable=AsyncMock
    ) as mock_emb:
        mock_emb.return_value = new_vector

        result = await pgvector_provider.update_document(
            collection=str(collection_name),
            doc_id=document_id,
            content=new_text,
            metadata=new_metadata,
        )

        assert result is True
        assert mock_asyncpg_connection.execute.called
        # Verify UPDATE query was executed
        call_args = str(mock_asyncpg_connection.execute.call_args)
        assert "UPDATE" in call_args or "update" in call_args.lower()
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_pgvector_count_documents(pgvector_provider, mock_asyncpg_connection):
    """Test counting documents in PGVector table."""
    _, _, _, _, _, collection_name, _ = _require_pgvector_test_config()
    pgvector_provider.client = mock_asyncpg_connection
    pgvector_provider._initialized = True

    mock_asyncpg_connection.fetchval.return_value = 42

    count = await pgvector_provider.count_documents(str(collection_name))

    assert count == 42
    assert mock_asyncpg_connection.fetchval.called
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_pgvector_count_documents_with_filter(pgvector_provider, mock_asyncpg_connection):
    """Test counting documents with metadata filter."""
    _, _, _, _, _, collection_name, _ = _require_pgvector_test_config()
    pgvector_provider.client = mock_asyncpg_connection
    pgvector_provider._initialized = True

    filter_dict = {"source": "test1"}
    mock_asyncpg_connection.fetchval.return_value = 10

    count = await pgvector_provider.count_documents(str(collection_name), filter=filter_dict)

    assert count == 10
    assert mock_asyncpg_connection.fetchval.called
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_pgvector_health_check_healthy(pgvector_provider, mock_asyncpg_connection):
    """Test PGVector health check when healthy."""
    pgvector_provider.client = mock_asyncpg_connection
    pgvector_provider._initialized = True

    mock_asyncpg_connection.fetchval.return_value = 1

    result = await pgvector_provider.health_check()

    assert result is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_pgvector_health_check_unhealthy(pgvector_provider, mock_asyncpg_connection):
    """Test PGVector health check when unhealthy."""
    pgvector_provider.client = mock_asyncpg_connection
    pgvector_provider._initialized = True

    mock_asyncpg_connection.fetchval.side_effect = Exception("Connection error")

    result = await pgvector_provider.health_check()

    assert result is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_pgvector_health_check_not_initialized(pgvector_provider):
    """Test PGVector health check when not initialized."""
    pgvector_provider._initialized = False

    result = await pgvector_provider.health_check()

    assert result is False

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.vdb, pytest.mark.db, pytest.mark.fast]

