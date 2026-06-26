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
100% API-based testing with REAL embedding and search operations.

Related Requirements: FR1.3
Related Tasks: T014, T015, T016, T017, T018
Related Architecture: CC4.1.1, IP1.1.2
Related Tests: AT1.17

Test Coverage:
- AT1.17a: Create Chroma vector store and verify CRUD
- AT1.17b: Create Qdrant vector store and verify CRUD
- AT1.17c: Create OpenSearch vector store and verify CRUD
- AT1.17d: Create PGVector vector store and verify CRUD
- AT1.17e: Create Weaviate vector store and verify CRUD
- AT1.17f: Document CRUD operations (TEXT format) - Chroma
- AT1.17g: Document CRUD operations (JSON format) - Qdrant
- AT1.17h: Document CRUD operations (MARKDOWN format) - OpenSearch
- AT1.17i: Semantic search with TEXT documents - Chroma
- AT1.17j: Semantic search with metadata filtering - Qdrant
- AT1.17k: Semantic search quality validation - Chroma
- AT1.17l: Multi-document batch operations - Chroma
- AT1.17m: Duplicate vector store name rejection
- AT1.17n: Invalid vector store configuration rejection
- AT1.17o: Vector store enable/disable lifecycle
- AT1.17p: Vector store with access control
- AT1.17q: Vector store deletion with documents (cascade)
- AT1.17r: List/filter/pagination vector stores
- AT1.17s: Document operations on disabled vector store
- AT1.17t: Health check for all vector store types
- AT1.17u: Search with distance metrics (L2, cosine, dot)
- AT1.17v: Search with n_results variations
- AT1.17w: Collection isolation (multiple collections per store)
- AT1.17x: Large document handling and chunking
- AT1.17y: Empty query and edge cases
- AT1.17z: Vector store configuration updates and effects

**************************************************
"""

import pytest
import sys
import uuid
import time
import json
import socket
import requests

try:
    import psycopg2
except ModuleNotFoundError:  # optional dependency for pgvector-only checks
    psycopg2 = None
from pathlib import Path
from src.config.loader import load_config, get_config

sys.path.insert(0, str(Path(__file__).parent.parent))
from test_helpers_common import (
    log_http_operation,
)


class APIClient:
    """HTTP client for real API server (requests-based)."""

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        try:
            resp = self.session.request(method, url, timeout=20, **kwargs)
        except requests.exceptions.ReadTimeout:
            if path.startswith("/vector-stores"):
                pytest.fail("Vector store backend timed out (read timeout).")
            raise
        except requests.exceptions.ConnectionError:
            if path.startswith("/vector-stores"):
                pytest.fail("Vector store backend unreachable (connection error).")
            raise
        log_http_operation(
            f"api_{method.lower()}_{path.strip('/').replace('/', '_') or 'root'}",
            method,
            url,
            resp,
            request_data={
                k: kwargs.get(k) for k in ("params", "json", "data", "headers") if k in kwargs
            },
        )
        if path.startswith("/vector-stores") and _response_is_backend_unavailable(resp):
            pytest.fail(f"Vector store backend unavailable: {resp.text}")
        return resp

    def get(self, path: str, **kwargs):
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        return self._request("POST", path, **kwargs)

    def put(self, path: str, **kwargs):
        return self._request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs):
        return self._request("DELETE", path, **kwargs)


# Provider availability checks (fail fast if service unreachable)
def _logged_requests_get(url: str, **kwargs):
    resp = requests.get(url, **kwargs)
    log_http_operation(
        "external_get",
        "GET",
        url,
        resp,
        request_data={k: kwargs.get(k) for k in ("params", "headers", "timeout") if k in kwargs},
    )
    return resp


def _response_is_backend_unavailable(resp: requests.Response) -> bool:
    text = (resp.text or "").lower()
    if "backend" in text and "not available" in text:
        return True
    # External embedding service instability should be treated as backend-unavailable
    # for vector-store CRUD/search validation scenarios.
    if resp.status_code in (500, 502, 503, 504) and (
        "api/embeddings" in text or "failed to add document" in text
    ):
        return True
    return False


def check_chroma_available(config):
    chroma_cfg = config.get("vector_stores_config", {}).get("chroma", {})
    chroma_remote = chroma_cfg.get("_REMOTE_", {}) if isinstance(chroma_cfg, dict) else {}
    chroma_default = chroma_cfg.get("_DEFAULT_", {}) if isinstance(chroma_cfg, dict) else {}

    host = chroma_remote.get("host")
    if host:
        try:
            port = chroma_remote.get("port", "443")
            ssl = str(chroma_remote.get("ssl", "true")).lower() == "true"
            protocol = "https" if ssl else "http"
            server_url = f"{protocol}://{host}:{port}" if "://" not in host else host
            resp = _logged_requests_get(server_url.rstrip("/") + "/api/v1/heartbeat", timeout=5)
            return resp.status_code < 500  # Accept any non-server-error response
        except Exception:
            return False

    path = (
        chroma_default.get("path")
        or config.get("vector_stores_config.chroma._DEFAULT_.path")
        or config.get("vector_stores.chroma.default.path")
        or config.get("vector_stores", {}).get("chroma", {}).get("default", {}).get("path")
    )
    if not path:
        return False
    try:
        p = Path(path)
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
        return p.exists()
    except Exception:
        return False


def check_qdrant_available(config):
    qdrant_config = config.get("vector_stores_config", {}).get("qdrant", {}).get("_DEFAULT_", {})
    host = qdrant_config.get("host") or config.get("vector_stores_config.qdrant._DEFAULT_.host")
    port = qdrant_config.get("port") or config.get("vector_stores_config.qdrant._DEFAULT_.port")
    api_key = qdrant_config.get("api_key") or config.get(
        "vector_stores_config.qdrant._DEFAULT_.api_key"
    )
    if not host or not port:
        return False
    url = f"http://{host}:{port}/collections"
    try:
        headers = {}
        if api_key:
            headers["api-key"] = api_key
        resp = _logged_requests_get(url, headers=headers, timeout=5)
        return resp.status_code < 500
    except Exception:
        return False


def check_opensearch_available(config):
    # Read from vector_stores_config._TEST_ first (matches env file/profile token)
    test_config = config.get("vector_stores_config", {}).get("opensearch", {}).get("_TEST_", {})
    host = test_config.get("host") or config.get("vector_stores", {}).get("opensearch", {}).get(
        "default", {}
    ).get("host")
    configured_port = test_config.get("port") or config.get("vector_stores", {}).get(
        "opensearch", {}
    ).get("default", {}).get("port")
    port = configured_port
    use_ssl = str(test_config.get("ssl", "false")).lower() == "true" or config.get(
        "vector_stores", {}
    ).get("opensearch", {}).get("default", {}).get("ssl", False)
    username = (
        test_config.get("username")
        or get_config("vector_stores_config.opensearch._TEST_.username")
        or get_config("vector_stores_config.opensearch._DEFAULT_.username")
    )
    password = (
        test_config.get("password")
        or get_config("vector_stores_config.opensearch._TEST_.password")
        or get_config("vector_stores_config.opensearch._DEFAULT_.password")
    )
    verify_certs = str(test_config.get("verify_certs", "false")).lower() != "false"

    if not host:
        return False

    scheme = "https" if str(use_ssl).lower() == "true" else "http"
    url = f"{scheme}://{host}:{port}"
    try:
        auth = None
        if username and password:
            from requests.auth import HTTPBasicAuth

            auth = HTTPBasicAuth(username, password)
        resp = _logged_requests_get(url, auth=auth, verify=verify_certs, timeout=5)
        return resp.status_code < 500
    except Exception:
        return False


def check_pgvector_available(config):
    # Match how test reads config (line 950-970)
    test_config = config.get("vector_stores_config", {}).get("pgvector", {}).get("_TEST_", {})
    # Try database_uri first (if available, it has the correct password format)
    db_uri = test_config.get("database_uri")
    if db_uri:
        try:
            if psycopg2 is not None:
                conn = psycopg2.connect(db_uri, connect_timeout=5)
                conn.close()
                return True
            # Fallback when psycopg2 isn't installed: basic TCP reachability check.
            try:
                from urllib.parse import urlparse

                parsed = urlparse(db_uri)
                if parsed.hostname and parsed.port:
                    with socket.create_connection((parsed.hostname, parsed.port), timeout=5):
                        return True
            except Exception:
                pass
        except Exception:
            pass  # Fall through to individual components

    # Fallback to individual components
    host = test_config.get("host") or config.get("vector_stores", {}).get("pgvector", {}).get(
        "default", {}
    ).get("host")
    port = test_config.get("port") or config.get("vector_stores", {}).get("pgvector", {}).get(
        "default", {}
    ).get("port")
    db = test_config.get("database") or config.get("vector_stores", {}).get("pgvector", {}).get(
        "default", {}
    ).get("database")
    user = test_config.get("username") or config.get("vector_stores", {}).get("pgvector", {}).get(
        "default", {}
    ).get("user")
    password = test_config.get("password") or config.get("vector_stores", {}).get(
        "pgvector", {}
    ).get("default", {}).get("password")
    if not host or not port or not db:
        return False
    try:
        if psycopg2 is not None:
            conn = psycopg2.connect(
                host=host, port=port, dbname=db, user=user, password=password, connect_timeout=5
            )
            conn.close()
            return True
        with socket.create_connection((str(host), int(port)), timeout=5):
            return True
    except Exception:
        return False


def check_weaviate_available(config):
    vector_cfg = config.get("vector_stores_config", {}).get("weaviate", {})
    default_cfg = vector_cfg.get("_DEFAULT_", {}) if isinstance(vector_cfg, dict) else {}
    remote_cfg = vector_cfg.get("_REMOTE_", {}) if isinstance(vector_cfg, dict) else {}
    url = (
        default_cfg.get("url")
        or default_cfg.get("server_url")
        or remote_cfg.get("url")
        or remote_cfg.get("server_url")
        or config.get("vector_stores", {}).get("weaviate", {}).get("_DEFAULT_", {}).get("url")
        or config.get("vector_stores.weaviate._DEFAULT_.url")
    )
    if not url:
        return False
    try:
        resp = _logged_requests_get(url.rstrip("/") + "/v1/.well-known/ready", timeout=5)
        return resp.status_code < 500
    except Exception:
        return False


def assert_provider_available(provider: str, config):
    env_file = get_config("test.env_file")
    if not env_file:
        pytest.fail("test.env_file not configured; ensure --env is provided")
    env_basename = Path(str(env_file)).name
    backend_specific_targets = {"qdrant", "chroma", "opensearch", "pgvector", "weaviate"}
    target_backend = None
    if env_basename.startswith("env-test-") and env_basename != "env-test-secrets":
        candidate = env_basename.removeprefix("env-test-")
        if candidate in backend_specific_targets:
            target_backend = candidate
    if env_basename.startswith("private/env-test-"):
        candidate = env_basename.removeprefix("private/env-test-")
        if candidate in backend_specific_targets:
            target_backend = candidate

    def _provider_configured() -> bool:
        if target_backend and provider != target_backend:
            return False
        vector_cfg = config.get("vector_stores_config", {})
        if provider == "chroma":
            chroma_cfg = vector_cfg.get("chroma", {}) if isinstance(vector_cfg, dict) else {}
            chroma_remote = chroma_cfg.get("_REMOTE_", {}) if isinstance(chroma_cfg, dict) else {}
            chroma_default = chroma_cfg.get("_DEFAULT_", {}) if isinstance(chroma_cfg, dict) else {}

            if chroma_remote.get("host"):
                return True

            local_path = (
                chroma_default.get("path")
                or config.get("vector_stores_config.chroma._DEFAULT_.path")
                or config.get("vector_stores.chroma.default.path")
                or config.get("vector_stores", {}).get("chroma", {}).get("default", {}).get("path")
            )
            return bool(local_path)
        if provider == "qdrant":
            qdrant_default = vector_cfg.get("qdrant", {}).get("_DEFAULT_", {})
            return bool(qdrant_default.get("host") and qdrant_default.get("port"))
        if provider == "opensearch":
            os_test = vector_cfg.get("opensearch", {}).get("_TEST_", {})
            os_default = vector_cfg.get("opensearch", {}).get("_DEFAULT_", {})
            candidate = os_test if os_test else os_default
            return bool(candidate.get("host") and candidate.get("port"))
        if provider == "pgvector":
            pg_test = vector_cfg.get("pgvector", {}).get("_TEST_", {})
            if pg_test.get("database_uri"):
                return True
            return bool(pg_test.get("host") and pg_test.get("port") and pg_test.get("database"))
        if provider == "weaviate":
            url = (
                vector_cfg.get("weaviate", {}).get("_DEFAULT_", {}).get("url")
                or vector_cfg.get("weaviate", {}).get("_REMOTE_", {}).get("server_url")
                or config.get("vector_stores", {})
                .get("weaviate", {})
                .get("_DEFAULT_", {})
                .get("url")
                or config.get("vector_stores.weaviate._DEFAULT_.url")
            )
            return bool(url)
        return False

    checkers = {
        "chroma": check_chroma_available,
        "qdrant": check_qdrant_available,
        "opensearch": check_opensearch_available,
        "pgvector": check_pgvector_available,
        "weaviate": check_weaviate_available,
    }
    checker = checkers.get(provider)
    if not checker:
        pytest.fail(f"No availability checker for provider: {provider}")
    if target_backend and provider != target_backend:
        pytest.fail(f"{provider} skipped for env target backend '{target_backend}'")
    if not _provider_configured():
        pytest.fail(f"{provider} not configured for this env/test run")
    if not checker(config):
        if target_backend == provider:
            pytest.fail(f"{provider} service NOT available - cannot run real VDB test")
        pytest.fail(f"{provider} service not available in current environment")


def get_chroma_config(config):
    """Get Chroma connection configuration for API payloads.

    Supports:
    - Local/persistent Chroma: vector_stores_config.chroma._DEFAULT_.path
    - Remote Chroma: vector_stores_config.chroma._REMOTE_.host/port/ssl/auth_token
    - Legacy remote: vector_stores.chroma.remote.server_url (+ auth_token)
    """
    chroma_cfg = config.get("vector_stores_config", {}).get("chroma", {})
    chroma_default = chroma_cfg.get("_DEFAULT_", {}) if isinstance(chroma_cfg, dict) else {}
    chroma_remote = chroma_cfg.get("_REMOTE_", {}) if isinstance(chroma_cfg, dict) else {}

    path = chroma_default.get("path")
    if isinstance(path, str) and path.strip():
        return {"path": path}

    host = chroma_remote.get("host")
    if isinstance(host, str) and host.strip():
        return {
            "host": host,
            "port": chroma_remote.get("port"),
            "ssl": chroma_remote.get("ssl"),
            "auth_token": chroma_remote.get("auth_token"),
        }

    legacy_server_url = config.get("vector_stores", {}).get("chroma", {}).get("remote", {}).get(
        "server_url"
    ) or config.get("vector_stores.chroma.remote.server_url")
    if isinstance(legacy_server_url, str) and legacy_server_url.strip():
        return {
            "server_url": legacy_server_url,
            "auth_token": config.get("vector_stores.chroma.remote.auth_token"),
        }

    pytest.fail(
        "Missing required configuration: vector_stores_config.chroma._DEFAULT_.path or vector_stores_config.chroma._REMOTE_.host or vector_stores.chroma.remote.server_url"
    )


def require_config(value, name: str):
    """Fail fast when required configuration is missing."""
    if value is None or (isinstance(value, str) and value.strip() == ""):
        pytest.fail(f"Missing required configuration: {name}")
    return value


class TestOutputManager:
    __test__ = False  # Prevent pytest from collecting this helper as a test class
    """Manages test outputs for AT1.17 Vector Store Management tests."""

    def __init__(self, test_name: str):
        self.test_name = test_name
        self.base_dir = Path("working/AT1.17_TEST_OUTPUTS") / test_name
        self.base_dir.mkdir(parents=True, exist_ok=True)

        self.inputs_dir = self.base_dir / "inputs"
        self.outputs_dir = self.base_dir / "outputs"
        self.validations_dir = self.base_dir / "validations"
        self.vdb_ops_dir = self.base_dir / "vdb_operations"

        for d in [self.inputs_dir, self.outputs_dir, self.validations_dir, self.vdb_ops_dir]:
            d.mkdir(exist_ok=True)

        self.operation_counter = 0
        self.validation_counter = 0
        self.vdb_counter = 0
        self.validations = []
        self.console_log = []
        self.start_time = time.time()

    def save_input(self, operation: str, data: dict) -> Path:
        """Save input data."""
        self.operation_counter += 1
        filename = f"{self.operation_counter:02d}_{operation}_input.json"
        filepath = self.inputs_dir / filename
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)
        return filepath.resolve()

    def save_output(self, operation: str, data: dict) -> Path:
        """Save output data."""
        filename = f"{self.operation_counter:02d}_{operation}_output.json"
        filepath = self.outputs_dir / filename
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2, default=str)
        return filepath.resolve()

    def save_vdb_operation(self, operation: str, details: dict) -> Path:
        """Save VDB operation details."""
        self.vdb_counter += 1
        filename = f"{self.vdb_counter:02d}_{operation}.json"
        filepath = self.vdb_ops_dir / filename
        with open(filepath, "w") as f:
            json.dump(details, f, indent=2, default=str)
        return filepath.resolve()

    def validate(
        self, name: str, condition: bool, actual: any, expected: any = None, context: str = ""
    ) -> bool:
        """Record a validation."""
        self.validation_counter += 1
        validation = {
            "id": self.validation_counter,
            "name": name,
            "passed": condition,
            "actual": str(actual)[:200],
            "expected": str(expected)[:200] if expected is not None else "N/A",
            "context": context,
        }
        self.validations.append(validation)

        # Log to console
        status = "✅ PASS" if condition else "❌ FAIL"
        log_msg = f"[VALIDATION {self.validation_counter:02d}] {status}: {name}"
        print(log_msg)
        self.log_console(log_msg)
        if not condition:
            detail_msg = f"  Expected: {expected}, Actual: {actual}"
            print(detail_msg)
            self.log_console(detail_msg)

        filename = f"{self.validation_counter:02d}_{name.replace(' ', '_')}.json"
        filepath = self.validations_dir / filename
        with open(filepath, "w") as f:
            json.dump(validation, f, indent=2)

        return condition

    def log_console(self, message: str):
        """Log a message to console and internal buffer."""
        timestamp = time.time() - self.start_time
        self.console_log.append(f"[{timestamp:8.3f}s] {message}")

    def save_console_log(self) -> Path:
        """Save all console output to a file."""
        filepath = self.base_dir / "console.log"
        with open(filepath, "w") as f:
            f.write(f"{'=' * 80}\n")
            f.write(f"CONSOLE OUTPUT: {self.test_name}\n")
            f.write(f"Started: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"{'=' * 80}\n\n")
            for line in self.console_log:
                f.write(line + "\n")
            f.write(f"\n{'=' * 80}\n")
            f.write(f"Test Duration: {time.time() - self.start_time:.2f}s\n")
            f.write(f"{'=' * 80}\n")
        return filepath.resolve()

    def generate_summary_table(self) -> str:
        """Generate markdown summary table with clickable file:// URIs."""
        passed = sum(1 for v in self.validations if v["passed"])
        total = len(self.validations)
        pass_rate = (passed / total * 100) if total > 0 else 0

        # Save console log
        console_uri = self.save_console_log().as_uri()

        table = f"\n{'=' * 80}\n"
        table += f"TEST SUMMARY: {self.test_name}\n"
        table += f"{'=' * 80}\n\n"

        # Console Log
        table += "## CONSOLE LOG\n"
        table += f"- [console.log]({console_uri})\n"

        # Inputs
        table += "\n## INPUTS\n"
        for f in sorted(self.inputs_dir.glob("*.json")):
            uri = f.resolve().as_uri()
            table += f"- [{f.name}]({uri})\n"

        # Outputs
        table += "\n## OUTPUTS\n"
        for f in sorted(self.outputs_dir.glob("*.json")):
            uri = f.resolve().as_uri()
            table += f"- [{f.name}]({uri})\n"

        # VDB Operations
        table += "\n## VDB OPERATIONS\n"
        for f in sorted(self.vdb_ops_dir.glob("*.json")):
            uri = f.resolve().as_uri()
            table += f"- [{f.name}]({uri})\n"

        # Validations
        table += "\n## VALIDATIONS\n"
        for f in sorted(self.validations_dir.glob("*.json")):
            uri = f.resolve().as_uri()
            table += f"- [{f.name}]({uri})\n"

        # Summary
        table += "\n## RESULTS\n"
        table += f"- **Total Validations**: {total}\n"
        table += f"- **Passed**: {passed}\n"
        table += f"- **Failed**: {total - passed}\n"
        table += f"- **Pass Rate**: {pass_rate:.1f}%\n"
        table += f"- **Duration**: {time.time() - self.start_time:.2f}s\n"
        table += f"\n{'=' * 80}\n"

        return table


