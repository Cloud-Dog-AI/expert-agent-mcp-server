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
Application Test: AT1.11 - Vector Store Production-Like Scenarios

License: Apache 2.0
Ownership: Cloud Dog
Description: Production-like scenario tests for all 5 vector stores with comprehensive options

Related Requirements: FR1.3, FR1.30
Related Tasks: T068
Related Architecture: CC4.1.1
Related Tests: AT1.11

Test Organization:
- Chroma tests: No external service required (uses local file storage)
- Qdrant tests: Requires Qdrant service - run with: pytest --env env-test-qdrant
- OpenSearch tests: Requires OpenSearch service - run with: pytest --env env-test-opensearch
"""

import sys
from pathlib import Path

# Add parent directory to path for shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import build_test_email, create_api_client_fixture, validate_config_loaded


import pytest
import uuid
from src.config.loader import get_config


@pytest.fixture(scope="module")
def api_client():
    """Create API client that connects to real running API server."""
    validate_config_loaded()
    return create_api_client_fixture(check_health=True)()


@pytest.fixture
def test_user_credentials(test_env_file, test_secrets_file):
    """Get test user credentials from configuration system."""
    from src.config.loader import load_config

    load_config.cache_clear()

    base_username = get_config("test.user.username")
    base_email = get_config("test.user.email")
    base_password = get_config("test.user.password")

    if not base_username or not base_email or not base_password:
        pytest.fail(
            "Test user credentials not configured. Set test.user.* keys in your --env file."
        )

    unique_id = str(uuid.uuid4())[:8]
    return {
        "username": f"{base_username}_prod_{unique_id}",
        "email": build_test_email("prod", unique_id, base_email),
        "password": base_password,
    }


@pytest.fixture
def test_user(api_client, test_user_credentials):
    """Create test user via API."""
    creds = test_user_credentials

    response = api_client.post(
        "/users",
        json={
            "username": creds["username"],
            "email": creds["email"],
            "password": creds["password"],
        },
    )
    assert response.status_code == 200, f"Failed to create test user: {response.text}"
    user_data = response.json()

    yield user_data

    # Cleanup via API
    try:
        api_client.delete(f"/users/{user_data['id']}")
    except Exception:
        pass


def _run_full_workflow_test(api_client, store_name, store_type, config):
    """
    Helper function to run the full workflow test for any vector store.

    Scenario:
    1. Create vector store with production-like options
    2. Add multiple documents with metadata
    3. Query with various search options
    4. Update documents
    5. Delete documents
    6. Verify all operations work correctly
    """
    print(f"\n[PRODUCTION SCENARIO] {store_type} - Full Workflow")

    # Step 1: Create vector store with production-like options
    create_response = api_client.post(
        "/vector-stores",
        json={"name": store_name, "store_type": store_type, "config": config, "enabled": True},
    )
    assert create_response.status_code == 200, (
        f"Vector store {store_type} create failed: {create_response.status_code} {create_response.text}"
    )

    store_data = create_response.json()
    store_id = store_data["id"]
    collection = config["collection_name"]

    # Validate store was created with options
    assert store_data["enabled"] is True
    assert "config" in store_data
    assert (
        store_data["config"].get("indexing") is not None
        or store_data["config"].get("options") is not None
    )

    def _assert_or_skip(resp, action: str):
        if resp.status_code == 503 and "not available" in resp.text.lower():
            pytest.fail(f"Vector store backend unavailable: {resp.text}")
        assert resp.status_code == 200, (
            f"{store_type} {action} failed: {resp.status_code} {resp.text}"
        )

    # Step 2: Add multiple documents with metadata
    documents = [
        {
            "text": "Python is a high-level programming language",
            "metadata": {"category": "programming", "language": "python"},
        },
        {
            "text": "JavaScript is used for web development",
            "metadata": {"category": "programming", "language": "javascript"},
        },
        {
            "text": "Machine learning is a subset of AI",
            "metadata": {"category": "ai", "topic": "ml"},
        },
        {
            "text": "Vector databases store embeddings",
            "metadata": {"category": "database", "type": "vector"},
        },
        {"text": "REST APIs use HTTP methods", "metadata": {"category": "api", "protocol": "http"}},
    ]

    added_ids = []
    for doc in documents:
        add_response = api_client.post(
            f"/vector-stores/{store_id}/documents",
            json={
                "collection": collection,
                "document": doc["text"],
                "metadata": doc["metadata"],
                "id": str(uuid.uuid4()),
            },
        )
        _assert_or_skip(add_response, "add document")
        added_ids.append(add_response.json()["id"])

    assert len(added_ids) == 5, "Should have added 5 documents"

    # Step 3: Query with various search options
    # Test 3a: Basic query
    query1_response = api_client.post(
        f"/vector-stores/{store_id}/query",
        json={"collection": collection, "query": "programming language", "n_results": 5},
    )
    _assert_or_skip(query1_response, "basic query")
    query1_data = query1_response.json()
    assert "results" in query1_data
    assert len(query1_data["results"]) > 0

    # Test 3b: Query with search options override
    query2_response = api_client.post(
        f"/vector-stores/{store_id}/query",
        json={
            "collection": collection,
            "query": "programming",
            "n_results": 3,
            "filter": {"category": "programming"},
            "search_options": {
                "search": {
                    "limit": 3,
                    "score_threshold": 0.0,
                    "include_metadata": True,
                    "include_distances": True,
                }
            },
        },
    )
    _assert_or_skip(query2_response, "query with options")
    query2_data = query2_response.json()
    assert "results" in query2_data
    assert len(query2_data["results"]) <= 3

    # Validate result structure
    for result in query2_data["results"]:
        assert "id" in result
        assert "document" in result
        assert "metadata" in result
        assert "distance" in result or "score" in result

    # Step 4: Update a document
    if added_ids:
        update_response = api_client.put(
            f"/vector-stores/{store_id}/documents/{added_ids[0]}",
            params={"collection": collection},
            json={
                "document": "Python is a versatile high-level programming language",
                "metadata": {"category": "programming", "language": "python", "updated": True},
            },
        )
        _assert_or_skip(update_response, "update document")

    # Step 5: Delete a document
    if len(added_ids) > 1:
        delete_response = api_client.delete(
            f"/vector-stores/{store_id}/documents/{added_ids[1]}", params={"collection": collection}
        )
        _assert_or_skip(delete_response, "delete document")

    # Step 6: Verify final state with query
    final_query_response = api_client.post(
        f"/vector-stores/{store_id}/query",
        json={"collection": collection, "query": "programming", "n_results": 10},
    )
    _assert_or_skip(final_query_response, "final query")
    final_data = final_query_response.json()
    assert "results" in final_data

    print(f"[PRODUCTION SCENARIO] {store_type} - Full Workflow COMPLETE")


# ============================================================================
# CHROMA TESTS - No external service required
# ============================================================================
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.chroma
def test_production_scenario_full_workflow_chroma(api_client, test_user):
    """
    Production scenario: Full workflow for Chroma.

    Environment: No special environment file required (uses local file storage)
    Run: pytest tests/application/AT1.11_MCPToolWorkflows/test_vector_store_production_scenarios.py::test_production_scenario_full_workflow_chroma
    """
    store_name = f"prod_chroma_{str(uuid.uuid4())[:8]}"
    config = {
        "path": get_config("test.at1_11.chroma.prod_path"),
        "collection_name": f"prod_collection_{str(uuid.uuid4())[:8]}",
        "indexing": {"distance_metric": "cosine", "index_type": "ann", "ann_algorithm": "hnsw"},
        "options": {
            "hnsw_space": "cosine",
            "hnsw_construction_ef": 200,
            "hnsw_M": 32,
            "hnsw_search_ef": 100,
        },
        "search": {"limit": 10, "score_threshold": 0.5},
    }
    _run_full_workflow_test(api_client, store_name, "chroma", config)


# ============================================================================
# QDRANT TESTS - Requires Qdrant service
# ============================================================================
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.qdrant
@pytest.mark.requires_external_service
def test_production_scenario_full_workflow_qdrant(
    api_client, test_user, test_env_file, test_secrets_file
):
    """
    Production scenario: Full workflow for Qdrant.

    Environment: Requires Qdrant service
    Run: pytest --env env-test-qdrant tests/application/AT1.11_MCPToolWorkflows/test_vector_store_production_scenarios.py::test_production_scenario_full_workflow_qdrant
    """
    from src.config.loader import load_config

    load_config.cache_clear()

    # Get Qdrant config from config system (loaded via --env)
    qdrant_host = get_config("vector_stores_config.qdrant._DEFAULT_.host")
    qdrant_port = get_config("vector_stores_config.qdrant._DEFAULT_.port")
    qdrant_api_key = get_config("vector_stores_config.qdrant._DEFAULT_.api_key")
    qdrant_collection = get_config("vector_stores_config.qdrant._DEFAULT_.collection_name")

    if not qdrant_host or qdrant_port is None or qdrant_api_key is None or not qdrant_collection:
        pytest.fail(
            "Qdrant config missing (host/port/api_key/collection_name). Check your --env file."
        )

    unique_id = str(uuid.uuid4())[:8]
    store_name = f"prod_qdrant_{unique_id}"
    config = {
        "host": qdrant_host,
        "port": int(qdrant_port),
        "api_key": qdrant_api_key,
        # Use unique collection to avoid collisions
        "collection_name": f"{qdrant_collection}_{unique_id}",
        "indexing": {"distance_metric": "cosine", "index_type": "ann", "ann_algorithm": "hnsw"},
        "options": {
            "hnsw_m": 32,
            "hnsw_ef_construct": 400,
            "shard_number": 1,
            "replication_factor": 1,
        },
        "search": {"limit": 10, "score_threshold": 0.5},
    }
    _run_full_workflow_test(api_client, store_name, "qdrant", config)


# ============================================================================
# OPENSEARCH TESTS - Requires OpenSearch service
# ============================================================================
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.opensearch
@pytest.mark.requires_external_service
def test_production_scenario_full_workflow_opensearch(
    api_client, test_user, test_env_file, test_secrets_file
):
    """
    Production scenario: Full workflow for OpenSearch.

    Environment: Requires OpenSearch service
    Run: pytest --env env-test-opensearch tests/application/AT1.11_MCPToolWorkflows/test_vector_store_production_scenarios.py::test_production_scenario_full_workflow_opensearch
    """
    from src.config.loader import load_config

    load_config.cache_clear()

    # Get OpenSearch config from config system (loaded via --env)
    opensearch_host = get_config("vector_stores_config.opensearch._TEST_.host") or get_config(
        "vector_stores_config.opensearch._DEFAULT_.host"
    )
    opensearch_port = get_config("vector_stores_config.opensearch._TEST_.port") or get_config(
        "vector_stores_config.opensearch._DEFAULT_.port"
    )
    opensearch_username = get_config(
        "vector_stores_config.opensearch._TEST_.username"
    ) or get_config("vector_stores_config.opensearch._DEFAULT_.username")
    opensearch_password = get_config(
        "vector_stores_config.opensearch._TEST_.password"
    ) or get_config("vector_stores_config.opensearch._DEFAULT_.password")
    opensearch_collection = get_config(
        "vector_stores_config.opensearch._TEST_.collection_name"
    ) or get_config("vector_stores_config.opensearch._DEFAULT_.collection_name")

    if (
        not opensearch_host
        or opensearch_port is None
        or not opensearch_username
        or opensearch_password is None
        or not opensearch_collection
    ):
        pytest.fail(
            "OpenSearch config missing (host/port/username/password/collection_name). Check your --env file."
        )

    store_name = f"prod_opensearch_{str(uuid.uuid4())[:8]}"
    config = {
        "host": opensearch_host,
        "port": int(opensearch_port),
        "username": opensearch_username,
        "password": opensearch_password,
        "collection_name": opensearch_collection,
        "ssl": False,
        "verify_certs": False,
        "indexing": {"distance_metric": "cosine", "index_type": "ann"},
        "options": {
            "space_type": "cosinesimil",
            "method": "hnsw",
            "engine": "nmslib",
            "ef_construction": 200,
            "m": 32,
            "ef_search": 150,
        },
        "search": {"limit": 10, "score_threshold": 0.5},
    }
    _run_full_workflow_test(api_client, store_name, "opensearch", config)


# ============================================================================
# COMMON TESTS - Work with any vector store
# ============================================================================
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.chroma
def test_production_scenario_options_override(api_client, test_user):
    """
    Production scenario: Options override at query time.

    Environment: No special environment file required
    Run: pytest tests/application/AT1.11_MCPToolWorkflows/test_vector_store_production_scenarios.py::test_production_scenario_options_override
    """
    print("\n[PRODUCTION SCENARIO] Options Override")

    # Create store with default search options
    store_name = f"prod_override_{str(uuid.uuid4())[:8]}"
    create_response = api_client.post(
        "/vector-stores",
        json={
            "name": store_name,
            "store_type": "chroma",
            "config": {
                "path": get_config("test.at1_11.chroma.prod_override_path"),
                "collection_name": f"override_collection_{str(uuid.uuid4())[:8]}",
                "search": {"limit": 5, "score_threshold": 0.3, "include_vectors": False},
            },
        },
    )
    assert create_response.status_code == 200
    store_id = create_response.json()["id"]
    collection = create_response.json()["config"]["collection_name"]

    # Add documents
    message_count = int(get_config("test.at1_10.message_counts.medium"))
    for i in range(message_count):
        api_client.post(
            f"/vector-stores/{store_id}/documents",
            json={
                "collection": collection,
                "document": f"Test document {i} with content about topic {i % 3}",
                "metadata": {"topic": i % 3, "index": i},
            },
        )

    # Query with override (should use override, not defaults)
    query_response = api_client.post(
        f"/vector-stores/{store_id}/query",
        json={
            "collection": collection,
            "query": "topic",
            "n_results": 3,  # Override default limit of 5
            "search_options": {
                "search": {
                    "limit": 3,
                    "score_threshold": 0.0,  # Override default of 0.3
                    "include_vectors": True,  # Override default of False
                }
            },
        },
    )
    assert query_response.status_code == 200
    query_data = query_response.json()

    # Verify override worked
    assert len(query_data["results"]) <= 3, "Should respect override limit of 3"

    print("[PRODUCTION SCENARIO] Options Override COMPLETE")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.qdrant
@pytest.mark.requires_external_service
def test_production_scenario_options_merging(
    api_client, test_user, test_env_file, test_secrets_file
):
    """
    Production scenario: Options merging on update.

    Environment: Requires Qdrant service
    Run: pytest --env env-test-qdrant tests/application/AT1.11_MCPToolWorkflows/test_vector_store_production_scenarios.py::test_production_scenario_options_merging
    """
    from src.config.loader import load_config

    load_config.cache_clear()

    print("\n[PRODUCTION SCENARIO] Options Merging")

    # Get Qdrant config from config system (loaded via --env)
    qdrant_host = get_config("vector_stores_config.qdrant._DEFAULT_.host")
    qdrant_port = get_config("vector_stores_config.qdrant._DEFAULT_.port")
    qdrant_api_key = get_config("vector_stores_config.qdrant._DEFAULT_.api_key")
    qdrant_collection = get_config("vector_stores_config.qdrant._DEFAULT_.collection_name")

    if not qdrant_host or qdrant_port is None or qdrant_api_key is None or not qdrant_collection:
        pytest.fail(
            "Qdrant config missing (host/port/api_key/collection_name). Check your --env file."
        )

    # Create with initial options
    store_name = f"prod_merge_{str(uuid.uuid4())[:8]}"
    create_response = api_client.post(
        "/vector-stores",
        json={
            "name": store_name,
            "store_type": "qdrant",
            "config": {
                "host": qdrant_host,
                "port": int(qdrant_port),
                "api_key": qdrant_api_key,
                # Use configured collection to avoid Qdrant-side collection-creation issues
                "collection_name": qdrant_collection,
                "indexing": {"distance_metric": "cosine"},
                "options": {"hnsw_m": 16},
            },
        },
    )
    assert create_response.status_code == 200, (
        f"Qdrant create failed: {create_response.status_code} {create_response.text}"
    )

    store_id = create_response.json()["id"]

    # Update with additional options
    update_response = api_client.put(
        f"/vector-stores/{store_id}",
        json={
            "config": {
                "indexing": {
                    "index_type": "ann"  # Add new indexing option
                },
                "options": {
                    "hnsw_ef_construct": 300  # Add new product option
                },
                "search": {
                    "limit": 10  # Add new search option
                },
            }
        },
    )
    assert update_response.status_code == 200
    updated_data = update_response.json()

    # Verify merging (original options preserved, new options added)
    config = updated_data.get("config", {})
    assert config["indexing"]["distance_metric"] == "cosine", "Original option should be preserved"
    assert config["indexing"]["index_type"] == "ann", "New option should be added"
    assert config["options"]["hnsw_m"] == 16, "Original product option should be preserved"
    assert config["options"]["hnsw_ef_construct"] == 300, "New product option should be added"
    assert config["search"]["limit"] == 10, "New search option should be added"

    print("[PRODUCTION SCENARIO] Options Merging COMPLETE")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.chroma
def test_production_scenario_high_performance_config(api_client, test_user):
    """
    Production scenario: High-performance configuration.

    Environment: No special environment file required
    Run: pytest tests/application/AT1.11_MCPToolWorkflows/test_vector_store_production_scenarios.py::test_production_scenario_high_performance_config
    """
    print("\n[PRODUCTION SCENARIO] High-Performance Config")

    # Create with high-performance options
    store_name = f"prod_perf_{str(uuid.uuid4())[:8]}"
    create_response = api_client.post(
        "/vector-stores",
        json={
            "name": store_name,
            "store_type": "chroma",
            "config": {
                "path": get_config("test.at1_11.chroma.prod_perf_path"),
                "collection_name": f"perf_collection_{str(uuid.uuid4())[:8]}",
                "indexing": {
                    "distance_metric": "cosine",
                    "index_type": "ann",
                    "ann_algorithm": "hnsw",
                },
                "options": {
                    "hnsw_construction_ef": 300,  # Higher for better quality
                    "hnsw_M": 32,  # Higher for better recall
                    "hnsw_search_ef": 200,  # Higher for better recall
                    "hnsw_num_threads": 8,  # Parallel processing
                },
                "search": {"limit": 20, "score_threshold": 0.0},
            },
        },
    )
    assert create_response.status_code == 200
    store_id = create_response.json()["id"]
    collection = create_response.json()["config"]["collection_name"]

    # Add batch of documents
    batch_size = 20
    for i in range(batch_size):
        api_client.post(
            f"/vector-stores/{store_id}/documents",
            json={
                "collection": collection,
                "document": f"High-performance test document {i} with detailed content about various topics including technology, science, and engineering",
                "metadata": {"batch": i // 5, "index": i},
            },
        )

    # Query with performance options
    query_response = api_client.post(
        f"/vector-stores/{store_id}/query",
        json={
            "collection": collection,
            "query": "technology science engineering",
            "n_results": 10,
            "search_options": {
                "search": {"limit": 10, "include_metadata": True, "include_distances": True}
            },
        },
    )
    assert query_response.status_code == 200
    query_data = query_response.json()

    # Verify results
    assert "results" in query_data
    assert len(query_data["results"]) <= 10

    print("[PRODUCTION SCENARIO] High-Performance Config COMPLETE")

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.vdb, pytest.mark.db, pytest.mark.smtp, pytest.mark.heavy]
