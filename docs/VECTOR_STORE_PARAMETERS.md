# Vector Store Configuration Parameters

**Version:** 0.1 • 2025-01-XX  
**Related:** [API_DOCUMENTATION.md](API_DOCUMENTATION.md), [PARAMETERS.md](PARAMETERS.md)

---

## Overview

This document provides comprehensive documentation for all configuration parameters supported by each vector store provider. All parameters can be set via the vector store configuration API endpoint (`POST /vector-stores`) or via environment variables.

---

## Supported Vector Stores

- **Qdrant** - High-performance vector database
- **Chroma** - Open-source embedding database
- **Weaviate** - Cloud-native vector database
- **OpenSearch** - Open-source search and analytics engine
- **PGVector** - PostgreSQL extension for vector similarity search

---

## Qdrant Parameters

### Required Parameters
- `host` (string): Qdrant server hostname or IP address
- `port` (integer, default: 6333): Qdrant server port

### Optional Parameters
- `api_key` (string): API key for authentication (required for cloud Qdrant)
- `collection_name` (string, default: "expert_agent_default"): Collection name for vectors
- `ssl` (boolean, default: false): Enable SSL/TLS connection
- `timeout` (integer, default: 10): Connection timeout in seconds
- `prefer_grpc` (boolean, default: false): Prefer gRPC over HTTP
- `https` (boolean, default: false): Use HTTPS protocol

### Example Configuration
```json
{
  "name": "qdrant_store",
  "store_type": "qdrant",
  "config": {
    "host": "vdb1.internal.example",
    "port": 6333,
    "api_key": "your-api-key",
    "collection_name": "expert_agent_qdrant",
    "ssl": false,
    "timeout": 30,
    "prefer_grpc": false,
    "https": false
  },
  "enabled": true
}
```

### Environment Variables
```bash
CLOUD_DOG__EXPERT__VECTOR__STORES__QDRANT__DEFAULT__HOST=vdb1.internal.example
CLOUD_DOG__EXPERT__VECTOR__STORES__QDRANT__DEFAULT__PORT=6333
CLOUD_DOG__EXPERT__VECTOR__STORES__QDRANT__DEFAULT__API_KEY=your-api-key
CLOUD_DOG__EXPERT__VECTOR__STORES__QDRANT__DEFAULT__COLLECTION_NAME=expert_agent_qdrant
```

---

## Chroma Parameters

### Required Parameters
- None (uses defaults if not specified)

### Optional Parameters
- `path` (string, default: "./database/chroma-data"): Local file path for persistent storage
- `host` (string): Remote Chroma server hostname (alternative to path)
- `port` (integer, default: 8000): Remote Chroma server port (used with host)
- `collection_name` (string, default: "expert_default"): Collection name for vectors
- `anonymized_telemetry` (boolean, default: false): Enable/disable anonymized telemetry

### Example Configuration (Local)
```json
{
  "name": "chroma_local",
  "store_type": "chroma",
  "config": {
    "path": "./database/chroma-data",
    "collection_name": "expert_agent_chroma",
    "anonymized_telemetry": false
  },
  "enabled": true
}
```

### Example Configuration (Remote)
```json
{
  "name": "chroma_remote",
  "store_type": "chroma",
  "config": {
    "host": "chroma-server.example.com",
    "port": 8000,
    "collection_name": "expert_agent_chroma",
    "anonymized_telemetry": false
  },
  "enabled": true
}
```

### Environment Variables
```bash
CLOUD_DOG__EXPERT__VECTOR__STORES__CHROMA__PATH=./database/chroma-data
CLOUD_DOG__EXPERT__VECTOR__STORES__CHROMA__HOST=chroma-server.example.com
CLOUD_DOG__EXPERT__VECTOR__STORES__CHROMA__PORT=8000
```

---

## Weaviate Parameters

### Required Parameters
- `url` (string): Weaviate server URL

### Optional Parameters
- `api_key` (string): API key for authentication
- `collection_name` (string, default: "expert_agent_default"): Class name for vectors
- `timeout` (integer, default: 10): Connection timeout in seconds
- `headers` (object): Custom HTTP headers

### Example Configuration
```json
{
  "name": "weaviate_store",
  "store_type": "weaviate",
  "config": {
    "url": "https://weaviate.example.com",
    "api_key": "your-api-key",
    "collection_name": "expert_agent_weaviate",
    "timeout": 30,
    "headers": {
      "X-Custom-Header": "value"
    }
  },
  "enabled": true
}
```