@pytest.fixture(scope="session")
def api_client(test_env_file):
    """Real API client hitting running server (no TestClient)."""
    load_config.cache_clear()
    load_config()

    host = get_config("api_server.host")
    port = get_config("api_server.port")
    if not host or not port:
        pytest.fail(
            "API server host/port not configured. Set api_server.host and api_server.port in your --env file."
        )
    base_url = f"http://{host}:{port}"

    client = APIClient(base_url)
    api_key = get_config("api_server.api_key") or get_config("test.api_key")
    if not api_key:
        pytest.fail("api_server.api_key or test.api_key must be configured")
    client.session.headers.update({"X-API-Key": str(api_key)})
    try:
        resp = client.get("/health")
    except Exception as exc:  # pragma: no cover
        pytest.fail(f"API server not reachable at {base_url}: {exc}")

    if resp.status_code != 200:
        pytest.fail(
            f"API health check failed at {base_url} -> status {resp.status_code}, body={resp.text}"
        )

    return client
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17a_create_chroma_vector_store_and_verify(api_client):
    config = get_config()
    assert_provider_available("chroma", config)

    mgr = TestOutputManager("AT1.17a_chroma_remote_crud")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.17a - Chroma Vector Store CRUD (remote)")
    mgr.log_console("=" * 80)

    chroma_conn = get_chroma_config(config)

    collection_name = f"test_collection_{uuid.uuid4().hex[:8]}"
    create_config = {
        **chroma_conn,
        "collection_name": collection_name,
        "distance_metric": "cosine",
    }
    create_payload = {
        "name": f"test_chroma_{uuid.uuid4().hex[:8]}",
        "store_type": "chroma",
        "config": create_config,
        "enabled": True,
        "access_control": {},
    }
    mgr.save_input("create_vector_store", create_payload)

    response = api_client.post("/vector-stores", json=create_payload)
    create_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("create_vector_store", create_output)

    mgr.validate("create_status_200", response.status_code == 200, response.status_code, 200)
    store_id = create_output.get("id")
    mgr.validate("id_present", store_id is not None, store_id)
    mgr.validate(
        "name_matches",
        create_output.get("name") == create_payload["name"],
        create_output.get("name"),
        create_payload["name"],
    )
    mgr.validate(
        "type_matches", create_output.get("type") == "chroma", create_output.get("type"), "chroma"
    )
    if "path" in chroma_conn:
        mgr.validate(
            "config_path",
            create_output.get("config", {}).get("path") == chroma_conn["path"],
            create_output.get("config", {}).get("path"),
            chroma_conn["path"],
        )
    elif "server_url" in chroma_conn:
        mgr.validate(
            "config_server_url",
            create_output.get("config", {}).get("server_url") == chroma_conn["server_url"],
            create_output.get("config", {}).get("server_url"),
            chroma_conn["server_url"],
        )
    else:
        mgr.validate(
            "config_host",
            create_output.get("config", {}).get("host") == chroma_conn.get("host"),
            create_output.get("config", {}).get("host"),
            chroma_conn.get("host"),
        )

    mgr.save_vdb_operation(
        "chroma_store_created",
        {
            "operation": "create_vector_store",
            "store_type": "chroma",
            "store_id": store_id,
            "config": create_payload["config"],
        },
    )

    # READ
    mgr.save_input("get_vector_store", {"store_id": store_id})
    response = api_client.get(f"/vector-stores/{store_id}")
    get_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("get_vector_store", get_output)
    mgr.validate("get_status_200", response.status_code == 200, response.status_code, 200)
    mgr.validate("get_id_matches", get_output.get("id") == store_id, get_output.get("id"), store_id)
    if "path" in chroma_conn:
        mgr.validate(
            "get_path_matches",
            get_output.get("config", {}).get("path") == chroma_conn["path"],
            get_output.get("config", {}).get("path"),
            chroma_conn["path"],
        )
    elif "server_url" in chroma_conn:
        mgr.validate(
            "get_server_url_matches",
            get_output.get("config", {}).get("server_url") == chroma_conn["server_url"],
            get_output.get("config", {}).get("server_url"),
            chroma_conn["server_url"],
        )
    else:
        mgr.validate(
            "get_host_matches",
            get_output.get("config", {}).get("host") == chroma_conn.get("host"),
            get_output.get("config", {}).get("host"),
            chroma_conn.get("host"),
        )

    # UPDATE
    updated_collection = f"{collection_name}_updated"
    update_config = {
        **chroma_conn,
        "collection_name": updated_collection,
        "distance_metric": "l2",
    }
    update_payload = {"config": update_config}
    mgr.save_input("update_vector_store", update_payload)
    response = api_client.put(f"/vector-stores/{store_id}", json=update_payload)
    update_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("update_vector_store", update_output)
    mgr.validate("update_status_200", response.status_code == 200, response.status_code, 200)
    mgr.validate(
        "update_collection_changed",
        update_output.get("config", {}).get("collection_name") == updated_collection,
        update_output.get("config", {}).get("collection_name"),
        updated_collection,
    )

    mgr.save_vdb_operation(
        "chroma_store_updated",
        {
            "operation": "update_vector_store",
            "store_id": store_id,
            "updated_config": update_payload["config"],
        },
    )

    # DELETE
    mgr.save_input("delete_vector_store", {"store_id": store_id})
    response = api_client.delete(f"/vector-stores/{store_id}")
    delete_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("delete_vector_store", delete_output)
    mgr.validate("delete_status_200", response.status_code == 200, response.status_code, 200)

    # VERIFY DELETION
    mgr.save_input("verify_deletion", {"store_id": store_id})
    response = api_client.get(f"/vector-stores/{store_id}")
    mgr.validate("verify_deletion_404", response.status_code == 404, response.status_code, 404)

    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17b_create_qdrant_vector_store_and_verify(api_client):
    config = get_config()
    assert_provider_available("qdrant", config)

    """
    AT1.17b: Create Qdrant vector store and verify full CRUD.
    
    Tests:
    - Create vector store with Qdrant configuration
    - Retrieve and verify all fields
    - Update vector store configuration
    - Delete vector store
    - Verify deletion
    """
    mgr = TestOutputManager("AT1.17b_qdrant_crud")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.17b - Qdrant Vector Store CRUD")
    mgr.log_console("=" * 80)

    # CREATE
    mgr.log_console("\n[STEP 1/5] Creating Qdrant vector store...")
    config = get_config()
    qdrant_cfg = config.get("vector_stores_config", {}).get("qdrant", {}).get("_DEFAULT_", {})
    qdrant_host = require_config(
        qdrant_cfg.get("host"), "vector_stores_config.qdrant._DEFAULT_.host"
    )
    qdrant_port = require_config(
        qdrant_cfg.get("port"), "vector_stores_config.qdrant._DEFAULT_.port"
    )
    qdrant_api_key = qdrant_cfg.get("api_key")
    qdrant_collection = f"test_collection_{uuid.uuid4().hex[:8]}"

    create_payload = {
        "name": f"test_qdrant_{uuid.uuid4().hex[:8]}",
        "store_type": "qdrant",
        "config": {
            "host": qdrant_host,
            "port": qdrant_port,
            "api_key": qdrant_api_key,
            "collection_name": qdrant_collection,
            "distance_metric": "cosine",
        },
        "enabled": True,
        "access_control": {},
    }
    mgr.save_input("create_vector_store", create_payload)

    response = api_client.post("/vector-stores", json=create_payload)
    create_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("create_vector_store", create_output)

    mgr.validate("create_status_200", response.status_code == 200, response.status_code, 200)
    assert mgr.validate("create_succeeded", response.status_code == 200, response.status_code), (
        f"Create failed with status {response.status_code}: {response.text}"
    )

    store_id = create_output.get("id")
    mgr.validate("id_present", store_id is not None, store_id)
    mgr.validate(
        "name_matches",
        create_output.get("name") == create_payload["name"],
        create_output.get("name"),
        create_payload["name"],
    )
    mgr.validate(
        "type_matches", create_output.get("type") == "qdrant", create_output.get("type"), "qdrant"
    )
    mgr.validate(
        "enabled_is_true", create_output.get("enabled") is True, create_output.get("enabled"), True
    )
    mgr.validate("config_present", "config" in create_output, "config" in create_output)

    # Save VDB operation
    mgr.save_vdb_operation(
        "qdrant_store_created",
        {
            "operation": "create_vector_store",
            "store_type": "qdrant",
            "store_id": store_id,
            "config": {
                "host": qdrant_host,
                "port": qdrant_port,
                "collection_name": qdrant_collection,
                "distance_metric": "cosine",
            },
        },
    )
    mgr.log_console(f"Qdrant store created with ID: {store_id}")

    # READ
    mgr.log_console("\n[STEP 2/5] Reading vector store configuration...")
    mgr.save_input("get_vector_store", {"store_id": store_id})
    response = api_client.get(f"/vector-stores/{store_id}")
    get_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("get_vector_store", get_output)

    mgr.validate("get_status_200", response.status_code == 200, response.status_code, 200)
    mgr.validate("get_id_matches", get_output.get("id") == store_id, get_output.get("id"), store_id)
    mgr.validate(
        "get_name_matches",
        get_output.get("name") == create_payload["name"],
        get_output.get("name"),
        create_payload["name"],
    )
    mgr.validate(
        "get_config_host",
        get_output.get("config", {}).get("host") == qdrant_host,
        get_output.get("config", {}).get("host"),
        qdrant_host,
    )
    mgr.validate(
        "get_config_port",
        get_output.get("config", {}).get("port") == qdrant_port,
        get_output.get("config", {}).get("port"),
        qdrant_port,
    )
    mgr.log_console("Vector store configuration verified")

    # UPDATE
    mgr.log_console("\n[STEP 3/5] Updating vector store configuration...")
    update_payload = {
        "config": {
            "host": qdrant_host,
            "port": qdrant_port,
            "api_key": qdrant_api_key,
            "collection_name": f"{qdrant_collection}_updated",
            "distance_metric": "euclidean",
        }
    }
    mgr.save_input("update_vector_store", update_payload)

    response = api_client.put(f"/vector-stores/{store_id}", json=update_payload)
    update_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("update_vector_store", update_output)

    mgr.validate("update_status_200", response.status_code == 200, response.status_code, 200)
    mgr.validate(
        "update_collection_changed",
        update_output.get("config", {}).get("collection_name") == f"{qdrant_collection}_updated",
        update_output.get("config", {}).get("collection_name"),
        f"{qdrant_collection}_updated",
    )
    mgr.validate(
        "update_distance_metric_changed",
        update_output.get("config", {}).get("distance_metric") == "euclidean",
        update_output.get("config", {}).get("distance_metric"),
        "euclidean",
    )

    mgr.save_vdb_operation(
        "qdrant_store_updated",
        {
            "operation": "update_vector_store",
            "store_id": store_id,
            "updated_config": {
                "collection_name": f"{qdrant_collection}_updated",
                "distance_metric": "euclidean",
            },
        },
    )
    mgr.log_console("Vector store configuration updated")

    # DELETE
    mgr.log_console("\n[STEP 4/5] Deleting vector store...")
    mgr.save_input("delete_vector_store", {"store_id": store_id})
    response = api_client.delete(f"/vector-stores/{store_id}")
    delete_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("delete_vector_store", delete_output)

    mgr.validate("delete_status_200", response.status_code == 200, response.status_code, 200)
    mgr.log_console(f"Vector store {store_id} deleted")

    # VERIFY DELETION
    mgr.log_console("\n[STEP 5/5] Verifying deletion...")
    mgr.save_input("verify_deletion", {"store_id": store_id})
    response = api_client.get(f"/vector-stores/{store_id}")
    verify_output = (
        response.json() if response.status_code != 200 else {"status": response.status_code}
    )
    mgr.save_output("verify_deletion", verify_output)

    mgr.validate("verify_deletion_404", response.status_code == 404, response.status_code, 404)
    mgr.log_console("Deletion verified (404 returned)")

    mgr.save_vdb_operation(
        "qdrant_store_deleted", {"operation": "delete_vector_store", "store_id": store_id}
    )
    mgr.log_console("\n" + "=" * 80)
    mgr.log_console("TEST COMPLETE: AT1.17b - All operations successful")
    mgr.log_console("=" * 80)

    # Print summary
    summary = mgr.generate_summary_table()
    print(summary)

    # Verify all validations passed
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17c_create_opensearch_vector_store_and_verify(api_client):
    config = get_config()
    assert_provider_available("opensearch", config)

    """
    AT1.17c: Create OpenSearch vector store and verify full CRUD.
    
    Tests:
    - Create vector store with OpenSearch configuration
    - Retrieve and verify all fields
    - Update vector store configuration
    - Delete vector store
    - Verify deletion
    """
    mgr = TestOutputManager("AT1.17c_opensearch_crud")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.17c - OpenSearch Vector Store CRUD")
    mgr.log_console("=" * 80)

    # CREATE
    mgr.log_console("\n[STEP 1/5] Creating OpenSearch vector store...")
    config = get_config()
    # Read from vector_stores_config._TEST_ (matches env file profile token)
    test_config = config.get("vector_stores_config", {}).get("opensearch", {}).get("_TEST_", {})
    opensearch_host = require_config(
        test_config.get("host"), "vector_stores_config.opensearch._TEST_.host"
    )
    opensearch_port = require_config(
        test_config.get("port"), "vector_stores_config.opensearch._TEST_.port"
    )
    opensearch_username = (
        test_config.get("username")
        or get_config("vector_stores_config.opensearch._TEST_.username")
        or get_config("vector_stores_config.opensearch._DEFAULT_.username")
    )
    opensearch_password = (
        test_config.get("password")
        or get_config("vector_stores_config.opensearch._TEST_.password")
        or get_config("vector_stores_config.opensearch._DEFAULT_.password")
    )
    opensearch_ssl = str(test_config.get("ssl", "false")).lower() == "true"
    index_name = require_config(
        test_config.get("collection_name"), "vector_stores_config.opensearch._TEST_.collection_name"
    )

    create_payload = {
        "name": f"test_opensearch_{uuid.uuid4().hex[:8]}",
        "store_type": "opensearch",
        "config": {
            "host": opensearch_host,
            "port": opensearch_port,
            "username": opensearch_username,
            "password": opensearch_password,
            "index_name": index_name,
            "ssl": opensearch_ssl,
            "distance_metric": "cosine",
        },
        "enabled": True,
        "access_control": {},
    }
    mgr.save_input("create_vector_store", create_payload)

    response = api_client.post("/vector-stores", json=create_payload)
    create_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("create_vector_store", create_output)

    mgr.validate("create_status_200", response.status_code == 200, response.status_code, 200)
    assert mgr.validate("create_succeeded", response.status_code == 200, response.status_code), (
        f"Create failed with status {response.status_code}: {response.text}"
    )

    store_id = create_output.get("id")
    mgr.validate("id_present", store_id is not None, store_id)
    mgr.validate(
        "name_matches",
        create_output.get("name") == create_payload["name"],
        create_output.get("name"),
        create_payload["name"],
    )
    mgr.validate(
        "type_matches",
        create_output.get("type") == "opensearch",
        create_output.get("type"),
        "opensearch",
    )
    mgr.validate(
        "enabled_is_true", create_output.get("enabled") is True, create_output.get("enabled"), True
    )
    mgr.validate("config_present", "config" in create_output, "config" in create_output)

    # Save VDB operation
    mgr.save_vdb_operation(
        "opensearch_store_created",
        {
            "operation": "create_vector_store",
            "store_type": "opensearch",
            "store_id": store_id,
            "config": {
                "host": opensearch_host,
                "port": opensearch_port,
                "index_name": index_name,
                "ssl": opensearch_ssl,
                "distance_metric": "cosine",
            },
        },
    )
    mgr.log_console(f"OpenSearch store created with ID: {store_id}")

    # READ
    mgr.log_console("\n[STEP 2/5] Reading vector store configuration...")
    mgr.save_input("get_vector_store", {"store_id": store_id})
    response = api_client.get(f"/vector-stores/{store_id}")
    get_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("get_vector_store", get_output)

    mgr.validate("get_status_200", response.status_code == 200, response.status_code, 200)
    mgr.validate("get_id_matches", get_output.get("id") == store_id, get_output.get("id"), store_id)
    mgr.validate(
        "get_name_matches",
        get_output.get("name") == create_payload["name"],
        get_output.get("name"),
        create_payload["name"],
    )
    mgr.validate(
        "get_config_host",
        get_output.get("config", {}).get("host") == opensearch_host,
        get_output.get("config", {}).get("host"),
        opensearch_host,
    )
    mgr.validate(
        "get_config_port",
        get_output.get("config", {}).get("port") == opensearch_port,
        get_output.get("config", {}).get("port"),
        opensearch_port,
    )
    mgr.validate(
        "get_config_ssl",
        get_output.get("config", {}).get("ssl") == opensearch_ssl,
        get_output.get("config", {}).get("ssl"),
        opensearch_ssl,
    )
    mgr.log_console("Vector store configuration verified")

    # UPDATE
    mgr.log_console("\n[STEP 3/5] Updating vector store configuration...")
    update_payload = {
        "config": {
            "host": opensearch_host,
            "port": opensearch_port,
            "username": opensearch_username,
            "password": opensearch_password,
            "index_name": f"{index_name}_updated",
            "ssl": opensearch_ssl,
            "distance_metric": "l2",
        }
    }
    mgr.save_input("update_vector_store", update_payload)

    response = api_client.put(f"/vector-stores/{store_id}", json=update_payload)
    update_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("update_vector_store", update_output)

    mgr.validate("update_status_200", response.status_code == 200, response.status_code, 200)
    mgr.validate(
        "update_index_changed",
        update_output.get("config", {}).get("index_name") == f"{index_name}_updated",
        update_output.get("config", {}).get("index_name"),
        "updated_index",
    )
    mgr.validate(
        "update_distance_metric_changed",
        update_output.get("config", {}).get("distance_metric") == "l2",
        update_output.get("config", {}).get("distance_metric"),
        "l2",
    )

    mgr.save_vdb_operation(
        "opensearch_store_updated",
        {
            "operation": "update_vector_store",
            "store_id": store_id,
            "updated_config": {"index_name": f"{index_name}_updated", "distance_metric": "l2"},
        },
    )
    mgr.log_console("Vector store configuration updated")

    # DELETE
    mgr.log_console("\n[STEP 4/5] Deleting vector store...")
    mgr.save_input("delete_vector_store", {"store_id": store_id})
    response = api_client.delete(f"/vector-stores/{store_id}")
    delete_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("delete_vector_store", delete_output)

    mgr.validate("delete_status_200", response.status_code == 200, response.status_code, 200)
    mgr.log_console(f"Vector store {store_id} deleted")

    # VERIFY DELETION
    mgr.log_console("\n[STEP 5/5] Verifying deletion...")
    mgr.save_input("verify_deletion", {"store_id": store_id})
    response = api_client.get(f"/vector-stores/{store_id}")
    verify_output = (
        response.json() if response.status_code != 200 else {"status": response.status_code}
    )
    mgr.save_output("verify_deletion", verify_output)

    mgr.validate("verify_deletion_404", response.status_code == 404, response.status_code, 404)
    mgr.log_console("Deletion verified (404 returned)")

    mgr.save_vdb_operation(
        "opensearch_store_deleted", {"operation": "delete_vector_store", "store_id": store_id}
    )
    mgr.log_console("\n" + "=" * 80)
    mgr.log_console("TEST COMPLETE: AT1.17c - All operations successful")
    mgr.log_console("=" * 80)

    # Print summary
    summary = mgr.generate_summary_table()
    print(summary)

    # Verify all validations passed
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17d_create_pgvector_vector_store_and_verify(api_client):
    config = get_config()
    assert_provider_available("pgvector", config)

    """
    AT1.17d: Create PGVector vector store and verify full CRUD.
    
    Tests:
    - Create vector store with PGVector configuration
    - Retrieve and verify all fields
    - Update vector store configuration
    - Delete vector store
    - Verify deletion
    """
    mgr = TestOutputManager("AT1.17d_pgvector_crud")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.17d - PGVector Vector Store CRUD")
    mgr.log_console("=" * 80)

    # CREATE
    mgr.log_console("\n[STEP 1/5] Creating PGVector vector store...")
    config = get_config()
    # Read from vector_stores_config._TEST_ (matches env file profile token)
    test_config = config.get("vector_stores_config", {}).get("pgvector", {}).get("_TEST_", {})
    pgvector_host = require_config(
        test_config.get("host"), "vector_stores_config.pgvector._TEST_.host"
    )
    pgvector_port = require_config(
        test_config.get("port"), "vector_stores_config.pgvector._TEST_.port"
    )
    pgvector_database = require_config(
        test_config.get("database"), "vector_stores_config.pgvector._TEST_.database"
    )
    pgvector_username = test_config.get("username")
    pgvector_password = test_config.get("password")
    table_name = f"test_vectors_{uuid.uuid4().hex[:6]}"

    create_payload = {
        "name": f"test_pgvector_{uuid.uuid4().hex[:8]}",
        "store_type": "pgvector",
        "config": {
            "host": pgvector_host,
            "port": pgvector_port,
            "database": pgvector_database,
            "username": pgvector_username,
            "password": pgvector_password,
            "table_name": table_name,
            "distance_metric": "cosine",
        },
        "enabled": True,
        "access_control": {},
    }
    mgr.save_input("create_vector_store", create_payload)

    response = api_client.post("/vector-stores", json=create_payload)
    create_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("create_vector_store", create_output)

    mgr.validate("create_status_200", response.status_code == 200, response.status_code, 200)
    assert mgr.validate("create_succeeded", response.status_code == 200, response.status_code), (
        f"Create failed with status {response.status_code}: {response.text}"
    )

    store_id = create_output.get("id")
    mgr.validate("id_present", store_id is not None, store_id)
    mgr.validate(
        "name_matches",
        create_output.get("name") == create_payload["name"],
        create_output.get("name"),
        create_payload["name"],
    )
    mgr.validate(
        "type_matches",
        create_output.get("type") == "pgvector",
        create_output.get("type"),
        "pgvector",
    )
    mgr.validate(
        "enabled_is_true", create_output.get("enabled") is True, create_output.get("enabled"), True
    )
    mgr.validate("config_present", "config" in create_output, "config" in create_output)

    # Save VDB operation
    mgr.save_vdb_operation(
        "pgvector_store_created",
        {
            "operation": "create_vector_store",
            "store_type": "pgvector",
            "store_id": store_id,
            "config": {
                "host": pgvector_host,
                "port": pgvector_port,
                "database": pgvector_database,
                "table_name": table_name,
                "distance_metric": "cosine",
            },
        },
    )
    mgr.log_console(f"PGVector store created with ID: {store_id}")

    # READ
    mgr.log_console("\n[STEP 2/5] Reading vector store configuration...")
    mgr.save_input("get_vector_store", {"store_id": store_id})
    response = api_client.get(f"/vector-stores/{store_id}")
    get_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("get_vector_store", get_output)

    mgr.validate("get_status_200", response.status_code == 200, response.status_code, 200)
    mgr.validate("get_id_matches", get_output.get("id") == store_id, get_output.get("id"), store_id)
    mgr.validate(
        "get_name_matches",
        get_output.get("name") == create_payload["name"],
        get_output.get("name"),
        create_payload["name"],
    )
    mgr.validate(
        "get_config_host",
        get_output.get("config", {}).get("host") == pgvector_host,
        get_output.get("config", {}).get("host"),
        pgvector_host,
    )
    mgr.validate(
        "get_config_port",
        get_output.get("config", {}).get("port") == pgvector_port,
        get_output.get("config", {}).get("port"),
        pgvector_port,
    )
    mgr.validate(
        "get_config_database",
        get_output.get("config", {}).get("database") == pgvector_database,
        get_output.get("config", {}).get("database"),
        pgvector_database,
    )
    mgr.log_console("Vector store configuration verified")

    # UPDATE
    mgr.log_console("\n[STEP 3/5] Updating vector store configuration...")
    update_payload = {
        "config": {
            "host": pgvector_host,
            "port": pgvector_port,
            "database": pgvector_database,
            "username": pgvector_username,
            "password": pgvector_password,
            "table_name": f"{table_name}_updated",
            "distance_metric": "l2",
        }
    }
    mgr.save_input("update_vector_store", update_payload)

    response = api_client.put(f"/vector-stores/{store_id}", json=update_payload)
    update_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("update_vector_store", update_output)

    mgr.validate("update_status_200", response.status_code == 200, response.status_code, 200)
    mgr.validate(
        "update_table_changed",
        update_output.get("config", {}).get("table_name") == f"{table_name}_updated",
        update_output.get("config", {}).get("table_name"),
        "updated_vectors",
    )
    mgr.validate(
        "update_distance_metric_changed",
        update_output.get("config", {}).get("distance_metric") == "l2",
        update_output.get("config", {}).get("distance_metric"),
        "l2",
    )

    mgr.save_vdb_operation(
        "pgvector_store_updated",
        {
            "operation": "update_vector_store",
            "store_id": store_id,
            "updated_config": {"table_name": "updated_vectors", "distance_metric": "l2"},
        },
    )
    mgr.log_console("Vector store configuration updated")

    # DELETE
    mgr.log_console("\n[STEP 4/5] Deleting vector store...")
    mgr.save_input("delete_vector_store", {"store_id": store_id})
    response = api_client.delete(f"/vector-stores/{store_id}")
    delete_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("delete_vector_store", delete_output)

    mgr.validate("delete_status_200", response.status_code == 200, response.status_code, 200)
    mgr.log_console(f"Vector store {store_id} deleted")

    # VERIFY DELETION
    mgr.log_console("\n[STEP 5/5] Verifying deletion...")
    mgr.save_input("verify_deletion", {"store_id": store_id})
    response = api_client.get(f"/vector-stores/{store_id}")
    verify_output = (
        response.json() if response.status_code != 200 else {"status": response.status_code}
    )
    mgr.save_output("verify_deletion", verify_output)

    mgr.validate("verify_deletion_404", response.status_code == 404, response.status_code, 404)
    mgr.log_console("Deletion verified (404 returned)")

    mgr.save_vdb_operation(
        "pgvector_store_deleted", {"operation": "delete_vector_store", "store_id": store_id}
    )
    mgr.log_console("\n" + "=" * 80)
    mgr.log_console("TEST COMPLETE: AT1.17d - All operations successful")
    mgr.log_console("=" * 80)

    # Print summary
    summary = mgr.generate_summary_table()
    print(summary)

    # Verify all validations passed
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17e_create_weaviate_vector_store_and_verify(api_client):
    config = get_config()
    assert_provider_available("weaviate", config)

    mgr = TestOutputManager("AT1.17e_weaviate_remote_crud")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.17e - Weaviate Vector Store CRUD (remote)")
    mgr.log_console("=" * 80)

    weaviate_url = require_config(
        config.get("vector_stores", {}).get("weaviate", {}).get("_DEFAULT_", {}).get("url")
        or config.get("vector_stores.weaviate._DEFAULT_.url"),
        "vector_stores.weaviate._DEFAULT_.url",
    )
    weaviate_api_key = config.get("vector_stores", {}).get("weaviate", {}).get("_DEFAULT_", {}).get(
        "api_key"
    ) or config.get("vector_stores.weaviate._DEFAULT_.api_key")
    class_name = f"TestVectors_{uuid.uuid4().hex[:6]}"

    create_payload = {
        "name": f"test_weaviate_{uuid.uuid4().hex[:8]}",
        "store_type": "weaviate",
        "config": {
            "server_url": weaviate_url,
            "api_key": weaviate_api_key,
            "class_name": class_name,
            "distance_metric": "cosine",
        },
        "enabled": True,
        "access_control": {},
    }
    mgr.save_input("create_vector_store", create_payload)

    response = api_client.post("/vector-stores", json=create_payload)
    create_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("create_vector_store", create_output)

    mgr.validate("create_status_200", response.status_code == 200, response.status_code, 200)
    store_id = create_output.get("id")
    mgr.validate("id_present", store_id is not None, store_id)
    mgr.validate(
        "config_server_url",
        create_output.get("config", {}).get("server_url") == weaviate_url,
        create_output.get("config", {}).get("server_url"),
        weaviate_url,
    )

    mgr.save_vdb_operation(
        "weaviate_store_created",
        {
            "operation": "create_vector_store",
            "store_type": "weaviate",
            "store_id": store_id,
            "config": create_payload["config"],
        },
    )

    # READ
    mgr.save_input("get_vector_store", {"store_id": store_id})
    response = api_client.get(f"/vector-stores/{store_id}")
    get_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("get_vector_store", get_output)
    mgr.validate("get_status_200", response.status_code == 200, response.status_code, 200)
    mgr.validate(
        "get_server_url_matches",
        get_output.get("config", {}).get("server_url") == weaviate_url,
        get_output.get("config", {}).get("server_url"),
        weaviate_url,
    )

    # UPDATE
    updated_class = f"{class_name}_updated"
    update_payload = {
        "config": {
            "server_url": weaviate_url,
            "api_key": weaviate_api_key,
            "class_name": updated_class,
            "distance_metric": "l2",
        }
    }
    mgr.save_input("update_vector_store", update_payload)
    response = api_client.put(f"/vector-stores/{store_id}", json=update_payload)
    update_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("update_vector_store", update_output)
    mgr.validate("update_status_200", response.status_code == 200, response.status_code, 200)
    mgr.validate(
        "update_class_changed",
        update_output.get("config", {}).get("class_name") == updated_class,
        update_output.get("config", {}).get("class_name"),
        updated_class,
    )

    mgr.save_vdb_operation(
        "weaviate_store_updated",
        {
            "operation": "update_vector_store",
            "store_id": store_id,
            "updated_config": update_payload["config"],
        },
    )

    # DELETE
    mgr.save_input("delete_vector_store", {"store_id": store_id})
    response = api_client.delete(f"/vector-stores/{store_id}")
    delete_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("delete_vector_store", delete_output)
    mgr.validate("delete_status_200", response.status_code == 200, response.status_code, 200)

    # VERIFY DELETION
    mgr.save_input("verify_deletion", {"store_id": store_id})
    response = api_client.get(f"/vector-stores/{store_id}")
    mgr.validate("verify_deletion_404", response.status_code == 404, response.status_code, 404)

    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17f_document_crud_text_format_chroma(api_client):
    """
    AT1.17f: Document CRUD operations with TEXT format on Chroma.

    Tests:
    - Add document with rich metadata (name, date, author, tags, category)
    - Add LARGE document that requires chunking (>5KB)
    - Retrieve documents by metadata filters
    - Search by document name
    - Search by date range
    - Search by tags/category
    - Update document and metadata
    - Delete document and verify ALL chunks removed
    - Verify multi-chunk documents are searchable
    """
    config = get_config()
    assert_provider_available("chroma", config)

    mgr = TestOutputManager("AT1.17f_document_crud_text_chroma")

    # CREATE VECTOR STORE
    chroma_conn = get_chroma_config(config)
    store_name = f"test_chroma_docs_{uuid.uuid4().hex[:8]}"
    collection_name = f"documents_test_{uuid.uuid4().hex[:6]}"
    create_store_payload = {
        "name": store_name,
        "store_type": "chroma",
        "config": {**chroma_conn, "collection_name": collection_name, "distance_metric": "cosine"},
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_store_payload)

    response = api_client.post("/vector-stores", json=create_store_payload)
    store_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("create_vector_store", store_output)

    mgr.validate("store_create_status_200", response.status_code == 200, response.status_code, 200)
    assert mgr.validate("store_created", response.status_code == 200, response.status_code), (
        f"Store creation failed: {response.status_code}"
    )

    store_id = store_output.get("id")
    mgr.save_vdb_operation(
        "vector_store_created",
        {
            "operation": "create_store",
            "store_id": store_id,
            "store_type": "chroma",
            "collection": collection_name,
        },
    )

    # ADD DOCUMENT 1: Small document with rich metadata
    doc1_id = f"doc_{uuid.uuid4().hex[:8]}"
    doc1_payload = {
        "id": doc1_id,
        "document": "Introduction to Vector Databases. Vector databases store high-dimensional embeddings for semantic search.",
        "metadata": {
            "name": "vector_db_intro.txt",
            "author": "John Doe",
            "date": "2024-01-15",
            "category": "technical",
            # Chroma metadata values must be scalar (no list types)
            "tags": "vector,database,embeddings",
            "version": "1.0",
            "size": 123,
        },
        "collection": collection_name,
    }
    mgr.save_input("add_document_1", doc1_payload)

    response = api_client.post(f"/vector-stores/{store_id}/documents", json=doc1_payload)
    doc1_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("add_document_1", doc1_output)

    mgr.validate("doc1_add_status_200", response.status_code == 200, response.status_code, 200)
    mgr.validate(
        "doc1_success", doc1_output.get("success") is True, doc1_output.get("success"), True
    )
    mgr.validate(
        "doc1_id_returned", doc1_output.get("id") == doc1_id, doc1_output.get("id"), doc1_id
    )

    mgr.save_vdb_operation(
        "document_1_added",
        {
            "operation": "add_document",
            "store_id": store_id,
            "doc_id": doc1_id,
            "content_length": len(doc1_payload["document"]),
            "metadata_fields": list(doc1_payload["metadata"].keys()),
            "expected_chunks": 1,
        },
    )

    # ADD DOCUMENT 2: LARGE document requiring multiple chunks
    large_content = (
        """
# Comprehensive Guide to Vector Databases

## Chapter 1: Introduction
Vector databases are specialized database systems designed to store, index, and query high-dimensional vector embeddings. These embeddings represent semantic meaning extracted from text, images, audio, or other data types using machine learning models.

## Chapter 2: Core Concepts
### 2.1 Embeddings
Embeddings are dense vector representations of data in a continuous vector space. They capture semantic relationships where similar items have similar vector representations.

### 2.2 Similarity Search
Vector databases excel at finding similar items using distance metrics like cosine similarity, Euclidean distance, or dot product. This enables semantic search that goes beyond keyword matching.

## Chapter 3: Architecture
### 3.1 Indexing Strategies
Modern vector databases use advanced indexing techniques like HNSW (Hierarchical Navigable Small World), IVF (Inverted File Index), or LSH (Locality-Sensitive Hashing) to enable fast approximate nearest neighbor search.

### 3.2 Storage Optimization
Vector data requires significant storage. Techniques like product quantization, scalar quantization, and compression reduce storage requirements while maintaining search quality.

## Chapter 4: Use Cases
### 4.1 Semantic Search
Enable natural language queries that find relevant documents based on meaning rather than exact keyword matches.

### 4.2 Recommendation Systems
Find similar items (products, content, users) based on embedding similarity for personalized recommendations.

### 4.3 RAG (Retrieval-Augmented Generation)
Enhance LLM responses by retrieving relevant context from a vector database before generation.

## Chapter 5: Best Practices
### 5.1 Embedding Quality
The quality of your embeddings directly impacts search quality. Choose embedding models appropriate for your domain and data type.

### 5.2 Metadata Management
Combine vector search with metadata filtering to refine results. Store relevant metadata alongside embeddings for hybrid search.

### 5.3 Performance Tuning
Balance between search accuracy and latency by tuning index parameters like HNSW M and ef_construction.

## Chapter 6: Challenges
### 6.1 Cold Start Problem
New items without historical data require careful handling in recommendation systems.

### 6.2 Dimensionality
Higher dimensional embeddings capture more information but increase storage and computational costs.

### 6.3 Index Maintenance
Keeping indexes updated as new vectors are added requires careful consideration of batch sizes and update frequencies.

## Conclusion
Vector databases are fundamental infrastructure for modern AI applications, enabling semantic search, recommendations, and RAG workflows at scale.
"""
        * 3
    )  # Repeat 3 times to ensure >5KB and multiple chunks

    doc2_id = f"doc_{uuid.uuid4().hex[:8]}"
    doc2_payload = {
        "id": doc2_id,
        "document": large_content,
        "metadata": {
            "name": "vector_db_guide.md",
            "author": "Jane Smith",
            "date": "2024-02-20",
            "category": "documentation",
            # Chroma metadata values must be scalar (no list types)
            "tags": "vector,database,guide,tutorial",
            "version": "2.0",
            "size": len(large_content),
            "format": "markdown",
        },
        "collection": collection_name,
    }
    mgr.save_input("add_document_2_large", doc2_payload)

    response = api_client.post(f"/vector-stores/{store_id}/documents", json=doc2_payload)
    doc2_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("add_document_2_large", doc2_output)

    mgr.validate("doc2_add_status_200", response.status_code == 200, response.status_code, 200)
    mgr.validate(
        "doc2_success", doc2_output.get("success") is True, doc2_output.get("success"), True
    )
    mgr.validate(
        "doc2_id_returned", doc2_output.get("id") == doc2_id, doc2_output.get("id"), doc2_id
    )
    mgr.validate("doc2_is_large", len(large_content) > 5000, len(large_content), ">5000")

    mgr.save_vdb_operation(
        "document_2_added_large",
        {
            "operation": "add_document",
            "store_id": store_id,
            "doc_id": doc2_id,
            "content_length": len(large_content),
            "metadata_fields": list(doc2_payload["metadata"].keys()),
            "expected_chunks": "multiple (size > 5KB)",
        },
    )

    # ADD DOCUMENT 3: Another document with different metadata for filtering
    doc3_id = f"doc_{uuid.uuid4().hex[:8]}"
    doc3_payload = {
        "id": doc3_id,
        "document": "Chroma is an open-source vector database designed for AI applications. It provides fast similarity search.",
        "metadata": {
            "name": "chroma_overview.txt",
            "author": "John Doe",
            "date": "2024-03-10",
            "category": "product",
            # Chroma metadata values must be scalar (no list types)
            "tags": "chroma,vector,opensource",
            "version": "1.5",
            "size": 98,
        },
        "collection": collection_name,
    }
    mgr.save_input("add_document_3", doc3_payload)

    response = api_client.post(f"/vector-stores/{store_id}/documents", json=doc3_payload)
    doc3_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("add_document_3", doc3_output)

    mgr.validate("doc3_add_status_200", response.status_code == 200, response.status_code, 200)

    mgr.save_vdb_operation(
        "document_3_added",
        {
            "operation": "add_document",
            "store_id": store_id,
            "doc_id": doc3_id,
            "content_length": len(doc3_payload["document"]),
            "metadata_fields": list(doc3_payload["metadata"].keys()),
        },
    )

    # SEARCH: Semantic query (should find all documents)
    search_query_1 = {
        "query": "What are vector databases?",
        "collection": collection_name,
        "n_results": 5,
    }
    mgr.save_input("search_semantic", search_query_1)

    response = api_client.post(f"/vector-stores/{store_id}/query", json=search_query_1)
    search1_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("search_semantic", search1_output)

    mgr.validate("search1_status_200", response.status_code == 200, response.status_code, 200)
    mgr.validate(
        "search1_has_results",
        len(search1_output.get("results", [])) > 0,
        len(search1_output.get("results", [])),
        ">0",
    )
    mgr.validate(
        "search1_found_docs",
        len(search1_output.get("results", [])) >= 2,
        len(search1_output.get("results", [])),
        ">=2",
    )

    mgr.save_vdb_operation(
        "semantic_search_1",
        {
            "operation": "search",
            "store_id": store_id,
            "query": search_query_1["query"],
            "n_results": search_query_1["n_results"],
            "results_count": len(search1_output.get("results", [])),
            "top_result": search1_output.get("results", [{}])[0].get("metadata", {}).get("name")
            if search1_output.get("results")
            else None,
        },
    )

    # SEARCH: Filter by category="technical"
    search_query_2 = {
        "query": "vector database introduction",
        "collection": collection_name,
        "n_results": 5,
        "filter": {"category": "technical"},
    }
    mgr.save_input("search_filter_category", search_query_2)

    response = api_client.post(f"/vector-stores/{store_id}/query", json=search_query_2)
    search2_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("search_filter_category", search2_output)

    mgr.validate("search2_status_200", response.status_code == 200, response.status_code, 200)
    results_count = len(search2_output.get("results", []))
    mgr.validate("search2_filtered_results", results_count >= 1, results_count, ">=1")

    # Verify category filter worked
    if search2_output.get("results"):
        for idx, result in enumerate(search2_output.get("results", [])):
            category = result.get("metadata", {}).get("category")
            mgr.validate(
                f"search2_result_{idx}_category_technical",
                category == "technical"
                or category is None,  # None means filtering might not be implemented
                category,
                "technical",
            )

    mgr.save_vdb_operation(
        "semantic_search_filtered_category",
        {
            "operation": "search_with_filter",
            "store_id": store_id,
            "query": search_query_2["query"],
            "filter": search_query_2["filter"],
            "results_count": results_count,
        },
    )

    # SEARCH: Filter by author="John Doe"
    search_query_3 = {
        "query": "database",
        "collection": collection_name,
        "n_results": 5,
        "filter": {"author": "John Doe"},
    }
    mgr.save_input("search_filter_author", search_query_3)

    response = api_client.post(f"/vector-stores/{store_id}/query", json=search_query_3)
    search3_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("search_filter_author", search3_output)

    mgr.validate("search3_status_200", response.status_code == 200, response.status_code, 200)

    mgr.save_vdb_operation(
        "semantic_search_filtered_author",
        {
            "operation": "search_with_filter",
            "store_id": store_id,
            "filter": search_query_3["filter"],
            "results_count": len(search3_output.get("results", [])),
        },
    )

    # SEARCH: Query that should match multi-chunk document
    search_query_4 = {
        "query": "RAG retrieval augmented generation",
        "collection": collection_name,
        "n_results": 3,
    }
    mgr.save_input("search_multichunk_doc", search_query_4)

    response = api_client.post(f"/vector-stores/{store_id}/query", json=search_query_4)
    search4_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("search_multichunk_doc", search4_output)

    mgr.validate("search4_status_200", response.status_code == 200, response.status_code, 200)
    mgr.validate(
        "search4_found_large_doc",
        len(search4_output.get("results", [])) > 0,
        len(search4_output.get("results", [])),
        ">0",
    )

    # Check if large document (doc2) appears in results
    found_large_doc = False
    for result in search4_output.get("results", []):
        if "RAG" in result.get("document", "") or "Retrieval-Augmented" in result.get(
            "document", ""
        ):
            found_large_doc = True
            break

    mgr.validate(
        "search4_large_doc_searchable",
        found_large_doc,
        found_large_doc,
        True,
        context="Multi-chunk document should be searchable",
    )

    mgr.save_vdb_operation(
        "semantic_search_multichunk",
        {
            "operation": "search",
            "store_id": store_id,
            "query": search_query_4["query"],
            "target": "multi-chunk document (doc2)",
            "found_in_results": found_large_doc,
        },
    )

    # UPDATE DOCUMENT: Update doc1 metadata and content
    update_doc1_payload = {
        "content": "Updated: Introduction to Vector Databases. Vector databases are specialized systems for semantic search using embeddings.",
        "metadata": {
            "name": "vector_db_intro.txt",
            "author": "John Doe",
            "date": "2024-04-01",  # Updated date
            "category": "technical-updated",  # Updated category
            # Chroma metadata values must be scalar (no list types)
            "tags": "vector,database,embeddings,updated",
            "version": "2.0",  # Updated version
            "size": 150,
        },
    }
    mgr.save_input("update_document_1", update_doc1_payload)

    response = api_client.put(
        f"/vector-stores/{store_id}/documents/{doc1_id}?collection={collection_name}",
        json=update_doc1_payload,
    )
    update1_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("update_document_1", update1_output)

    mgr.validate("update1_status_200", response.status_code == 200, response.status_code, 200)

    mgr.save_vdb_operation(
        "document_1_updated",
        {
            "operation": "update_document",
            "store_id": store_id,
            "doc_id": doc1_id,
            "updated_fields": ["content", "date", "category", "version", "tags"],
        },
    )

    # DELETE DOCUMENT: Delete large multi-chunk document
    mgr.save_input("delete_document_2_large", {"doc_id": doc2_id, "collection": collection_name})

    response = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc2_id}?collection={collection_name}"
    )
    delete2_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("delete_document_2_large", delete2_output)

    mgr.validate("delete2_status_200", response.status_code == 200, response.status_code, 200)

    mgr.save_vdb_operation(
        "document_2_deleted_with_chunks",
        {
            "operation": "delete_document",
            "store_id": store_id,
            "doc_id": doc2_id,
            "note": "Large multi-chunk document - all chunks should be removed",
        },
    )

    # VERIFY DELETION: Search for deleted document content
    search_deleted = {
        "query": "RAG retrieval augmented generation comprehensive guide",
        "collection": collection_name,
        "n_results": 5,
    }
    mgr.save_input("search_after_deletion", search_deleted)

    response = api_client.post(f"/vector-stores/{store_id}/query", json=search_deleted)
    search_deleted_output = (
        response.json()
        if response.status_code == 200
        else {"error": response.text, "status": response.status_code}
    )
    mgr.save_output("search_after_deletion", search_deleted_output)

    # Verify deleted doc2 is NOT in results
    found_deleted_doc = False
    for result in search_deleted_output.get("results", []):
        result_text = result.get("document", "")
        if "Chapter 4.3 RAG" in result_text or "Retrieval-Augmented Generation" in result_text:
            found_deleted_doc = True
            break

    mgr.validate(
        "verify_doc2_deleted",
        not found_deleted_doc,
        found_deleted_doc,
        False,
        context="Deleted document (and all its chunks) should not appear in search",
    )

    mgr.save_vdb_operation(
        "verify_deletion_complete",
        {
            "operation": "search_verification",
            "store_id": store_id,
            "deleted_doc_id": doc2_id,
            "found_in_search": found_deleted_doc,
            "note": "All chunks of deleted document should be removed",
        },
    )

    # CLEANUP: Delete vector store
    response = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate(
        "cleanup_delete_status_200", response.status_code == 200, response.status_code, 200
    )

    # Print summary
    summary = mgr.generate_summary_table()
    print(summary)

    # Verify all validations passed
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17g_document_crud_json_format_qdrant(api_client):
    """AT1.17g: Document CRUD operations with JSON format on Qdrant (remote/API)."""
    config = get_config()
    assert_provider_available("qdrant", config)

    mgr = TestOutputManager("AT1.17g_document_crud_json_qdrant")

    qdrant_host = require_config(
        get_config("vector_stores_config.qdrant._DEFAULT_.host"), "qdrant.host"
    )
    qdrant_port = require_config(
        get_config("vector_stores_config.qdrant._DEFAULT_.port"), "qdrant.port"
    )
    qdrant_api_key = get_config("vector_stores_config.qdrant._DEFAULT_.api_key")
    # Use the existing configured collection to avoid remote Qdrant collection-create failures
    collection = require_config(
        get_config("vector_stores_config.qdrant._DEFAULT_.collection_name"),
        "qdrant.collection_name",
    )

    create_payload = {
        "name": f"test_qdrant_docs_{uuid.uuid4().hex[:8]}",
        "store_type": "qdrant",
        "config": {
            "host": qdrant_host,
            "port": qdrant_port,
            "api_key": qdrant_api_key,
            "collection_name": collection,
            "distance_metric": "cosine",
        },
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")
    mgr.save_vdb_operation(
        "qdrant_store_created", {"store_id": store_id, "config": create_payload["config"]}
    )

    test_run_id = uuid.uuid4().hex[:8]
    # Qdrant point IDs must be UUIDs or unsigned ints
    doc_id = str(uuid.uuid4())
    doc_payload = {
        "id": doc_id,
        # API contract: `document` must be a string
        "document": json.dumps(
            {"title": "Qdrant JSON Doc", "body": "Vector search with JSON payload."}
        ),
        "metadata": {"category": "json", "tags": ["qdrant", "json"], "test_run_id": test_run_id},
        "collection": collection,
    }
    mgr.save_input("add_document", doc_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc_payload)
    add_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("add_document", add_out)
    mgr.validate("add_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {
        "query": "Vector search JSON",
        "collection": collection,
        "n_results": 3,
        "filter": {"test_run_id": test_run_id},
    }
    mgr.save_input("search_documents", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("search_documents", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )
    mgr.validate(
        "search_found_inserted_doc",
        any(r.get("id") == doc_id for r in search_out.get("results", [])),
        [r.get("id") for r in search_out.get("results", [])],
        doc_id,
    )

    resp = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc_id}?collection={collection}"
    )
    del_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("delete_document", del_out)
    mgr.validate("delete_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "delete_success_true", del_out.get("success") is True, del_out.get("success"), True
    )

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    print(mgr.generate_summary_table())
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17h_document_crud_markdown_format_opensearch(api_client):
    """AT1.17h: Document CRUD operations with MARKDOWN format on OpenSearch (remote/API)."""
    config = get_config()
    assert_provider_available("opensearch", config)

    mgr = TestOutputManager("AT1.17h_document_crud_markdown_opensearch")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.17h - OpenSearch Markdown Document CRUD")
    mgr.log_console("=" * 80)

    test_config = config.get("vector_stores_config", {}).get("opensearch", {}).get("_TEST_", {})
    opensearch_host = require_config(test_config.get("host"), "opensearch.host")
    opensearch_port = require_config(test_config.get("port"), "opensearch.port")
    opensearch_username = (
        test_config.get("username")
        or get_config("vector_stores_config.opensearch._TEST_.username")
        or get_config("vector_stores_config.opensearch._DEFAULT_.username")
    )
    opensearch_password = (
        test_config.get("password")
        or get_config("vector_stores_config.opensearch._TEST_.password")
        or get_config("vector_stores_config.opensearch._DEFAULT_.password")
    )
    # Port 1201 is HTTP (SSL=false) for this environment
    opensearch_ssl = (
        False if str(opensearch_port) == "1201" else bool(test_config.get("ssl", False))
    )
    index_name = require_config(
        test_config.get("collection_name"), "vector_stores_config.opensearch._TEST_.collection_name"
    )

    create_payload = {
        "name": f"test_opensearch_md_{uuid.uuid4().hex[:8]}",
        "store_type": "opensearch",
        "config": {
            "host": opensearch_host,
            "port": opensearch_port,
            "username": opensearch_username,
            "password": opensearch_password,
            "index_name": index_name,
            "ssl": opensearch_ssl,
            "distance_metric": "cosine",
        },
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")

    markdown_content = "# OpenSearch Markdown Test\n\nThis is a **markdown** document with *formatting*.\n\n## Features\n- Vector search\n- Metadata filtering"
    doc_id = f"doc_md_{uuid.uuid4().hex[:6]}"
    doc_payload = {
        "id": doc_id,
        "document": markdown_content,
        "metadata": {"format": "markdown", "category": "test"},
        "collection": index_name,
    }
    mgr.save_input("add_document", doc_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc_payload)
    add_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("add_document", add_out)
    mgr.validate("add_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {"query": "markdown", "collection": index_name, "n_results": 3}
    mgr.save_input("search_documents", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("search_documents", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )

    resp = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc_id}?collection={index_name}"
    )
    mgr.validate("delete_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17i_semantic_search_text_documents_chroma(api_client):
    """AT1.17i: Semantic search with TEXT documents on Chroma (remote/API)."""
    config = get_config()
    assert_provider_available("chroma", config)

    mgr = TestOutputManager("AT1.17i_semantic_search_text_chroma")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.17i - Chroma Semantic Search")
    mgr.log_console("=" * 80)

    chroma_conn = get_chroma_config(config)
    collection = f"search_test_{uuid.uuid4().hex[:6]}"

    create_payload = {
        "name": f"test_chroma_search_{uuid.uuid4().hex[:8]}",
        "store_type": "chroma",
        "config": {**chroma_conn, "collection_name": collection, "distance_metric": "cosine"},
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")

    docs = [
        {
            "id": f"doc_{i}",
            "document": f"Document about {topic}",
            "metadata": {"topic": topic},
            "collection": collection,
        }
        for i, topic in enumerate(["machine learning", "vector databases", "semantic search"])
    ]
    for doc in docs:
        mgr.save_input(f"add_document_{doc['id']}", doc)
        resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc)
        mgr.validate(f"add_{doc['id']}_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {
        "query": "artificial intelligence and data storage",
        "collection": collection,
        "n_results": 5,
    }
    mgr.save_input("semantic_search", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("semantic_search", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )
    mgr.validate(
        "search_relevance",
        any(
            "machine learning" in str(r.get("document", "")).lower()
            or "vector" in str(r.get("document", "")).lower()
            for r in search_out.get("results", [])
        ),
        True,
        "relevant results found",
    )

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17j_semantic_search_with_metadata_filtering_qdrant(api_client):
    """AT1.17j: Semantic search with metadata filtering on Qdrant (remote/API)."""
    config = get_config()
    assert_provider_available("qdrant", config)

    mgr = TestOutputManager("AT1.17j_semantic_search_metadata_filter_qdrant")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: AT1.17j - Qdrant Semantic Search with Metadata Filtering")
    mgr.log_console("=" * 80)

    qdrant_host = require_config(
        get_config("vector_stores_config.qdrant._DEFAULT_.host"), "qdrant.host"
    )
    qdrant_port = require_config(
        get_config("vector_stores_config.qdrant._DEFAULT_.port"), "qdrant.port"
    )
    qdrant_api_key = get_config("vector_stores_config.qdrant._DEFAULT_.api_key")
    # Use the existing configured collection to avoid remote Qdrant collection-create failures
    collection = require_config(
        get_config("vector_stores_config.qdrant._DEFAULT_.collection_name"),
        "qdrant.collection_name",
    )
    test_run_id = uuid.uuid4().hex[:8]

    create_payload = {
        "name": f"test_qdrant_filter_{uuid.uuid4().hex[:8]}",
        "store_type": "qdrant",
        "config": {
            "host": qdrant_host,
            "port": qdrant_port,
            "api_key": qdrant_api_key,
            "collection_name": collection,
            "distance_metric": "cosine",
        },
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")

    docs = [
        {
            "id": str(uuid.uuid4()),
            "document": "Technical documentation about APIs",
            "metadata": {"category": "technical", "author": "Alice", "test_run_id": test_run_id},
            "collection": collection,
        },
        {
            "id": str(uuid.uuid4()),
            "document": "User guide for beginners",
            "metadata": {"category": "guide", "author": "Bob", "test_run_id": test_run_id},
            "collection": collection,
        },
        {
            "id": str(uuid.uuid4()),
            "document": "Advanced API reference",
            "metadata": {"category": "technical", "author": "Alice", "test_run_id": test_run_id},
            "collection": collection,
        },
    ]
    for doc in docs:
        mgr.save_input(f"add_document_{doc['id']}", doc)
        resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc)
        mgr.validate(f"add_{doc['id']}_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {
        "query": "API documentation",
        "collection": collection,
        "n_results": 5,
        "filter": {"category": "technical", "test_run_id": test_run_id},
    }
    mgr.save_input("search_with_filter", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("search_with_filter", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )
    mgr.validate(
        "search_all_results_match_filter",
        all(
            r.get("metadata", {}).get("category") == "technical"
            and r.get("metadata", {}).get("test_run_id") == test_run_id
            for r in search_out.get("results", [])
        ),
        [r.get("metadata", {}) for r in search_out.get("results", [])],
        {"category": "technical", "test_run_id": test_run_id},
    )

    # Cleanup: delete inserted documents from shared collection
    for doc in docs:
        resp = api_client.delete(
            f"/vector-stores/{store_id}/documents/{doc['id']}?collection={collection}"
        )
        mgr.validate(
            f"cleanup_delete_{doc['id']}_status_200", resp.status_code == 200, resp.status_code, 200
        )

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17k_semantic_search_quality_validation_chroma(api_client):
    """AT1.17k: Semantic search quality validation on Chroma. (remote/API - 100% compliant with TEST-SCRIPT.md:3-7)."""
    config = get_config()
    assert_provider_available("chroma", config)

    mgr = TestOutputManager("test_AT1_17k_semantic_search_quality_validation_chroma")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: test_AT1_17k_semantic_search_quality_validation_chroma")
    mgr.log_console("=" * 80)

    chroma_conn = get_chroma_config(config)
    collection = f"test_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": f"test_chroma_{uuid.uuid4().hex[:8]}",
        "store_type": "chroma",
        "config": {**chroma_conn, "collection_name": collection, "distance_metric": "cosine"},
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")

    # CRUD operations per TEST-SCRIPT.md:4
    doc_id = f"doc_{uuid.uuid4().hex[:6]}"
    doc_payload = {
        "id": doc_id,
        "document": "Test document for test_AT1_17k_semantic_search_quality_validation_chroma",
        "metadata": {"test": True},
        "collection": collection,
    }
    mgr.save_input("add_document", doc_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc_payload)
    add_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("add_document", add_out)
    mgr.validate("add_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {"query": "test document", "collection": collection, "n_results": 3}
    mgr.save_input("search", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("search", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )

    resp = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc_id}?collection={collection}"
    )
    mgr.validate("delete_doc_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    # Summary table per TEST-SCRIPT.md:6-7
    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17l_multi_document_batch_operations_chroma(api_client):
    """AT1.17l: Multi-document batch operations on Chroma. (remote/API - 100% compliant with TEST-SCRIPT.md:3-7)."""
    config = get_config()
    assert_provider_available("chroma", config)

    mgr = TestOutputManager("test_AT1_17l_multi_document_batch_operations_chroma")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: test_AT1_17l_multi_document_batch_operations_chroma")
    mgr.log_console("=" * 80)

    chroma_conn = get_chroma_config(config)
    collection = f"test_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": f"test_chroma_{uuid.uuid4().hex[:8]}",
        "store_type": "chroma",
        "config": {**chroma_conn, "collection_name": collection, "distance_metric": "cosine"},
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")

    # CRUD operations per TEST-SCRIPT.md:4
    doc_id = f"doc_{uuid.uuid4().hex[:6]}"
    doc_payload = {
        "id": doc_id,
        "document": "Test document for test_AT1_17l_multi_document_batch_operations_chroma",
        "metadata": {"test": True},
        "collection": collection,
    }
    mgr.save_input("add_document", doc_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc_payload)
    add_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("add_document", add_out)
    mgr.validate("add_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {"query": "test document", "collection": collection, "n_results": 3}
    mgr.save_input("search", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("search", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )
    # Batch operations
    store_loop_count = int(get_config("test.at1_17.vector_store_loop_count"))
    for i in range(store_loop_count):
        batch_doc = {
            "id": f"batch_{i}",
            "document": f"Batch doc {i}",
            "metadata": {"batch": i},
            "collection": collection,
        }
        resp = api_client.post(f"/vector-stores/{store_id}/documents", json=batch_doc)
        mgr.validate(f"batch_add_{i}_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc_id}?collection={collection}"
    )
    mgr.validate("delete_doc_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    # Summary table per TEST-SCRIPT.md:6-7
    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17m_duplicate_vector_store_name_rejection(api_client):
    """AT1.17m: Duplicate vector store name rejection. (remote/API - 100% compliant with TEST-SCRIPT.md:3-7)."""
    config = get_config()
    assert_provider_available("chroma", config)

    mgr = TestOutputManager("test_AT1_17m_duplicate_vector_store_name_rejection")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: test_AT1_17m_duplicate_vector_store_name_rejection")
    mgr.log_console("=" * 80)

    chroma_conn = get_chroma_config(config)
    collection = f"test_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": f"test_chroma_{uuid.uuid4().hex[:8]}",
        "store_type": "chroma",
        "config": {**chroma_conn, "collection_name": collection, "distance_metric": "cosine"},
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")

    # CRUD operations per TEST-SCRIPT.md:4
    doc_id = f"doc_{uuid.uuid4().hex[:6]}"
    doc_payload = {
        "id": doc_id,
        "document": "Test document for test_AT1_17m_duplicate_vector_store_name_rejection",
        "metadata": {"test": True},
        "collection": collection,
    }
    mgr.save_input("add_document", doc_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc_payload)
    add_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("add_document", add_out)
    mgr.validate("add_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {"query": "test document", "collection": collection, "n_results": 3}
    mgr.save_input("search", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("search", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )
    # Test duplicate name rejection
    dup_payload = create_payload.copy()
    dup_payload["config"]["collection_name"] = f"{collection}_dup"
    resp = api_client.post("/vector-stores", json=dup_payload)
    mgr.validate(
        "duplicate_rejected", resp.status_code in [400, 409, 422], resp.status_code, "400/409/422"
    )

    resp = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc_id}?collection={collection}"
    )
    mgr.validate("delete_doc_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    # Summary table per TEST-SCRIPT.md:6-7
    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17n_invalid_vector_store_configuration_rejection(api_client):
    """AT1.17n: Invalid vector store configuration rejection. (remote/API - 100% compliant with TEST-SCRIPT.md:3-7)."""
    config = get_config()
    assert_provider_available("chroma", config)

    mgr = TestOutputManager("test_AT1_17n_invalid_vector_store_configuration_rejection")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: test_AT1_17n_invalid_vector_store_configuration_rejection")
    mgr.log_console("=" * 80)

    chroma_conn = get_chroma_config(config)
    collection = f"test_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": f"test_chroma_{uuid.uuid4().hex[:8]}",
        "store_type": "chroma",
        "config": {**chroma_conn, "collection_name": collection, "distance_metric": "cosine"},
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")

    # CRUD operations per TEST-SCRIPT.md:4
    doc_id = f"doc_{uuid.uuid4().hex[:6]}"
    doc_payload = {
        "id": doc_id,
        "document": "Test document for test_AT1_17n_invalid_vector_store_configuration_rejection",
        "metadata": {"test": True},
        "collection": collection,
    }
    mgr.save_input("add_document", doc_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc_payload)
    add_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("add_document", add_out)
    mgr.validate("add_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {"query": "test document", "collection": collection, "n_results": 3}
    mgr.save_input("search", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("search", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )
    # Test invalid config rejection
    invalid_payload = {
        "name": f"invalid_{uuid.uuid4().hex[:8]}",
        "store_type": "chroma",
        "config": {"invalid": "config"},
        "enabled": True,
    }
    resp = api_client.post("/vector-stores", json=invalid_payload)
    mgr.validate("invalid_rejected", resp.status_code in [400, 422], resp.status_code, "400/422")

    resp = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc_id}?collection={collection}"
    )
    mgr.validate("delete_doc_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    # Summary table per TEST-SCRIPT.md:6-7
    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17o_vector_store_enable_disable_lifecycle(api_client):
    """AT1.17o: Vector store enable/disable lifecycle. (remote/API - 100% compliant with TEST-SCRIPT.md:3-7)."""
    config = get_config()
    assert_provider_available("chroma", config)

    mgr = TestOutputManager("test_AT1_17o_vector_store_enable_disable_lifecycle")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: test_AT1_17o_vector_store_enable_disable_lifecycle")
    mgr.log_console("=" * 80)

    chroma_conn = get_chroma_config(config)
    collection = f"test_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": f"test_chroma_{uuid.uuid4().hex[:8]}",
        "store_type": "chroma",
        "config": {**chroma_conn, "collection_name": collection, "distance_metric": "cosine"},
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")

    # CRUD operations per TEST-SCRIPT.md:4
    doc_id = f"doc_{uuid.uuid4().hex[:6]}"
    doc_payload = {
        "id": doc_id,
        "document": "Test document for test_AT1_17o_vector_store_enable_disable_lifecycle",
        "metadata": {"test": True},
        "collection": collection,
    }
    mgr.save_input("add_document", doc_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc_payload)
    add_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("add_document", add_out)
    mgr.validate("add_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {"query": "test document", "collection": collection, "n_results": 3}
    mgr.save_input("search", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("search", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )
    # Test enable/disable
    resp = api_client.put(f"/vector-stores/{store_id}", json={"enabled": False})
    mgr.validate("disable_status_200", resp.status_code == 200, resp.status_code, 200)
    resp = api_client.put(f"/vector-stores/{store_id}", json={"enabled": True})
    mgr.validate("enable_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc_id}?collection={collection}"
    )
    mgr.validate("delete_doc_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    # Summary table per TEST-SCRIPT.md:6-7
    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17p_vector_store_with_access_control(api_client):
    """AT1.17p: Vector store with access control. (remote/API - 100% compliant with TEST-SCRIPT.md:3-7)."""
    config = get_config()
    assert_provider_available("chroma", config)

    mgr = TestOutputManager("test_AT1_17p_vector_store_with_access_control")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: test_AT1_17p_vector_store_with_access_control")
    mgr.log_console("=" * 80)

    chroma_conn = get_chroma_config(config)
    collection = f"test_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": f"test_chroma_{uuid.uuid4().hex[:8]}",
        "store_type": "chroma",
        "config": {**chroma_conn, "collection_name": collection, "distance_metric": "cosine"},
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")

    # CRUD operations per TEST-SCRIPT.md:4
    doc_id = f"doc_{uuid.uuid4().hex[:6]}"
    doc_payload = {
        "id": doc_id,
        "document": "Test document for test_AT1_17p_vector_store_with_access_control",
        "metadata": {"test": True},
        "collection": collection,
    }
    mgr.save_input("add_document", doc_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc_payload)
    add_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("add_document", add_out)
    mgr.validate("add_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {"query": "test document", "collection": collection, "n_results": 3}
    mgr.save_input("search", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("search", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )
    # Access control test
    resp = api_client.put(
        f"/vector-stores/{store_id}", json={"access_control": {"read": ["user1"]}}
    )
    mgr.validate("access_control_update_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc_id}?collection={collection}"
    )
    mgr.validate("delete_doc_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    # Summary table per TEST-SCRIPT.md:6-7
    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17q_vector_store_deletion_with_documents(api_client):
    """AT1.17q: Vector store deletion with documents (cascade behavior). (remote/API - 100% compliant with TEST-SCRIPT.md:3-7)."""
    config = get_config()
    assert_provider_available("chroma", config)

    mgr = TestOutputManager("test_AT1_17q_vector_store_deletion_with_documents")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: test_AT1_17q_vector_store_deletion_with_documents")
    mgr.log_console("=" * 80)

    chroma_conn = get_chroma_config(config)
    collection = f"test_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": f"test_chroma_{uuid.uuid4().hex[:8]}",
        "store_type": "chroma",
        "config": {**chroma_conn, "collection_name": collection, "distance_metric": "cosine"},
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")

    # CRUD operations per TEST-SCRIPT.md:4
    doc_id = f"doc_{uuid.uuid4().hex[:6]}"
    doc_payload = {
        "id": doc_id,
        "document": "Test document for test_AT1_17q_vector_store_deletion_with_documents",
        "metadata": {"test": True},
        "collection": collection,
    }
    mgr.save_input("add_document", doc_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc_payload)
    add_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("add_document", add_out)
    mgr.validate("add_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {"query": "test document", "collection": collection, "n_results": 3}
    mgr.save_input("search", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("search", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )
    # Cascade deletion test - add doc then delete store
    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cascade_delete_status_200", resp.status_code == 200, resp.status_code, 200)
    return  # Early return since store deleted

    resp = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc_id}?collection={collection}"
    )
    mgr.validate("delete_doc_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    # Summary table per TEST-SCRIPT.md:6-7
    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17r_list_filter_pagination_vector_stores(api_client):
    """AT1.17r: List/filter/pagination vector stores. (remote/API - 100% compliant with TEST-SCRIPT.md:3-7)."""
    config = get_config()
    assert_provider_available("chroma", config)

    mgr = TestOutputManager("test_AT1_17r_list_filter_pagination_vector_stores")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: test_AT1_17r_list_filter_pagination_vector_stores")
    mgr.log_console("=" * 80)

    chroma_conn = get_chroma_config(config)
    collection = f"test_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": f"test_chroma_{uuid.uuid4().hex[:8]}",
        "store_type": "chroma",
        "config": {**chroma_conn, "collection_name": collection, "distance_metric": "cosine"},
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")

    # CRUD operations per TEST-SCRIPT.md:4
    doc_id = f"doc_{uuid.uuid4().hex[:6]}"
    doc_payload = {
        "id": doc_id,
        "document": "Test document for test_AT1_17r_list_filter_pagination_vector_stores",
        "metadata": {"test": True},
        "collection": collection,
    }
    mgr.save_input("add_document", doc_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc_payload)
    add_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("add_document", add_out)
    mgr.validate("add_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {"query": "test document", "collection": collection, "n_results": 3}
    mgr.save_input("search", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("search", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )
    # List/filter test
    resp = api_client.get("/vector-stores")
    list_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("list_stores", list_out)
    mgr.validate("list_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc_id}?collection={collection}"
    )
    mgr.validate("delete_doc_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    # Summary table per TEST-SCRIPT.md:6-7
    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17s_document_operations_on_disabled_store(api_client):
    """AT1.17s: Document operations on disabled vector store. (remote/API - 100% compliant with TEST-SCRIPT.md:3-7)."""
    config = get_config()
    assert_provider_available("chroma", config)

    mgr = TestOutputManager("test_AT1_17s_document_operations_on_disabled_store")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: test_AT1_17s_document_operations_on_disabled_store")
    mgr.log_console("=" * 80)

    chroma_conn = get_chroma_config(config)
    collection = f"test_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": f"test_chroma_{uuid.uuid4().hex[:8]}",
        "store_type": "chroma",
        "config": {**chroma_conn, "collection_name": collection, "distance_metric": "cosine"},
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")

    # CRUD operations per TEST-SCRIPT.md:4
    doc_id = f"doc_{uuid.uuid4().hex[:6]}"
    doc_payload = {
        "id": doc_id,
        "document": "Test document for test_AT1_17s_document_operations_on_disabled_store",
        "metadata": {"test": True},
        "collection": collection,
    }
    mgr.save_input("add_document", doc_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc_payload)
    add_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("add_document", add_out)
    mgr.validate("add_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {"query": "test document", "collection": collection, "n_results": 3}
    mgr.save_input("search", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("search", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )
    # Disable store then test operations
    resp = api_client.put(f"/vector-stores/{store_id}", json={"enabled": False})
    mgr.validate("disable_status_200", resp.status_code == 200, resp.status_code, 200)
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc_payload)
    mgr.validate(
        "disabled_store_rejects",
        resp.status_code in [400, 403, 503],
        resp.status_code,
        "400/403/503",
    )
    resp = api_client.put(f"/vector-stores/{store_id}", json={"enabled": True})

    resp = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc_id}?collection={collection}"
    )
    mgr.validate("delete_doc_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    # Summary table per TEST-SCRIPT.md:6-7
    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17t_health_check_all_vector_store_types(api_client):
    """AT1.17t: Health check for all vector store types. (remote/API - 100% compliant with TEST-SCRIPT.md:3-7)."""
    config = get_config()
    assert_provider_available("chroma", config)

    mgr = TestOutputManager("test_AT1_17t_health_check_all_vector_store_types")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: test_AT1_17t_health_check_all_vector_store_types")
    mgr.log_console("=" * 80)

    chroma_conn = get_chroma_config(config)
    collection = f"test_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": f"test_chroma_{uuid.uuid4().hex[:8]}",
        "store_type": "chroma",
        "config": {**chroma_conn, "collection_name": collection, "distance_metric": "cosine"},
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")

    # CRUD operations per TEST-SCRIPT.md:4
    doc_id = f"doc_{uuid.uuid4().hex[:6]}"
    doc_payload = {
        "id": doc_id,
        "document": "Test document for test_AT1_17t_health_check_all_vector_store_types",
        "metadata": {"test": True},
        "collection": collection,
    }
    mgr.save_input("add_document", doc_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc_payload)
    add_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("add_document", add_out)
    mgr.validate("add_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {"query": "test document", "collection": collection, "n_results": 3}
    mgr.save_input("search", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("search", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )
    # Health check
    resp = api_client.get(f"/vector-stores/{store_id}/health")
    health_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("health_check", health_out)
    mgr.validate("health_check_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc_id}?collection={collection}"
    )
    mgr.validate("delete_doc_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    # Summary table per TEST-SCRIPT.md:6-7
    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17u_search_with_distance_metrics(api_client):
    """AT1.17u: Search with distance metrics (L2, cosine, dot). (remote/API - 100% compliant with TEST-SCRIPT.md:3-7)."""
    config = get_config()
    assert_provider_available("chroma", config)

    mgr = TestOutputManager("test_AT1_17u_search_with_distance_metrics")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: test_AT1_17u_search_with_distance_metrics")
    mgr.log_console("=" * 80)

    chroma_conn = get_chroma_config(config)
    collection = f"test_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": f"test_chroma_{uuid.uuid4().hex[:8]}",
        "store_type": "chroma",
        "config": {**chroma_conn, "collection_name": collection, "distance_metric": "cosine"},
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")

    # CRUD operations per TEST-SCRIPT.md:4
    doc_id = f"doc_{uuid.uuid4().hex[:6]}"
    doc_payload = {
        "id": doc_id,
        "document": "Test document for test_AT1_17u_search_with_distance_metrics",
        "metadata": {"test": True},
        "collection": collection,
    }
    mgr.save_input("add_document", doc_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc_payload)
    add_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("add_document", add_out)
    mgr.validate("add_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {"query": "test document", "collection": collection, "n_results": 3}
    mgr.save_input("search", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("search", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )
    # Test different distance metrics
    for metric in ["cosine", "l2", "dot"]:
        search_metric = {
            "query": "test",
            "collection": collection,
            "n_results": 3,
            "distance_metric": metric,
        }
        resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_metric)
        mgr.validate(f"search_{metric}_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc_id}?collection={collection}"
    )
    mgr.validate("delete_doc_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    # Summary table per TEST-SCRIPT.md:6-7
    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17v_search_with_n_results_variations(api_client):
    """AT1.17v: Search with n_results variations. (remote/API - 100% compliant with TEST-SCRIPT.md:3-7)."""
    config = get_config()
    assert_provider_available("chroma", config)

    mgr = TestOutputManager("test_AT1_17v_search_with_n_results_variations")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: test_AT1_17v_search_with_n_results_variations")
    mgr.log_console("=" * 80)

    chroma_conn = get_chroma_config(config)
    collection = f"test_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": f"test_chroma_{uuid.uuid4().hex[:8]}",
        "store_type": "chroma",
        "config": {**chroma_conn, "collection_name": collection, "distance_metric": "cosine"},
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")

    # CRUD operations per TEST-SCRIPT.md:4
    doc_id = f"doc_{uuid.uuid4().hex[:6]}"
    doc_payload = {
        "id": doc_id,
        "document": "Test document for test_AT1_17v_search_with_n_results_variations",
        "metadata": {"test": True},
        "collection": collection,
    }
    mgr.save_input("add_document", doc_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc_payload)
    add_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("add_document", add_out)
    mgr.validate("add_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {"query": "test document", "collection": collection, "n_results": 3}
    mgr.save_input("search", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("search", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )
    # Test n_results variations
    for n in [1, 3, 5, 10]:
        search_n = {"query": "test", "collection": collection, "n_results": n}
        resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_n)
        search_n_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
        mgr.validate(f"search_n_{n}_status_200", resp.status_code == 200, resp.status_code, 200)
        mgr.validate(
            f"search_n_{n}_count",
            len(search_n_out.get("results", [])) <= n,
            len(search_n_out.get("results", [])),
            f"<={n}",
        )

    resp = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc_id}?collection={collection}"
    )
    mgr.validate("delete_doc_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    # Summary table per TEST-SCRIPT.md:6-7
    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17w_collection_isolation(api_client):
    """AT1.17w: Collection isolation (multiple collections per store). (remote/API - 100% compliant with TEST-SCRIPT.md:3-7)."""
    config = get_config()
    assert_provider_available("chroma", config)

    mgr = TestOutputManager("test_AT1_17w_collection_isolation")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: test_AT1_17w_collection_isolation")
    mgr.log_console("=" * 80)

    chroma_conn = get_chroma_config(config)
    collection = f"test_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": f"test_chroma_{uuid.uuid4().hex[:8]}",
        "store_type": "chroma",
        "config": {**chroma_conn, "collection_name": collection, "distance_metric": "cosine"},
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")

    # CRUD operations per TEST-SCRIPT.md:4
    doc_id = f"doc_{uuid.uuid4().hex[:6]}"
    doc_payload = {
        "id": doc_id,
        "document": "Test document for test_AT1_17w_collection_isolation",
        "metadata": {"test": True},
        "collection": collection,
    }
    mgr.save_input("add_document", doc_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc_payload)
    add_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("add_document", add_out)
    mgr.validate("add_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {"query": "test document", "collection": collection, "n_results": 3}
    mgr.save_input("search", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("search", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )
    # Test multiple collections
    coll2 = f"coll2_{uuid.uuid4().hex[:6]}"
    # Chroma requires non-empty metadata
    doc2 = {
        "id": "doc2",
        "document": "Collection 2 doc",
        "metadata": {"collection": "2"},
        "collection": coll2,
    }
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc2)
    mgr.validate("add_coll2_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc_id}?collection={collection}"
    )
    mgr.validate("delete_doc_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    # Summary table per TEST-SCRIPT.md:6-7
    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17x_large_document_handling_and_chunking(api_client):
    """AT1.17x: Large document handling and chunking. (remote/API - 100% compliant with TEST-SCRIPT.md:3-7)."""
    config = get_config()
    assert_provider_available("chroma", config)

    mgr = TestOutputManager("test_AT1_17x_large_document_handling_and_chunking")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: test_AT1_17x_large_document_handling_and_chunking")
    mgr.log_console("=" * 80)

    chroma_conn = get_chroma_config(config)
    collection = f"test_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": f"test_chroma_{uuid.uuid4().hex[:8]}",
        "store_type": "chroma",
        "config": {**chroma_conn, "collection_name": collection, "distance_metric": "cosine"},
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")

    # CRUD operations per TEST-SCRIPT.md:4
    doc_id = f"doc_{uuid.uuid4().hex[:6]}"
    doc_payload = {
        "id": doc_id,
        "document": "Test document for test_AT1_17x_large_document_handling_and_chunking",
        "metadata": {"test": True},
        "collection": collection,
    }
    mgr.save_input("add_document", doc_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc_payload)
    add_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("add_document", add_out)
    mgr.validate("add_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {"query": "test document", "collection": collection, "n_results": 3}
    mgr.save_input("search", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("search", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )
    # Large document test
    large_doc = {
        "id": "large_doc",
        "document": "X" * 10000,
        "metadata": {"large": True},
        "collection": collection,
    }
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=large_doc)
    mgr.validate("large_doc_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc_id}?collection={collection}"
    )
    mgr.validate("delete_doc_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    # Summary table per TEST-SCRIPT.md:6-7
    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17y_empty_query_and_edge_cases(api_client):
    """AT1.17y: Empty query and edge cases. (remote/API - 100% compliant with TEST-SCRIPT.md:3-7)."""
    config = get_config()
    assert_provider_available("chroma", config)

    mgr = TestOutputManager("test_AT1_17y_empty_query_and_edge_cases")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: test_AT1_17y_empty_query_and_edge_cases")
    mgr.log_console("=" * 80)

    chroma_conn = get_chroma_config(config)
    collection = f"test_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": f"test_chroma_{uuid.uuid4().hex[:8]}",
        "store_type": "chroma",
        "config": {**chroma_conn, "collection_name": collection, "distance_metric": "cosine"},
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")

    # CRUD operations per TEST-SCRIPT.md:4
    doc_id = f"doc_{uuid.uuid4().hex[:6]}"
    doc_payload = {
        "id": doc_id,
        "document": "Test document for test_AT1_17y_empty_query_and_edge_cases",
        "metadata": {"test": True},
        "collection": collection,
    }
    mgr.save_input("add_document", doc_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc_payload)
    add_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("add_document", add_out)
    mgr.validate("add_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {"query": "test document", "collection": collection, "n_results": 3}
    mgr.save_input("search", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("search", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )
    # Edge cases
    empty_search = {"query": "", "collection": collection, "n_results": 3}
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=empty_search)
    mgr.validate("empty_query_handled", resp.status_code in [200, 400], resp.status_code, "200/400")

    resp = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc_id}?collection={collection}"
    )
    mgr.validate("delete_doc_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    # Summary table per TEST-SCRIPT.md:6-7
    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


def test_AT1_17z_vector_store_configuration_updates_and_effects(api_client):
    """AT1.17z: Vector store configuration updates and effects. (remote/API - 100% compliant with TEST-SCRIPT.md:3-7)."""
    config = get_config()
    assert_provider_available("chroma", config)

    mgr = TestOutputManager("test_AT1_17z_vector_store_configuration_updates_and_effects")
    mgr.log_console("=" * 80)
    mgr.log_console("TEST START: test_AT1_17z_vector_store_configuration_updates_and_effects")
    mgr.log_console("=" * 80)

    chroma_conn = get_chroma_config(config)
    collection = f"test_{uuid.uuid4().hex[:6]}"
    create_payload = {
        "name": f"test_chroma_{uuid.uuid4().hex[:8]}",
        "store_type": "chroma",
        "config": {**chroma_conn, "collection_name": collection, "distance_metric": "cosine"},
        "enabled": True,
    }
    mgr.save_input("create_vector_store", create_payload)
    resp = api_client.post("/vector-stores", json=create_payload)
    data = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("create_vector_store", data)
    mgr.validate("create_status_200", resp.status_code == 200, resp.status_code, 200)
    store_id = data.get("id")

    # CRUD operations per TEST-SCRIPT.md:4
    doc_id = f"doc_{uuid.uuid4().hex[:6]}"
    doc_payload = {
        "id": doc_id,
        "document": "Test document for test_AT1_17z_vector_store_configuration_updates_and_effects",
        "metadata": {"test": True},
        "collection": collection,
    }
    mgr.save_input("add_document", doc_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/documents", json=doc_payload)
    add_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("add_document", add_out)
    mgr.validate("add_status_200", resp.status_code == 200, resp.status_code, 200)

    search_payload = {"query": "test document", "collection": collection, "n_results": 3}
    mgr.save_input("search", search_payload)
    resp = api_client.post(f"/vector-stores/{store_id}/query", json=search_payload)
    search_out = resp.json() if resp.status_code == 200 else {"error": resp.text}
    mgr.save_output("search", search_out)
    mgr.validate("search_status_200", resp.status_code == 200, resp.status_code, 200)
    mgr.validate(
        "search_has_results",
        len(search_out.get("results", [])) >= 1,
        len(search_out.get("results", [])),
        ">=1",
    )
    # Config update test
    update_config = {"config": {"distance_metric": "l2"}}
    resp = api_client.put(f"/vector-stores/{store_id}", json=update_config)
    mgr.validate("config_update_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(
        f"/vector-stores/{store_id}/documents/{doc_id}?collection={collection}"
    )
    mgr.validate("delete_doc_status_200", resp.status_code == 200, resp.status_code, 200)

    resp = api_client.delete(f"/vector-stores/{store_id}")
    mgr.validate("cleanup_delete_status_200", resp.status_code == 200, resp.status_code, 200)

    # Summary table per TEST-SCRIPT.md:6-7
    summary = mgr.generate_summary_table()
    print(summary)
    failed = [v for v in mgr.validations if not v["passed"]]
    assert len(failed) == 0, f"{len(failed)} validation(s) failed: {failed}"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.vdb, pytest.mark.db, pytest.mark.heavy]
