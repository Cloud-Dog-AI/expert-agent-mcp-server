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
Description: Tests for indexing options, metadata fields, and search functionality

Related Requirements: FR1.3
Related Tasks: T017, T021
Related Architecture: CC4.1.2
Related Tests: UT1.21

Recent Changes:
- Initial implementation
"""

import pytest
import json
from unittest.mock import Mock, AsyncMock
from src.config.loader import get_config
from src.core.vector.indexing import (
    VectorIndexingManager,
    IndexFormat,
    MetadataFieldType,
    IndexingConfig,
    MetadataField,
)
from src.database.models import VectorStore as VectorStoreModel


@pytest.fixture
def indexing_manager(db_session):
    """Create a VectorIndexingManager instance."""
    return VectorIndexingManager(db=db_session)


@pytest.fixture
def mock_vector_store(db_session):
    """Create a mock vector store."""
    qdrant_host = get_config("vector_stores_config.qdrant._DEFAULT_.host")
    qdrant_port = get_config("vector_stores_config.qdrant._DEFAULT_.port")
    if not qdrant_host or qdrant_port is None:
        pytest.fail("Missing vector_stores_config.qdrant._DEFAULT_.host/port in config (--env)")
    store = VectorStoreModel(
        name="test_store",
        type="qdrant",
        enabled=True,
        config_json=json.dumps({"host": qdrant_host, "port": int(qdrant_port)}),
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
    provider.add_documents = AsyncMock(return_value=["doc1", "doc2"])
    provider.search = AsyncMock(
        return_value=[
            {
                "id": "doc1",
                "document": "Test document",
                "metadata": {"source": "test"},
                "score": 0.9,
            }
        ]
    )
    provider.initialize = AsyncMock(return_value=True)
    return provider
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_get_supported_formats(indexing_manager):
    """Test getting list of supported formats."""
    formats = indexing_manager.get_supported_formats()

    assert isinstance(formats, list)
    assert len(formats) > 0
    assert "text" in formats
    assert "json" in formats
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_get_supported_metadata_types(indexing_manager):
    """Test getting list of supported metadata field types."""
    types = indexing_manager.get_supported_metadata_types()

    assert isinstance(types, list)
    assert len(types) > 0
    assert "string" in types
    assert "integer" in types
    assert "datetime" in types
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_create_indexing_config(indexing_manager):
    """Test creating indexing configuration."""
    config = indexing_manager.create_indexing_config(
        format=IndexFormat.TEXT, chunk_size=500, chunk_overlap=100
    )

    assert isinstance(config, IndexingConfig)
    assert config.format == IndexFormat.TEXT
    assert config.chunk_size == 500
    assert config.chunk_overlap == 100
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_create_indexing_config_with_metadata_fields(indexing_manager):
    """Test creating indexing configuration with metadata fields."""
    metadata_fields = [
        MetadataField(name="source", field_type=MetadataFieldType.STRING),
        MetadataField(name="timestamp", field_type=MetadataFieldType.DATETIME),
    ]

    config = indexing_manager.create_indexing_config(
        format=IndexFormat.JSON, metadata_fields=metadata_fields
    )

    assert len(config.metadata_fields) == 2
    assert config.metadata_fields[0]["name"] == "source"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_add_metadata_field(indexing_manager):
    """Test adding metadata field to configuration."""
    config = indexing_manager.create_indexing_config()

    updated_config = indexing_manager.add_metadata_field(
        config=config,
        name="category",
        field_type=MetadataFieldType.STRING,
        required=True,
        default_value="default",
    )

    assert len(updated_config.metadata_fields) == 1
    assert updated_config.metadata_fields[0]["name"] == "category"
    assert updated_config.metadata_fields[0]["required"] is True
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_indexing_config_to_dict(indexing_manager):
    """Test converting indexing config to dictionary."""
    config = indexing_manager.create_indexing_config(format=IndexFormat.MARKDOWN, chunk_size=2000)

    config_dict = config.to_dict()

    assert isinstance(config_dict, dict)
    assert config_dict["format"] == "markdown"
    assert config_dict["chunk_size"] == 2000
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_indexing_config_from_dict(indexing_manager):
    """Test creating indexing config from dictionary."""
    config_dict = {
        "format": "html",
        "chunk_size": 1500,
        "chunk_overlap": 300,
        "metadata_fields": [],
    }

    config = IndexingConfig.from_dict(config_dict)

    assert config.format == IndexFormat.HTML
    assert config.chunk_size == 1500
    assert config.chunk_overlap == 300
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_index_documents(indexing_manager, mock_vector_store, mock_provider):
    """Test indexing documents with configuration."""
    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = mock_vector_store
    mock_vm._get_provider.return_value = mock_provider
    indexing_manager._vector_manager = mock_vm

    config = indexing_manager.create_indexing_config(format=IndexFormat.TEXT)
    documents = ["Document 1", "Document 2"]

    result = await indexing_manager.index_documents(
        store_name="test_store", collection="test_collection", documents=documents, config=config
    )

    assert isinstance(result, list)
    assert len(result) == 2
    assert mock_provider.add_documents.called
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_index_documents_with_metadata(indexing_manager, mock_vector_store, mock_provider):
    """Test indexing documents with custom metadata."""
    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = mock_vector_store
    mock_vm._get_provider.return_value = mock_provider
    indexing_manager._vector_manager = mock_vm

    metadata_fields = [MetadataField(name="source", field_type=MetadataFieldType.STRING)]
    config = indexing_manager.create_indexing_config(
        format=IndexFormat.TEXT, metadata_fields=metadata_fields
    )

    documents = ["Document 1"]
    metadatas = [{"source": "test"}]

    result = await indexing_manager.index_documents(
        store_name="test_store",
        collection="test_collection",
        documents=documents,
        config=config,
        metadatas=metadatas,
    )

    assert len(result) > 0
    assert mock_provider.add_documents.called
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_index_documents_chunking(indexing_manager, mock_vector_store, mock_provider):
    """Test that documents are chunked when exceeding chunk_size."""
    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = mock_vector_store
    mock_vm._get_provider.return_value = mock_provider
    indexing_manager._vector_manager = mock_vm

    # Create a long document that will be chunked
    long_document = "A" * 2500  # Exceeds default chunk_size of 1000
    config = indexing_manager.create_indexing_config(
        format=IndexFormat.TEXT, chunk_size=1000, chunk_overlap=200
    )

    result = await indexing_manager.index_documents(
        store_name="test_store",
        collection="test_collection",
        documents=[long_document],
        config=config,
    )

    # Should create multiple chunks
    assert len(result) > 1
    assert mock_provider.add_documents.called
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_index_documents_json_format(indexing_manager, mock_vector_store, mock_provider):
    """Test indexing JSON format documents."""
    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = mock_vector_store
    mock_vm._get_provider.return_value = mock_provider
    indexing_manager._vector_manager = mock_vm

    json_doc = json.dumps({"title": "Test", "content": "Test content"})
    config = indexing_manager.create_indexing_config(format=IndexFormat.JSON)

    result = await indexing_manager.index_documents(
        store_name="test_store", collection="test_collection", documents=[json_doc], config=config
    )

    assert len(result) > 0
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_index_documents_html_format(indexing_manager, mock_vector_store, mock_provider):
    """Test indexing HTML format documents."""
    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = mock_vector_store
    mock_vm._get_provider.return_value = mock_provider
    indexing_manager._vector_manager = mock_vm

    html_doc = "<html><body><p>Test content</p></body></html>"
    config = indexing_manager.create_indexing_config(format=IndexFormat.HTML)

    result = await indexing_manager.index_documents(
        store_name="test_store", collection="test_collection", documents=[html_doc], config=config
    )

    assert len(result) > 0
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_index_documents_error_handling(indexing_manager, mock_vector_store, mock_provider):
    """Test error handling during indexing."""
    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = mock_vector_store
    mock_vm._get_provider.return_value = mock_provider
    indexing_manager._vector_manager = mock_vm

    mock_provider.add_documents.side_effect = Exception("Indexing failed")
    config = indexing_manager.create_indexing_config()

    with pytest.raises(Exception):
        await indexing_manager.index_documents(
            store_name="test_store", collection="test_collection", documents=["Test"], config=config
        )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_index_documents_store_not_found(indexing_manager):
    """Test indexing when vector store is not found."""
    mock_vm = Mock()
    mock_vm.get_vector_store.return_value = None
    indexing_manager._vector_manager = mock_vm

    config = indexing_manager.create_indexing_config()

    with pytest.raises(ValueError, match="not found or disabled"):
        await indexing_manager.index_documents(
            store_name="nonexistent_store",
            collection="test_collection",
            documents=["Test"],
            config=config,
        )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_metadata_field_to_dict():
    """Test converting metadata field to dictionary."""
    field = MetadataField(
        name="source", field_type=MetadataFieldType.STRING, required=True, default_value="default"
    )

    field_dict = field.to_dict()

    assert field_dict["name"] == "source"
    assert field_dict["type"] == "string"
    assert field_dict["required"] is True
    assert field_dict["default_value"] == "default"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_metadata_field_from_dict():
    """Test creating metadata field from dictionary."""
    field_dict = {"name": "timestamp", "type": "datetime", "required": False}

    field = MetadataField.from_dict(field_dict)

    assert field.name == "timestamp"
    assert field.field_type == MetadataFieldType.DATETIME
    assert field.required is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_indexing_config_metadata_enrichment(indexing_manager):
    """Test that metadata is enriched with default values."""
    metadata_fields = [
        MetadataField(
            name="source",
            field_type=MetadataFieldType.STRING,
            required=True,
            default_value="default_source",
        )
    ]
    config = indexing_manager.create_indexing_config(metadata_fields=metadata_fields)

    # Test metadata enrichment (internal method)
    documents = ["Document 1"]
    enriched = indexing_manager._enrich_metadata(documents, config, metadatas=[])

    assert len(enriched) == 1
    assert enriched[0]["source"] == "default_source"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_indexing_config_metadata_validation(indexing_manager):
    """Test that metadata field types are validated."""
    metadata_fields = [MetadataField(name="count", field_type=MetadataFieldType.INTEGER)]
    config = indexing_manager.create_indexing_config(metadata_fields=metadata_fields)

    documents = ["Document 1"]
    metadatas = [{"count": "123"}]  # String that should be converted to int

    enriched = indexing_manager._enrich_metadata(documents, config, metadatas=metadatas)

    assert isinstance(enriched[0]["count"], int)
    assert enriched[0]["count"] == 123

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.vdb, pytest.mark.db, pytest.mark.fast]