### Environment Variables
```bash
CLOUD_DOG__EXPERT__VECTOR__STORES__WEAVIATE__URL=https://weaviate.example.com
CLOUD_DOG__EXPERT__VECTOR__STORES__WEAVIATE__API_KEY=your-api-key
CLOUD_DOG__EXPERT__VECTOR__STORES__WEAVIATE__COLLECTION_NAME=expert_agent_weaviate
```

---

## OpenSearch Parameters

### Required Parameters
- `host` (string): OpenSearch server hostname or IP address
- `port` (integer, default: 1201): OpenSearch server port

### Optional Parameters
- `username` (string): Username for authentication
- `password` (string): Password for authentication
- `api_key` (string): API key for authentication (alternative to username/password)
- `collection_name` (string, default: "expert_agent_default"): Index name for vectors
- `ssl` (boolean, default: false): Enable SSL/TLS connection
- `verify_certs` (boolean, default: true): Verify SSL certificates
- `timeout` (integer, default: 10): Connection timeout in seconds
- `max_retries` (integer, default: 3): Maximum number of retry attempts
- `retry_on_timeout` (boolean, default: true): Retry on timeout errors

### Example Configuration
```json
{
  "name": "opensearch_store",
  "store_type": "opensearch",
  "config": {
    "host": "opensearch0.internal.example",
    "port": 1201,
    "username": "admin",
    "password": "your-password",
    "collection_name": "expert_agent_opensearch",
    "ssl": false,
    "verify_certs": false,
    "timeout": 30,
    "max_retries": 3,
    "retry_on_timeout": true
  },
  "enabled": true
}
```

### Environment Variables
```bash
CLOUD_DOG__EXPERT__VECTOR_STORES_CONFIG__OPENSEARCH___TEST___HOST=opensearch0.internal.example
CLOUD_DOG__EXPERT__VECTOR_STORES_CONFIG__OPENSEARCH___TEST___PORT=1201
CLOUD_DOG__EXPERT__VECTOR_STORES_CONFIG__OPENSEARCH___TEST___USERNAME=admin
CLOUD_DOG__EXPERT__VECTOR_STORES_CONFIG__OPENSEARCH___TEST___COLLECTION_NAME=expert_agent_opensearch
CLOUD_DOG__EXPERT__VECTOR_STORES_CONFIG__OPENSEARCH___TEST___SSL=false
CLOUD_DOG__EXPERT__VECTOR_STORES_CONFIG__OPENSEARCH___TEST___VERIFY_CERTS=false
```

---

## PGVector Parameters

### Required Parameters
- `database_uri` (string) OR connection components:
  - `host` (string, default: "localhost")
  - `port` (integer, default: 5432)
  - `database` (string, default: "expert_agent")
  - `username` (string, default: "postgres")
  - `password` (string)

### Optional Parameters
- `collection_name` (string, default: "expert_agent_default"): Table name for vectors

### Example Configuration (URI)
```json
{
  "name": "pgvector_store",
  "store_type": "pgvector",
  "config": {
    "database_uri": "postgresql://user:password@host:5432/database",
    "collection_name": "expert_agent_pgvector"
  },
  "enabled": true
}
```

### Example Configuration (Components)
```json
{
  "name": "pgvector_store",
  "store_type": "pgvector",
  "config": {
    "host": "postgres.example.com",
    "port": 5432,
    "database": "expert_agent",
    "username": "postgres",
    "password": "your-password",
    "collection_name": "expert_agent_pgvector"
  },
  "enabled": true
}
```

### Environment Variables
```bash
CLOUD_DOG__EXPERT__VECTOR__STORES__PGVECTOR__DATABASE_URI=postgresql://user:password@host:5432/database
CLOUD_DOG__EXPERT__VECTOR__STORES__PGVECTOR__HOST=postgres.example.com
CLOUD_DOG__EXPERT__VECTOR__STORES__PGVECTOR__PORT=5432
CLOUD_DOG__EXPERT__VECTOR__STORES__PGVECTOR__DATABASE=expert_agent
CLOUD_DOG__EXPERT__VECTOR__STORES__PGVECTOR__USERNAME=postgres
CLOUD_DOG__EXPERT__VECTOR__STORES__PGVECTOR__PASSWORD=your-password
```

