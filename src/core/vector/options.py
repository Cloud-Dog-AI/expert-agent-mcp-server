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
Vector Store Options Management

License: Apache 2.0
Ownership: Cloud Dog
Description: Manages common and product-specific vector store options

Related Requirements: FR1.3
Related Tasks: T014
Related Architecture: CC4.1.1
"""

from typing import Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
from src.config.loader import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)


class DistanceMetric(str, Enum):
    """Distance/similarity metrics."""

    L2 = "l2"  # Euclidean distance
    COSINE = "cosine"  # Cosine similarity
    DOT = "dot"  # Dot product / inner product
    IP = "ip"  # Inner product (alias for dot)


class IndexType(str, Enum):
    """Index types."""

    EXACT = "exact"  # Brute-force exact search
    ANN = "ann"  # Approximate nearest neighbor
    HNSW = "hnsw"  # Hierarchical Navigable Small World
    IVFFLAT = "ivfflat"  # Inverted File Index Flat
    FLAT = "flat"  # Flat index (exact)


@dataclass
class CommonIndexingOptions:
    """Common indexing options across vector stores."""

    # Vector dimensionality (must match embedding model)
    dimension: Optional[int] = None

    # Distance / similarity metric
    distance_metric: DistanceMetric = DistanceMetric.COSINE

    # Index type: exact vs ANN
    index_type: IndexType = IndexType.ANN

    # ANN algorithm family (HNSW, IVF, etc.)
    ann_algorithm: str = "hnsw"

    # Compression / quantization (optional)
    compression_enabled: bool = False
    quantization_type: Optional[str] = None  # e.g., "scalar", "product", "binary"

    # Shards / replicas / persistence
    shards: int = 1
    replicas: int = 0
    persistence: bool = True


@dataclass
class CommonSearchOptions:
    """Common search options across vector stores."""

    # Top-K / limit
    limit: int = 5
    top_k: Optional[int] = None  # Alias for limit

    # Filters (metadata predicates)
    filter: Optional[Dict[str, Any]] = None
    pre_filter: bool = False  # Apply filter before vector search

    # Pagination
    offset: int = 0
    cursor: Optional[str] = None
    after: Optional[str] = None

    # Score thresholds
    score_threshold: Optional[float] = None
    min_score: Optional[float] = None
    max_distance: Optional[float] = None

    # Return controls
    include_vectors: bool = False
    include_metadata: bool = True
    include_distances: bool = True
    include_scores: bool = True

    # Hybrid search
    hybrid_enabled: bool = False
    hybrid_alpha: float = 0.5  # Weight between vector and keyword (0=keyword, 1=vector)


@dataclass
class ChromaOptions:
    """Chroma-specific options."""

    # HNSW collection metadata keys
    hnsw_space: str = "cosine"  # l2 | cosine | ip
    hnsw_construction_ef: int = 200
    hnsw_M: int = 16
    hnsw_search_ef: int = 50
    hnsw_num_threads: int = 4
    hnsw_resize_factor: float = 1.2
    hnsw_batch_size: int = 100  # Bruteforce → HNSW transfer threshold
    hnsw_sync_threshold: int = 10000  # Flush/write threshold

    # Search options
    where: Optional[Dict[str, Any]] = None  # Metadata filtering
    where_document: Optional[Dict[str, Any]] = None  # Document content filtering
    include: Optional[list] = (
        None  # Result projection: ["embeddings", "metadatas", "documents", "distances"]
    )


@dataclass
class QdrantOptions:
    """Qdrant-specific options."""

    # HNSW config block
    hnsw_m: int = 16
    hnsw_ef_construct: int = 200
    hnsw_full_scan_threshold: int = 10000
    hnsw_max_indexing_threads: int = 0  # 0 = auto
    hnsw_on_disk: bool = False
    hnsw_payload_m: int = 16
    hnsw_inline_storage: bool = True

    # Sharding + replication
    shard_number: int = 1
    sharding_method: str = "auto"  # auto | custom
    replication_factor: int = 1
    write_consistency_factor: int = 1
    read_fan_out_factor: int = 1

    # On-disk payload
    on_disk_payload: bool = False

    # Quantization
    quantization_enabled: bool = False
    quantization_type: str = "scalar"  # scalar | product | binary
    quantization_always_ram: bool = True

    # Search options
    with_payload: bool = True
    with_vector: bool = False
    hnsw_ef: Optional[int] = None  # Query-time HNSW ef
    exact: bool = False  # Force exact search
    consistency: Optional[str] = None
    shard_key: Optional[str] = None


@dataclass
class PGVectorOptions:
    """PGVector-specific options."""

    # Index type
    index_type: str = "ivfflat"  # ivfflat | hnsw

    # IVFFlat parameters
    ivfflat_lists: int = 100  # Number of partitions
    ivfflat_probes: int = 10  # Query-time: how many lists to search

    # HNSW parameters
    hnsw_m: int = 16
    hnsw_ef_construction: int = 200
    hnsw_ef_search: Optional[int] = None  # Query-time

    # Vector storage type
    vector_type: str = "vector"  # vector | halfvec | bit

    # Iterative scan options (pgvector >= 0.8.0)
    iterative_scan: bool = False
    max_probes: Optional[int] = None
    max_scan_tuples: Optional[int] = None


@dataclass
class OpenSearchOptions:
    """OpenSearch-specific options."""

    # knn_vector mapping
    dimension: int = 1024
    space_type: str = "cosinesimil"  # cosinesimil | l2 | innerproduct
    method: str = "hnsw"  # hnsw | ivf
    engine: str = "nmslib"  # lucene | faiss | nmslib

    # HNSW parameters
    ef_construction: int = 128
    m: int = 24
    ef_search: int = 100

    # Faiss encoders for compression
    encoder_type: Optional[str] = None  # pq | flat
    pq_m: Optional[int] = None
    pq_code_size: Optional[int] = None

    # Index settings
    index_knn: bool = True
    index_knn_algo_param_ef_search: int = 100

    # Search options
    k: Optional[int] = None  # Alias for limit
    method_parameters: Optional[Dict[str, Any]] = None  # e.g., {"ef_search": 100, "nprobes": 10}
    rescore: bool = False


@dataclass
class WeaviateOptions:
    """Weaviate-specific options."""

    # Vector index type
    vector_index_type: str = "hnsw"  # hnsw | flat | dynamic

    # HNSW controls
    ef_construction: int = 128
    max_connections: int = 64
    dynamic_ef_min: int = 100
    dynamic_ef_max: int = 500
    dynamic_ef_factor: int = 8
    filter_strategy: str = "acorn"  # acorn | sweeping
    flat_search_cutoff: int = 40000
    skip: bool = False  # Don't index
    vector_cache_max_objects: int = 1000000000

    # Compression options
    compression_type: Optional[str] = None  # rq | pq | bq | sq
    compression_rq_bits: Optional[int] = None
    compression_rq_rescore_limit: Optional[int] = None
    compression_rq_cache: Optional[int] = None

    # Search options
    distance: Optional[float] = None
    certainty: Optional[float] = None
    autocut: Optional[int] = None
    alpha: float = 0.5  # Hybrid search weight
    fusion_strategy: str = "ranked"  # ranked | relative
    max_vector_distance: Optional[float] = None


class VectorStoreOptionsManager:
    """Manages vector store options from config and API."""

    @staticmethod
    def get_common_indexing_options(
        store_type: str,
        config: Optional[Dict[str, Any]] = None,
        override: Optional[Dict[str, Any]] = None,
    ) -> CommonIndexingOptions:
        """Get common indexing options with defaults and overrides."""
        # Get defaults from config (no hardcoded fallbacks)
        defaults = get_config("vector_stores.common.indexing")
        if not isinstance(defaults, dict):
            raise RuntimeError("vector_stores.common.indexing not configured")

        # Merge with store-specific defaults
        store_defaults = get_config(f"vector_stores.{store_type}._DEFAULT_.indexing")
        if not isinstance(store_defaults, dict):
            raise RuntimeError(f"vector_stores.{store_type}._DEFAULT_.indexing not configured")
        defaults = {**defaults, **store_defaults}

        # Merge with provided config
        if config:
            defaults = {**defaults, **config.get("indexing", {})}

        # Apply overrides
        if override:
            defaults = {**defaults, **override.get("indexing", {})}

        # Create options object
        if not defaults.get("distance_metric"):
            raise RuntimeError("vector_stores.*.indexing.distance_metric not configured")
        if not defaults.get("index_type"):
            raise RuntimeError("vector_stores.*.indexing.index_type not configured")
        if not defaults.get("ann_algorithm"):
            raise RuntimeError("vector_stores.*.indexing.ann_algorithm not configured")
        return CommonIndexingOptions(
            dimension=defaults.get("dimension"),
            distance_metric=DistanceMetric(defaults.get("distance_metric")),
            index_type=IndexType(defaults.get("index_type")),
            ann_algorithm=defaults.get("ann_algorithm"),
            compression_enabled=defaults.get("compression_enabled"),
            quantization_type=defaults.get("quantization_type"),
            shards=defaults.get("shards"),
            replicas=defaults.get("replicas"),
            persistence=defaults.get("persistence"),
        )

    @staticmethod
    def get_common_search_options(
        store_type: str,
        config: Optional[Dict[str, Any]] = None,
        override: Optional[Dict[str, Any]] = None,
    ) -> CommonSearchOptions:
        """Get common search options with defaults and overrides."""
        # Get defaults from config (no hardcoded fallbacks)
        defaults = get_config("vector_stores.common.search")
        if not isinstance(defaults, dict):
            raise RuntimeError("vector_stores.common.search not configured")

        # Merge with store-specific defaults
        store_defaults = get_config(f"vector_stores.{store_type}._DEFAULT_.search")
        if not isinstance(store_defaults, dict):
            raise RuntimeError(f"vector_stores.{store_type}._DEFAULT_.search not configured")
        defaults = {**defaults, **store_defaults}

        # Merge with provided config
        if config:
            defaults = {**defaults, **config.get("search", {})}

        # Apply overrides
        if override:
            defaults = {**defaults, **override.get("search", {})}

        # Create options object
        if defaults.get("limit") is None:
            raise RuntimeError("vector_stores.*.search.limit not configured")
        if defaults.get("pre_filter") is None:
            raise RuntimeError("vector_stores.*.search.pre_filter not configured")
        if defaults.get("offset") is None:
            raise RuntimeError("vector_stores.*.search.offset not configured")
        if defaults.get("include_vectors") is None:
            raise RuntimeError("vector_stores.*.search.include_vectors not configured")
        if defaults.get("include_metadata") is None:
            raise RuntimeError("vector_stores.*.search.include_metadata not configured")
        if defaults.get("include_distances") is None:
            raise RuntimeError("vector_stores.*.search.include_distances not configured")
        if defaults.get("include_scores") is None:
            raise RuntimeError("vector_stores.*.search.include_scores not configured")
        if defaults.get("hybrid_enabled") is None:
            raise RuntimeError("vector_stores.*.search.hybrid_enabled not configured")
        if defaults.get("hybrid_alpha") is None:
            raise RuntimeError("vector_stores.*.search.hybrid_alpha not configured")
        return CommonSearchOptions(
            limit=defaults.get("limit"),
            top_k=defaults.get("top_k"),
            filter=defaults.get("filter"),
            pre_filter=defaults.get("pre_filter"),
            offset=defaults.get("offset"),
            cursor=defaults.get("cursor"),
            after=defaults.get("after"),
            score_threshold=defaults.get("score_threshold"),
            min_score=defaults.get("min_score"),
            max_distance=defaults.get("max_distance"),
            include_vectors=defaults.get("include_vectors"),
            include_metadata=defaults.get("include_metadata"),
            include_distances=defaults.get("include_distances"),
            include_scores=defaults.get("include_scores"),
            hybrid_enabled=defaults.get("hybrid_enabled"),
            hybrid_alpha=defaults.get("hybrid_alpha"),
        )

    @staticmethod
    def get_product_specific_options(
        store_type: str,
        config: Optional[Dict[str, Any]] = None,
        override: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Get product-specific options as dict."""
        # Get defaults from config (no hardcoded fallbacks)
        defaults = get_config(f"vector_stores.{store_type}._DEFAULT_.options")
        if not isinstance(defaults, dict):
            raise RuntimeError(f"vector_stores.{store_type}._DEFAULT_.options not configured")

        # Merge with provided config
        if config:
            defaults = {**defaults, **config.get("options", {})}

        # Apply overrides
        if override:
            defaults = {**defaults, **override.get("options", {})}

        return defaults

    @staticmethod
    def merge_options(
        store_type: str,
        base_config: Optional[Dict[str, Any]] = None,
        api_options: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Merge base config with API-provided options.

        Args:
            store_type: Vector store type
            base_config: Base configuration from database
            api_options: Options provided via API (can override base)

        Returns:
            Merged configuration dict
        """
        result = base_config.copy() if base_config else {}

        if api_options:
            # First, update all top-level fields from api_options
            for key, value in api_options.items():
                if key not in ["indexing", "search", "options"]:
                    # Simple override for top-level fields
                    result[key] = value

            # Merge indexing options (nested)
            if "indexing" in api_options:
                if "indexing" not in result:
                    result["indexing"] = {}
                result["indexing"].update(api_options["indexing"])

            # Merge search options (nested)
            if "search" in api_options:
                if "search" not in result:
                    result["search"] = {}
                result["search"].update(api_options["search"])

            # Merge product-specific options (nested)
            if "options" in api_options:
                if "options" not in result:
                    result["options"] = {}
                result["options"].update(api_options["options"])

        return result
