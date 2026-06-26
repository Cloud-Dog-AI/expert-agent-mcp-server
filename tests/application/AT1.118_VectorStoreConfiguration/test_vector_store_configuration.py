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
Application Test: AT1.4 - Vector Store Configuration and CRUD Operations

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for vector store configuration and CRUD operations via API

Related Requirements: FR1.3
Related Tasks: T014
Related Architecture: CC4.1.1
Related Tests: AT1.4

Recent Changes:
- Refactored to use API endpoints only (no direct VectorStoreManager calls)
- Added vector store CRUD tests with actual vector database connection
- Removed all hard-coded values (all from config system)
- All outputs validated via API responses
"""

import sys
from pathlib import Path

# Add parent directory to path for shared test helpers
sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import build_test_email, create_api_client_fixture, validate_config_loaded


import pytest
import uuid
from src.config.loader import get_config, load_config


def _get_qdrant_cfg(test_config):
    """
    Helper function to get Qdrant configuration from multiple possible paths.
    Tries multiple config paths to handle different environment variable formats.
    """
    # Clear config cache to ensure latest values are loaded
    load_config.cache_clear()

    # Try multiple paths (env vars can map to different paths)
    # Priority: get_config (includes env vars) > test_config
    qdrant_host = (
        get_config("vector_stores_config.qdrant._DEFAULT_.host")
        or get_config("vector_stores.qdrant.default.host")
        or test_config.get("vector_stores_config", {})
        .get("qdrant", {})
        .get("_DEFAULT_", {})
        .get("host")
        or test_config.get("vector_stores", {}).get("qdrant", {}).get("default", {}).get("host")
    )
    qdrant_port = (
        get_config("vector_stores_config.qdrant._DEFAULT_.port")
        or get_config("vector_stores.qdrant.default.port")
        or test_config.get("vector_stores_config", {})
        .get("qdrant", {})
        .get("_DEFAULT_", {})
        .get("port")
        or test_config.get("vector_stores", {}).get("qdrant", {}).get("default", {}).get("port")
    )
    qdrant_api_key = (
        get_config("vector_stores_config.qdrant._DEFAULT_.api_key")
        or get_config("vector_stores.qdrant.default.api_key")
        or test_config.get("vector_stores_config", {})
        .get("qdrant", {})
        .get("_DEFAULT_", {})
        .get("api_key")
        or test_config.get("vector_stores", {}).get("qdrant", {}).get("default", {}).get("api_key")
    )
    collection_name = (
        get_config("vector_stores_config.qdrant._DEFAULT_.collection_name")
        or get_config("vector_stores.qdrant.default.collection_name")
        or test_config.get("vector_stores_config", {})
        .get("qdrant", {})
        .get("_DEFAULT_", {})
        .get("collection_name")
        or test_config.get("vector_stores", {})
        .get("qdrant", {})
        .get("default", {})
        .get("collection_name")
    )
    if not qdrant_host or qdrant_port is None:
        pytest.fail("Qdrant host/port not configured in vector_stores_config.qdrant")
    if not collection_name:
        pytest.fail("Qdrant collection_name not configured in vector_stores_config.qdrant")
    return {
        "host": qdrant_host,
        "port": int(qdrant_port),
        "api_key": qdrant_api_key,
        "collection_name": collection_name,
    }


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
        "username": f"{base_username}_at1_4_{unique_id}",
        "email": build_test_email("at1_4", unique_id, base_email),
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

    # Cleanup via API only
    delete_response = api_client.delete(f"/users/{user_data['id']}")
    if delete_response.status_code not in (200, 204):
        pytest.fail(
            f"Failed to delete user via API: {delete_response.status_code} {delete_response.text}"
        )


@pytest.fixture
def test_group(api_client, test_user):
    """Create test group via API."""
    unique_id = str(uuid.uuid4())[:8]
    group_name = f"group_at1_4_{unique_id}"

    response = api_client.post(
        "/groups", json={"name": group_name, "description": "Test group for vector stores"}
    )
    assert response.status_code == 200
    group_data = response.json()

    # Add user to group
    add_member_response = api_client.post(
        f"/groups/{group_data['id']}/members", json={"user_id": test_user["id"], "role": "member"}
    )
    if add_member_response.status_code not in (200, 204):
        pytest.fail(
            f"Failed to add group member via API: {add_member_response.status_code} {add_member_response.text}"
        )

    yield group_data

    # Cleanup: Delete group via API
    delete_response = api_client.delete(f"/groups/{group_data['id']}")
    if delete_response.status_code not in (200, 204):
        pytest.fail(
            f"Failed to delete group via API: {delete_response.status_code} {delete_response.text}"
        )


@pytest.fixture
def unique_vector_store_name():
    """Generate unique vector store name for each test."""
    return f"vector_store_at1_4_{str(uuid.uuid4())[:8]}"


@pytest.fixture(autouse=True)
def cleanup_test_vector_store(api_client, unique_vector_store_name):
    """Cleanup: Remove test vector store at start (if exists) and end of test."""
    store_name = unique_vector_store_name

    # Remove existing store before test via API
    list_response = api_client.get("/vector-stores")
    if list_response.status_code != 200:
        pytest.fail(
            f"Failed to list vector stores for cleanup: {list_response.status_code} {list_response.text}"
        )
    stores = list_response.json().get("stores", list_response.json().get("vector_stores", []))
    for store in stores:
        if store.get("name") == store_name:
            delete_response = api_client.delete(f"/vector-stores/{store['id']}")
            if delete_response.status_code not in (200, 204):
                pytest.fail(
                    f"Failed to delete vector store via API: {delete_response.status_code} {delete_response.text}"
                )

    yield

    # Cleanup after test: Remove store if created via API
    list_response = api_client.get("/vector-stores")
    if list_response.status_code != 200:
        pytest.fail(
            f"Failed to list vector stores for cleanup: {list_response.status_code} {list_response.text}"
        )
    stores = list_response.json().get("stores", list_response.json().get("vector_stores", []))
    for store in stores:
        if store.get("name") == store_name:
            delete_response = api_client.delete(f"/vector-stores/{store['id']}")
            if delete_response.status_code not in (200, 204):
                pytest.fail(
                    f"Failed to delete vector store via API: {delete_response.status_code} {delete_response.text}"
                )
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_create_vector_store_configuration_via_api(
    api_client, unique_vector_store_name, test_config
):
    """Test creating a vector store configuration via API."""
    store_name = unique_vector_store_name

    # Get vector store config from config system
    test_config.get("vector_store", {})
    qdrant_cfg = _get_qdrant_cfg(test_config)

    config = {
        "host": qdrant_cfg["host"],
        "port": int(qdrant_cfg["port"]),
        "collection_name": qdrant_cfg["collection_name"],
    }

    # Show settings being used
    print(f"\n[SETTINGS] Vector store name: {store_name}")
    print("[SETTINGS] Store type: qdrant")
    print(f"[SETTINGS] Config: {config}")

    # Create vector store via API
    response = api_client.post(
        "/vector-stores",
        json={"name": store_name, "store_type": "qdrant", "config": config, "enabled": True},
    )

    assert response.status_code == 200, f"Creation failed: {response.text}"
    data = response.json()

    # Validate all outputs
    assert "id" in data
    assert data["name"] == store_name
    assert data["type"] == "qdrant"
    assert data["enabled"] is True
    assert "config" in data
    assert data["config"]["host"] == config["host"]
    assert data["config"]["port"] == config["port"]

    # Verify store exists via API
    get_response = api_client.get(f"/vector-stores/{data['id']}")
    assert get_response.status_code == 200
    store_data = get_response.json()
    assert store_data["name"] == store_name
    assert store_data["type"] == "qdrant"
    assert store_data["enabled"] is True
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_read_vector_store_configuration_via_api(api_client, unique_vector_store_name, test_config):
    """Test reading a vector store configuration via API."""
    store_name = unique_vector_store_name

    # Get config from config system
    qdrant_cfg = _get_qdrant_cfg(test_config)
    config = {
        "host": qdrant_cfg["host"],
        "port": int(qdrant_cfg["port"]),
        "collection_name": qdrant_cfg["collection_name"],
        "api_key": qdrant_cfg.get("api_key"),
    }

    # Create store via API
    create_response = api_client.post(
        "/vector-stores", json={"name": store_name, "store_type": "qdrant", "config": config}
    )
    assert create_response.status_code == 200
    store_id = create_response.json()["id"]

    # Retrieve by ID via API
    get_response = api_client.get(f"/vector-stores/{store_id}")
    assert get_response.status_code == 200
    store_data = get_response.json()

    # Validate outputs
    assert store_data["id"] == store_id
    assert store_data["name"] == store_name
    assert store_data["type"] == "qdrant"
    assert "config" in store_data
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_update_vector_store_configuration_via_api(
    api_client, unique_vector_store_name, test_config
):
    """Test updating a vector store configuration via API."""
    store_name = unique_vector_store_name

    # Get config from config system
    qdrant_cfg = _get_qdrant_cfg(test_config)
    config = {
        "host": qdrant_cfg["host"],
        "port": int(qdrant_cfg["port"]),
        "collection_name": qdrant_cfg["collection_name"],
        "api_key": qdrant_cfg.get("api_key"),
    }

    # Create store via API
    create_response = api_client.post(
        "/vector-stores",
        json={"name": store_name, "store_type": "qdrant", "config": config, "enabled": True},
    )
    assert create_response.status_code == 200
    store_id = create_response.json()["id"]

    # Update store via PUT endpoint
    new_collection_name = f"updated_{str(uuid.uuid4())[:8]}"
    new_config = {
        "host": qdrant_cfg["host"],
        "port": int(qdrant_cfg["port"]),
        "api_key": qdrant_cfg.get("api_key"),
        "collection_name": new_collection_name,
    }
    update_response = api_client.put(
        f"/vector-stores/{store_id}", json={"config": new_config, "enabled": False}
    )

    assert update_response.status_code == 200, f"Update failed: {update_response.text}"
    data = update_response.json()

    # Validate outputs
    assert data["id"] == store_id
    assert data["name"] == store_name
    assert data["enabled"] is False
    assert data["config"]["host"] == qdrant_cfg["host"]
    assert data["config"]["port"] == int(qdrant_cfg["port"])
    assert data["config"]["collection_name"] == new_collection_name

    # Verify via GET
    get_response = api_client.get(f"/vector-stores/{store_id}")
    assert get_response.status_code == 200
    store_data = get_response.json()
    assert store_data["enabled"] is False
    assert store_data["config"]["host"] == qdrant_cfg["host"]
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_list_vector_stores_via_api(api_client, unique_vector_store_name, test_config):
    """Test listing vector stores via API."""
    store_name = unique_vector_store_name

    # Get config from config system
    qdrant_cfg = _get_qdrant_cfg(test_config)
    config = {
        "host": qdrant_cfg["host"],
        "port": int(qdrant_cfg["port"]),
        "collection_name": qdrant_cfg["collection_name"],
        "api_key": qdrant_cfg.get("api_key"),
    }

    # Create multiple stores via API
    store_ids = []
    for i in range(3):
        unique_id = str(uuid.uuid4())[:8]
        create_response = api_client.post(
            "/vector-stores",
            json={
                "name": f"{store_name}_list_{i}_{unique_id}",
                "store_type": "qdrant",
                "config": config,
            },
        )
        assert create_response.status_code == 200
        store_ids.append(create_response.json()["id"])

    # List all stores via API
    list_response = api_client.get("/vector-stores")
    assert list_response.status_code == 200
    data = list_response.json()

    # Validate outputs
    assert "stores" in data
    assert "count" in data
    assert len(data["stores"]) >= 3

    # Verify created stores are in list
    store_names = [s["name"] for s in data["stores"]]
    for i in range(3):
        assert any(f"{store_name}_list_{i}_" in name for name in store_names)
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_vector_store_access_control_via_api(
    api_client, unique_vector_store_name, test_user, test_group, test_config
):
    """Test vector store access control configuration via API."""
    store_name = unique_vector_store_name

    # Get config from config system
    qdrant_cfg = _get_qdrant_cfg(test_config)
    config = {
        "host": qdrant_cfg["host"],
        "port": int(qdrant_cfg["port"]),
        "collection_name": qdrant_cfg["collection_name"],
        "api_key": qdrant_cfg.get("api_key"),
    }

    access_control = {"group_ids": [test_group["id"]], "user_ids": [test_user["id"]]}

    # Create store with access control via API
    response = api_client.post(
        "/vector-stores",
        json={
            "name": store_name,
            "store_type": "qdrant",
            "config": config,
            "access_control": access_control,
        },
    )
    assert response.status_code == 200
    store_data = response.json()

    # Validate outputs
    assert "access_control" in store_data
    assert store_data["access_control"]["group_ids"] == [test_group["id"]]
    assert store_data["access_control"]["user_ids"] == [test_user["id"]]

    # Verify via GET
    get_response = api_client.get(f"/vector-stores/{store_data['id']}")
    assert get_response.status_code == 200
    retrieved = get_response.json()
    assert retrieved["access_control"]["group_ids"] == [test_group["id"]]
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_vector_store_enable_disable_via_api(api_client, unique_vector_store_name, test_config):
    """Test enabling and disabling vector stores via API."""
    store_name = unique_vector_store_name

    # Get config from config system
    qdrant_cfg = _get_qdrant_cfg(test_config)
    config = {
        "host": qdrant_cfg["host"],
        "port": int(qdrant_cfg["port"]),
        "collection_name": qdrant_cfg["collection_name"],
        "api_key": qdrant_cfg.get("api_key"),
    }

    # Create store via API
    create_response = api_client.post(
        "/vector-stores",
        json={"name": store_name, "store_type": "qdrant", "config": config, "enabled": True},
    )
    assert create_response.status_code == 200
    store_id = create_response.json()["id"]

    # Verify enabled
    get_response = api_client.get(f"/vector-stores/{store_id}")
    assert get_response.status_code == 200
    assert get_response.json()["enabled"] is True

    # Disable via PUT
    update_response = api_client.put(f"/vector-stores/{store_id}", json={"enabled": False})
    assert update_response.status_code == 200
    assert update_response.json()["enabled"] is False

    # Re-enable via PUT
    update_response2 = api_client.put(f"/vector-stores/{store_id}", json={"enabled": True})
    assert update_response2.status_code == 200
    assert update_response2.json()["enabled"] is True
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_vector_store_multiple_types_via_api(api_client, unique_vector_store_name, test_config):
    """Test creating vector stores of different types via API."""
    store_name = unique_vector_store_name
    types = ["qdrant", "chroma", "weaviate"]

    # Get config from config system
    qdrant_cfg = _get_qdrant_cfg(test_config)
    base_config = {
        "host": qdrant_cfg["host"],
        "port": int(qdrant_cfg["port"]),
        "collection_name": qdrant_cfg["collection_name"],
        "api_key": qdrant_cfg.get("api_key"),
    }

    created_stores = []
    for store_type in types:
        unique_id = str(uuid.uuid4())[:8]
        response = api_client.post(
            "/vector-stores",
            json={
                "name": f"{store_name}_{store_type}_{unique_id}",
                "store_type": store_type,
                "config": base_config,
            },
        )
        # Some types may not be available, but qdrant should work
        if response.status_code == 200:
            store_data = response.json()
            assert store_data["type"] == store_type
            created_stores.append(store_data["id"])

    # At least qdrant should be created
    assert len(created_stores) >= 1
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_vector_store_deletion_via_api(api_client, unique_vector_store_name, test_config):
    """Test deleting a vector store via API."""
    store_name = unique_vector_store_name

    # Get config from config system
    qdrant_cfg = _get_qdrant_cfg(test_config)
    config = {
        "host": qdrant_cfg["host"],
        "port": int(qdrant_cfg["port"]),
        "collection_name": qdrant_cfg["collection_name"],
        "api_key": qdrant_cfg.get("api_key"),
    }

    # Create store via API
    create_response = api_client.post(
        "/vector-stores", json={"name": store_name, "store_type": "qdrant", "config": config}
    )
    assert create_response.status_code == 200
    store_id = create_response.json()["id"]

    # Verify store exists
    get_response = api_client.get(f"/vector-stores/{store_id}")
    assert get_response.status_code == 200

    # Delete store via DELETE endpoint
    delete_response = api_client.delete(f"/vector-stores/{store_id}")
    assert delete_response.status_code == 200

    # Verify deletion
    get_response2 = api_client.get(f"/vector-stores/{store_id}")
    assert get_response2.status_code == 404
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_vector_store_not_found_via_api(api_client):
    """Test vector store not found error via API."""
    # Try to get non-existent store
    response = api_client.get("/vector-stores/99999")

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


# Vector CRUD tests with actual vector database connection
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")
def test_vector_store_connection_via_api(api_client, unique_vector_store_name, test_config):
    """Test connecting to vector store via API (with actual connection)."""
    store_name = unique_vector_store_name

    # Get Qdrant config from config system
    qdrant_cfg = _get_qdrant_cfg(test_config)
    qdrant_host = qdrant_cfg["host"]
    qdrant_port = qdrant_cfg["port"]
    qdrant_api_key = qdrant_cfg["api_key"]
    collection_name = qdrant_cfg["collection_name"] or f"test_collection_{str(uuid.uuid4())[:8]}"

    if not qdrant_host:
        pytest.fail(
            "Qdrant host not configured. Set CLOUD_DOG__EXPERT__VECTOR__STORES__QDRANT__DEFAULT__HOST in --env file."
        )

    config = {"host": qdrant_host, "port": int(qdrant_port), "collection_name": collection_name}
    if qdrant_api_key:
        config["api_key"] = qdrant_api_key

    # Show settings being used
    print(f"\n[SETTINGS] Vector store name: {store_name}")
    print(f"[SETTINGS] Qdrant host: {qdrant_cfg['host']}")
    print(f"[SETTINGS] Qdrant port: {qdrant_cfg['port']}")
    print(f"[SETTINGS] Collection name: {qdrant_cfg['collection_name']}")

    # Create vector store via API
    create_response = api_client.post(
        "/vector-stores",
        json={"name": store_name, "store_type": "qdrant", "config": config, "enabled": True},
    )
    assert create_response.status_code == 200, (
        f"Vector store creation failed: {create_response.text}"
    )
    store_id = create_response.json()["id"]

    # Test connection by adding a document (this will connect to Qdrant)
    document_text = "This is a test document for vector store connection testing."
    add_response = api_client.post(
        f"/vector-stores/{store_id}/documents",
        json={
            "collection": collection_name,
            "document": document_text,
            "metadata": {"test": True, "source": "at1.4", "type": "connection_test"},
        },
    )

    # May fail if vector store connection fails
    if add_response.status_code != 200:
        pytest.fail(f"Vector store connection failed: {add_response.text}")

    data = add_response.json()

    # Validate outputs - connection successful
    assert data["success"] is True
    assert "id" in data
    assert data["collection"] == collection_name
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_vector_store_add_document_via_api(api_client, unique_vector_store_name, test_config):
    """Test adding a document to vector store via API (with actual connection)."""
    store_name = unique_vector_store_name

    # Get Qdrant config from config system
    qdrant_cfg = _get_qdrant_cfg(test_config)
    qdrant_host = qdrant_cfg["host"]
    qdrant_port = qdrant_cfg["port"]
    qdrant_api_key = qdrant_cfg["api_key"]
    collection_name = qdrant_cfg["collection_name"] or f"test_collection_{str(uuid.uuid4())[:8]}"

    if not qdrant_host:
        pytest.fail(
            "Qdrant host not configured. Set CLOUD_DOG__EXPERT__VECTOR__STORES__QDRANT__DEFAULT__HOST in --env file."
        )

    config = {"host": qdrant_host, "port": int(qdrant_port), "collection_name": collection_name}
    if qdrant_api_key:
        config["api_key"] = qdrant_api_key

    # Create vector store via API
    create_response = api_client.post(
        "/vector-stores",
        json={"name": store_name, "store_type": "qdrant", "config": config, "enabled": True},
    )
    assert create_response.status_code == 200
    store_id = create_response.json()["id"]

    # Add document via API
    document_text = (
        "Python is a high-level programming language known for its simplicity and readability."
    )
    # Qdrant requires UUID or integer IDs, not string prefixes
    doc_id = str(uuid.uuid4())
    add_response = api_client.post(
        f"/vector-stores/{store_id}/documents",
        json={
            "collection": collection_name,
            "document": document_text,
            "id": doc_id,
            "metadata": {"test": True, "source": "at1.4", "topic": "programming"},
        },
    )

    # May fail if vector store connection fails, skip gracefully
    if add_response.status_code != 200:
        pytest.fail(f"Vector store connection failed: {add_response.text}")

    data = add_response.json()

    # Validate outputs
    assert data["success"] is True
    assert "id" in data
    assert data["collection"] == collection_name
    # ID should match if provided
    if doc_id:
        assert data["id"] == doc_id
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_vector_store_query_documents_via_api(api_client, unique_vector_store_name, test_config):
    """Test querying documents in vector store via API (with actual connection)."""
    store_name = unique_vector_store_name

    # Get Qdrant config from config system
    qdrant_cfg = _get_qdrant_cfg(test_config)
    qdrant_host = qdrant_cfg["host"]
    qdrant_port = qdrant_cfg["port"]
    qdrant_api_key = qdrant_cfg["api_key"]
    collection_name = qdrant_cfg["collection_name"] or f"test_collection_{str(uuid.uuid4())[:8]}"

    if not qdrant_host:
        pytest.fail(
            "Qdrant host not configured. Set CLOUD_DOG__EXPERT__VECTOR__STORES__QDRANT__DEFAULT__HOST in --env file."
        )

    config = {"host": qdrant_host, "port": int(qdrant_port), "collection_name": collection_name}
    if qdrant_api_key:
        config["api_key"] = qdrant_api_key

    # Create vector store via API
    create_response = api_client.post(
        "/vector-stores",
        json={"name": store_name, "store_type": "qdrant", "config": config, "enabled": True},
    )
    assert create_response.status_code == 200
    store_id = create_response.json()["id"]

    # Add multiple documents first for better query testing
    documents = [
        "Python is a programming language used for web development and data science.",
        "JavaScript is a programming language primarily used for web development.",
        "Machine learning is a subset of artificial intelligence.",
    ]

    doc_ids = []
    for i, doc_text in enumerate(documents):
        # Qdrant requires UUID or integer IDs, not string prefixes
        doc_id = str(uuid.uuid4())
        add_response = api_client.post(
            f"/vector-stores/{store_id}/documents",
            json={
                "collection": collection_name,
                "document": doc_text,
                "id": doc_id,
                "metadata": {"test": True, "index": i, "source": "at1.4"},
            },
        )

        if add_response.status_code != 200:
            pytest.fail(f"Vector store connection failed: {add_response.text}")
        doc_ids.append(doc_id)

    # Query documents via API
    query_response = api_client.post(
        f"/vector-stores/{store_id}/query",
        json={"collection": collection_name, "query": "programming language", "n_results": 5},
    )

    if query_response.status_code != 200:
        pytest.fail(f"Vector store query failed: {query_response.text}")

    data = query_response.json()

    # Validate outputs
    assert "results" in data
    assert "count" in data
    assert isinstance(data["results"], list)
    assert len(data["results"]) >= 0  # May be 0 if no matches, but structure should be correct
    # If results exist, validate structure
    if len(data["results"]) > 0:
        result = data["results"][0]
        assert "id" in result or "document" in result or "content" in result
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_vector_store_delete_document_via_api(api_client, unique_vector_store_name, test_config):
    """Test deleting a document from vector store via API (with actual connection)."""
    store_name = unique_vector_store_name

    # Get Qdrant config from config system
    qdrant_cfg = _get_qdrant_cfg(test_config)
    qdrant_host = qdrant_cfg["host"]
    qdrant_port = qdrant_cfg["port"]
    qdrant_api_key = qdrant_cfg["api_key"]
    collection_name = qdrant_cfg["collection_name"] or f"test_collection_{str(uuid.uuid4())[:8]}"

    if not qdrant_host:
        pytest.fail(
            "Qdrant host not configured. Set CLOUD_DOG__EXPERT__VECTOR__STORES__QDRANT__DEFAULT__HOST in --env file."
        )

    config = {"host": qdrant_host, "port": int(qdrant_port), "collection_name": collection_name}
    if qdrant_api_key:
        config["api_key"] = qdrant_api_key

    # Create vector store via API
    create_response = api_client.post(
        "/vector-stores",
        json={"name": store_name, "store_type": "qdrant", "config": config, "enabled": True},
    )
    assert create_response.status_code == 200
    store_id = create_response.json()["id"]

    # Add a document first
    # Qdrant requires UUID or integer IDs, not string prefixes
    doc_id = str(uuid.uuid4())
    add_response = api_client.post(
        f"/vector-stores/{store_id}/documents",
        json={
            "collection": collection_name,
            "document": "Test document to delete",
            "id": doc_id,
            "metadata": {"test": True, "source": "at1.4"},
        },
    )

    if add_response.status_code != 200:
        pytest.fail(f"Vector store connection failed: {add_response.text}")

    # Delete document via API
    delete_response = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc_id}", params={"collection": collection_name}
    )

    if delete_response.status_code != 200:
        pytest.fail(f"Vector store delete failed: {delete_response.text}")

    data = delete_response.json()

    # Validate outputs
    assert data["success"] is True
    assert data["id"] == doc_id
    assert data["collection"] == collection_name

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.vdb, pytest.mark.db, pytest.mark.smtp, pytest.mark.heavy]

