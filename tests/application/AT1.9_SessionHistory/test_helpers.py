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
Test Helpers for AT1.9 Session History Tests

License: Apache 2.0
Ownership: Cloud Dog
Description: Shared helper functions for session history tests
"""

import uuid
import urllib.parse
from typing import Dict, Any, List, Optional

import pytest
from src.config.loader import get_config


def _get_nested(config: Dict[str, Any], keys: List[str]) -> Any:
    cur: Any = config
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _get_enabled_profile_config(
    store: str, preferred_profiles: List[str]
) -> Optional[Dict[str, Any]]:
    """
    Return the first enabled profile config for a vector store backend.

    If no enabled profile exists, return None and the caller must fail.
    """
    cfg = get_config()
    if not isinstance(cfg, dict):
        pytest.fail(
            "Config not loaded (get_config() did not return dict). Run tests with --env <file>."
        )

    for profile in preferred_profiles:
        profile_cfg = _get_nested(cfg, ["vector_stores_config", store, profile])
        if not isinstance(profile_cfg, dict):
            continue
        enabled = profile_cfg.get("enabled")
        # env may yield strings; accept bool or truthy string.
        if isinstance(enabled, str):
            enabled = enabled.strip().lower() == "true"
        if enabled is True:
            return profile_cfg
    return None


def _require(value: Any, message: str) -> Any:
    if value is None or (isinstance(value, str) and not value.strip()):
        pytest.fail(message)
    return value


def create_test_vector_store(
    api_client, store_type: str, name_suffix: Optional[str] = None
) -> Dict[str, Any]:
    """Create a test vector store via API.

    Args:
        api_client: Test client
        store_type: Vector store type (chroma, qdrant, opensearch, weaviate, pgvector)
        name_suffix: Optional suffix for store name

    Returns:
        Created vector store data
    """
    unique_id = str(uuid.uuid4())[:8]
    suffix = f"_{name_suffix}" if name_suffix else ""
    store_name = f"test_history_{store_type}{suffix}_{unique_id}"

    # Build provider-compatible config from canonical vector_stores_config.*
    config: Dict[str, Any] = {}
    if store_type == "chroma":
        chroma_cfg = _get_enabled_profile_config("chroma", ["_DEFAULT_", "_REMOTE_"])
        if not chroma_cfg:
            pytest.fail(
                "Chroma not configured/enabled in this environment (vector_stores_config.chroma.*)"
            )
        # Prefer local path if present; otherwise remote host config.
        if chroma_cfg.get("path"):
            config = {
                "path": _require(chroma_cfg.get("path"), "Chroma enabled but missing chroma.path"),
                "collection_name": _require(
                    chroma_cfg.get("collection_name"),
                    "Chroma enabled but missing chroma.collection_name",
                ),
            }
        else:
            config = {
                "host": _require(
                    chroma_cfg.get("host"), "Chroma remote enabled but missing chroma.host"
                ),
                "port": int(
                    _require(
                        chroma_cfg.get("port"), "Chroma remote enabled but missing chroma.port"
                    )
                ),
                "ssl": chroma_cfg.get("ssl", False),
                "auth_token": chroma_cfg.get("auth_token"),
                "collection_name": _require(
                    chroma_cfg.get("collection_name"),
                    "Chroma enabled but missing chroma.collection_name",
                ),
            }
    elif store_type == "qdrant":
        qdrant_cfg = _get_enabled_profile_config("qdrant", ["_DEFAULT_", "_TEST_"])
        if not qdrant_cfg:
            pytest.fail(
                "Qdrant not configured/enabled in this environment (vector_stores_config.qdrant.*)"
            )
        base_collection = _require(
            qdrant_cfg.get("collection_name"), "Qdrant enabled but missing qdrant.collection_name"
        )
        collection_name = f"{base_collection}_{unique_id}"
        config = {
            "host": _require(qdrant_cfg.get("host"), "Qdrant enabled but missing qdrant.host"),
            "port": int(_require(qdrant_cfg.get("port"), "Qdrant enabled but missing qdrant.port")),
            "api_key": qdrant_cfg.get("api_key"),
            "collection_name": collection_name,
            "ssl": qdrant_cfg.get("ssl", False),
        }
    elif store_type == "opensearch":
        opensearch_cfg = _get_enabled_profile_config("opensearch", ["_TEST_", "_DEFAULT_"])
        if not opensearch_cfg:
            pytest.fail(
                "OpenSearch not configured/enabled in this environment (vector_stores_config.opensearch.*)"
            )
        base_collection = _require(
            opensearch_cfg.get("collection_name"),
            "OpenSearch enabled but missing opensearch.collection_name",
        )
        # Reuse the shared test index. This environment is at the OpenSearch
        # shard limit, so per-test index creation is no longer reliable.
        collection_name = base_collection
        config = {
            "host": _require(
                opensearch_cfg.get("host"), "OpenSearch enabled but missing opensearch.host"
            ),
            "port": int(
                _require(
                    opensearch_cfg.get("port"), "OpenSearch enabled but missing opensearch.port"
                )
            ),
            "ssl": opensearch_cfg.get("ssl", False),
            "verify_certs": opensearch_cfg.get("verify_certs", True),
            "username": opensearch_cfg.get("username"),
            "password": opensearch_cfg.get("password"),
            "api_key": opensearch_cfg.get("api_key"),
            "collection_name": collection_name,
        }
    elif store_type == "weaviate":
        weaviate_cfg = _get_enabled_profile_config("weaviate", ["_DEFAULT_", "_TEST_"])
        if not weaviate_cfg:
            pytest.fail(
                "Weaviate not configured/enabled in this environment (vector_stores_config.weaviate.*)"
            )
        base_collection = _require(
            weaviate_cfg.get("collection_name"),
            "Weaviate enabled but missing weaviate.collection_name",
        )
        collection_name = f"{base_collection}_{unique_id}"
        config = {
            "server_url": _require(
                weaviate_cfg.get("url"), "Weaviate enabled but missing weaviate.url"
            ),
            "api_key": weaviate_cfg.get("api_key"),
            "collection_name": collection_name,
        }
    elif store_type == "pgvector":
        pg_cfg = _get_enabled_profile_config("pgvector", ["_TEST_", "_DEFAULT_"])
        if not pg_cfg:
            pytest.fail(
                "PGVector not configured/enabled in this environment (vector_stores_config.pgvector.*)"
            )
        database_uri = _require(
            pg_cfg.get("database_uri"), "PGVector enabled but missing pgvector.database_uri"
        )
        parsed = urllib.parse.urlparse(database_uri)
        base_collection = _require(
            pg_cfg.get("collection_name"), "PGVector enabled but missing pgvector.collection_name"
        )
        collection_name = f"{base_collection}_{unique_id}"
        config = {
            "database_uri": database_uri,
            "host": _require(parsed.hostname, "PGVector enabled but database_uri missing host"),
            "port": int(parsed.port or 5432),
            "database": _require(
                parsed.path.lstrip("/") or None,
                "PGVector enabled but database_uri missing database path",
            ),
            "username": _require(
                parsed.username, "PGVector enabled but database_uri missing username"
            ),
            "password": parsed.password or "",
            "collection_name": collection_name,
        }
    else:
        pytest.fail(f"Unsupported vector store type '{store_type}' in AT1.9 helper")

    response = api_client.post(
        "/vector-stores",
        json={"name": store_name, "store_type": store_type, "config": config, "enabled": True},
    )

    if response.status_code != 200:
        pytest.fail(
            f"Failed to create vector store '{store_type}': {response.status_code} {response.text}"
        )

    return response.json()


def add_message_to_vector_store(
    api_client,
    vector_store_id: int,
    collection: str,
    message_content: str,
    message_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Add a message as a document to a vector store via API.

    Args:
        api_client: Test client
        vector_store_id: Vector store ID
        collection: Collection name
        message_content: Message content
        message_id: Optional message ID
        metadata: Optional metadata

    Returns:
        Added document data
    """
    response = api_client.post(
        f"/vector-stores/{vector_store_id}/documents",
        json={
            "collection": collection,
            "document": message_content,
            "id": message_id,
            "metadata": metadata or {},
        },
    )

    if response.status_code != 200:
        if response.status_code == 503 and "not available" in response.text.lower():
            pytest.fail(f"Vector store backend unavailable: {response.text}")
        raise Exception(f"Failed to add document to vector store: {response.text}")

    return response.json()