---

## Common Parameters

All vector stores support these common parameters:

- `collection_name` (string): Collection/index/table name for vectors
- `enabled` (boolean, default: true): Enable/disable the vector store
- `access_control` (object): Access control settings (user/group permissions)

---

## Vector Store Options

All vector stores support comprehensive **indexing** and **search** options that can be configured via the API or `default.yaml`. Options are organized into:

1. **Common Options** - Shared across all vector stores
2. **Product-Specific Options** - Unique to each vector store type

### Common Indexing Options

These options apply to all vector stores and control how vectors are indexed:

- `vector_dimensionality` (integer, default: 1024): Vector dimension (must match embedding model)
- `distance_metric` (string, default: "cosine"): Distance metric - `l2`, `cosine`, `dot`, `ip`
- `index_type` (string, default: "ann"): Index type - `exact` (brute-force) or `ann` (approximate)
- `ann_algorithm` (string, default: "hnsw"): ANN algorithm - `hnsw`, `ivf`
- `compression` (string, default: "none"): Compression type - `none`, `scalar`, `pq`, `bq`, `rq`, `sq`
- `shards` (integer, default: 1): Number of shards
- `replicas` (integer, default: 0): Number of replicas
- `persistence` (boolean, default: true): Whether to persist data

### Common Search Options

These options apply to all vector stores and control search behavior:

- `limit` / `top_k` (integer, default: 5): Number of results to return
- `filters_enabled` (boolean, default: true): Whether filters are enabled
- `pagination_enabled` (boolean, default: true): Whether pagination is enabled
- `offset` (integer, default: 0): Pagination offset
- `score_threshold` / `min_score` (float, default: 0.0): Minimum score threshold
- `max_distance` (float): Maximum distance threshold
- `return_vectors` / `include_vectors` (boolean, default: false): Whether to return vectors
- `return_payload` / `include_metadata` (boolean, default: true): Whether to return metadata
- `return_distances` / `include_distances` (boolean, default: true): Whether to return distances
- `include_scores` (boolean, default: true): Whether to return scores
- `hybrid_search_enabled` (boolean, default: false): Whether hybrid search is enabled
- `hybrid_search_alpha` (float, default: 0.5): Hybrid search alpha parameter
- `hybrid_search_fusion_strategy` (string, default: "ranked"): Fusion strategy - `ranked`, `relative`

### Product-Specific Options

Each vector store has unique options. See sections below for details.

---

## Chroma Options

### Chroma-Specific Indexing Options

- `hnsw_space` (string, default: "cosine"): HNSW space type - `l2`, `cosine`, `ip`
- `hnsw_construction_ef` (integer, default: 100): HNSW construction EF parameter
- `hnsw_M` (integer, default: 16): HNSW M parameter (number of connections)
- `hnsw_search_ef` (integer, default: 100): HNSW search EF parameter
- `hnsw_num_threads` (integer, default: 0): Number of threads (0 for auto)
- `hnsw_resize_factor` (float, default: 1.2): Resize factor
- `hnsw_batch_size` (integer, default: 10000): Batch size for bruteforce → HNSW transfer
- `hnsw_sync_threshold` (integer, default: 1000): Sync threshold for flush/write

### Chroma-Specific Search Options

- `where_document` (object): Document content filters
- `include` (array): Result projection - `["metadatas", "distances", "documents", "embeddings"]`

### Example with Options
```json
{
  "name": "chroma_with_options",
  "store_type": "chroma",
  "config": {
    "path": "./database/chroma-data",
    "collection_name": "expert_agent_chroma",
    "indexing": {
      "distance_metric": "cosine",
      "index_type": "ann",
      "ann_algorithm": "hnsw"
    },
    "options": {
      "hnsw_space": "cosine",
      "hnsw_construction_ef": 200,
      "hnsw_M": 32,
      "hnsw_search_ef": 100
    },
    "search": {
      "limit": 10,
      "score_threshold": 0.5
    }
  }
}
```

---

## Qdrant Options

### Qdrant-Specific Indexing Options

