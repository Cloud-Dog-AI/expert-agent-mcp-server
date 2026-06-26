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
Test Helpers for AT1.15, AT1.16, AT1.17, AT1.18
Output Storage and Test Utilities for REAL Integration Tests

License: Apache 2.0
Ownership: Cloud Dog
Description: Helper functions for comprehensive test output storage, validation,
and artifact management. Ensures ALL test operations are saved for manual validation.

Related Requirements: NF1.1 (Audit & Monitoring)
Related Tasks: T034
Related Architecture: SE1.3 (Security), MO1.2 (Monitoring)
Related Tests: AT1.15, AT1.16, AT1.17, AT1.18

Recent Changes (max 10):
- Initial creation for REAL comprehensive tests
- Full output storage with operation tracking
- LLM call recording
- Vector DB operation recording
- Business rule validation tracking
"""

from src.utils.logger import get_logger

logger = get_logger(__name__)


import json  # noqa: E402
from pathlib import Path  # noqa: E402
from typing import Dict, Any, List, Optional  # noqa: E402
from contextvars import ContextVar  # noqa: E402
from datetime import datetime  # noqa: E402
from urllib.parse import urlparse  # noqa: E402
import pytest  # noqa: E402
import requests  # noqa: E402
import time  # noqa: E402
import os  # noqa: E402
import subprocess  # noqa: E402
from src.config.loader import get_config  # noqa: E402


_CURRENT_OUTPUT_STORE: ContextVar[Optional["TestOutputStorage"]] = ContextVar(
    "current_output_store", default=None
)


def set_current_output_store(store: Optional["TestOutputStorage"]):
    """Set current TestOutputStorage for auto-logging."""
    return _CURRENT_OUTPUT_STORE.set(store)


def reset_current_output_store(token) -> None:
    """Reset current TestOutputStorage after a test finishes."""
    _CURRENT_OUTPUT_STORE.reset(token)


def get_current_output_store() -> Optional["TestOutputStorage"]:
    """Get current TestOutputStorage for auto-logging."""
    return _CURRENT_OUTPUT_STORE.get()


def get_admin_api_key():
    """Get admin API key from config (RULES.md compliant - no hardcoded values)."""
    api_key = get_config("test.api_key")
    if not api_key:
        pytest.fail("test.api_key not configured (set in secrets env file)")
    return str(api_key)


def require_test_user_base_email() -> str:
    """Return configured test user email, failing if missing or malformed."""
    base_email = get_config("test.user.email")
    if not base_email:
        pytest.fail("test.user.email not configured (set in --env file)")
    if "@" not in base_email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    return str(base_email)


def get_test_email_domain(base_email: Optional[str] = None) -> str:
    """Return domain portion of a configured test email."""
    base = base_email or require_test_user_base_email()
    if not base:
        pytest.fail("test.user.email not configured (set in --env file)")
    if "@" not in str(base):
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    return str(base).split("@", 1)[1]


def build_test_email(prefix: str, unique_id: str, base_email: Optional[str] = None) -> str:
    """Build a unique test email address using configured domain."""
    domain = get_test_email_domain(base_email)
    return f"{prefix}_{unique_id}@{domain}"


def response_to_dict(response: requests.Response) -> Dict[str, Any]:
    """Convert a requests response to a serialisable dict for logging."""
    data: Dict[str, Any] = {
        "status_code": getattr(response, "status_code", None),
        "headers": dict(getattr(response, "headers", {}) or {}),
        "body": None,
        "text": None,
    }
    try:
        data["body"] = response.json()
    except Exception:
        try:
            data["text"] = response.text
        except Exception:
            data["text"] = str(response)
    return data


def log_api_operation(
    store: "TestOutputStorage",
    operation_name: str,
    input_data: Dict[str, Any],
    response: requests.Response,
    expected_status: int = 200,
    required_fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Log API operation input/output and validation in a single call."""
    output_data = response_to_dict(response)
    validation = validate_api_response(response, expected_status, required_fields)
    store.save_operation(operation_name, input_data, output_data, validation_results=validation)
    store.save_validation(
        f"{operation_name}_status",
        {
            "expected_status": expected_status,
            "actual_status": response.status_code,
            "required_fields": required_fields or [],
        },
        bool(validation.get("overall_passed")),
    )
    return validation


