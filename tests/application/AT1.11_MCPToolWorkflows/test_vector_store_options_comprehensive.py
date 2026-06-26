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
Application Test: AT1.11 - Vector Store Options Comprehensive Tests

License: Apache 2.0
Ownership: Cloud Dog
Description: Comprehensive tests for vector store options (common and product-specific)

Related Requirements: FR1.3, FR1.30
Related Tasks: T068
Related Architecture: CC4.1.1
Related Tests: AT1.11
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
        "username": f"{base_username}_at1_11_options_{unique_id}",
        "email": build_test_email("at1_11_options", unique_id, base_email),
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
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_chroma_common_indexing_options(api_client, test_user):
    """Test Chroma with common indexing options via API."""
    print("\n[TEST START] test_chroma_common_indexing_options")

    # Create vector store with common indexing options
    store_name = f"chroma_options_{str(uuid.uuid4())[:8]}"
    create_response = api_client.post(
        "/vector-stores",
        json={
            "name": store_name,
            "store_type": "chroma",
            "config": {
                "path": get_config("test.at1_11.chroma.options_path"),
                "collection_name": f"test_collection_{str(uuid.uuid4())[:8]}",
                "indexing": {
                    "distance_metric": "cosine",
                    "index_type": "ann",
                    "ann_algorithm": "hnsw",
                },
            },
        },
    )
    assert create_response.status_code == 200, (
        f"Failed to create vector store: {create_response.text}"
    )
    store_data = create_response.json()
    store_data["id"]

    # Validate response includes options
    config = store_data.get("config", {})
    assert "indexing" in config, "Config should include indexing options"
    assert config["indexing"]["distance_metric"] == "cosine"
    assert config["indexing"]["index_type"] == "ann"

    print("[TEST END] test_chroma_common_indexing_options")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_chroma_product_specific_options(api_client, test_user):
    """Test Chroma with product-specific HNSW options via API."""
    print("\n[TEST START] test_chroma_product_specific_options")

    # Create vector store with Chroma-specific options
    store_name = f"chroma_hnsw_{str(uuid.uuid4())[:8]}"
    create_response = api_client.post(
        "/vector-stores",
        json={
            "name": store_name,
            "store_type": "chroma",
            "config": {
                "path": get_config("test.at1_11.chroma.hnsw_path"),
                "collection_name": f"test_collection_{str(uuid.uuid4())[:8]}",
                "options": {
                    "hnsw_space": "cosine",
                    "hnsw_construction_ef": 300,
                    "hnsw_M": 32,
                    "hnsw_search_ef": 100,
                    "hnsw_num_threads": 8,
                },
            },
        },
    )
    assert create_response.status_code == 200, (
        f"Failed to create vector store: {create_response.text}"
    )
    store_data = create_response.json()

    # Validate response includes product-specific options
    config = store_data.get("config", {})
    assert "options" in config, "Config should include product-specific options"
    assert config["options"]["hnsw_space"] == "cosine"
    assert config["options"]["hnsw_construction_ef"] == 300
    assert config["options"]["hnsw_M"] == 32

    print("[TEST END] test_chroma_product_specific_options")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_qdrant_common_and_product_options(api_client, test_user):
    """Test Qdrant with both common and product-specific options via API."""
    print("\n[TEST START] test_qdrant_common_and_product_options")

    # Get Qdrant config from config system (no hardcoded fallbacks)
    qdrant_host = get_config("vector_stores_config.qdrant._DEFAULT_.host")
    qdrant_port = get_config("vector_stores_config.qdrant._DEFAULT_.port")
    if not qdrant_host or qdrant_port is None:
        pytest.fail("Missing vector_stores_config.qdrant._DEFAULT_.host/port in config (--env)")

    # Create vector store with both common and product-specific options
    store_name = f"qdrant_options_{str(uuid.uuid4())[:8]}"
    create_response = api_client.post(
        "/vector-stores",
        json={
            "name": store_name,
            "store_type": "qdrant",
            "config": {
                "host": qdrant_host,
                "port": qdrant_port,
                "collection_name": f"test_collection_{str(uuid.uuid4())[:8]}",
                "indexing": {
                    "distance_metric": "cosine",
                    "index_type": "ann",
                    "ann_algorithm": "hnsw",
                },
                "options": {
                    "hnsw_m": 32,
                    "hnsw_ef_construct": 400,
                    "shard_number": 2,
                    "replication_factor": 1,
                },
            },
        },
    )
    assert create_response.status_code == 200, (
        f"Failed to create vector store: {create_response.text}"
    )
    store_data = create_response.json()

    # Validate response includes both option types
    config = store_data.get("config", {})
    assert "indexing" in config, "Config should include indexing options"
    assert "options" in config, "Config should include product-specific options"
    assert config["indexing"]["distance_metric"] == "cosine"
    assert config["options"]["hnsw_m"] == 32
    assert config["options"]["hnsw_ef_construct"] == 400

    print("[TEST END] test_qdrant_common_and_product_options")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_opensearch_options(api_client, test_user):
    """Test OpenSearch with options via API."""
    print("\n[TEST START] test_opensearch_options")

    # Get OpenSearch config from config system (no hardcoded fallbacks)
    opensearch_host = get_config("vector_stores_config.opensearch._TEST_.host")
    opensearch_port = get_config("vector_stores_config.opensearch._TEST_.port")
    if not opensearch_host or opensearch_port is None:
        pytest.fail("Missing vector_stores_config.opensearch._TEST_.host/port in config (--env)")

    # Create vector store with OpenSearch options
    store_name = f"opensearch_options_{str(uuid.uuid4())[:8]}"
    create_response = api_client.post(
        "/vector-stores",
        json={
            "name": store_name,
            "store_type": "opensearch",
            "config": {
                "host": opensearch_host,
                "port": opensearch_port,
                "collection_name": f"test_collection_{str(uuid.uuid4())[:8]}",
                "indexing": {"distance_metric": "cosine", "index_type": "ann"},
                "options": {
                    "space_type": "cosinesimil",
                    "method": "hnsw",
                    "engine": "nmslib",
                    "ef_construction": 200,
                    "m": 32,
                    "ef_search": 150,
                },
            },
        },
    )
    assert create_response.status_code == 200, (
        f"Failed to create vector store: {create_response.text}"
    )
    store_data = create_response.json()

    # Validate response includes options
    config = store_data.get("config", {})
    assert "indexing" in config
    assert "options" in config
    assert config["options"]["method"] == "hnsw"
    assert config["options"]["ef_construction"] == 200

    print("[TEST END] test_opensearch_options")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_search_options_override(api_client, test_user):
    """Test that search options can override config defaults via API."""
    print("\n[TEST START] test_search_options_override")

    # Create vector store with default search options
    store_name = f"search_options_{str(uuid.uuid4())[:8]}"
    create_response = api_client.post(
        "/vector-stores",
        json={
            "name": store_name,
            "store_type": "chroma",
            "config": {
                "path": get_config("test.at1_11.chroma.search_path"),
                "collection_name": f"test_collection_{str(uuid.uuid4())[:8]}",
                "search": {"limit": 5, "include_vectors": False},
            },
        },
    )
    assert create_response.status_code == 200
    store_id = create_response.json()["id"]

    # Add a document first
    add_response = api_client.post(
        f"/vector-stores/{store_id}/documents",
        json={
            "collection": create_response.json()["config"]["collection_name"],
            "document": "Test document for search options",
            "metadata": {"category": "test"},
        },
    )
    assert add_response.status_code == 200

    # Query with search options that override config
    query_response = api_client.post(
        f"/vector-stores/{store_id}/query",
        json={
            "collection": create_response.json()["config"]["collection_name"],
            "query": "test",
            "n_results": 10,
            "search_options": {
                "search": {"limit": 10, "include_vectors": True, "score_threshold": 0.5}
            },
        },
    )
    assert query_response.status_code == 200, f"Failed to query: {query_response.text}"
    query_data = query_response.json()

    # Validate response
    assert "results" in query_data
    assert "count" in query_data

    print("[TEST END] test_search_options_override")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_options_merging_on_update(api_client, test_user):
    """Test that options are properly merged when updating vector store via API."""
    print("\n[TEST START] test_options_merging_on_update")

    qdrant_cfg = (
        get_config("vector_stores_config.qdrant._DEFAULT_")
        or get_config("vector_stores_config.qdrant._TEST_")
        or {}
    )
    host = qdrant_cfg.get("host")
    port = qdrant_cfg.get("port")
    if not host or port is None:
        pytest.fail("Qdrant host/port not configured in vector_stores_config.qdrant")

    # Create vector store with initial options
    store_name = f"merge_options_{str(uuid.uuid4())[:8]}"
    create_response = api_client.post(
        "/vector-stores",
        json={
            "name": store_name,
            "store_type": "qdrant",
            "config": {
                "host": host,
                "port": int(port),
                "collection_name": f"test_collection_{str(uuid.uuid4())[:8]}",
                "indexing": {"distance_metric": "cosine"},
                "options": {"hnsw_m": 16},
            },
        },
    )
    assert create_response.status_code == 200
    store_id = create_response.json()["id"]

    # Update with additional options (should merge)
    update_response = api_client.put(
        f"/vector-stores/{store_id}",
        json={"config": {"indexing": {"index_type": "ann"}, "options": {"hnsw_ef_construct": 300}}},
    )
    assert update_response.status_code == 200
    updated_data = update_response.json()

    # Validate options were merged (not replaced)
    config = updated_data.get("config", {})
    assert config["indexing"]["distance_metric"] == "cosine", (
        "Original indexing option should be preserved"
    )
    assert config["indexing"]["index_type"] == "ann", "New indexing option should be added"
    assert config["options"]["hnsw_m"] == 16, "Original product option should be preserved"
    assert config["options"]["hnsw_ef_construct"] == 300, "New product option should be added"

    print("[TEST END] test_options_merging_on_update")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_all_common_search_options(api_client, test_user):
    """Test all common search options work via API."""
    print("\n[TEST START] test_all_common_search_options")

    # Create vector store
    store_name = f"search_all_{str(uuid.uuid4())[:8]}"
    create_response = api_client.post(
        "/vector-stores",
        json={
            "name": store_name,
            "store_type": "chroma",
            "config": {
                "path": get_config("test.at1_11.chroma.all_path"),
                "collection_name": f"test_collection_{str(uuid.uuid4())[:8]}",
            },
        },
    )
    assert create_response.status_code == 200
    store_id = create_response.json()["id"]
    collection = create_response.json()["config"]["collection_name"]

    # Add documents
    message_count = int(get_config("test.at1_10.message_counts.short"))
    for i in range(message_count):
        add_response = api_client.post(
            f"/vector-stores/{store_id}/documents",
            json={
                "collection": collection,
                "document": f"Test document {i}",
                "metadata": {"index": i, "category": "test"},
            },
        )
        assert add_response.status_code == 200

    # Test search with all common options
    query_response = api_client.post(
        f"/vector-stores/{store_id}/query",
        json={
            "collection": collection,
            "query": "test",
            "n_results": 3,
            "filter": {"category": "test"},
            "search_options": {
                "search": {
                    "limit": 3,
                    "offset": 0,
                    "score_threshold": 0.0,
                    "include_vectors": False,
                    "include_metadata": True,
                    "include_distances": True,
                    "include_scores": True,
                }
            },
        },
    )
    assert query_response.status_code == 200, f"Failed to query: {query_response.text}"
    query_data = query_response.json()

    # Validate response structure
    assert "results" in query_data
    assert "count" in query_data
    assert isinstance(query_data["results"], list)
    assert len(query_data["results"]) <= 3

    # Validate result structure
    for result in query_data["results"]:
        assert "id" in result
        assert "document" in result
        assert "metadata" in result
        assert "distance" in result or "score" in result

    print("[TEST END] test_all_common_search_options")

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.vdb, pytest.mark.smtp, pytest.mark.heavy]