def query_vector_store(
    api_client,
    vector_store_id: int,
    collection: str,
    query: str,
    n_results: int = 5,
    filter: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Query a vector store via API.

    Args:
        api_client: Test client
        vector_store_id: Vector store ID
        collection: Collection name
        query: Query text
        n_results: Number of results
        filter: Optional filter

    Returns:
        Query results
    """
    response = api_client.post(
        f"/vector-stores/{vector_store_id}/query",
        json={
            "collection": collection,
            "query": query,
            "n_results": n_results,
            "filter": filter or {},
        },
    )

    if response.status_code != 200:
        if response.status_code == 503 and "not available" in response.text.lower():
            pytest.fail(f"Vector store backend unavailable: {response.text}")
        raise Exception(f"Failed to query vector store: {response.text}")

    return response.json()


def create_session_with_messages(
    api_client,
    user_id: int,
    expert_id: int,
    messages: List[Dict[str, str]],
    context_window: Optional[int] = None,
) -> Dict[str, Any]:
    """Create a session and add messages via API.

    Args:
        api_client: Test client
        user_id: User ID
        expert_id: Expert ID
        messages: List of messages (role, content)
        context_window: Context window size

    Returns:
        Session data with message IDs
    """
    if context_window is None:
        cw = get_config("session.context_window_size")
        if cw is None:
            pytest.fail("session.context_window_size not configured (required for AT1.9)")
        context_window = int(cw)

    # Create session
    session_response = api_client.post(
        "/sessions",
        json={
            "user_id": user_id,
            "expert_config_id": expert_id,
            "title": f"Test Session {uuid.uuid4().hex[:8]}",
            "context_window": context_window,
        },
    )

    if session_response.status_code != 200:
        pytest.fail(
            f"Failed to create session: {session_response.status_code} {session_response.text}"
        )

    session_data = session_response.json()
    session_id = session_data["id"]

    # Add messages
    message_ids = []
    for msg in messages:
        msg_response = api_client.post(f"/sessions/{session_id}/messages", json=msg)
        if msg_response.status_code != 200:
            pytest.fail(f"Failed to add message: {msg_response.status_code} {msg_response.text}")
        message_data = msg_response.json()
        message_ids.append(message_data["id"])

    return {"session": session_data, "message_ids": message_ids}

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.vdb, pytest.mark.db, pytest.mark.heavy]