def log_validation(
    store: "TestOutputStorage",
    name: str,
    passed: bool,
    actual: Any,
    expected: Any,
    context: str = "",
):
    """Log a validation record with expected/actual values."""
    store.save_validation(
        name,
        {"actual": actual, "expected": expected, "context": context},
        bool(passed),
    )


def log_validation_checks(
    store: "TestOutputStorage",
    name: str,
    checks: Dict[str, bool],
    context: Optional[Dict[str, Any]] = None,
) -> bool:
    """Log a grouped set of boolean checks as a single validation."""
    passed = all(bool(v) for v in checks.values())
    store.save_validation(
        name,
        {"checks": checks, "context": context or {}},
        passed,
    )
    return passed


def assert_with_log(
    store: "TestOutputStorage",
    name: str,
    condition: bool,
    context: Optional[Dict[str, Any]] = None,
    message: str = "",
) -> None:
    """Assert a condition while logging it as a validation."""
    log_validation_checks(store, name, {"condition": bool(condition)}, context=context or {})
    assert condition, message or f"Validation failed: {name}"


def log_http_operation(
    name: str,
    method: str,
    url: str,
    response: requests.Response,
    request_data: Optional[Dict[str, Any]] = None,
) -> None:
    """Log a raw HTTP operation (non-APIClient)."""
    store = get_current_output_store()
    if not store:
        return
    input_data = {"method": method, "url": url, "request": request_data or {}}
    output_data = response_to_dict(response)
    store.save_operation(name, input_data, output_data)


