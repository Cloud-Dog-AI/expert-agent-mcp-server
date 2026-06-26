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
Vector Store Lifecycle Management

License: Apache 2.0
Ownership: Cloud Dog
Description: Lifecycle management operations for vector stores (purge, compress, consolidate)

Related Requirements: FR1.3
Related Tasks: T018
Related Architecture: CC4.1.3
Related Tests: UT1.22

Recent Changes:
- Initial implementation
"""

from typing import List, Dict, Any, Optional, TYPE_CHECKING
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from src.core.vector.providers import VectorStoreProvider
from src.database.connection import get_db
from src.utils.logger import get_logger

if TYPE_CHECKING:
    pass

logger = get_logger(__name__)


class VectorLifecycleManager:
    """Manages vector store lifecycle operations."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize lifecycle manager.

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

    def _get_db(self) -> Session:
        """Get database session."""
        if self.db:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    async def purge(
        self,
        store_name: str,
        collection: str,
        filter_criteria: Optional[Dict[str, Any]] = None,
        older_than_days: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Purge documents from vector store collection.

        Args:
            store_name: Vector store name
            collection: Collection name
            filter_criteria: Filter criteria for documents to purge
            older_than_days: Purge documents older than this many days

        Returns:
            Dict with purge statistics
        """
        try:
            vector_store = self.vector_manager.get_vector_store(name=store_name)
            if not vector_store or not vector_store.enabled:
                raise ValueError(f"Vector store '{store_name}' not found or disabled")

            provider = self.vector_manager._get_provider(vector_store.type)
            # Parse config_json if it's a string
            if vector_store.config_json:
                if isinstance(vector_store.config_json, str):
                    import json

                    config = json.loads(vector_store.config_json)
                else:
                    config = vector_store.config_json
            else:
                config = {}

            # Initialize provider if needed
            if not hasattr(provider, "_initialized") or not provider._initialized:
                await provider.initialize(config)

            # Build purge filter
            purge_filter = filter_criteria or {}
            if older_than_days:
                cutoff_date = datetime.utcnow() - timedelta(days=older_than_days)
                purge_filter["created_before"] = cutoff_date.isoformat()

            # Get count before purge (provider-specific)
            count_before = await self._count_documents(provider, collection, purge_filter)

            # Perform purge (provider-specific)
            purged_count = await self._purge_documents(provider, collection, purge_filter)

            logger.info(f"Purged {purged_count} documents from {store_name}/{collection}")

            return {
                "store_name": store_name,
                "collection": collection,
                "count_before": count_before,
                "purged_count": purged_count,
                "count_after": count_before - purged_count,
                "filter": purge_filter,
            }
        except Exception as e:
            logger.error(f"Failed to purge vector store: {e}", exc_info=True)
            raise

    async def compress(
        self, store_name: str, collection: str, target_ratio: float = 0.5
    ) -> Dict[str, Any]:
        """
        Compress vector store collection by removing similar/duplicate documents.

        Args:
            store_name: Vector store name
            collection: Collection name
            target_ratio: Target compression ratio (0.0 to 1.0)

        Returns:
            Dict with compression statistics
        """
        try:
            vector_store = self.vector_manager.get_vector_store(name=store_name)
            if not vector_store or not vector_store.enabled:
                raise ValueError(f"Vector store '{store_name}' not found or disabled")

            provider = self.vector_manager._get_provider(vector_store.type)
            # Parse config_json if it's a string
            if vector_store.config_json:
                if isinstance(vector_store.config_json, str):
                    import json

                    config = json.loads(vector_store.config_json)
                else:
                    config = vector_store.config_json
            else:
                config = {}

            # Initialize provider if needed
            if not hasattr(provider, "_initialized") or not provider._initialized:
                await provider.initialize(config)

            # Get all documents (or sample)
            count_before = await self._count_documents(provider, collection)

            # Find similar documents and remove duplicates
            compressed_count = await self._compress_documents(provider, collection, target_ratio)

            count_after = await self._count_documents(provider, collection)

            logger.info(
                f"Compressed {store_name}/{collection}: {count_before} -> {count_after} documents"
            )

            return {
                "store_name": store_name,
                "collection": collection,
                "count_before": count_before,
                "compressed_count": compressed_count,
                "count_after": count_after,
                "compression_ratio": count_after / count_before if count_before > 0 else 0.0,
                "target_ratio": target_ratio,
            }
        except Exception as e:
            logger.error(f"Failed to compress vector store: {e}", exc_info=True)
            raise

    async def consolidate(
        self,
        store_name: str,
        collection: str,
        merge_similar: bool = True,
        similarity_threshold: float = 0.9,
    ) -> Dict[str, Any]:
        """
        Consolidate vector store collection by merging similar documents.

        Args:
            store_name: Vector store name
            collection: Collection name
            merge_similar: Whether to merge similar documents
            similarity_threshold: Similarity threshold for merging (0.0 to 1.0)

        Returns:
            Dict with consolidation statistics
        """
        try:
            vector_store = self.vector_manager.get_vector_store(name=store_name)
            if not vector_store or not vector_store.enabled:
                raise ValueError(f"Vector store '{store_name}' not found or disabled")

            provider = self.vector_manager._get_provider(vector_store.type)
            # Parse config_json if it's a string
            if vector_store.config_json:
                if isinstance(vector_store.config_json, str):
                    import json

                    config = json.loads(vector_store.config_json)
                else:
                    config = vector_store.config_json
            else:
                config = {}

            # Initialize provider if needed
            if not hasattr(provider, "_initialized") or not provider._initialized:
                await provider.initialize(config)

            count_before = await self._count_documents(provider, collection)

            if merge_similar:
                consolidated_count = await self._consolidate_documents(
                    provider, collection, similarity_threshold
                )
            else:
                consolidated_count = 0

            count_after = await self._count_documents(provider, collection)

            logger.info(
                f"Consolidated {store_name}/{collection}: {count_before} -> {count_after} documents"
            )

            return {
                "store_name": store_name,
                "collection": collection,
                "count_before": count_before,
                "consolidated_count": consolidated_count,
                "count_after": count_after,
                "similarity_threshold": similarity_threshold,
            }
        except Exception as e:
            logger.error(f"Failed to consolidate vector store: {e}", exc_info=True)
            raise

    async def _count_documents(
        self,
        provider: VectorStoreProvider,
        collection: str,
        filter: Optional[Dict[str, Any]] = None,
    ) -> int:
        """Count documents in collection (provider-specific)."""
        try:
            return await provider.count_documents(collection, filter)
        except Exception:
            # Fallback to search-based count
            try:
                results = await provider.search(collection, "", n_results=10000, filter=filter)
                return len(results)
            except Exception:
                return 0

    async def _purge_documents(
        self, provider: VectorStoreProvider, collection: str, filter: Dict[str, Any]
    ) -> int:
        """Purge documents (provider-specific implementation)."""
        # This is a placeholder - actual implementation depends on provider
        # Most providers don't have direct delete-by-filter, so we'd need to:
        # 1. Search for documents matching filter
        # 2. Delete them by ID

        try:
            # Search for documents matching filter
            results = await provider.search(collection, "", n_results=10000, filter=filter)

            # Delete by IDs (provider-specific)
            purged = 0
            for result in results:
                try:
                    await self._delete_document(provider, collection, result["id"])
                    purged += 1
                except Exception as e:
                    logger.warning(f"Failed to delete document {result['id']}: {e}")

            return purged
        except Exception as e:
            logger.error(f"Failed to purge documents: {e}", exc_info=True)
            return 0

    async def _compress_documents(
        self, provider: VectorStoreProvider, collection: str, target_ratio: float
    ) -> int:
        """Compress documents by removing duplicates (provider-specific)."""
        # This is a simplified implementation
        # Real compression would:
        # 1. Find similar documents using vector similarity
        # 2. Remove duplicates keeping the most recent/complete version

        try:
            # Get sample of documents
            results = await provider.search(collection, "", n_results=1000)

            # Group by similarity and remove duplicates
            # This is a simplified version - real implementation would use clustering
            compressed = 0
            seen_hashes = set()

            for result in results:
                # Simple deduplication by content hash
                content_hash = hash(result.get("document", ""))
                if content_hash in seen_hashes:
                    await self._delete_document(provider, collection, result["id"])
                    compressed += 1
                else:
                    seen_hashes.add(content_hash)

            return compressed
        except Exception as e:
            logger.error(f"Failed to compress documents: {e}", exc_info=True)
            return 0

    async def _consolidate_documents(
        self, provider: VectorStoreProvider, collection: str, similarity_threshold: float
    ) -> int:
        """Consolidate documents by merging similar ones (provider-specific)."""
        # This is a simplified implementation
        # Real consolidation would:
        # 1. Find similar documents using vector similarity
        # 2. Merge their content
        # 3. Update one document and delete others

        try:
            # Get documents
            results = await provider.search(collection, "", n_results=1000)

            # Group similar documents and merge
            consolidated = 0
            processed = set()

            for i, result1 in enumerate(results):
                if result1["id"] in processed:
                    continue

                # Find similar documents
                similar = [result1]
                for j, result2 in enumerate(results[i + 1 :], start=i + 1):
                    if result2["id"] in processed:
                        continue

                    # Calculate similarity (simplified - would use actual vector similarity)
                    similarity = self._calculate_similarity(
                        result1.get("document", ""), result2.get("document", "")
                    )

                    if similarity >= similarity_threshold:
                        similar.append(result2)

                # Merge similar documents
                if len(similar) > 1:
                    merged_doc = self._merge_documents(similar)
                    # Update first document with merged content
                    await self._update_document(provider, collection, similar[0]["id"], merged_doc)
                    # Delete other similar documents
                    for doc in similar[1:]:
                        await self._delete_document(provider, collection, doc["id"])
                        processed.add(doc["id"])
                        consolidated += 1

                processed.add(result1["id"])

            return consolidated
        except Exception as e:
            logger.error(f"Failed to consolidate documents: {e}", exc_info=True)
            return 0

    def _calculate_similarity(self, doc1: str, doc2: str) -> float:
        """Calculate similarity between two documents (simplified)."""
        # Simplified Jaccard similarity
        words1 = set(doc1.lower().split())
        words2 = set(doc2.lower().split())

        if not words1 or not words2:
            return 0.0

        intersection = len(words1 & words2)
        union = len(words1 | words2)

        return intersection / union if union > 0 else 0.0

    def _merge_documents(self, documents: List[Dict[str, Any]]) -> str:
        """Merge multiple documents into one."""
        # Simple merge: concatenate unique content
        merged_parts = []
        seen_content = set()

        for doc in documents:
            content = doc.get("document", "")
            if content and content not in seen_content:
                merged_parts.append(content)
                seen_content.add(content)

        return "\n\n".join(merged_parts)

    async def _delete_document(self, provider: VectorStoreProvider, collection: str, doc_id: str):
        """Delete a document by ID (provider-specific)."""
        try:
            return await provider.delete_document(collection, doc_id)
        except Exception as e:
            logger.warning(f"Failed to delete document {doc_id}: {e}")
            return False

    async def _update_document(
        self, provider: VectorStoreProvider, collection: str, doc_id: str, new_content: str
    ):
        """Update a document (provider-specific)."""
        try:
            return await provider.update_document(collection, doc_id, new_content)
        except Exception as e:
            logger.warning(f"Failed to update document {doc_id}: {e}")
            return False