- `hnsw_m` (integer, default: 16): HNSW M parameter
- `hnsw_ef_construct` (integer, default: 200): HNSW construction EF
- `hnsw_full_scan_threshold` (integer, default: 10000): Full scan threshold
- `hnsw_max_indexing_threads` (integer, default: 0): Max indexing threads (0 for auto)
- `hnsw_on_disk` (boolean, default: false): Whether HNSW is on disk
- `hnsw_payload_m` (integer, default: 16): HNSW payload M
- `quantization_enabled` (boolean, default: false): Whether quantization is enabled
- `quantization_type` (string): Quantization type - `scalar`, `product`, `binary`
- `shard_number` (integer, default: 1): Number of shards
- `replication_factor` (integer, default: 1): Replication factor
- `write_consistency_factor` (integer, default: 1): Write consistency factor
- `on_disk_payload` (boolean, default: false): Whether payload is on disk

### Qdrant-Specific Search Options

- `hnsw_ef` (integer): HNSW search EF (query-time)
- `exact` (boolean, default: false): Whether to use exact search
- `with_payload` (boolean, default: true): Whether to return payload
- `with_vector` (boolean, default: false): Whether to return vectors
- `score_threshold` (float): Score threshold (query-time)

### Example with Options
```json
{
  "name": "qdrant_with_options",
  "store_type": "qdrant",
  "config": {
    "host": "localhost",
    "port": 6333,
    "collection_name": "expert_agent_qdrant",
    "indexing": {
      "distance_metric": "cosine",
      "index_type": "ann"
    },
    "options": {
      "hnsw_m": 32,
      "hnsw_ef_construct": 400,
      "shard_number": 2,
      "replication_factor": 1
    },
    "search": {
      "limit": 10,
      "score_threshold": 0.5
    }
  }
}
```

---

## OpenSearch Options

### OpenSearch-Specific Indexing Options

- `space_type` (string, default: "cosinesimil"): Space type - `cosinesimil`, `l2`, `innerproduct`
- `method` (string, default: "hnsw"): Index method - `hnsw`
- `engine` (string, default: "nmslib"): Engine - `nmslib`, `faiss`
- `ef_construction` (integer, default: 128): HNSW construction EF
- `m` (integer, default: 24): HNSW M parameter
- `ef_search` (integer, default: 100): HNSW search EF
- `index_knn` (boolean, default: true): Whether KNN is enabled
- `index_knn_algo_param_ef_search` (integer, default: 100): Index-level EF search
- `encoder_type` (string): Encoder type - `pq`, `flat`
- `pq_m` (integer): Product quantization M
- `pq_code_size` (integer): Product quantization code size

### OpenSearch-Specific Search Options

- `k` (integer): Number of results (query-time)
- `max_distance` / `min_score` (float): Distance/score thresholds
- `method_parameters` (object): Method parameters (e.g., `{"ef_search": 150}`)
- `rescore` (boolean, default: false): Whether rescore is enabled
- `filter_strategy` (string): Filter strategy - `pre_filter`, `post_filter`

### Example with Options
```json
{
  "name": "opensearch_with_options",
  "store_type": "opensearch",
  "config": {
    "host": "localhost",
    "port": 1201,
    "collection_name": "expert_agent_opensearch",
    "indexing": {
      "distance_metric": "cosine",
      "index_type": "ann"
    },
    "options": {
      "space_type": "cosinesimil",
      "method": "hnsw",
      "engine": "nmslib",
      "ef_construction": 200,
      "m": 32,
      "ef_search": 150
    },
    "search": {
      "limit": 10,
      "score_threshold": 0.5
    }
  }
}
```

---

## Weaviate Options

### Weaviate-Specific Indexing Options

- `vector_index_type` (string, default: "hnsw"): Vector index type - `hnsw`, `flat`, `dynamic`
- `ef_construction` (integer, default: 128): HNSW construction EF
- `max_connections` (integer, default: 64): HNSW max connections
- `dynamic_ef_min` (integer, default: 100): Dynamic EF min
- `dynamic_ef_max` (integer, default: 500): Dynamic EF max
- `dynamic_ef_factor` (integer, default: 8): Dynamic EF factor
- `filter_strategy` (string, default: "acorn"): Filter strategy - `acorn`, `sweeping`
- `flat_search_cutoff` (integer, default: 40000): Flat search cutoff
- `vector_cache_max_objects` (integer, default: 1000000000): Vector cache max objects
- `compression_type` (string, default: "none"): Compression type - `none`, `rq`, `pq`, `bq`, `sq`

### Weaviate-Specific Search Options