class APIClient:
    """HTTP client for real API server using requests library.

    This class provides a standardized way to interact with the API server
    for application tests, following RULES.md requirement to use requests
    library instead of TestClient.
    """

    def __init__(self, base_url: str):
        """Initialize API client.

        Args:
            base_url: Base URL of API server (e.g., http://<host>:<port>)
        """
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        # Default auth header for RULES.md compliance
        api_key = get_config("test.api_key")
        if api_key:
            self.session.headers.update({"X-API-Key": str(api_key)})

    def _is_llm_request(self, path: str) -> bool:
        p = (path or "").lower()
        return (
            "/chat" in p
            or "/summarize" in p
            or "/complete" in p
            or "/completions" in p
            or "/generate" in p
        )

    def _is_embedding_backed_vector_write(self, method: str, path: str) -> bool:
        m = (method or "").upper()
        p = (path or "").lower()
        return m in ("POST", "PUT") and "/vector-stores/" in p and "/documents" in p

    def _is_health_probe(self, path: str) -> bool:
        p = (path or "").split("?", 1)[0].strip().rstrip("/").lower()
        return p in {"/health", "/api/health", "/mcp/health", "/a2a/health"}

    def _get_timeout_seconds(self, is_llm: bool) -> float:
        base_timeout = get_config("test.http_timeout_seconds")
        llm_timeout = get_config("test.llm_http_timeout_seconds")
        if is_llm:
            if llm_timeout is None:
                pytest.fail("test.llm_http_timeout_seconds not configured for LLM requests")
            return float(llm_timeout)
        if base_timeout is None:
            pytest.fail("test.http_timeout_seconds not configured for non-LLM requests")
        return float(base_timeout)

    def _llm_retry_policy(self) -> Dict[str, Any]:
        retry_on_read_timeout = get_config("test.llm_retry_on_read_timeout")
        retries = get_config("test.llm_retries")
        grace_seconds = get_config("test.llm_retry_grace_seconds")
        backoff_seconds = get_config("test.llm_retry_backoff_seconds")
        if (
            retries is None
            or grace_seconds is None
            or backoff_seconds is None
            or retry_on_read_timeout is None
        ):
            pytest.fail(
                "Missing test.llm_retries/test.llm_retry_grace_seconds/"
                "test.llm_retry_backoff_seconds/test.llm_retry_on_read_timeout in config"
            )
        return {
            "retries": int(retries),
            "grace_seconds": float(grace_seconds),
            "backoff_seconds": float(backoff_seconds),
            "retry_on_read_timeout": bool(retry_on_read_timeout),
        }

    def _extract_loggable_kwargs(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        safe: Dict[str, Any] = {}
        for key in ("params", "json", "data", "headers", "timeout"):
            if key in kwargs:
                safe[key] = kwargs.get(key)
        return safe

    def _is_local_base_url(self) -> bool:
        parsed = urlparse(self.base_url)
        host = (parsed.hostname or "").strip().lower()
        return host in {"127.0.0.1", "localhost", "0.0.0.0", "::1"}

    def _is_api_reachable(self) -> bool:
        try:
            resp = self.session.get(f"{self.base_url}/health", timeout=5)
            return resp.status_code == 200
        except Exception:
            return False

    def _restart_local_stack(self) -> bool:
        """Best-effort local stack recovery for ST/IT/AT runs."""
        if not self._is_local_base_url():
            return False

        env_file = os.environ.get("CLOUD_DOG__EXPERT__ENV_FILE") or str(
            get_config("env_file") or ""
        )
        env_file = str(env_file).strip()
        if not env_file:
            return False

        project_root = Path(__file__).resolve().parents[2]

        def _run(*args: str) -> int:
            result = subprocess.run(
                ["./server_control.sh", "--env", env_file, *args],
                cwd=project_root,
                text=True,
                capture_output=True,
            )
            return int(result.returncode)

        # Fast path: try start-all first (handles dead PID cleanup internally)
        _run("start-all")
        for _ in range(20):
            if self._is_api_reachable():
                return True
            time.sleep(1)

        # If still unavailable, force-stop stale processes and clean-start
        _run("force-stop-all")
        _run("start-all")
        for _ in range(30):
            if self._is_api_reachable():
                return True
            time.sleep(1)
        return False

    def _maybe_log_operation(
        self, method: str, path: str, kwargs: Dict[str, Any], response: requests.Response
    ) -> None:
        store = get_current_output_store()
        if not store:
            return
        operation_name = f"{method.lower()}_{path.strip('/').replace('/', '_') or 'root'}"
        input_data = {
            "method": method,
            "path": path,
            "base_url": self.base_url,
            "request": self._extract_loggable_kwargs(kwargs),
        }
        output_data = response_to_dict(response)
        store.save_operation(operation_name, input_data, output_data)

    def _request(self, method: str, path: str, **kwargs):
        """Make HTTP request to API server.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            path: API path (e.g., /sessions)
            **kwargs: Additional arguments passed to requests

        Returns:
            requests.Response object
        """
        url = f"{self.base_url}{path}"
        is_llm = self._is_llm_request(path) or self._is_embedding_backed_vector_write(method, path)
        kwargs["timeout"] = self._get_timeout_seconds(is_llm)

        if not is_llm:
            try:
                resp = self.session.request(method, url, **kwargs)
                self._maybe_log_operation(method, path, kwargs, resp)
                return resp
            except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout):
                # Never auto-restart the stack for health probes. Server-control and
                # config-hierarchy tests intentionally verify downtime/port isolation.
                if (not self._is_health_probe(path)) and self._restart_local_stack():
                    resp = self.session.request(method, url, **kwargs)
                    self._maybe_log_operation(method, path, kwargs, resp)
                    return resp
                raise

        policy = self._llm_retry_policy()
        attempts = max(1, int(policy["retries"]) + 1)
        last_exc = None
        last_resp = None

        for attempt in range(attempts):
            if attempt > 0:
                sleep_s = (
                    float(policy["grace_seconds"])
                    if attempt == 1
                    else float(policy["backoff_seconds"]) * (2 ** (attempt - 2))
                )
                sleep_s = float(sleep_s)
                logger.warning(
                    f"LLM request retry {attempt}/{attempts - 1} after {sleep_s:.1f}s sleep: {method} {path}"
                )
                time.sleep(sleep_s)
            try:
                resp = self.session.request(method, url, **kwargs)
                last_resp = resp
                if resp.status_code in (500, 502, 503, 504) and attempt < attempts - 1:
                    logger.warning(
                        "LLM request transient HTTP %s (attempt %s/%s): %s %s",
                        resp.status_code,
                        attempt + 1,
                        attempts,
                        method,
                        path,
                    )
                    continue
                self._maybe_log_operation(method, path, kwargs, resp)
                return resp
            except (requests.exceptions.ConnectionError, requests.exceptions.ConnectTimeout) as e:
                last_exc = e
                if attempt >= attempts - 1:
                    raise
                logger.warning(
                    "LLM request connection error (attempt %s/%s): %s %s (%s)",
                    attempt + 1,
                    attempts,
                    method,
                    path,
                    type(e).__name__,
                )
                continue
            except requests.exceptions.ReadTimeout as e:
                last_exc = e
                if not policy.get("retry_on_read_timeout"):
                    raise
                if attempt >= attempts - 1:
                    pytest.fail(
                        f"LLM request read timeout after {attempts} attempts: {method} {path}"
                    )
                logger.warning(
                    "LLM request read timeout (attempt %s/%s): %s %s",
                    attempt + 1,
                    attempts,
                    method,
                    path,
                )
                continue

        if last_exc is not None:
            raise last_exc
        return last_resp

    def get(self, path: str, **kwargs):
        """HTTP GET request."""
        return self._request("GET", path, **kwargs)

    def post(self, path: str, **kwargs):
        """HTTP POST request."""
        return self._request("POST", path, **kwargs)

    def put(self, path: str, **kwargs):
        """HTTP PUT request."""
        return self._request("PUT", path, **kwargs)

    def delete(self, path: str, **kwargs):
        """HTTP DELETE request."""
        return self._request("DELETE", path, **kwargs)


