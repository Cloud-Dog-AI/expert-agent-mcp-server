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
AT1.11 MCP Tool Workflow Test Helpers

License: Apache 2.0
Ownership: Cloud Dog
Description: Shared helper functions for AT1.11 tests (API-only, config-only).

Related Requirements: FR1.24, FR1.30
Related Tasks: T039, T068
Related Architecture: AI1.2, CC4.1.2
Related Tests: AT1.11
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pytest

from src.config.loader import get_config


def _get_nested(config: Dict[str, Any], keys: List[str]) -> Any:
    cur: Any = config
    for key in keys:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(key)
    return cur


def _require(value: Any, message: str) -> Any:
    if value is None or (isinstance(value, str) and not value.strip()):
        pytest.fail(message)
    return value


def _get_enabled_profile_config(
    store: str, preferred_profiles: List[str]
) -> Optional[Dict[str, Any]]:
    """
    Return the first enabled profile config for a vector store backend.

    Skip ONLY when no enabled profile exists (i.e., backend not configured/enabled).
    Fail when a profile is enabled but missing required keys (callers should `_require`).
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
        if isinstance(enabled, str):
            enabled = enabled.strip().lower() == "true"
        if enabled is True:
            return profile_cfg

    return None


def get_qdrant_profile_cfg() -> Optional[Dict[str, Any]]:
    return _get_enabled_profile_config("qdrant", ["_TEST_", "_DEFAULT_"])


def get_opensearch_profile_cfg() -> Optional[Dict[str, Any]]:
    return _get_enabled_profile_config("opensearch", ["_TEST_", "_DEFAULT_"])


def get_weaviate_profile_cfg() -> Optional[Dict[str, Any]]:
    return _get_enabled_profile_config("weaviate", ["_TEST_", "_DEFAULT_"])


def get_pgvector_profile_cfg() -> Optional[Dict[str, Any]]:
    return _get_enabled_profile_config("pgvector", ["_TEST_", "_DEFAULT_"])


def get_chroma_profile_cfg() -> Optional[Dict[str, Any]]:
    return _get_enabled_profile_config("chroma", ["_DEFAULT_", "_REMOTE_"])


def qdrant_vector_store_create_config() -> Dict[str, Any]:
    cfg = get_qdrant_profile_cfg()
    if not cfg:
        pytest.fail(
            "Qdrant not configured/enabled in this environment (vector_stores_config.qdrant.*)"
        )
    return {
        "host": _require(cfg.get("host"), "Qdrant enabled but missing qdrant.host"),
        "port": int(_require(cfg.get("port"), "Qdrant enabled but missing qdrant.port")),
        "api_key": cfg.get("api_key"),
        "collection_name": _require(
            cfg.get("collection_name"), "Qdrant enabled but missing qdrant.collection_name"
        ),
        "ssl": cfg.get("ssl", False),
    }


def opensearch_vector_store_create_config(collection_name: Optional[str] = None) -> Dict[str, Any]:
    cfg = get_opensearch_profile_cfg()
    if not cfg:
        pytest.fail(
            "OpenSearch not configured/enabled in this environment (vector_stores_config.opensearch.*)"
        )
    return {
        "host": _require(cfg.get("host"), "OpenSearch enabled but missing opensearch.host"),
        "port": int(_require(cfg.get("port"), "OpenSearch enabled but missing opensearch.port")),
        "ssl": cfg.get("ssl", False),
        "verify_certs": cfg.get("verify_certs", True),
        "username": cfg.get("username"),
        "password": cfg.get("password"),
        "api_key": cfg.get("api_key"),
        "collection_name": collection_name
        or _require(
            cfg.get("collection_name"), "OpenSearch enabled but missing opensearch.collection_name"
        ),
    }


def weaviate_vector_store_create_config() -> Dict[str, Any]:
    cfg = get_weaviate_profile_cfg()
    if not cfg:
        pytest.fail(
            "Weaviate not configured/enabled in this environment (vector_stores_config.weaviate.*)"
        )
    return {
        "url": _require(cfg.get("url"), "Weaviate enabled but missing weaviate.url"),
        "api_key": cfg.get("api_key"),
        "collection_name": _require(
            cfg.get("collection_name"), "Weaviate enabled but missing weaviate.collection_name"
        ),
    }


def pgvector_vector_store_create_config() -> Dict[str, Any]:
    cfg = get_pgvector_profile_cfg()
    if not cfg:
        pytest.fail(
            "PGVector not configured/enabled in this environment (vector_stores_config.pgvector.*)"
        )
    return {
        "database_uri": _require(
            cfg.get("database_uri"), "PGVector enabled but missing pgvector.database_uri"
        ),
        "collection_name": _require(
            cfg.get("collection_name"), "PGVector enabled but missing pgvector.collection_name"
        ),
    }


def chroma_vector_store_create_config() -> Dict[str, Any]:
    cfg = get_chroma_profile_cfg()
    if not cfg:
        pytest.fail(
            "Chroma not configured/enabled in this environment (vector_stores_config.chroma.*)"
        )
    if cfg.get("path"):
        return {
            "path": _require(cfg.get("path"), "Chroma enabled but missing chroma.path"),
            "collection_name": _require(
                cfg.get("collection_name"), "Chroma enabled but missing chroma.collection_name"
            ),
        }
    return {
        "host": _require(cfg.get("host"), "Chroma remote enabled but missing chroma.host"),
        "port": int(_require(cfg.get("port"), "Chroma remote enabled but missing chroma.port")),
        "ssl": cfg.get("ssl", False),
        "auth_token": cfg.get("auth_token"),
        "collection_name": _require(
            cfg.get("collection_name"), "Chroma enabled but missing chroma.collection_name"
        ),
    }
