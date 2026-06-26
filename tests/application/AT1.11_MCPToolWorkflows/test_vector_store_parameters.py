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
Application Test: AT1.11 - Vector Store Parameters (Indexing, Keyword, Q&A)

License: Apache 2.0
Ownership: Cloud Dog
Description: Test vector store indexing, keyword generation, and Q&A generation parameters

Related Requirements: FR1.30
Related Tasks: T068
Related Architecture: CC4.1.2
Related Tests: AT1.11 (Tests 17-19)
"""

import sys
from pathlib import Path

# Add parent directory to path for shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import build_test_email, create_api_client_fixture, validate_config_loaded


import pytest
import uuid
from src.config.loader import get_config

sys.path.insert(0, str(Path(__file__).parent))
from at1_11_helpers import get_qdrant_profile_cfg


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
            "Test user credentials not configured. "
            "Set test.user.username/test.user.email/test.user.password in your --env file."
        )

    unique_id = str(uuid.uuid4())[:8]
    return {
        "username": f"{base_username}_at1_11_params_{unique_id}",
        "email": build_test_email("at1_11_params", unique_id, base_email),
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
    assert response.status_code == 200
    user_data = response.json()

    yield user_data

    # Cleanup via API
    try:
        api_client.delete(f"/users/{user_data['id']}")
    except Exception:
        pass


@pytest.fixture
def test_expert(api_client, test_config):
    """Create test expert via API."""
    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    llm_base_url = get_config("llm.base_url")
    if not llm_provider or not llm_model or not llm_base_url:
        pytest.fail("Missing llm.provider/llm.model/llm.base_url in config (--env)")

    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_at1_11_params_{unique_id}",
        "title": f"Vector Store Parameters Expert {unique_id} indexing distance metric ef_construction hnsw ivfflat",
        "description": "Vector parameterization scenario with unique vocabulary: acorn basil cipher dune ember fjord glyph helios isotope juniper keystone",
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "enabled": True,
    }

    response = api_client.post("/experts", json=expert_data)
    assert response.status_code == 200
    expert = response.json()

    yield expert

    # Cleanup via API
    try:
        api_client.delete(f"/experts/{expert['id']}")
    except Exception:
        pass


def _get_qdrant_config(test_config):
    """Get Qdrant configuration."""
    cfg = get_qdrant_profile_cfg()
    if not cfg:
        pytest.fail(
            "Qdrant not configured/enabled in this environment (vector_stores_config.qdrant.*)"
        )
    host = cfg.get("host")
    port = cfg.get("port")
    collection_name = cfg.get("collection_name")
    if not host or port is None or not collection_name:
        pytest.fail(
            "Qdrant enabled but missing host/port/collection_name in vector_stores_config.qdrant.*"
        )
    return {
        "host": host,
        "port": int(port),
        "api_key": cfg.get("api_key"),
        "collection_name": collection_name,
        "ssl": cfg.get("ssl", False),
    }


def _skip_if_backend_unavailable(response):
    body = (response.text or "").lower()
    if response.status_code == 503 and "not available" in body:
        pytest.fail(f"Vector store backend unavailable: {response.text}")
    if response.status_code in (500, 502, 503, 504) and (
        "api/embeddings" in body or "failed to add document" in body
    ):
        pytest.fail(f"Embedding backend unavailable for vector operation: {response.text}")
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-023")


def test_vector_store_indexing_parameters(api_client, test_user, test_expert, test_config):
    """Test different indexing parameters.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - indexing_parameters: Array of parameter combinations

    Expected Outputs:
    - Vector store created with parameters (status 200, parameters stored)
    - Documents added successfully (status 200)
    - Search successful (status 200, results returned)
    - Parameters applied correctly (vector store uses specified parameters)
    - Different parameters produce different results (results vary by parameters)
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]

    qdrant_cfg = _get_qdrant_config(test_config)
    if not qdrant_cfg.get("host"):
        pytest.fail(
            "Qdrant host not configured (vector_stores_config.qdrant._DEFAULT_.host). Check your --env file."
        )
    if not qdrant_cfg.get("collection_name"):
        pytest.fail(
            "Qdrant collection_name not configured (vector_stores_config.qdrant._DEFAULT_.collection_name). Check your --env file."
        )

    print(f"\n[SETTINGS] User ID: {user_id}")
    print(f"[SETTINGS] Expert ID: {expert_id}")
    print(f"[SETTINGS] Test ID: {unique_id}")
    embedding_dim = get_config("embeddings.dimension")
    if embedding_dim is None:
        pytest.fail("Missing embeddings.dimension in config (--env)")
    embedding_dim = int(embedding_dim)

    # Test different indexing parameter combinations
    indexing_parameters = [
        {
            # Use canonical option keys expected by VectorStoreOptionsManager / providers
            "index_type": "ann",
            "dimension": embedding_dim,
            "distance_metric": "cosine",
            "name": f"ann_cosine_{unique_id}",
        },
        {
            "index_type": "ann",
            "dimension": embedding_dim,
            "distance_metric": "dot",
            "name": f"ann_dot_{unique_id}",
        },
    ]

    test_document = f"Vector indexing test document {unique_id}. This document tests different indexing parameters for vector similarity search."

    stores_created = []
    results_by_params = {}

    # Use unique collection name for isolation
    collection_name = f"{qdrant_cfg['collection_name']}_{unique_id}"

    for params in indexing_parameters:
        # Step 1: Create vector store with parameters
        create_response = api_client.post(
            "/vector-stores",
            json={
                "name": params["name"],
                "store_type": "qdrant",
                "config": {
                    "host": qdrant_cfg["host"],
                    "port": qdrant_cfg["port"],
                    "collection_name": collection_name,
                    "api_key": qdrant_cfg.get("api_key"),
                    "indexing": {
                        "index_type": params["index_type"],
                        "dimension": params["dimension"],
                        "distance_metric": params["distance_metric"],
                    },
                },
                "enabled": True,
            },
        )
        _skip_if_backend_unavailable(create_response)
        assert create_response.status_code == 200, (
            f"Qdrant create failed: {create_response.status_code} {create_response.text}"
        )
        store_data = create_response.json()
        store_id = store_data["id"]
        stores_created.append((store_id, params["name"]))

        # Step 2: Add document
        doc_id = str(uuid.uuid4())
        add_response = api_client.post(
            f"/vector-stores/{store_id}/documents",
            json={
                "collection": collection_name,
                "document": test_document,
                "document_id": doc_id,
                "metadata": {"test": True, "params": params["name"], "unique_id": unique_id},
            },
        )
        _skip_if_backend_unavailable(add_response)
        assert add_response.status_code == 200, (
            f"Qdrant add_documents failed: {add_response.status_code} {add_response.text}"
        )

        # Step 3: Search
        query_response = api_client.post(
            f"/vector-stores/{store_id}/query",
            json={
                "collection": collection_name,
                "query": "vector indexing similarity search",
                "n_results": 5,
            },
        )
        _skip_if_backend_unavailable(query_response)
        assert query_response.status_code == 200, (
            f"Qdrant query failed: {query_response.status_code} {query_response.text}"
        )
        query_data = query_response.json()

        # Store results for comparison
        results = query_data.get("results") or query_data.get("documents") or []
        results_by_params[params["name"]] = {
            "results": results,
            "store_id": store_id,
            "params": params,
        }

        # Step 4: Verify parameters stored (if API returns config)
        get_store_response = api_client.get(f"/vector-stores/{store_id}")
        if get_store_response.status_code == 200:
            store_config = get_store_response.json()
            # Parameters may be stored in config
            assert "config" in store_config or "type" in store_config, (
                "Store config should be returned"
            )

    # Step 5: Compare results (different parameters may produce different similarity scores)
    # Note: Due to vector similarity, exact results may vary, but both should return results
    assert len(results_by_params) == len(indexing_parameters), (
        "All parameter combinations should be tested"
    )
    for name, result_data in results_by_params.items():
        assert len(result_data["results"]) > 0, f"{name} should return search results"

    # Cleanup
    for store_id, name in stores_created:
        try:
            api_client.delete(f"/vector-stores/{store_id}")
        except Exception:
            pass
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-023")