- `distance` / `certainty` (float): Distance/certainty thresholds (query-time)
- `autocut` (integer): Autocut parameter
- `hybrid_alpha` (float): Hybrid search alpha
- `hybrid_fusion_strategy` (string): Hybrid fusion strategy - `ranked`, `relative`
- `hybrid_max_vector_distance` (float): Hybrid max vector distance

---

## PGVector Options

### PGVector-Specific Indexing Options

- `vector_type` (string, default: "vector"): Vector type
- `index_type` (string, default: "ivfflat"): Index type - `ivfflat`, `hnsw`
- `opclass` (string, default: "vector_cosine_ops"): Operator class - `vector_l2_ops`, `vector_cosine_ops`, `vector_ip_ops`
- `ivfflat_lists` (integer, default: 100): IVFFlat lists
- `hnsw_m` (integer, default: 16): HNSW M parameter
- `hnsw_ef_construction` (integer, default: 200): HNSW construction EF

### PGVector-Specific Search Options

- `ivfflat_probes` (integer, default: 10): IVFFlat probes (query-time)
- `hnsw_ef_search` (integer, default: 10): HNSW search EF (query-time)
- `iterative_scan` (boolean, default: false): Whether to use iterative scan
- `max_probes` (integer): Max probes for iterative scan
- `max_scan_tuples` (integer): Max scan tuples for iterative scan

---

## Options Usage

### Via Configuration (default.yaml)

Options can be set globally in `default.yaml`:

```yaml
vector_stores_config:
  common:
    indexing:
      distance_metric: "cosine"
      index_type: "ann"
      ann_algorithm: "hnsw"
    searching:
      top_k: 10
      score_threshold: 0.5
  chroma:
    _DEFAULT_:
      hnsw:
        space: "cosine"
        construction_ef: 200
        M: 32
```

### Via API Request

Options can be set or overridden via API:

```json
POST /vector-stores
{
  "name": "my_store",
  "store_type": "qdrant",
  "config": {
    "host": "localhost",
    "port": 6333,
    "indexing": {
      "distance_metric": "cosine",
      "index_type": "ann"
    },
    "options": {
      "hnsw_m": 32,
      "hnsw_ef_construct": 400
    },
    "search": {
      "limit": 10,
      "score_threshold": 0.5
    }
  }
}
```

### Via Query Search Options

Search options can be overridden at query time:

```json
POST /vector-stores/{id}/query
{
  "collection": "my_collection",
  "query": "test query",
  "n_results": 10,
  "search_options": {
    "search": {
      "limit": 10,
      "score_threshold": 0.7,
      "include_vectors": true
    },
    "options": {
      "hnsw_ef": 200
    }
  }
}
```

### Options Merging

When updating a vector store, options are **merged** (not replaced):

- Original options are preserved
- New options are added
- Overlapping options are updated

See [API_DOCUMENTATION.md](API_DOCUMENTATION.md) for complete API details.

---

## Parameter Validation

### Type Validation
- All parameters are validated against their expected types
- Invalid types result in `400 Bad Request` errors

### Required Parameter Validation
- Missing required parameters result in `400 Bad Request` errors
- Provider-specific validation is performed during initialization

### Default Values
- All optional parameters have sensible defaults
- Defaults are applied when parameters are not specified

---

## Configuration Hierarchy

1. **API Request** - Parameters in `POST /vector-stores` request body
2. **Environment Variables** - `CLOUD_DOG__EXPERT__VECTOR__STORES__*`
3. **Config File** - `config.yaml` or `default.yaml`
4. **Provider Defaults** - Built-in defaults

---

## Testing Configuration

### Test Environment Files
- `private/env-test-qdrant` - Qdrant test configuration
- `private/env-test-chroma` - Chroma test configuration
- `private/env-test-opensearch` - OpenSearch test configuration

### Usage
```bash
pytest --env env-test-qdrant
pytest --env env-test-chroma
pytest --env env-test-opensearch
```

---

## Related Documentation

- [API_DOCUMENTATION.md](API_DOCUMENTATION.md) - Vector store API endpoints
- [PARAMETERS.md](PARAMETERS.md) - General configuration parameters
- [ARCHITECTURE.md](ARCHITECTURE.md) - System architecture

---

## Updates and Changelog

### Version 0.1 (2025-01-XX)
- Initial vector store parameter documentation
- Qdrant, Chroma, Weaviate, OpenSearch, PGVector parameters
- Environment variable mappings
- Configuration examples

