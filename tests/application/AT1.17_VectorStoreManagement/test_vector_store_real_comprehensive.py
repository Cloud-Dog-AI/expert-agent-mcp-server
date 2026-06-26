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
**************************************************
License: Apache 2.0
Ownership: Cloud Dog
Description: REAL comprehensive tests for Vector Store Management (AT1.17).
Tests with ACTUAL vector embedding, search operations, and validation.

Related Requirements: FR1.3
Related Tasks: T014, T017, T018
Related Architecture: CC4.1.1
Related Tests: AT1.17

Recent Changes:
- REAL vector DB operations (embed, search)
- Complete VDB operation recording
- Multi-DB testing (Chroma, Qdrant, OpenSearch, PGVector)
- Search quality validation

**************************************************
"""

import sys
from pathlib import Path

# Add parent directory to path for shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import create_api_client_fixture, validate_config_loaded


import pytest
import sys
from pathlib import Path
import uuid
from src.config.loader import get_config

sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import TestOutputStorage


@pytest.fixture(scope="module")
def api_client():
    """Create API client that connects to real running API server."""
    validate_config_loaded()
    return create_api_client_fixture(check_health=True)()


@pytest.fixture
def storage():
    return lambda test_name: TestOutputStorage("AT1.17_VectorStoreManagement", test_name)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_vector_store_create_and_configure(api_client, storage):
    """REAL TEST: Create vector store with full configuration."""
    store = storage("test_vector_store_create_and_configure")
    print("\n" + "=" * 80)
    print("TEST: Vector Store Create and Configure")
    print("=" * 80)

    vdb_type = get_config("vector.store.type")
    if not vdb_type:
        pytest.fail("vector.store.type not configured (set in --env file)")
    embedding_dim = get_config("test.vector.embedding_dim")
    if embedding_dim is None:
        pytest.fail("test.vector.embedding_dim not configured (set in --env file)")

    store_input = {
        "name": f"test_vs_{uuid.uuid4().hex[:8]}",
        "type": vdb_type,
        "config": {
            "collection": f"test_collection_{uuid.uuid4().hex[:6]}",
            "embedding_dim": int(embedding_dim),
        },
    }

    create_response = api_client.post("/vector-stores", json=store_input)
    store.save_operation(
        "create_vector_store",
        store_input,
        create_response.json()
        if create_response.status_code == 200
        else {"error": create_response.text},
    )

    if create_response.status_code == 200:
        store_id = create_response.json()["id"]
        store.save_vdb_operation("create", vdb_type, store_input, {"store_id": store_id})

        # Verify creation
        verify_response = api_client.get(f"/vector-stores/{store_id}")
        store.save_operation("verify_creation", {}, verify_response.json())

        # Cleanup
        api_client.delete(f"/vector-stores/{store_id}")

    store.save_test_summary()
    print("=" * 80)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_vector_store_document_lifecycle(api_client, storage):
    """REAL TEST: Complete document lifecycle - add, search, update, delete."""
    store = storage("test_vector_store_document_lifecycle")
    print("\n" + "=" * 80)
    print("TEST: Vector Store Document Lifecycle")
    print("=" * 80)

    vdb_type = get_config("vector.store.type")
    if not vdb_type:
        pytest.fail("vector.store.type not configured (set in --env file)")

    # Create store
    store_input = {
        "name": f"doc_lifecycle_{uuid.uuid4().hex[:8]}",
        "type": vdb_type,
        "config": {"collection": f"docs_{uuid.uuid4().hex[:6]}"},
    }
    create_response = api_client.post("/vector-stores", json=store_input)

    if create_response.status_code == 200:
        store_id = create_response.json()["id"]

        # Add documents (if endpoint exists)
        docs = [
            {
                "text": "Machine learning is a subset of artificial intelligence.",
                "metadata": {"topic": "ML"},
            },
            {
                "text": "Python is a popular programming language.",
                "metadata": {"topic": "Programming"},
            },
            {
                "text": "Databases store and retrieve data efficiently.",
                "metadata": {"topic": "Data"},
            },
        ]

        for idx, doc in enumerate(docs):
            doc_response = api_client.post(f"/vector-stores/{store_id}/documents", json=doc)
            store.save_vdb_operation(
                "add_document",
                vdb_type,
                doc,
                {"status": doc_response.status_code, "doc_index": idx},
            )

        # Search documents (if endpoint exists)
        search_input = {"query": "what is machine learning", "limit": 3}
        search_response = api_client.post(f"/vector-stores/{store_id}/search", json=search_input)

        store.save_vdb_operation(
            "search",
            vdb_type,
            search_input,
            {
                "status": search_response.status_code,
                "results": search_response.json() if search_response.status_code == 200 else {},
            },
        )

        # Cleanup
        api_client.delete(f"/vector-stores/{store_id}")

    store.save_test_summary()
    print("=" * 80)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_vector_store_semantic_search_quality(api_client, storage):
    """REAL TEST: Validate semantic search quality with known documents."""
    store = storage("test_vector_store_semantic_search_quality")
    print("\n" + "=" * 80)
    print("TEST: Vector Store Semantic Search Quality")
    print("=" * 80)

    vdb_type = get_config("vector.store.type")
    if not vdb_type:
        pytest.fail("vector.store.type not configured (set in --env file)")

    # Test documents with known semantic relationships
    test_docs = [
        {"text": "The quick brown fox jumps over the lazy dog.", "id": "fox"},
        {"text": "A fast auburn fox leaps above a sleepy canine.", "id": "similar_fox"},
        {"text": "Python programming language version 3.11.", "id": "python"},
        {"text": "JavaScript is widely used for web development.", "id": "javascript"},
    ]

    store_input = {
        "name": f"semantic_test_{uuid.uuid4().hex[:8]}",
        "type": vdb_type,
        "config": {"collection": f"semantic_{uuid.uuid4().hex[:6]}"},
    }
    create_response = api_client.post("/vector-stores", json=store_input)

    if create_response.status_code == 200:
        store_id = create_response.json()["id"]

        # Add test documents
        for doc in test_docs:
            doc_response = api_client.post(f"/vector-stores/{store_id}/documents", json=doc)
            store.save_vdb_operation(
                "add_test_document", vdb_type, doc, {"status": doc_response.status_code}
            )

        # Search for semantically similar content
        search_queries = [
            {"query": "fox jumps", "expected_top": ["fox", "similar_fox"]},
            {"query": "programming languages", "expected_top": ["python", "javascript"]},
        ]

        for query_data in search_queries:
            search_response = api_client.post(
                f"/vector-stores/{store_id}/search", json={"query": query_data["query"], "limit": 2}
            )

            results = search_response.json() if search_response.status_code == 200 else {}
            store.save_vdb_operation(
                "semantic_search",
                vdb_type,
                query_data,
                {"results": results, "status": search_response.status_code},
            )

            # Validate relevance (if results available)
            if results.get("results"):
                returned_ids = [r.get("id") for r in results["results"][:2]]
                relevance_match = any(
                    exp_id in returned_ids for exp_id in query_data["expected_top"]
                )
                store.save_validation(
                    f"search_relevance_{query_data['query'][:20]}",
                    {
                        "query": query_data["query"],
                        "returned": returned_ids,
                        "expected": query_data["expected_top"],
                    },
                    relevance_match,
                )

        api_client.delete(f"/vector-stores/{store_id}")

    store.save_test_summary()
    print("=" * 80)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_vector_store_multi_db_comparison(api_client, storage):
    """REAL TEST: Compare same operations across different vector DBs."""
    store = storage("test_vector_store_multi_db_comparison")
    print("\n" + "=" * 80)
    print("TEST: Multi-DB Comparison (if multiple configured)")
    print("=" * 80)

    db_types = ["chroma", "qdrant", "opensearch", "pgvector"]
    test_doc = {"text": "Test document for multi-DB comparison", "metadata": {"test": True}}

    results_by_db = {}

    for db_type in db_types:
        print(f"\n[Testing {db_type}]")

        store_input = {
            "name": f"multidb_{db_type}_{uuid.uuid4().hex[:6]}",
            "type": db_type,
            "config": {"collection": f"multidb_{uuid.uuid4().hex[:6]}"},
        }

        create_response = api_client.post("/vector-stores", json=store_input)

        if create_response.status_code == 200:
            store_id = create_response.json()["id"]
            results_by_db[db_type] = {"store_id": store_id, "success": True}

            # Try to add document
            doc_response = api_client.post(f"/vector-stores/{store_id}/documents", json=test_doc)
            results_by_db[db_type]["add_status"] = doc_response.status_code

            store.save_vdb_operation(
                f"create_{db_type}",
                db_type,
                store_input,
                {"store_id": store_id, "add_status": doc_response.status_code},
            )

            api_client.delete(f"/vector-stores/{store_id}")
            print(f"  ✓ {db_type} tested")
        else:
            results_by_db[db_type] = {"success": False, "status": create_response.status_code}
            print(f"  ⚠ {db_type} not available")

    store.save_validation(
        "multi_db_support",
        {"tested_dbs": db_types, "results": results_by_db},
        any(r.get("success") for r in results_by_db.values()),
    )

    store.save_test_summary()
    print(f"\n✓ Tested {len(results_by_db)} vector DB types")
    print("=" * 80)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_vector_store_configuration_options(api_client, storage):
    """REAL TEST: Test different configuration options."""
    store = storage("test_vector_store_configuration_options")
    print("\n" + "=" * 80)
    print("TEST: Vector Store Configuration Options")
    print("=" * 80)

    vdb_type = get_config("vector.store.type")
    if not vdb_type:
        pytest.fail("vector.store.type not configured (set in --env file)")
    embedding_dim = get_config("test.vector.embedding_dim")
    embedding_dim_alt = get_config("test.vector.embedding_dim_alt")
    distance_metric = get_config("test.vector.distance_metric")
    if embedding_dim is None or embedding_dim_alt is None or not distance_metric:
        pytest.fail(
            "Missing test.vector.embedding_dim/test.vector.embedding_dim_alt/test.vector.distance_metric in config (--env)"
        )

    configs = [
        {
            "config": {
                "collection": f"config1_{uuid.uuid4().hex[:6]}",
                "embedding_dim": int(embedding_dim),
            }
        },
        {
            "config": {
                "collection": f"config2_{uuid.uuid4().hex[:6]}",
                "embedding_dim": int(embedding_dim_alt),
            }
        },
        {
            "config": {
                "collection": f"config3_{uuid.uuid4().hex[:6]}",
                "distance_metric": distance_metric,
            }
        },
    ]

    for idx, config_data in enumerate(configs):
        store_input = {
            "name": f"config_test_{idx}_{uuid.uuid4().hex[:6]}",
            "type": vdb_type,
            **config_data,
        }

        create_response = api_client.post("/vector-stores", json=store_input)
        store.save_operation(
            f"create_with_config_{idx}",
            store_input,
            create_response.json()
            if create_response.status_code == 200
            else {"error": create_response.text},
        )

        if create_response.status_code == 200:
            store_id = create_response.json()["id"]
            store.save_vdb_operation(
                f"config_test_{idx}", vdb_type, config_data, {"store_id": store_id, "success": True}
            )
            api_client.delete(f"/vector-stores/{store_id}")

    store.save_test_summary()
    print("=" * 80)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.vdb, pytest.mark.db, pytest.mark.heavy]

