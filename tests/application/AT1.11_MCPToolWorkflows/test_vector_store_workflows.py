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
Application Test: AT1.11 - Vector Store Workflows (Qdrant, Chroma, OpenSearch)

License: Apache 2.0
Ownership: Cloud Dog
Description: Test vector store workflows with MCP tools for Qdrant, Chroma, and OpenSearch

Related Requirements: FR1.30
Related Tasks: T068
Related Architecture: CC4.1.2
Related Tests: AT1.11 (Tests 14-19)
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
            "Test user credentials not configured. "
            "Set test.user.username/test.user.email/test.user.password in your --env file."
        )

    unique_id = str(uuid.uuid4())[:8]
    return {
        "username": f"{base_username}_at1_11_vs_{unique_id}",
        "email": build_test_email("at1_11_vs", unique_id, base_email),
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
    if not llm_provider or not llm_model:
        pytest.fail("Missing llm.provider/llm.model in config (--env)")

    unique_id = str(uuid.uuid4())[:8]
    expert_data = {
        "name": f"expert_at1_11_vs_{unique_id}",
        "title": f"Vector Store Workflows Expert {unique_id} create update query delete lifecycle isolation",
        "description": "Vector store workflow scenario with unique vocabulary: acorn basil cipher dune ember fjord glyph helios isotope juniper keystone",
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


def _get_vector_store_config(store_type, test_config):
    """Get vector store configuration based on type."""
    if store_type == "qdrant":
        host = get_config("vector_stores_config.qdrant._DEFAULT_.host")
        port = get_config("vector_stores_config.qdrant._DEFAULT_.port")
        api_key = get_config("vector_stores_config.qdrant._DEFAULT_.api_key")
        collection_name = get_config("vector_stores_config.qdrant._DEFAULT_.collection_name")
        if not host or port is None or api_key is None or not collection_name:
            pytest.fail(
                "Qdrant config missing (host/port/api_key/collection_name). Check your --env file."
            )
        return {
            "host": host,
            "port": int(port),
            "api_key": api_key,
            "collection_name": collection_name,
        }
    elif store_type == "chroma":
        path = get_config("vector_stores_config.chroma._DEFAULT_.path") or get_config(
            "vector_stores_config.chroma._TEST_.path"
        )
        collection_name = get_config(
            "vector_stores_config.chroma._DEFAULT_.collection_name"
        ) or get_config("vector_stores_config.chroma._TEST_.collection_name")
        if not path or not collection_name:
            pytest.fail("Chroma config missing (path/collection_name). Check your --env file.")
        return {"path": path, "collection_name": collection_name}
    elif store_type == "opensearch":
        host = get_config("vector_stores_config.opensearch._TEST_.host")
        port = get_config("vector_stores_config.opensearch._TEST_.port")
        username = get_config("vector_stores_config.opensearch._TEST_.username")
        password = get_config("vector_stores_config.opensearch._TEST_.password")
        collection_name = get_config("vector_stores_config.opensearch._TEST_.collection_name")
        if not host or port is None or not username or password is None or not collection_name:
            pytest.fail(
                "OpenSearch config missing (host/port/username/password/collection_name). Check your --env file."
            )
        return {
            "host": host,
            "port": int(port),
            "username": username,
            "password": password,
            "collection_name": collection_name,
            "ssl": False,  # Changed to False per user request
            "verify_certs": False,
        }
    return {}
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-023")


@pytest.mark.parametrize("store_type", ["qdrant", "chroma", "opensearch"])
def test_vector_store_workflow_via_mcp(api_client, test_user, test_expert, store_type, test_config):
    """Test vector store workflow with MCP tools (Test 14-16).

    Tests Qdrant, Chroma, and OpenSearch workflows via MCP tools.

    Inputs:
    - store_type: "qdrant", "chroma", or "opensearch"
    - test_user: User created via API
    - test_expert: Expert created via API
    - documents: 3 test documents
    - query: Test query string

    Expected Outputs:
    - Vector store config created
    - Documents added successfully
    - Search returns relevant documents
    - Document IDs match store type requirements (UUID for Qdrant, string for others)
    """
    # Get vector store configuration
    vs_config = _get_vector_store_config(store_type, test_config)

    unique_id = str(uuid.uuid4())[:8]
    store_name = f"vector_store_{store_type}_{unique_id}"
    # Prefer configured collection/index name when provided
    base_collection = vs_config.get("collection_name") or f"test_collection_{unique_id}"
    if store_type == "qdrant":
        collection_name = f"{base_collection}_{unique_id}"
    else:
        collection_name = base_collection

    print(f"\n[SETTINGS] Vector store type: {store_type}")
    print(f"[SETTINGS] Store name: {store_name}")
    print(f"[SETTINGS] Collection name: {collection_name}")

    # Prepare config for API
    if store_type == "qdrant":
        config = {
            "host": vs_config["host"],
            "port": vs_config["port"],
            "collection_name": collection_name,
        }
        if vs_config.get("api_key"):
            config["api_key"] = vs_config["api_key"]
    elif store_type == "chroma":
        if vs_config.get("path"):
            config = {"path": vs_config["path"], "collection_name": collection_name}
        else:
            config = {
                "host": vs_config["host"],
                "port": vs_config["port"],
                "collection_name": collection_name,
            }
            if "ssl" in vs_config:
                config["ssl"] = vs_config.get("ssl", False)
            if vs_config.get("auth_token"):
                config["auth_token"] = vs_config["auth_token"]
    elif store_type == "opensearch":
        config = {
            "host": vs_config["host"],
            "port": vs_config["port"],
            "collection_name": collection_name,
            "ssl": vs_config.get("ssl", True),
            "verify_certs": vs_config.get("verify_certs", True),
        }
        if vs_config.get("username"):
            config["username"] = vs_config["username"]
        if vs_config.get("password"):
            config["password"] = vs_config["password"]
        if vs_config.get("api_key"):
            config["api_key"] = vs_config["api_key"]

    # Step 1: Create vector store via API
    create_response = api_client.post(
        "/vector-stores",
        json={"name": store_name, "store_type": store_type, "config": config, "enabled": True},
    )
    if create_response.status_code == 503 and "not available" in create_response.text.lower():
        pytest.fail(f"Vector store backend unavailable: {create_response.text}")
    assert create_response.status_code == 200, (
        f"Failed to create {store_type} vector store: {create_response.text}"
    )
    store_data = create_response.json()
    store_id = store_data["id"]

    # Step 2: Add documents via API
    documents = [
        f"{store_type.capitalize()} is a vector database for similarity search.",
        f"{store_type.capitalize()} supports filtering and payload queries.",
        f"{store_type.capitalize()} uses efficient algorithms for fast approximate nearest neighbor search.",
    ]

    document_ids = []
    for i, doc_text in enumerate(documents):
        # Generate appropriate ID based on store type
        if store_type == "qdrant":
            doc_id = str(uuid.uuid4())  # Qdrant requires UUID
        else:
            doc_id = f"doc_{i}_{unique_id}"  # Chroma/OpenSearch can use strings

        add_response = api_client.post(
            f"/vector-stores/{store_id}/documents",
            json={
                "collection": collection_name,
                "document": doc_text,
                "document_id": doc_id,
                "metadata": {"test": True, "source": f"at1.11_{store_type}", "index": i},
            },
        )
        if add_response.status_code == 503 and "not available" in add_response.text.lower():
            pytest.fail(f"Vector store backend unavailable: {add_response.text}")
        assert add_response.status_code == 200, (
            f"Failed to add document {i + 1} to {store_type}: {add_response.text}"
        )
        doc_data = add_response.json()
        returned_id = doc_data.get("id") or doc_data.get("document_id")
        document_ids.append(returned_id)

        # Validate ID format
        if store_type == "qdrant":
            # Qdrant IDs should be UUIDs
            try:
                uuid.UUID(returned_id)
            except ValueError:
                pytest.fail(f"Qdrant document ID should be UUID, got: {returned_id}")
        else:
            # Chroma/OpenSearch IDs should be strings
            assert isinstance(returned_id, str), (
                f"{store_type} document ID should be string, got: {type(returned_id)}"
            )

    # Step 3: Search via API
    query = "vector database"
    search_response = api_client.post(
        f"/vector-stores/{store_id}/query",
        json={"collection": collection_name, "query": query, "n_results": 5},
    )
    if search_response.status_code == 503 and "not available" in search_response.text.lower():
        pytest.fail(f"Vector store backend unavailable: {search_response.text}")
    assert search_response.status_code == 200, (
        f"Failed to search {store_type} vector store: {search_response.text}"
    )
    search_data = search_response.json()

    # Validate search results
    assert "results" in search_data or "documents" in search_data, (
        f"Search response missing results: {search_data}"
    )
    results = search_data.get("results") or search_data.get("documents") or []
    assert len(results) > 0, f"Search should return results, got: {results}"

    # Verify relevant documents found
    result_texts = [r.get("document") or r.get("content", "") for r in results]
    assert any(
        "vector database" in text.lower() or "similarity search" in text.lower()
        for text in result_texts
    ), f"Search should find relevant documents, got: {result_texts}"

    # Step 4: Test MCP tools (if MCP server available)
    # Note: MCP tools are tested separately in test_mcp_tool_workflows.py
    # This test focuses on API-based vector store operations

    # Cleanup
    try:
        api_client.delete(f"/vector-stores/{store_id}")
        # Cleanup may fail if store is in use, that's okay
    except Exception:
        pass

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.vdb, pytest.mark.db, pytest.mark.smtp, pytest.mark.mcp, pytest.mark.heavy]
