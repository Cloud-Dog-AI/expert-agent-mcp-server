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
Vector Store Indexing Options

License: Apache 2.0
Ownership: Cloud Dog
Description: Provides all indexing options on format and metadata setup/fields

Related Requirements: FR1.3
Related Tasks: T021
Related Architecture: CC4.1.2
Related Tests: UT1.21

Recent Changes:
- Initial implementation
"""

from typing import List, Dict, Any, Optional, TYPE_CHECKING
from enum import Enum
from sqlalchemy.orm import Session
import json

from src.utils.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class IndexFormat(str, Enum):
    """Supported indexing formats."""

    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"
    HTML = "html"
    PDF = "pdf"
    CSV = "csv"
    CUSTOM = "custom"


class MetadataFieldType(str, Enum):
    """Supported metadata field types."""

    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    DATE = "date"
    DATETIME = "datetime"
    ARRAY = "array"
    OBJECT = "object"


class IndexingConfig:
    """Configuration for indexing operations."""

    def __init__(
        self,
        format: IndexFormat = IndexFormat.TEXT,
        metadata_fields: Optional[List[Dict[str, Any]]] = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
        include_metadata: bool = True,
        custom_parser: Optional[str] = None,
    ):
        """
        Initialize indexing configuration.

        Args:
            format: Document format
            metadata_fields: List of metadata field definitions
            chunk_size: Chunk size for splitting documents
            chunk_overlap: Overlap between chunks
            include_metadata: Whether to include metadata in index
            custom_parser: Custom parser function name
        """
        self.format = format
        self.metadata_fields = metadata_fields or []
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.include_metadata = include_metadata
        self.custom_parser = custom_parser

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "format": self.format.value,
            "metadata_fields": self.metadata_fields,
            "chunk_size": self.chunk_size,
            "chunk_overlap": self.chunk_overlap,
            "include_metadata": self.include_metadata,
            "custom_parser": self.custom_parser,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "IndexingConfig":
        """Create from dictionary."""
        return cls(
            format=IndexFormat(data.get("format", "text")),
            metadata_fields=data.get("metadata_fields", []),
            chunk_size=data.get("chunk_size", 1000),
            chunk_overlap=data.get("chunk_overlap", 200),
            include_metadata=data.get("include_metadata", True),
            custom_parser=data.get("custom_parser"),
        )


class MetadataField:
    """Metadata field definition."""

    def __init__(
        self,
        name: str,
        field_type: MetadataFieldType,
        required: bool = False,
        default_value: Any = None,
        description: Optional[str] = None,
        validation_rules: Optional[Dict[str, Any]] = None,
    ):
        """
        Initialize metadata field.

        Args:
            name: Field name
            field_type: Field type
            required: Whether field is required
            default_value: Default value
            description: Field description
            validation_rules: Validation rules
        """
        self.name = name
        self.field_type = field_type
        self.required = required
        self.default_value = default_value
        self.description = description
        self.validation_rules = validation_rules or {}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "type": self.field_type.value,
            "required": self.required,
            "default_value": self.default_value,
            "description": self.description,
            "validation_rules": self.validation_rules,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MetadataField":
        """Create from dictionary."""
        return cls(
            name=data["name"],
            field_type=MetadataFieldType(data["type"]),
            required=data.get("required", False),
            default_value=data.get("default_value"),
            description=data.get("description"),
            validation_rules=data.get("validation_rules", {}),
        )


class VectorIndexingManager:
    """Manages vector store indexing with format and metadata options."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize indexing manager.

        Args:
            db: Database session (if None, creates new)
        """
        self.db = db
        self._vector_manager = None

    @property
    def vector_manager(self):
        """Lazy import to avoid circular dependency."""
        if self._vector_manager is None:
            from src.core.vector.manager import VectorStoreManager

            self._vector_manager = VectorStoreManager(self.db)
        return self._vector_manager

    def create_indexing_config(
        self,
        format: IndexFormat = IndexFormat.TEXT,
        metadata_fields: Optional[List[MetadataField]] = None,
        chunk_size: int = 1000,
        chunk_overlap: int = 200,
    ) -> IndexingConfig:
        """
        Create indexing configuration.

        Args:
            format: Document format
            metadata_fields: List of metadata fields
            chunk_size: Chunk size
            chunk_overlap: Chunk overlap

        Returns:
            IndexingConfig instance
        """
        metadata_dicts = [field.to_dict() for field in (metadata_fields or [])]
        return IndexingConfig(
            format=format,
            metadata_fields=metadata_dicts,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )

    def add_metadata_field(
        self,
        config: IndexingConfig,
        name: str,
        field_type: MetadataFieldType,
        required: bool = False,
        default_value: Any = None,
        description: Optional[str] = None,
    ) -> IndexingConfig:
        """
        Add metadata field to indexing configuration.

        Args:
            config: Indexing configuration
            name: Field name
            field_type: Field type
            required: Whether required
            default_value: Default value
            description: Field description

        Returns:
            Updated IndexingConfig
        """
        field = MetadataField(
            name=name,
            field_type=field_type,
            required=required,
            default_value=default_value,
            description=description,
        )
        config.metadata_fields.append(field.to_dict())
        return config

    async def index_documents(
        self,
        store_name: str,
        collection: str,
        documents: List[str],
        config: IndexingConfig,
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> List[str]:
        """
        Index documents with format and metadata options.

        Args:
            store_name: Vector store name
            collection: Collection name
            documents: List of documents to index
            config: Indexing configuration
            metadatas: Optional metadata for each document

        Returns:
            List of document IDs
        """
        try:
            # Process documents based on format
            processed_docs = await self._process_documents(documents, config)

            # Validate and enrich metadata
            enriched_metadatas = self._enrich_metadata(processed_docs, config, metadatas)

            # Chunk documents if needed
            chunked_docs, chunked_metadatas = self._chunk_documents(
                processed_docs, enriched_metadatas, config
            )

            # Index documents
            vector_store = self.vector_manager.get_vector_store(name=store_name)
            if not vector_store or not vector_store.enabled:
                raise ValueError(f"Vector store '{store_name}' not found or disabled")

            provider = self.vector_manager._get_provider(vector_store.type)
            # Parse config_json if it's a string
            if vector_store.config_json:
                if isinstance(vector_store.config_json, str):
                    store_config = json.loads(vector_store.config_json)
                else:
                    store_config = vector_store.config_json
            else:
                store_config = {}

            # Initialize provider if needed
            if not hasattr(provider, "_initialized") or not provider._initialized:
                await provider.initialize(store_config)

            # Add documents to vector store
            ids = await provider.add_documents(
                collection=collection, documents=chunked_docs, metadatas=chunked_metadatas
            )

            logger.info(f"Indexed {len(ids)} document chunks in {store_name}/{collection}")
            return ids
        except Exception as e:
            logger.error(f"Failed to index documents: {e}", exc_info=True)
            raise

    async def _process_documents(self, documents: List[str], config: IndexingConfig) -> List[str]:
        """Process documents based on format."""
        processed = []

        for doc in documents:
            if config.format == IndexFormat.TEXT:
                processed.append(doc)
            elif config.format == IndexFormat.JSON:
                # Parse and extract text from JSON
                import json

                try:
                    data = json.loads(doc)
                    # Extract text fields
                    text = json.dumps(data, indent=2)
                    processed.append(text)
                except json.JSONDecodeError:
                    processed.append(doc)
            elif config.format == IndexFormat.MARKDOWN:
                # Markdown processing (could use markdown parser)
                processed.append(doc)
            elif config.format == IndexFormat.HTML:
                # HTML processing (could use BeautifulSoup)
                import re

                # Simple HTML tag removal
                text = re.sub(r"<[^>]+>", "", doc)
                processed.append(text)
            elif config.format == IndexFormat.CSV:
                # CSV processing
                processed.append(doc)
            else:
                processed.append(doc)

        return processed

    def _enrich_metadata(
        self,
        documents: List[str],
        config: IndexingConfig,
        metadatas: Optional[List[Dict[str, Any]]] = None,
    ) -> List[Dict[str, Any]]:
        """Validate and enrich metadata based on field definitions."""
        enriched = []

        for i, doc in enumerate(documents):
            metadata = metadatas[i] if metadatas and i < len(metadatas) else {}

            # Add default values for required fields
            for field_def in config.metadata_fields:
                field_name = field_def.get("name")
                if field_name not in metadata:
                    if field_def.get("required", False):
                        default = field_def.get("default_value")
                        if default is not None:
                            metadata[field_name] = default
                        else:
                            logger.warning(
                                f"Required metadata field '{field_name}' missing, using None"
                            )
                            metadata[field_name] = None
                    else:
                        # Optional field with default
                        default = field_def.get("default_value")
                        if default is not None:
                            metadata[field_name] = default

            # Validate field types
            for field_def in config.metadata_fields:
                field_name = field_def.get("name")
                if field_name in metadata:
                    field_type = MetadataFieldType(field_def.get("type", "string"))
                    metadata[field_name] = self._validate_field_type(
                        metadata[field_name], field_type
                    )

            enriched.append(metadata)

        return enriched

    def _validate_field_type(self, value: Any, field_type: MetadataFieldType) -> Any:
        """Validate and convert field value to correct type."""
        try:
            if field_type == MetadataFieldType.STRING:
                return str(value)
            elif field_type == MetadataFieldType.INTEGER:
                return int(value)
            elif field_type == MetadataFieldType.FLOAT:
                return float(value)
            elif field_type == MetadataFieldType.BOOLEAN:
                return bool(value)
            elif field_type == MetadataFieldType.DATE:
                from datetime import datetime

                if isinstance(value, str):
                    return datetime.fromisoformat(value).date().isoformat()
                return value
            elif field_type == MetadataFieldType.DATETIME:
                from datetime import datetime

                if isinstance(value, str):
                    return datetime.fromisoformat(value).isoformat()
                return value
            else:
                return value
        except (ValueError, TypeError) as e:
            logger.warning(f"Failed to validate field type {field_type}: {e}")
            return value

    def _chunk_documents(
        self, documents: List[str], metadatas: List[Dict[str, Any]], config: IndexingConfig
    ) -> tuple[List[str], List[Dict[str, Any]]]:
        """Chunk documents based on configuration."""
        chunked_docs = []
        chunked_metadatas = []

        for doc, metadata in zip(documents, metadatas):
            if len(doc) <= config.chunk_size:
                # Document fits in one chunk
                chunked_docs.append(doc)
                chunked_metadatas.append(metadata)
            else:
                # Split document into chunks
                chunks = self._split_text(
                    doc, chunk_size=config.chunk_size, chunk_overlap=config.chunk_overlap
                )

                for i, chunk in enumerate(chunks):
                    chunked_docs.append(chunk)
                    # Add chunk metadata
                    chunk_metadata = metadata.copy()
                    chunk_metadata["chunk_index"] = i
                    chunk_metadata["total_chunks"] = len(chunks)
                    chunked_metadatas.append(chunk_metadata)

        return chunked_docs, chunked_metadatas

    def _split_text(self, text: str, chunk_size: int, chunk_overlap: int) -> List[str]:
        """Split text into chunks with overlap."""
        chunks = []
        start = 0

        while start < len(text):
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)

            # Move start position with overlap
            start = end - chunk_overlap
            if start >= len(text):
                break

        return chunks

    def get_supported_formats(self) -> List[str]:
        """Get list of supported formats."""
        return [fmt.value for fmt in IndexFormat]

    def get_supported_metadata_types(self) -> List[str]:
        """Get list of supported metadata field types."""
        return [field_type.value for field_type in MetadataFieldType]
