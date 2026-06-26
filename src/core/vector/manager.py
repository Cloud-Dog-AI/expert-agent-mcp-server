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
Vector Store Manager

License: Apache 2.0
Ownership: Cloud Dog
Description: Manages vector store connections and operations

Related Requirements: FR1.3
Related Tasks: T014
Related Architecture: CC4.1.1
Related Tests: IT2.6

Recent Changes:
- Initial implementation
"""

import json
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session

from src.database.models import VectorStore as VectorStoreModel
from src.database.connection import get_db
from src.core.vector.providers import VectorStoreProvider, ChromaProvider
from src.core.vector.lifecycle import VectorLifecycleManager
from src.core.vector.isolation import VectorIsolationManager
from src.core.vector.indexing import VectorIndexingManager
from src.core.vector.options import VectorStoreOptionsManager
from src.config.loader import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


class VectorStoreManager:
    """Manages vector stores."""

    def __init__(self, db: Optional[Session] = None):
        """
        Initialize vector store manager.

        Args:
            db: Database session (if None, creates new)
        """
        self.db = db
        self.providers: Dict[str, VectorStoreProvider] = {}

    def _get_db(self) -> Session:
        """Get database session."""
        if self.db:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    def _get_provider(self, store_type: str) -> VectorStoreProvider:
        """Get or create vector store provider."""
        if store_type not in self.providers:
            if store_type == "chroma":
                self.providers[store_type] = ChromaProvider()
            elif store_type == "qdrant":
                from src.core.vector.providers import QdrantProvider

                self.providers[store_type] = QdrantProvider()
            elif store_type == "weaviate":
                from src.core.vector.providers import WeaviateProvider

                self.providers[store_type] = WeaviateProvider()
            elif store_type == "opensearch" or store_type == "elasticsearch":
                from src.core.vector.providers import OpenSearchProvider

                self.providers[store_type] = OpenSearchProvider()
            elif store_type == "pgvector":
                from src.core.vector.providers import PGVectorProvider

                self.providers[store_type] = PGVectorProvider()
            else:
                raise ValueError(f"Unsupported vector store type: {store_type}")
        return self.providers[store_type]

    @staticmethod
    async def _close_provider(provider: Optional[VectorStoreProvider]) -> None:
        """Best-effort provider cleanup for providers with async close()."""
        if provider is None:
            return
        close_fn = getattr(provider, "close", None)
        if callable(close_fn):
            try:
                maybe = close_fn()
                if hasattr(maybe, "__await__"):
                    await maybe
            except Exception:
                pass

    def _resolve_runtime_provider_config(
        self,
        vector_store: VectorStoreModel,
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Merge runtime-only secrets from config into a persisted vector store config.

        Persisted VectorStore.config_json must not contain external credentials (RULES.md).
        Some providers (qdrant/opensearch/weaviate/etc.) require secrets at runtime to
        initialize; those secrets are sourced from env via get_config().
        """
        merged: Dict[str, Any] = dict(config or {})

        store_type = (vector_store.type or "").lower().strip()
        if not store_type:
            return merged

        profiles = get_config(f"vector_stores_config.{store_type}")
        if not isinstance(profiles, dict):
            return merged

        def _norm_port(v: Any) -> Optional[int]:
            if v is None:
                return None
            if isinstance(v, int):
                return v
            if isinstance(v, str) and v.strip().isdigit():
                return int(v.strip())
            return None

        host = merged.get("host") or merged.get("url") or merged.get("server_url")
        port = _norm_port(merged.get("port"))
        collection = merged.get("collection_name")

        # Find the best matching profile by host/port/(collection) so we don't assume "_DEFAULT_".
        best_profile: Optional[Dict[str, Any]] = None
        for _profile_name, prof_cfg in profiles.items():
            if not isinstance(prof_cfg, dict):
                continue
            prof_host = prof_cfg.get("host") or prof_cfg.get("url") or prof_cfg.get("server_url")
            prof_port = _norm_port(prof_cfg.get("port"))
            prof_collection = prof_cfg.get("collection_name")

            if host and prof_host and str(host) != str(prof_host):
                continue
            if port is not None and prof_port is not None and port != prof_port:
                continue
            if collection and prof_collection and str(collection) != str(prof_collection):
                continue

            best_profile = prof_cfg
            break

        if not best_profile:
            return merged

        # Inject secrets only if missing from persisted config.
        if store_type == "qdrant":
            if not (isinstance(merged.get("api_key"), str) and merged.get("api_key").strip()):
                api_key = best_profile.get("api_key")
                if isinstance(api_key, str) and api_key.strip():
                    merged["api_key"] = api_key
        elif store_type in ("opensearch", "elasticsearch"):
            if not (isinstance(merged.get("password"), str) and merged.get("password").strip()):
                password = best_profile.get("password")
                if isinstance(password, str) and password.strip():
                    merged["password"] = password
        elif store_type == "weaviate":
            if not (isinstance(merged.get("api_key"), str) and merged.get("api_key").strip()):
                api_key = best_profile.get("api_key")
                if isinstance(api_key, str) and api_key.strip():
                    merged["api_key"] = api_key

        return merged

    def create_vector_store(
        self,
        name: str,
        store_type: str,
        config: Optional[Dict[str, Any]] = None,
        enabled: bool = True,
        access_control: Optional[Dict[str, Any]] = None,
    ) -> VectorStoreModel:
        """
        Create a new vector store configuration with options support.

        Args:
            name: Vector store name (unique)
            store_type: Store type (chroma, weaviate, qdrant, etc.)
            config: Store-specific configuration (can include indexing, search, and options)
            enabled: Whether store is enabled
            access_control: Access control settings

        Returns:
            Created vector store configuration
        """
        db = self._get_db()
        try:
            # Check if store exists
            existing = db.query(VectorStoreModel).filter(VectorStoreModel.name == name).first()
            if existing:
                raise ValueError(f"Vector store '{name}' already exists")

            # Validate config structure for known store types (fail fast)
            if not isinstance(config, dict) or not config:
                raise ValueError(f"Vector store '{store_type}' requires a non-empty config")

            def _require_any(keys: List[str]) -> None:
                if not any(isinstance(config.get(k), str) and config.get(k).strip() for k in keys):
                    raise ValueError(
                        f"Vector store '{store_type}' config must include one of: {', '.join(keys)}"
                    )

            def _require_str(key: str) -> None:
                if not (isinstance(config.get(key), str) and config.get(key).strip()):
                    raise ValueError(f"Vector store '{store_type}' config missing/invalid '{key}'")

            def _require_int(key: str) -> None:
                val = config.get(key)
                if isinstance(val, str) and val.isdigit():
                    return
                if not isinstance(val, int):
                    raise ValueError(f"Vector store '{store_type}' config missing/invalid '{key}'")

            if store_type == "chroma":
                # Accept either remote or local-style configuration
                _require_any(["server_url", "host", "path"])
            elif store_type == "qdrant":
                _require_str("host")
                _require_int("port")
                _require_str("collection_name")
            elif store_type in ("opensearch", "elasticsearch"):
                _require_str("host")
                _require_int("port")
                # Support either `collection_name` (preferred) or `index_name` (alias)
                if not (
                    (
                        isinstance(config.get("collection_name"), str)
                        and config.get("collection_name").strip()
                    )
                    or (
                        isinstance(config.get("index_name"), str)
                        and config.get("index_name").strip()
                    )
                ):
                    raise ValueError(
                        f"Vector store '{store_type}' config missing/invalid 'collection_name' (or 'index_name')"
                    )
            elif store_type == "pgvector":
                _require_str("host")
                _require_int("port")
                _require_str("database")
                _require_str("username")
            elif store_type == "weaviate":
                _require_str("server_url")

            # Merge options with defaults if config provided
            merged_config = (
                VectorStoreOptionsManager.merge_options(store_type, config, None)
                if config
                else None
            )

            vector_store = VectorStoreModel(
                name=name,
                type=store_type,
                config_json=json.dumps(merged_config) if merged_config else None,
                enabled=enabled,
                access_control_json=json.dumps(access_control) if access_control else None,
            )
            db.add(vector_store)
            db.commit()
            db.refresh(vector_store)

            logger.info(f"Created vector store: {name} ({store_type})")
            return vector_store
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to create vector store: {e}", exc_info=True)
            raise

    def get_vector_store(
        self, store_id: Optional[int] = None, name: Optional[str] = None
    ) -> Optional[VectorStoreModel]:
        """Get vector store by ID or name."""
        db = self._get_db()
        if store_id:
            return db.query(VectorStoreModel).filter(VectorStoreModel.id == store_id).first()
        elif name:
            return db.query(VectorStoreModel).filter(VectorStoreModel.name == name).first()
        return None

    async def add_documents(
        self,
        store_name: str,
        collection: str,
        documents: List[str],
        metadatas: Optional[List[Dict[str, Any]]] = None,
        ids: Optional[List[str]] = None,
    ) -> List[str]:
        """
        Add documents to a configured vector store.

        Args:
            store_name: Vector store name
            collection: Collection name
            documents: Documents to add
            metadatas: Optional metadata per document
            ids: Optional IDs per document

        Returns:
            List of document IDs
        """
        vector_store = self.get_vector_store(name=store_name)
        if not vector_store or not vector_store.enabled:
            raise ValueError(f"Vector store '{store_name}' not found or disabled")

        persisted_config = json.loads(vector_store.config_json) if vector_store.config_json else {}
        config = self._resolve_runtime_provider_config(vector_store, persisted_config)
        provider: Optional[VectorStoreProvider] = None
        try:
            provider = self._get_provider(vector_store.type)

            if not hasattr(provider, "_initialized") or not provider._initialized:
                ok = await provider.initialize(config)
                provider._initialized = bool(ok)
                if not ok:
                    raise RuntimeError(f"Vector store backend '{vector_store.type}' not available")

            return await provider.add_documents(
                collection=collection,
                documents=documents,
                metadatas=metadatas,
                ids=ids,
            )
        finally:
            await self._close_provider(provider)

    async def search(
        self,
        store_name: str,
        collection: str,
        query: str,
        n_results: int = 5,
        filter: Optional[Dict[str, Any]] = None,
        search_options: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """
        Search vector store with options support.

        Args:
            store_name: Vector store name
            collection: Collection name
            query: Search query
            n_results: Number of results
            filter: Filter criteria
            search_options: Search options (can override config defaults)

        Returns:
            List of search results
        """
        vector_store = self.get_vector_store(name=store_name)
        if not vector_store or not vector_store.enabled:
            raise ValueError(f"Vector store '{store_name}' not found or disabled")

        persisted_config = json.loads(vector_store.config_json) if vector_store.config_json else {}
        config = self._resolve_runtime_provider_config(vector_store, persisted_config)
        provider: Optional[VectorStoreProvider] = None
        try:
            provider = self._get_provider(vector_store.type)

            # Ensure provider is initialized
            if not hasattr(provider, "_initialized") or not provider._initialized:
                ok = await provider.initialize(config)
                provider._initialized = bool(ok)
                if not ok:
                    raise RuntimeError(f"Vector store backend '{vector_store.type}' not available")

            return await provider.search(collection, query, n_results, filter, search_options)
        finally:
            await self._close_provider(provider)

    def get_lifecycle_manager(self) -> VectorLifecycleManager:
        """
        Get lifecycle manager for vector store operations.

        Returns:
            VectorLifecycleManager instance
        """
        return VectorLifecycleManager(self.db)

    def get_isolation_manager(self) -> VectorIsolationManager:
        """
        Get isolation manager for cross-talk prevention.

        Returns:
            VectorIsolationManager instance
        """
        return VectorIsolationManager(self.db)

    def get_indexing_manager(self) -> VectorIndexingManager:
        """
        Get indexing manager for format and metadata options.

        Returns:
            VectorIndexingManager instance
        """
        return VectorIndexingManager(self.db)