def create_api_client_fixture(check_health: bool = True):
    """Factory to create api_client fixture for application tests.

    Returns a fixture function that creates an APIClient connected to
    the real API server (not TestClient).

    Args:
        check_health: If True, verify API server is reachable before returning client

    Usage in test files:
        api_client = create_api_client_fixture()
    """

    def _api_client_fixture():
        config = get_config()
        scheme = str(config.get("api_server", {}).get("scheme") or "http").strip().lower()
        host = config.get("api_server", {}).get("host")
        port = config.get("api_server", {}).get("port")
        verify_tls = config.get("test", {}).get("http_verify_tls")

        if not host or not port:
            pytest.fail("API server host/port not configured in config")
        if scheme not in {"http", "https"}:
            pytest.fail(f"Unsupported api_server.scheme: {scheme}")

        port = int(port) if isinstance(port, str) else port
        base_url = f"{scheme}://{host}:{port}"
        verify = (
            True
            if verify_tls is None
            else str(verify_tls).strip().lower() in {"1", "true", "yes", "on"}
        )

        if check_health:
            # Verify API server is reachable
            for attempt in range(5):
                try:
                    resp = requests.get(f"{base_url}/health", timeout=5, verify=verify)
                    if resp.status_code == 200:
                        break
                except Exception:
                    pass
                time.sleep(1)
            else:
                # Best-effort local recovery before hard failing.
                if str(host).strip().lower() in {"127.0.0.1", "localhost", "0.0.0.0", "::1"}:
                    env_file = os.environ.get("CLOUD_DOG__EXPERT__ENV_FILE") or str(
                        config.get("env_file") or ""
                    )
                    env_file = str(env_file).strip()
                    if env_file:
                        project_root = Path(__file__).resolve().parents[2]
                        subprocess.run(
                            ["./server_control.sh", "--env", env_file, "start-all"],
                            cwd=project_root,
                            text=True,
                            capture_output=True,
                        )
                        for _ in range(20):
                            try:
                                resp = requests.get(f"{base_url}/health", timeout=5, verify=verify)
                                if resp.status_code == 200:
                                    break
                            except Exception:
                                pass
                            time.sleep(1)
                        else:
                            pytest.fail(
                                f"API server not reachable at {base_url}. Start with: ./server_control.sh start api"
                            )
                    else:
                        pytest.fail(
                            f"API server not reachable at {base_url}. Start with: ./server_control.sh start api"
                        )
                else:
                    pytest.fail(
                        f"API server not reachable at {base_url}. Start with: ./server_control.sh start api"
                    )

        client = APIClient(base_url)
        client.session.verify = verify
        return client

    return _api_client_fixture