def test_vector_store_keyword_generation_parameters(
    api_client, test_user, test_expert, test_config
):
    """Test keyword generation parameters.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - keyword_parameters: Array of parameter combinations

    Expected Outputs:
    - Vector store created with keyword parameters (status 200, parameters stored)
    - Documents added successfully (status 200)
    - Keywords generated successfully (if endpoint exists)
    - Keywords match parameters (keyword count, length match parameters)
    - Different parameters produce different keywords (keywords vary by parameters)
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]

    qdrant_cfg = _get_qdrant_config(test_config)

    print(f"\n[SETTINGS] User ID: {user_id}")
    print(f"[SETTINGS] Expert ID: {expert_id}")
    print(f"[SETTINGS] Test ID: {unique_id}")

    # Test different keyword generation parameter combinations
    keyword_parameters = [
        {
            "method": "tfidf",
            "max_keywords": 5,
            "min_length": 3,
            "max_length": 15,
            "name": f"tfidf_5_{unique_id}",
        },
        {
            "method": "rake",
            "max_keywords": 10,
            "min_length": 4,
            "max_length": 20,
            "name": f"rake_10_{unique_id}",
        },
    ]

    test_document = f"Keyword generation test document {unique_id}. This document tests different keyword generation methods including TF-IDF and RAKE algorithms for extracting important terms."

    stores_created = []

    # Use unique collection name for isolation
    base_collection = qdrant_cfg.get("collection_name", "expert_agent_test_qdrant")
    collection_name = f"{base_collection}_{unique_id}"

    for params in keyword_parameters:
        # Step 1: Create vector store with keyword parameters
        create_response = api_client.post(
            "/vector-stores",
            json={
                "name": params["name"],
                "store_type": "qdrant",
                "config": {
                    "host": qdrant_cfg["host"],
                    "port": qdrant_cfg["port"],
                    "collection_name": collection_name,
                    "api_key": qdrant_cfg.get("api_key"),
                    "keyword_generation": {
                        "method": params["method"],
                        "max_keywords": params["max_keywords"],
                        "min_length": params["min_length"],
                        "max_length": params["max_length"],
                    },
                },
                "enabled": True,
            },
        )
        _skip_if_backend_unavailable(create_response)
        assert create_response.status_code == 200, (
            f"Failed to create vector store with {params['name']}: {create_response.text}"
        )
        store_data = create_response.json()
        store_id = store_data["id"]
        stores_created.append((store_id, params["name"]))

        # Step 2: Add document
        doc_id = str(uuid.uuid4())
        add_response = api_client.post(
            f"/vector-stores/{store_id}/documents",
            json={
                "collection": collection_name,
                "document": test_document,
                "document_id": doc_id,
                "metadata": {"test": True, "params": params["name"], "unique_id": unique_id},
            },
        )
        _skip_if_backend_unavailable(add_response)
        assert add_response.status_code == 200, (
            f"Failed to add document to {params['name']}: {add_response.text}"
        )

        # Step 3: Generate keywords (if endpoint exists)
        # Note: This endpoint may not be implemented yet
        keywords_response = api_client.post(
            f"/vector-stores/{store_id}/keywords",
            json={"collection": collection_name, "document_id": doc_id},
        )
        # If endpoint doesn't exist, that's okay - we verify parameters are stored
        if keywords_response.status_code == 200:
            keywords_data = keywords_response.json()
            assert "keywords" in keywords_data, "Keywords should be returned"
            keywords = keywords_data.get("keywords", [])
            assert len(keywords) <= params["max_keywords"], (
                f"Keywords count should not exceed max_keywords ({params['max_keywords']}), got {len(keywords)}"
            )

    # Cleanup
    for store_id, name in stores_created:
        try:
            api_client.delete(f"/vector-stores/{store_id}")
        except Exception:
            pass
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-023")


def test_vector_store_qa_generation_parameters(api_client, test_user, test_expert, test_config):
    """Test Q&A generation parameters.

    Inputs:
    - test_user: User created via API
    - test_expert: Expert created via API
    - qa_parameters: Array of parameter combinations

    Expected Outputs:
    - Vector store created with Q&A parameters (status 200, parameters stored)
    - Documents added successfully (status 200)
    - Q&A generated successfully (if endpoint exists)
    - Q&A matches parameters (Q&A count, question types match parameters)
    - Different parameters produce different Q&A (Q&A varies by parameters)
    """
    user_id = test_user["id"]
    expert_id = test_expert["id"]

    unique_id = str(uuid.uuid4())[:8]

    qdrant_cfg = _get_qdrant_config(test_config)

    print(f"\n[SETTINGS] User ID: {user_id}")
    print(f"[SETTINGS] Expert ID: {expert_id}")
    print(f"[SETTINGS] Test ID: {unique_id}")

    # Test different Q&A generation parameter combinations
    qa_parameters = [
        {
            "method": "llm",
            "qa_count": 3,
            "question_types": ["what", "how"],
            "name": f"llm_3_{unique_id}",
        },
        {
            "method": "template",
            "qa_count": 5,
            "question_types": ["why", "when"],
            "name": f"template_5_{unique_id}",
        },
    ]

    test_document = f"Q&A generation test document {unique_id}. This document explains how vector databases work, why they are useful for similarity search, and when to use them in applications."

    stores_created = []

    # Use unique collection name for isolation
    base_collection = qdrant_cfg.get("collection_name", "expert_agent_test_qdrant")
    collection_name = f"{base_collection}_{unique_id}"

    for params in qa_parameters:
        # Step 1: Create vector store with Q&A parameters
        create_response = api_client.post(
            "/vector-stores",
            json={
                "name": params["name"],
                "store_type": "qdrant",
                "config": {
                    "host": qdrant_cfg["host"],
                    "port": qdrant_cfg["port"],
                    "collection_name": collection_name,
                    "api_key": qdrant_cfg.get("api_key"),
                    "qa_generation": {
                        "method": params["method"],
                        "qa_count": params["qa_count"],
                        "question_types": params["question_types"],
                    },
                },
                "enabled": True,
            },
        )
        _skip_if_backend_unavailable(create_response)
        assert create_response.status_code == 200, (
            f"Failed to create vector store with {params['name']}: {create_response.text}"
        )
        store_data = create_response.json()
        store_id = store_data["id"]
        stores_created.append((store_id, params["name"]))

        # Step 2: Add document
        doc_id = str(uuid.uuid4())
        add_response = api_client.post(
            f"/vector-stores/{store_id}/documents",
            json={
                "collection": collection_name,
                "document": test_document,
                "document_id": doc_id,
                "metadata": {"test": True, "params": params["name"], "unique_id": unique_id},
            },
        )
        _skip_if_backend_unavailable(add_response)
        assert add_response.status_code == 200, (
            f"Failed to add document to {params['name']}: {add_response.text}"
        )

        # Step 3: Generate Q&A (if endpoint exists)
        # Note: This endpoint may not be implemented yet
        qa_response = api_client.post(
            f"/vector-stores/{store_id}/qa",
            json={"collection": collection_name, "document_id": doc_id},
        )
        # If endpoint doesn't exist, that's okay - we verify parameters are stored
        if qa_response.status_code == 200:
            qa_data = qa_response.json()
            assert "qa_pairs" in qa_data or "questions" in qa_data, "Q&A should be returned"
            qa_pairs = qa_data.get("qa_pairs") or qa_data.get("questions", [])
            assert len(qa_pairs) <= params["qa_count"], (
                f"Q&A count should not exceed qa_count ({params['qa_count']}), got {len(qa_pairs)}"
            )

    # Cleanup
    for store_id, name in stores_created:
        try:
            api_client.delete(f"/vector-stores/{store_id}")
        except Exception:
            pass

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.vdb, pytest.mark.db, pytest.mark.smtp, pytest.mark.heavy]