def assert_all_validations_passed(store: "TestOutputStorage"):
    failed = [v for v in store.metadata.get("validations", []) if not v.get("passed", False)]
    if failed:
        names = [v.get("validation_name") or v.get("name") for v in failed]
        pytest.fail(f"{len(failed)} validations failed: {names}")


def print_summary_table(store: "TestOutputStorage"):
    base = store.base_path.resolve()
    ops = sorted((base / "operations").glob("*.json"))
    vals = sorted((base / "validation").glob("*.json"))
    summary = store.save_test_summary()
    print("\n" + "=" * 80)
    print(f"TEST SUMMARY TABLE: {store.test_name}")
    print("=" * 80)
    print("\n## INPUT/OUTPUT FILES")
    for p in ops:
        print(f"- [{p.name}]({p.as_uri()})")
    print("\n## VALIDATIONS")
    for p in vals:
        print(f"- [{p.name}]({p.as_uri()})")
    print("\n## STATS")
    print(f"- Operations: {summary.get('total_operations')}")
    print(
        f"- Validations: {summary.get('total_validations')}, Passed: {summary.get('validations_passed')}"
    )
    print("=" * 80 + "\n")


class TestOutputStorage:
    """Manages comprehensive test output storage for validation."""

    __test__ = False  # Prevent pytest from collecting this helper as a test class

    def __init__(self, test_suite: str, test_name: str):
        """
        Initialize output storage.

        Args:
            test_suite: Test suite name (e.g., 'AT1.15_GroupManagement')
            test_name: Specific test name (e.g., 'test_group_lifecycle')
        """
        self.test_suite = test_suite
        self.test_name = test_name
        self.base_path = Path("working") / f"{test_suite}_TEST_OUTPUTS" / test_name
        self.base_path.mkdir(parents=True, exist_ok=True)

        # Create subdirectories
        self.operations_path = self.base_path / "operations"
        self.operations_path.mkdir(exist_ok=True)

        self.validation_path = self.base_path / "validation"
        self.validation_path.mkdir(exist_ok=True)

        self.llm_calls_path = self.base_path / "llm_calls"
        self.llm_calls_path.mkdir(exist_ok=True)

        self.vdb_operations_path = self.base_path / "vdb_operations"
        self.vdb_operations_path.mkdir(exist_ok=True)

        self.operation_counter = 0
        self.llm_call_counter = 0
        self.vdb_operation_counter = 0

        self.metadata = {
            "test_suite": test_suite,
            "test_name": test_name,
            "started_at": datetime.utcnow().isoformat(),
            "operations": [],
            "llm_calls": [],
            "vdb_operations": [],
            "validations": [],
        }

    def save_operation(
        self,
        operation_name: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        validation_results: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Save a complete operation (input, output, validation).

        Args:
            operation_name: Name of the operation (e.g., 'create_group')
            input_data: Input data sent
            output_data: Output data received
            validation_results: Validation results (optional)

        Returns:
            Operation number
        """
        self.operation_counter += 1
        op_num = self.operation_counter

        # Save input
        input_file = self.operations_path / f"op_{op_num:03d}_{operation_name}_input.json"
        with open(input_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "operation": operation_name,
                    "op_number": op_num,
                    "timestamp": datetime.utcnow().isoformat(),
                    "input": input_data,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

        # Save output
        output_file = self.operations_path / f"op_{op_num:03d}_{operation_name}_output.json"
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "operation": operation_name,
                    "op_number": op_num,
                    "timestamp": datetime.utcnow().isoformat(),
                    "output": output_data,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

        # Save validation if provided
        if validation_results:
            validation_file = (
                self.validation_path / f"op_{op_num:03d}_{operation_name}_validation.json"
            )
            with open(validation_file, "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "operation": operation_name,
                        "op_number": op_num,
                        "timestamp": datetime.utcnow().isoformat(),
                        "validation": validation_results,
                    },
                    f,
                    indent=2,
                    ensure_ascii=False,
                )

        # Track in metadata with absolute paths for clickable URIs
        self.metadata["operations"].append(
            {
                "op_number": op_num,
                "operation": operation_name,
                "input_file": str(input_file.absolute()),
                "output_file": str(output_file.absolute()),
                "validation_file": str(validation_file.absolute()) if validation_results else None,
            }
        )

        return op_num

    def save_llm_call(
        self,
        prompt: str,
        response: str,
        llm_config: Dict[str, Any],
        metadata: Optional[Dict[str, Any]] = None,
    ) -> int:
        """
        Save LLM call details.

        Args:
            prompt: Prompt sent to LLM
            response: Response from LLM
            llm_config: LLM configuration used
            metadata: Additional metadata

        Returns:
            LLM call number
        """
        self.llm_call_counter += 1
        call_num = self.llm_call_counter

        call_file = self.llm_calls_path / f"llm_call_{call_num:03d}.json"
        with open(call_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "call_number": call_num,
                    "timestamp": datetime.utcnow().isoformat(),
                    "prompt": prompt,
                    "response": response,
                    "llm_config": llm_config,
                    "metadata": metadata or {},
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

        self.metadata["llm_calls"].append(
            {
                "call_number": call_num,
                "file": str(call_file.absolute()),
                "prompt_preview": prompt[:100] + "..." if len(prompt) > 100 else prompt,
                "response_length": len(response),
            }
        )

        return call_num

    def save_vdb_operation(
        self,
        operation_type: str,
        vdb_type: str,
        operation_data: Dict[str, Any],
        results: Dict[str, Any],
    ) -> int:
        """
        Save vector database operation.

        Args:
            operation_type: Type of operation (e.g., 'embed', 'search', 'delete')
            vdb_type: Vector DB type (e.g., 'chroma', 'qdrant')
            operation_data: Operation parameters
            results: Operation results

        Returns:
            VDB operation number
        """
        self.vdb_operation_counter += 1
        op_num = self.vdb_operation_counter

        vdb_file = self.vdb_operations_path / f"vdb_op_{op_num:03d}_{operation_type}.json"
        with open(vdb_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "op_number": op_num,
                    "timestamp": datetime.utcnow().isoformat(),
                    "operation_type": operation_type,
                    "vdb_type": vdb_type,
                    "operation_data": operation_data,
                    "results": results,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

        self.metadata["vdb_operations"].append(
            {
                "op_number": op_num,
                "operation_type": operation_type,
                "vdb_type": vdb_type,
                "file": str(vdb_file.absolute()),
            }
        )

        return op_num

    def save_validation(self, validation_name: str, validation_data: Dict[str, Any], passed: bool):
        """
        Save validation results.

        Args:
            validation_name: Name of validation
            validation_data: Validation details
            passed: Whether validation passed
        """
        validation_file = self.validation_path / f"validation_{validation_name}.json"
        with open(validation_file, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "validation_name": validation_name,
                    "timestamp": datetime.utcnow().isoformat(),
                    "passed": passed,
                    "validation_data": validation_data,
                },
                f,
                indent=2,
                ensure_ascii=False,
            )

        self.metadata["validations"].append(
            {
                "validation_name": validation_name,
                "passed": passed,
                "file": str(validation_file.absolute()),
            }
        )

    def save_test_summary(self) -> Dict[str, Any]:
        """Save test summary with all links."""
        self.metadata["completed_at"] = datetime.utcnow().isoformat()
        self.metadata["total_operations"] = len(self.metadata["operations"])
        self.metadata["total_llm_calls"] = len(self.metadata["llm_calls"])
        self.metadata["total_vdb_operations"] = len(self.metadata["vdb_operations"])
        self.metadata["total_validations"] = len(self.metadata["validations"])
        self.metadata["validations_passed"] = sum(
            1 for v in self.metadata["validations"] if v["passed"]
        )

        summary_file = self.base_path / "test_summary.json"
        with open(summary_file, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=2, ensure_ascii=False)

        # Also save metadata
        metadata_file = self.base_path / "test_metadata.json"
        with open(metadata_file, "w", encoding="utf-8") as f:
            json.dump(self.metadata, f, indent=2, ensure_ascii=False)

        print(f"\n{'=' * 80}")
        print(f"TEST SUMMARY: {self.test_name}")
        print(f"{'=' * 80}")
        print(f"Operations: {self.metadata['total_operations']}")
        print(f"LLM Calls: {self.metadata['total_llm_calls']}")
        print(f"VDB Operations: {self.metadata['total_vdb_operations']}")
        print(
            f"Validations: {self.metadata['validations_passed']}/{self.metadata['total_validations']} passed"
        )
        print(f"\nSummary file: {summary_file}")
        print(f"{'=' * 80}\n")

        return self.metadata


def validate_config_loaded():
    """Validate that configuration is loaded (hard fail if not)."""
    from src.config.loader import load_config

    load_config.cache_clear()

    # Hard fail if critical config missing
    llm_provider = get_config("llm.provider")
    if not llm_provider:
        pytest.fail("llm.provider not configured. Use --env <env-file> to specify configuration.")

    llm_model = get_config("llm.model")
    if not llm_model:
        pytest.fail("llm.model not configured. Use --env <env-file> to specify configuration.")

    llm_base_url = get_config("llm.base_url")
    if not llm_base_url:
        pytest.fail("llm.base_url not configured. Use --env <env-file> to specify configuration.")

    # Explicit policy: never use local Ollama in tests (remote Ollama-compatible endpoints are allowed)
    if "localhost:11434" in str(llm_base_url) or "127.0.0.1:11434" in str(llm_base_url):
        pytest.fail(
            "llm.base_url points to local Ollama (localhost:11434), which is forbidden. Use remote LLM base URL in --env."
        )

    return True


def validate_api_response(
    response, expected_status: int, required_fields: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    Validate API response and return validation results.

    Args:
        response: API response object
        expected_status: Expected HTTP status code
        required_fields: Required fields in response JSON

    Returns:
        Validation results dict
    """
    validation = {
        "status_code_check": {
            "expected": expected_status,
            "actual": response.status_code,
            "passed": response.status_code == expected_status,
        }
    }

    if required_fields and response.status_code == expected_status:
        try:
            data = response.json()
            field_checks = {}
            for field in required_fields:
                field_checks[field] = field in data
            validation["required_fields"] = {
                "fields": field_checks,
                "passed": all(field_checks.values()),
            }
        except Exception:
            validation["required_fields"] = {"error": "Failed to parse JSON", "passed": False}

    validation["overall_passed"] = all(
        v.get("passed", True) for v in validation.values() if isinstance(v, dict)
    )

    return validation

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.application, pytest.mark.llm, pytest.mark.vdb, pytest.mark.db, pytest.mark.smtp, pytest.mark.mcp, pytest.mark.heavy]
