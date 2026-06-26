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
Pytest Configuration and Fixtures

License: Apache 2.0
Ownership: Cloud Dog
Description: Shared test fixtures and configuration

Related Requirements: NF1.1
Related Tasks: T112
Related Architecture: Various
Related Tests: All

Recent Changes:
- Added --env option support for test configuration
- Added environment file loading from private/ directory
- Added startup configuration checks
- Replaced hard-coded values with environment-based configuration
- Added timeout controls and CLI output visibility
"""

import pytest
import os
import sys
import tempfile
import uuid
import subprocess
import time
import fcntl
import json
import ssl
import urllib.request
from pathlib import Path
import requests

# Set TESTING environment variable to use test configuration
# This ensures tests use private/env-test instead of private/env-build
os.environ["TESTING"] = "true"

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

_VAULT_CFG_CACHE: dict[str, object] | None = None


def _load_vault_config_blob() -> dict[str, object]:
    """Load the shared Vault config blob once for test env resolution."""
    global _VAULT_CFG_CACHE
    if _VAULT_CFG_CACHE is not None:
        return _VAULT_CFG_CACHE

    addr = os.environ.get("VAULT_ADDR", "").strip()
    mount = os.environ.get("VAULT_MOUNT_POINT", "").strip()
    config_path = os.environ.get("VAULT_CONFIG_PATH", "").strip()
    token = os.environ.get("VAULT_TOKEN", "").strip()
    if not addr or not mount or not config_path or not token:
        pytest.fail(
            "VAULT_ADDR/VAULT_MOUNT_POINT/VAULT_CONFIG_PATH/VAULT_TOKEN must be set to resolve "
            "Vault expressions in expert-agent test env."
        )

    url = f"{addr}/v1/{mount}/data/{config_path}"
    req = urllib.request.Request(url, headers={"X-Vault-Token": token})
    try:
        with urllib.request.urlopen(req, context=ssl.create_default_context()) as resp:
            payload = json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        pytest.fail(f"Failed to read Vault config for env resolution: {exc}")

    raw_blob = payload.get("data", {}).get("data", {}).get("json", {})
    if isinstance(raw_blob, str):
        try:
            raw_blob = json.loads(raw_blob)
        except json.JSONDecodeError as exc:
            pytest.fail(f"Vault config payload json field is not valid JSON: {exc}")

    _VAULT_CFG_CACHE = raw_blob
    if not isinstance(_VAULT_CFG_CACHE, dict):
        pytest.fail("Vault config payload does not contain a json object")
    return _VAULT_CFG_CACHE


def _resolve_vault_expr(raw_value: str) -> str:
    """Resolve ${vault.dev...} expressions from the live Vault config blob."""
    value = str(raw_value).strip()
    if not (value.startswith("${vault.") and value.endswith("}")):
        return raw_value

    path = value[len("${vault.") : -1]
    current: object = _load_vault_config_blob()
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            pytest.fail(f"Vault expression path not found during test env resolution: {path}")
        current = current[part]
    if current in (None, ""):
        pytest.fail(f"Vault expression resolved empty during test env resolution: {path}")
    return str(current)


def _local_optional_vault_fallback(env_key: str) -> str | None:
    """Return a local fallback for optional Vault placeholders when safe.

    The Weaviate runtime used by expert-agent authenticates with the shared API
    token in local test secrets and does not consume a separate username. Some
    AT env profiles still carry a legacy Vault username placeholder, which
    should not force live Vault access when the token-based secret is already
    present locally.
    """

    if env_key != "CLOUD_DOG__EXPERT__VECTOR_STORES_CONFIG__WEAVIATE___DEFAULT___USERNAME":
        return None

    for candidate_key in (
        "CLOUD_DOG__EXPERT__VECTOR_STORES_CONFIG__WEAVIATE___DEFAULT___API_KEY",
        "CLOUD_DOG__EXPERT__VECTOR__STORES__WEAVIATE__REMOTE__AUTH_TOKEN",
    ):
        candidate = str(os.environ.get(candidate_key, "")).strip()
        if candidate and not _is_template_placeholder(candidate):
            return ""

    return None


def _coerce_int(value: str, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _is_local_stack_env(env_path: Path) -> bool:
    """True when tests should own local ST/IT/AT server lifecycle."""
    env_name = env_path.name.lower()
    tier = str(os.environ.get("TEST_ENV_TIER", "")).strip().upper()
    if (
        "preprod" in env_name
        or "docker" in env_name
        or tier.endswith("_DOCKER")
        or tier == "PREPROD"
    ):
        return False
    return (
        env_name.startswith("env-test")
        or
        env_name.startswith("env-st")
        or env_name.startswith("env-it")
        or env_name.startswith("env-at")
        or tier in {"ST", "IT", "AT"}
    )


@pytest.fixture(scope="session", autouse=True)
def sequential_test_session_lock(request):
    """
    Serialize test execution for this project to avoid contested local resources.
    """
    lock_file = os.environ.get(
        "CLOUD_DOG__EXPERT__TEST__SESSION_LOCK_FILE",
        "/tmp/cloud-dog-expert-agent-tests.lock",
    )
    wait_timeout = _coerce_int(
        os.environ.get("CLOUD_DOG__EXPERT__TEST__SESSION_LOCK_TIMEOUT_SECONDS"),
        3600,
    )

    lock_path = Path(lock_file)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(lock_path, "a+", encoding="utf-8")

    start = time.time()
    while True:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            elapsed = int(time.time() - start)
            if elapsed >= wait_timeout:
                handle.seek(0)
                owner = handle.read().strip() or "<unknown>"
                handle.close()
                pytest.fail(
                    f"Timed out waiting for sequential test lock: {lock_path} after {wait_timeout}s. "
                    f"Current lock owner: {owner}"
                )
            time.sleep(1.0)

    env_file = str(request.config.getoption("--env") or "<unset>")
    handle.seek(0)
    handle.truncate(0)
    handle.write(f"pid={os.getpid()} env={env_file} acquired_at={int(time.time())}\n")
    handle.flush()

    try:
        yield str(lock_path)
    finally:
        try:
            handle.seek(0)
            handle.truncate(0)
            handle.flush()
        except Exception:
            pass
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()


def pytest_addoption(parser):
    """Add custom pytest options."""
    parser.addoption(
        "--env",
        action="store",
        default=None,
        help="Environment file to use (e.g. 'private/env-test' or 'env-test')",
    )


def _resolve_env_path(env_file: str) -> Path:
    """Resolve --env to a path under tests/ (unless already provided)."""
    if env_file.startswith(("/", "tests/", "private/")):
        return Path(env_file)
    return Path("tests") / env_file


def _read_env_kv(path: Path) -> dict[str, str]:
    """Read key=value pairs from env-style files."""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _is_template_placeholder(raw: str) -> bool:
    text = str(raw).strip()
    return text.startswith("${") and text.endswith("}")


def _is_local_host(host: str) -> bool:
    return str(host).strip().lower() in {"127.0.0.1", "localhost", "0.0.0.0", "::1"}


def _http_status(url: str, timeout: float) -> int | None:
    try:
        return int(requests.get(url, timeout=timeout).status_code)
    except requests.RequestException:
        return None


def _all_local_server_health_ok(timeout: float, from_config) -> bool:
    checks = [
        ("api_server.host", "api_server.port", "/health"),
        ("web_server.host", "web_server.port", "/health"),
        ("mcp_server.host", "mcp_server.port", "/mcp/health"),
        ("a2a_server.host", "a2a_server.port", "/a2a/health"),
    ]
    for host_key, port_key, path in checks:
        host = from_config(host_key)
        port = from_config(port_key)
        if not host or port is None or not _is_local_host(str(host)):
            return False
        status = _http_status(f"http://{host}:{int(port)}{path}", timeout=timeout)
        if status != 200:
            return False
    return True


def _api_admin_key_works(timeout: float, from_config) -> bool:
    host = from_config("api_server.host")
    port = from_config("api_server.port")
    api_key = (
        from_config("api_server.api_key")
        or from_config("test.api_key")
        or os.environ.get("CLOUD_DOG__EXPERT__API_SERVER__API_KEY")
        or os.environ.get("CLOUD_DOG__EXPERT__TEST__API_KEY")
        or os.environ.get("TEST_API_KEY")
    )
    if not host or port is None or not api_key:
        return False
    status = _http_status(
        f"http://{host}:{int(port)}/users",
        timeout=timeout,
    )
    if status == 200:
        return True
    try:
        response = requests.get(
            f"http://{host}:{int(port)}/users",
            headers={"X-API-Key": str(api_key)},
            timeout=timeout,
        )
        return response.status_code == 200
    except requests.RequestException:
        return False


def _run_server_control(env_path: Path, command: str) -> subprocess.CompletedProcess:
    project_root = Path(__file__).resolve().parent.parent
    cmd = ["./server_control.sh", "--env", str(env_path.resolve()), command]
    return subprocess.run(cmd, cwd=project_root, text=True, capture_output=True)


def _reset_sqlite_test_db_if_needed(project_root: Path) -> None:
    """Keep sqlite unit-test runs reproducible across reruns."""
    db_uri = str(os.environ.get("CLOUD_DOG__EXPERT__DB__URI", "")).strip()
    if not db_uri.startswith("sqlite:///"):
        return

    sqlite_target = db_uri[len("sqlite:///") :].strip()
    if not sqlite_target or sqlite_target == ":memory:":
        return

    db_path = Path(sqlite_target)
    if not db_path.is_absolute():
        db_path = project_root / db_path

    db_name = db_path.name
    if db_name != "test_expert.db":
        return

    # Never reset the sqlite file while a live local server stack is already
    # bound to the configured env-test ports; doing so invalidates bootstrap
    # auth state and can leave long-lived server connections pointing at a
    # deleted/readonly database.
    live_stack_checks = [
        ("CLOUD_DOG__EXPERT__API_SERVER__HOST", "CLOUD_DOG__EXPERT__API_SERVER__PORT", "/health"),
        ("CLOUD_DOG__EXPERT__WEB_SERVER__HOST", "CLOUD_DOG__EXPERT__WEB_SERVER__PORT", "/health"),
        ("CLOUD_DOG__EXPERT__MCP_SERVER__HOST", "CLOUD_DOG__EXPERT__MCP_SERVER__PORT", "/mcp/health"),
        ("CLOUD_DOG__EXPERT__A2A_SERVER__HOST", "CLOUD_DOG__EXPERT__A2A_SERVER__PORT", "/a2a/health"),
    ]
    live_stack_healthy = True
    for host_key, port_key, path in live_stack_checks:
        host = os.environ.get(host_key)
        port = os.environ.get(port_key)
        if not host or not port or not _is_local_host(host):
            live_stack_healthy = False
            break
        status = _http_status(f"http://{host}:{int(port)}{path}", timeout=2.0)
        if status != 200:
            live_stack_healthy = False
            break
    if live_stack_healthy:
        return

    for suffix in ("", "-wal", "-shm"):
        candidate = Path(f"{db_path}{suffix}")
        try:
            if candidate.exists():
                candidate.unlink()
        except FileNotFoundError:
            pass


def _ensure_local_server_stack(env_path: Path) -> bool:
    """
    For local ST/IT/AT envs, ensure API/MCP/A2A/Web are reachable and aligned
    with the same env-profile keys used by tests.
    """
    if not _is_local_stack_env(env_path):
        return False

    env_values = _read_env_kv(env_path)
    expected_local_keys = {
        "CLOUD_DOG__EXPERT__API_SERVER__HOST": str(
            env_values.get("CLOUD_DOG__EXPERT__API_SERVER__HOST")
            or os.environ.get("CLOUD_DOG__EXPERT__API_SERVER__HOST")
            or "127.0.0.1"
        ),
        "CLOUD_DOG__EXPERT__WEB_SERVER__HOST": str(
            env_values.get("CLOUD_DOG__EXPERT__WEB_SERVER__HOST")
            or os.environ.get("CLOUD_DOG__EXPERT__WEB_SERVER__HOST")
            or "127.0.0.1"
        ),
        "CLOUD_DOG__EXPERT__MCP_SERVER__HOST": str(
            env_values.get("CLOUD_DOG__EXPERT__MCP_SERVER__HOST")
            or os.environ.get("CLOUD_DOG__EXPERT__MCP_SERVER__HOST")
            or "127.0.0.1"
        ),
        "CLOUD_DOG__EXPERT__A2A_SERVER__HOST": str(
            env_values.get("CLOUD_DOG__EXPERT__A2A_SERVER__HOST")
            or os.environ.get("CLOUD_DOG__EXPERT__A2A_SERVER__HOST")
            or "127.0.0.1"
        ),
        "CLOUD_DOG__EXPERT__API_SERVER__PORT": str(
            env_values.get("CLOUD_DOG__EXPERT__API_SERVER__PORT")
            or os.environ.get("CLOUD_DOG__EXPERT__API_SERVER__PORT")
            or "18083"
        ),
        "CLOUD_DOG__EXPERT__WEB_SERVER__PORT": str(
            env_values.get("CLOUD_DOG__EXPERT__WEB_SERVER__PORT")
            or os.environ.get("CLOUD_DOG__EXPERT__WEB_SERVER__PORT")
            or "18080"
        ),
        "CLOUD_DOG__EXPERT__MCP_SERVER__PORT": str(
            env_values.get("CLOUD_DOG__EXPERT__MCP_SERVER__PORT")
            or os.environ.get("CLOUD_DOG__EXPERT__MCP_SERVER__PORT")
            or "18081"
        ),
        "CLOUD_DOG__EXPERT__A2A_SERVER__PORT": str(
            env_values.get("CLOUD_DOG__EXPERT__A2A_SERVER__PORT")
            or os.environ.get("CLOUD_DOG__EXPERT__A2A_SERVER__PORT")
            or "18082"
        ),
    }
    # Bind the exact env-profile values into the process before restarting the
    # local stack so conftest health checks and server_control.sh target the
    # same ports instead of drifting to historical defaults.
    for key, expected in expected_local_keys.items():
        value = env_values.get(key)
        if env_path.name == "env-test" and value != expected:
            pytest.fail(
                f"{env_path} must define {key}={expected} for local stack verification, got {value!r}"
            )
        if value and not _is_template_placeholder(str(value)):
            os.environ[key] = str(value)
        elif (not os.environ.get(key)) or _is_template_placeholder(str(os.environ.get(key))):
            os.environ[key] = expected

    from src.config.loader import load_config, get_config

    load_config.cache_clear()
    timeout = float(get_config("test.http_timeout_seconds") or 30)

    config_expectations = {
        "api_server.host": os.environ["CLOUD_DOG__EXPERT__API_SERVER__HOST"],
        "api_server.port": os.environ["CLOUD_DOG__EXPERT__API_SERVER__PORT"],
        "web_server.host": os.environ["CLOUD_DOG__EXPERT__WEB_SERVER__HOST"],
        "web_server.port": os.environ["CLOUD_DOG__EXPERT__WEB_SERVER__PORT"],
        "mcp_server.host": os.environ["CLOUD_DOG__EXPERT__MCP_SERVER__HOST"],
        "mcp_server.port": os.environ["CLOUD_DOG__EXPERT__MCP_SERVER__PORT"],
        "a2a_server.host": os.environ["CLOUD_DOG__EXPERT__A2A_SERVER__HOST"],
        "a2a_server.port": os.environ["CLOUD_DOG__EXPERT__A2A_SERVER__PORT"],
    }
    for config_key, expected_value in config_expectations.items():
        resolved = get_config(config_key)
        if str(resolved) != str(expected_value):
            pytest.fail(
                f"Resolved config drift for {config_key}: expected {expected_value}, got {resolved}"
            )

    if _all_local_server_health_ok(timeout=5, from_config=get_config) and _api_admin_key_works(
        timeout=timeout, from_config=get_config
    ):
        return False

    def _wait_until_ready() -> bool:
        for _ in range(40):
            load_config.cache_clear()
            if _all_local_server_health_ok(
                timeout=5, from_config=get_config
            ) and _api_admin_key_works(timeout=timeout, from_config=get_config):
                return True
            time.sleep(1)
        return False

    # Enforce deterministic local stack: one clean stop/start with the env file
    # already bound above. Do not do a second force-stop/start cycle here; that
    # has been causing port drift under private/env-test.
    stop = _run_server_control(env_path, "stop-all")
    start = _run_server_control(env_path, "start-all")
    if _wait_until_ready():
        return True

    status = _run_server_control(env_path, "status-all")
    pytest.fail(
        "Local ST/IT/AT server stack did not become healthy/authenticated "
        f"for env {env_path}.\n"
        f"stop-all rc={stop.returncode}\n"
        f"start-all rc={start.returncode}\n"
        f"status-all rc={status.returncode}\n"
        f"status-all stdout:\n{status.stdout}\n"
        f"status-all stderr:\n{status.stderr}"
    )


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    db_file = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    db_path = db_file.name
    db_file.close()

    yield f"sqlite:///{db_path}"

    # Cleanup
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture(scope="session")
def test_env_file(request, sequential_test_session_lock):
    """Load environment file specified via --env option.

    HARD REQUIREMENT: --env file MUST be provided (hard fail if missing).
    All configuration MUST come from config system (get_config), NOT direct os.environ.
    Non-secret test env files live in tests/, secrets live in private/.
    """
    _ = sequential_test_session_lock
    env_file = request.config.getoption("--env")

    # HARD FAIL if --env not provided
    if env_file is None or str(env_file).strip() == "":
        pytest.fail(
            "--env file MUST be provided. Use: pytest --env private/env-test\n"
            "All tests require an environment file to be specified."
        )

    env_path = _resolve_env_path(str(env_file))

    if not env_path.exists():
        pytest.fail(
            f"Environment file not found: {env_path}. Use --env to specify a valid env file.\n"
            f"Available env files: {list(Path('tests').glob('env-*'))}"
        )

    # Set TESTING flag so config loader knows we're in test mode
    os.environ["TESTING"] = "true"

    # Load env file (non-secret) using the canonical config loader helper
    from src.config.loader import load_config, get_config
    from tests.env_file_loader import load_env_files

    for key, value in load_env_files(str(env_path), include_secrets=False, override=True).items():
        os.environ[key] = value

    # Load shared secrets (if available), then env-specific secrets
    shared_secrets_path = Path("private") / "env-test-secrets"
    if shared_secrets_path.exists():
        for key, value in load_env_files(
            str(shared_secrets_path), include_secrets=False, override=False
        ).items():
            if key not in os.environ or _is_template_placeholder(str(os.environ.get(key))):
                os.environ[key] = value

    secrets_path = Path("private") / f"{env_path.name}-secrets"
    if secrets_path.exists():
        for key, value in load_env_files(
            str(secrets_path), include_secrets=False, override=True
        ).items():
            os.environ[key] = value

    # Prefer already-loaded concrete local test credentials before forcing
    # live Vault resolution for env profiles that still carry ${vault...}
    # placeholders.
    concrete_api_key = None
    for candidate in (
        os.environ.get("CLOUD_DOG__EXPERT__API_KEY"),
        os.environ.get("CLOUD_DOG__EXPERT__API_SERVER__API_KEY"),
        os.environ.get("CLOUD_DOG__EXPERT__TEST__API_KEY"),
        os.environ.get("TEST_API_KEY"),
    ):
        if candidate and not _is_template_placeholder(str(candidate)):
            concrete_api_key = str(candidate)
            break
    if concrete_api_key and _is_template_placeholder(os.environ.get("CLOUD_DOG__EXPERT__API_KEY", "")):
        os.environ["CLOUD_DOG__EXPERT__API_KEY"] = concrete_api_key

    concrete_password = None
    for candidate in (
        os.environ.get("CLOUD_DOG__EXPERT__TEST__USER__PASSWORD"),
        os.environ.get("TEST_USER_PASSWORD"),
    ):
        if candidate and not _is_template_placeholder(str(candidate)):
            concrete_password = str(candidate)
            break
    if concrete_password and _is_template_placeholder(
        os.environ.get("CLOUD_DOG__EXPERT__TEST__USER__PASSWORD", "")
    ):
        os.environ["CLOUD_DOG__EXPERT__TEST__USER__PASSWORD"] = concrete_password

    # Resolve live Vault expressions for expert-agent test stacks because this
    # project's local config loader preserves ${vault...} literals verbatim.
    vault_env_ready = all(
        str(os.environ.get(key, "")).strip()
        for key in ("VAULT_ADDR", "VAULT_MOUNT_POINT", "VAULT_CONFIG_PATH", "VAULT_TOKEN")
    )
    for key, value in list(os.environ.items()):
        if isinstance(value, str) and value.startswith("${vault."):
            if not vault_env_ready:
                local_fallback = _local_optional_vault_fallback(key)
                if local_fallback is not None:
                    os.environ[key] = local_fallback
                    continue
            os.environ[key] = _resolve_vault_expr(value)

    # Ensure TEST_* env vars align with CLOUD_DOG__EXPERT__TEST__* for tests.
    # This prevents external TEST_* overrides from breaking env-file-driven runs.
    test_user_map = {
        "TEST_USER_USERNAME": "CLOUD_DOG__EXPERT__TEST__USER__USERNAME",
        "TEST_USER_EMAIL": "CLOUD_DOG__EXPERT__TEST__USER__EMAIL",
        "TEST_USER_PASSWORD": "CLOUD_DOG__EXPERT__TEST__USER__PASSWORD",
        "TEST_USER_DISPLAY_NAME": "CLOUD_DOG__EXPERT__TEST__USER__DISPLAY_NAME",
    }

    for test_key, expert_key in test_user_map.items():
        expert_value = os.environ.get(expert_key)
        if not expert_value:
            continue
        if _is_template_placeholder(expert_value):
            # Keep concrete TEST_* values from secrets files when env files contain template placeholders.
            continue
        current_test_value = os.environ.get(test_key)
        if (not current_test_value) or _is_template_placeholder(current_test_value):
            os.environ[test_key] = expert_value

    # Keep test password stable across TEST_* and CLOUD_DOG__EXPERT__TEST__* keys.
    # Some env profiles carry placeholders or weak defaults that violate password policy.
    from src.core.auth.password import validate_password_policy

    test_pwd = os.environ.get("TEST_USER_PASSWORD")
    expert_pwd = os.environ.get("CLOUD_DOG__EXPERT__TEST__USER__PASSWORD")
    resolved_pwd = test_pwd if test_pwd and not _is_template_placeholder(test_pwd) else expert_pwd
    fallback_pwd = "TestPassword123!"
    if not resolved_pwd or _is_template_placeholder(str(resolved_pwd)):
        resolved_pwd = fallback_pwd
    try:
        validate_password_policy(str(resolved_pwd))
    except Exception:
        resolved_pwd = fallback_pwd
    os.environ["TEST_USER_PASSWORD"] = str(resolved_pwd)
    os.environ["CLOUD_DOG__EXPERT__TEST__USER__PASSWORD"] = str(resolved_pwd)

    # Keep weak password deterministic for negative auth tests.
    # Prefer env-file CLOUD_DOG value, then TEST_* value, then a known weak fallback.
    expert_weak_pwd = os.environ.get("CLOUD_DOG__EXPERT__TEST__USER__PASSWORD_WEAK")
    test_weak_pwd = os.environ.get("TEST_USER_PASSWORD_WEAK")
    weak_pwd = (
        expert_weak_pwd
        if expert_weak_pwd and not _is_template_placeholder(expert_weak_pwd)
        else test_weak_pwd
    )
    if not weak_pwd or _is_template_placeholder(str(weak_pwd)):
        weak_pwd = "short"
    os.environ["TEST_USER_PASSWORD_WEAK"] = str(weak_pwd)
    os.environ["CLOUD_DOG__EXPERT__TEST__USER__PASSWORD_WEAK"] = str(weak_pwd)

    display_name = (
        os.environ.get("TEST_USER_DISPLAY_NAME")
        or os.environ.get("TEST_USER_USERNAME")
        or "Test User"
    )
    os.environ["TEST_USER_DISPLAY_NAME"] = str(display_name)
    if not os.environ.get("CLOUD_DOG__EXPERT__TEST__USER__DISPLAY_NAME"):
        os.environ["CLOUD_DOG__EXPERT__TEST__USER__DISPLAY_NAME"] = str(display_name)

    # Backfill older unit-test fixtures that still require test.group.* / test.pii.*
    fallback_test_values = {
        "CLOUD_DOG__EXPERT__TEST__GROUP__NAME_PREFIX": "testgroup",
        "CLOUD_DOG__EXPERT__TEST__PII__PHONE": "555-123-4567",
        "CLOUD_DOG__EXPERT__TEST__PII__PHONE_BASIC": "555-123-4567",
        "CLOUD_DOG__EXPERT__TEST__PII__PHONE_PAREN": "(555) 123-4567",
        "CLOUD_DOG__EXPERT__TEST__PII__PHONE_DOT": "555.123.4567",
        "CLOUD_DOG__EXPERT__TEST__PII__PHONE_INTL": "+1 555 123 4567",
        "CLOUD_DOG__EXPERT__TEST__PII__PHONE_COMPACT": "5551234567",
        "CLOUD_DOG__EXPERT__TEST__PII__EMAIL_SIMPLE": "john.doe@example.com",
        "CLOUD_DOG__EXPERT__TEST__PII__EMAIL_SECONDARY": "jane.smith@example.org",
        "CLOUD_DOG__EXPERT__TEST__PII__EMAIL_PLUS": "alerts+test@example.com",
        "CLOUD_DOG__EXPERT__TEST__PII__EMAIL_COMPLEX": "first.last-qa_01@example.co.uk",
        "CLOUD_DOG__EXPERT__TEST__PII__SSN": "123-45-6789",
        "CLOUD_DOG__EXPERT__TEST__PII__CARD": "4111111111111111",
        "CLOUD_DOG__EXPERT__TEST__PII__CREDIT_CARD": "4111 1111 1111 1111",
        "CLOUD_DOG__EXPERT__TEST__PII__IP_ADDRESS": "203.0.113.42",
        "CLOUD_DOG__EXPERT__TEST__PII__URL_BASE": "https://example.test",
    }
    for key, value in fallback_test_values.items():
        current_value = os.environ.get(key)
        if not current_value or _is_template_placeholder(str(current_value)):
            os.environ[key] = value

    if not os.environ.get("TEST_GROUP_NAME_PREFIX"):
        os.environ["TEST_GROUP_NAME_PREFIX"] = os.environ[
            "CLOUD_DOG__EXPERT__TEST__GROUP__NAME_PREFIX"
        ]

    # Backfill older message-history fixtures that still require test.message.*
    fallback_message_values = {
        "CLOUD_DOG__EXPERT__TEST__MESSAGE__TOKENS_USED": "100",
        "CLOUD_DOG__EXPERT__TEST__MESSAGE__MODEL": (
            os.environ.get("CLOUD_DOG__EXPERT__LLM__MODEL") or "qwen3:14b"
        ),
    }
    for key, value in fallback_message_values.items():
        current_value = os.environ.get(key)
        if not current_value or _is_template_placeholder(str(current_value)):
            os.environ[key] = str(value)

    # Backfill older LLM unit-test fixtures that still require test.llm_providers.*
    primary_llm_base_url = (
        os.environ.get("CLOUD_DOG__EXPERT__LLM__BASE_URL")
        or os.environ.get("CLOUD_DOG__EXPERT__TEST__CONFIG_OVERRIDE_URL")
        or "https://llm.example.com"
    )
    primary_llm_model = os.environ.get("CLOUD_DOG__EXPERT__LLM__MODEL") or "qwen3:14b"
    llm_timeout_seconds = (
        os.environ.get("CLOUD_DOG__EXPERT__TEST__LLM_TIMEOUT_SECONDS")
        or os.environ.get("CLOUD_DOG__EXPERT__TEST__LLM_HTTP_TIMEOUT_SECONDS")
        or "300"
    )
    openai_model = os.environ.get("CLOUD_DOG__EXPERT__TEST__LLM__MODEL_SECONDARY") or "gpt-4"
    openrouter_model = (
        os.environ.get("CLOUD_DOG__EXPERT__TEST__LLM__MODEL_TERTIARY")
        or "anthropic/claude-3-opus"
    )
    fallback_llm_values = {
        "CLOUD_DOG__EXPERT__TEST__LLM_PROVIDERS__OLLAMA__BASE_URL": primary_llm_base_url,
        "CLOUD_DOG__EXPERT__TEST__LLM_PROVIDERS__OLLAMA__MODEL": primary_llm_model,
        "CLOUD_DOG__EXPERT__TEST__LLM_PROVIDERS__OPENAI__BASE_URL": "https://api.openai.com/v1",
        "CLOUD_DOG__EXPERT__TEST__LLM_PROVIDERS__OPENAI__MODEL": openai_model,
        "CLOUD_DOG__EXPERT__TEST__LLM_PROVIDERS__OPENAI__API_KEY": "test-openai-key",
        "CLOUD_DOG__EXPERT__TEST__LLM_PROVIDERS__OPENAI__TIMEOUT_SECONDS": "60",
        "CLOUD_DOG__EXPERT__TEST__LLM_PROVIDERS__OPENROUTER__MODEL": openrouter_model,
        "CLOUD_DOG__EXPERT__TEST__LLM_PROVIDERS__OPENROUTER__API_KEY": "test-openrouter-key",
        "CLOUD_DOG__EXPERT__TEST__LLM_PROVIDERS__CUSTOM_OPENAI__BASE_URL": "https://custom-api.example.com/v1",
        "CLOUD_DOG__EXPERT__TEST__LLM_PROVIDERS__CUSTOM_OPENAI__MODEL": "custom-model",
        "CLOUD_DOG__EXPERT__TEST__LLM_TIMEOUT_SECONDS": str(llm_timeout_seconds),
        "CLOUD_DOG__EXPERT__TEST__LLM_INVALID_BASE_URL": "invalid-url",
    }
    for key, value in fallback_llm_values.items():
        current_value = os.environ.get(key)
        if not current_value or _is_template_placeholder(str(current_value)):
            os.environ[key] = str(value)

    # Keep test API key in sync with active runtime key to prevent 401 drift
    # when shell-level Vault exports override secret files.
    active_api_key = os.environ.get("CLOUD_DOG__EXPERT__API_KEY")
    api_server_api_key = os.environ.get("CLOUD_DOG__EXPERT__API_SERVER__API_KEY")
    test_api_key = os.environ.get("TEST_API_KEY")
    expert_test_api_key = os.environ.get("CLOUD_DOG__EXPERT__TEST__API_KEY")
    chosen_api_key = None
    for candidate in (active_api_key, api_server_api_key, expert_test_api_key, test_api_key):
        if candidate and not _is_template_placeholder(str(candidate)):
            chosen_api_key = str(candidate)
            break
    if chosen_api_key:
        os.environ["TEST_API_KEY"] = chosen_api_key
        os.environ["CLOUD_DOG__EXPERT__TEST__API_KEY"] = chosen_api_key
        if (not active_api_key) or _is_template_placeholder(str(active_api_key)):
            os.environ["CLOUD_DOG__EXPERT__API_KEY"] = chosen_api_key

    # Some integration suites require legacy vector.store.type.
    if not os.environ.get("CLOUD_DOG__EXPERT__VECTOR__STORE__TYPE"):
        os.environ["CLOUD_DOG__EXPERT__VECTOR__STORE__TYPE"] = "chroma"

    # Preserve the selected env file for downstream config logic
    os.environ["CLOUD_DOG_ENV_FILES"] = str(env_path)
    os.environ["CLOUD_DOG__EXPERT__ENV_FILE"] = str(env_path)
    os.environ["CLOUD_DOG__EXPERT__TEST__ENV_FILE"] = str(env_path)

    project_root = Path(__file__).resolve().parent.parent
    _reset_sqlite_test_db_if_needed(project_root)

    load_config.cache_clear()
    # Rebind DB engine/session factories to the active --env database.
    # Collection-time imports can initialize DB early with stale shell env.
    from src.database.connection import init_db

    init_db(force_reinit=True)

    # Always release local ST/IT/AT stack at end of this pytest session.
    if _is_local_stack_env(env_path):
        request.addfinalizer(lambda: _run_server_control(env_path, "stop-all"))

    _ensure_local_server_stack(env_path)

    # Hard fail if critical config missing
    llm_provider = get_config("llm.provider")
    if not llm_provider:
        pytest.fail(
            f"llm.provider not configured. Check your --env file: {env_path}\n"
            "Configuration must be loaded via get_config() from src.config.loader.\n"
            "Ensure your env file contains CLOUD_DOG__EXPERT__LLM__PROVIDER"
        )

    llm_base_url = get_config("llm.base_url")
    if not llm_base_url:
        pytest.fail(f"llm.base_url not configured. Check your --env file: {env_path}")
    if "localhost:11434" in str(llm_base_url) or "127.0.0.1:11434" in str(llm_base_url):
        pytest.fail(f"llm.base_url points to local Ollama (localhost:11434): {llm_base_url}")

    # AT suites include browser login flows that require a valid test user.
    # Ensure configured credentials can authenticate before tests start.
    if env_path.name.startswith("env-AT"):
        api_host = get_config("api_server.host")
        api_port = get_config("api_server.port")
        api_key = get_config("test.api_key")
        username = get_config("test.user.username")
        email = get_config("test.user.email")
        password = get_config("test.user.password")
        display_name = get_config("test.user.display_name") or str(username or "Test User")
        timeout = float(get_config("test.http_timeout_seconds") or 60)

        if not api_host or api_port is None:
            pytest.fail("api_server.host/api_server.port not configured for AT env")
        if not api_key:
            pytest.fail("test.api_key not configured for AT env")
        if not username or not email or not password:
            pytest.fail(
                "test.user.username/test.user.email/test.user.password not configured for AT env"
            )

        base_url = f"http://{api_host}:{int(api_port)}"
        health = requests.get(f"{base_url}/health", timeout=timeout)
        if health.status_code != 200:
            pytest.fail(
                f"API health failed before AT user setup: {base_url}/health => {health.status_code}"
            )

        login_payload = {
            "username": str(username),
            "password": str(password),
            "expires_in_seconds": 120,
        }
        login = requests.post(f"{base_url}/auth/login", json=login_payload, timeout=timeout)
        if login.status_code != 200:
            create = requests.post(
                f"{base_url}/users",
                headers={"X-API-Key": str(api_key)},
                json={
                    "username": str(username),
                    "email": str(email),
                    "password": str(password),
                    "display_name": str(display_name),
                    "role": "admin",
                    "enabled": True,
                },
                timeout=timeout,
            )
            if create.status_code != 200:
                token = uuid.uuid4().hex[:8]
                domain = str(email).split("@", 1)[1] if "@" in str(email) else "example.com"
                username = f"{str(username)}_{token}"
                email = f"{str(username)}@{domain}"
                os.environ["CLOUD_DOG__EXPERT__TEST__USER__USERNAME"] = username
                os.environ["CLOUD_DOG__EXPERT__TEST__USER__EMAIL"] = email
                os.environ["TEST_USER_USERNAME"] = username
                os.environ["TEST_USER_EMAIL"] = email
                load_config.cache_clear()
                login_payload = {
                    "username": username,
                    "password": str(password),
                    "expires_in_seconds": 120,
                }
                create = requests.post(
                    f"{base_url}/users",
                    headers={"X-API-Key": str(api_key)},
                    json={
                        "username": username,
                        "email": email,
                        "password": str(password),
                        "display_name": str(display_name),
                        "role": "admin",
                        "enabled": True,
                    },
                    timeout=timeout,
                )
                if create.status_code != 200:
                    pytest.fail(
                        f"Failed to seed AT login user: /users => {create.status_code} {create.text}"
                    )

            relogin = requests.post(f"{base_url}/auth/login", json=login_payload, timeout=timeout)
            if relogin.status_code != 200:
                pytest.fail(
                    f"AT login user not usable: /auth/login => {relogin.status_code} {relogin.text}"
                )

        # AT Web UI suites require admin panel access; enforce admin role for
        # the configured login principal to keep browser CRUD flows stable.
        users_resp = requests.get(
            f"{base_url}/users",
            headers={"X-API-Key": str(api_key)},
            timeout=timeout,
        )
        if users_resp.status_code != 200:
            pytest.fail(
                f"Failed to read users for AT role check: /users => {users_resp.status_code} {users_resp.text}"
            )

        login_username = str(login_payload.get("username", "")).strip().lower()
        login_email = str(email).strip().lower()
        matched_user = None
        for item in users_resp.json().get("users", []):
            if (
                str(item.get("username", "")).strip().lower() == login_username
                or str(item.get("email", "")).strip().lower() == login_email
            ):
                matched_user = item
                break

        if matched_user is None:
            pytest.fail("AT login principal missing from /users after setup")

        if str(matched_user.get("role", "")).strip().lower() != "admin" or not bool(
            matched_user.get("enabled", True)
        ):
            promote = requests.put(
                f"{base_url}/users/{int(matched_user['id'])}",
                headers={"X-API-Key": str(api_key)},
                json={"role": "admin", "enabled": True},
                timeout=timeout,
            )
            if promote.status_code != 200:
                pytest.fail(
                    f"Failed to promote AT login user to admin: /users/{matched_user['id']} => {promote.status_code} {promote.text}"
                )

    return env_path


@pytest.fixture(scope="session")
def baseline_test_environment(test_env_file):
    """
    Snapshot of the environment after loading --env.

    Used to restore a consistent baseline between tests without wiping the
    configuration loaded from the required env file.
    """
    return os.environ.copy()


@pytest.fixture(autouse=True)
def apply_db_uri_overrides_for_dialect_db_tests(request, test_env_file):
    """
    IT2.35/IT2.36 and ST1.43/ST1.44 validate concrete DB dialect URIs.

    The shared docker IT env is sqlite-based, so for these specific suites we
    temporarily override CLOUD_DOG__EXPERT__DB__URI from dialect-specific
    secret files.
    """
    node_id = str(request.node.nodeid)
    secret_file = None
    if "IT2.35_MariaDBIntegration" in node_id or "ST1.43_MariaDBReadiness" in node_id:
        secret_file = Path("private/env-test-mariadb-secrets")
    elif "IT2.36_PostgreSQLIntegration" in node_id or "ST1.44_PostgreSQLReadiness" in node_id:
        secret_file = Path("private/env-test-postgres-secrets")

    if secret_file is None:
        yield
        return

    key = "CLOUD_DOG__EXPERT__DB__URI"
    previous = os.environ.get(key)
    loaded = _read_env_kv(secret_file)
    uri = loaded.get(key)
    if not uri:
        pytest.fail(f"{key} missing from {secret_file}")

    os.environ[key] = uri
    from src.config.loader import load_config

    load_config.cache_clear()

    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous
        load_config.cache_clear()


@pytest.fixture(autouse=True)
def ensure_default_login_user_for_ui_integration(request, test_env_file):
    """
    IT2.17/IT2.21/IT2.22 sign into Web UI with test.user.* credentials.

    Ensure that login user exists before browser flow starts.
    """
    node_id = str(request.node.nodeid)
    if (
        "IT2.17_WebUICompleteCoverage" not in node_id
        and
        "IT2.21_WebUIChannelManagement" not in node_id
        and "IT2.22_WebUITestingInterface" not in node_id
    ):
        yield
        return

    from src.config.loader import get_config, load_config

    load_config.cache_clear()

    api_host = get_config("api_server.host")
    api_port = get_config("api_server.port")
    api_key = get_config("test.api_key")
    username = get_config("test.user.username")
    email = get_config("test.user.email")
    password = get_config("test.user.password")
    display_name = get_config("test.user.display_name") or str(username)
    timeout = float(get_config("test.http_timeout_seconds") or 60)

    api_base_url_cfg = get_config("api_server.base_url")
    if not api_base_url_cfg:
        if not api_host or api_port is None:
            pytest.fail("api_server.host/api_server.port not configured for UI integration tests")
    if not username or not email or not password:
        pytest.fail("test.user.username/test.user.email/test.user.password not configured")
    if not api_key:
        pytest.fail("test.api_key not configured")

    base_url = str(api_base_url_cfg).rstrip("/") if api_base_url_cfg else f"http://{api_host}:{int(api_port)}"
    health = requests.get(f"{base_url}/health", timeout=timeout)
    if health.status_code != 200:
        pytest.fail(f"API health failed before UI setup: {base_url}/health => {health.status_code}")

    login_payload = {
        "username": str(username),
        "password": str(password),
        "expires_in_seconds": 120,
    }
    login = requests.post(f"{base_url}/auth/login", json=login_payload, timeout=timeout)
    if login.status_code != 200:
        create = requests.post(
            f"{base_url}/users",
            headers={"X-API-Key": str(api_key)},
            json={
                "username": str(username),
                "email": str(email),
                "password": str(password),
                "display_name": str(display_name),
                "enabled": True,
            },
            timeout=timeout,
        )
        if create.status_code != 200:
            # Existing DBs can carry stale test users with unknown passwords.
            # Move this run to a unique login principal to make UI auth deterministic.
            token = uuid.uuid4().hex[:8]
            domain = str(email).split("@", 1)[1] if "@" in str(email) else "example.com"
            username = f"{str(username)}_{token}"
            email = f"{str(username)}@{domain}"
            os.environ["CLOUD_DOG__EXPERT__TEST__USER__USERNAME"] = username
            os.environ["CLOUD_DOG__EXPERT__TEST__USER__EMAIL"] = email
            os.environ["TEST_USER_USERNAME"] = username
            os.environ["TEST_USER_EMAIL"] = email
            load_config.cache_clear()

            login_payload = {
                "username": username,
                "password": str(password),
                "expires_in_seconds": 120,
            }
            create = requests.post(
                f"{base_url}/users",
                headers={"X-API-Key": str(api_key)},
                json={
                    "username": username,
                    "email": email,
                    "password": str(password),
                    "display_name": str(display_name),
                    "enabled": True,
                },
                timeout=timeout,
            )
            if create.status_code != 200:
                pytest.fail(
                    f"Failed to seed alternate UI login user: /users => {create.status_code} {create.text}"
                )

        relogin = requests.post(f"{base_url}/auth/login", json=login_payload, timeout=timeout)
        if relogin.status_code != 200:
            pytest.fail(
                f"UI login user not usable: /auth/login => {relogin.status_code} {relogin.text}"
            )

    users_resp = requests.get(
        f"{base_url}/users",
        headers={"X-API-Key": str(api_key)},
        timeout=timeout,
    )
    if users_resp.status_code != 200:
        pytest.fail(
            f"Failed to read users for UI role check: /users => {users_resp.status_code} {users_resp.text}"
        )

    login_username = str(username).strip().lower()
    login_email = str(email).strip().lower()
    matched_user = None
    for item in users_resp.json().get("users", []):
        if (
            str(item.get("username", "")).strip().lower() == login_username
            or str(item.get("email", "")).strip().lower() == login_email
        ):
            matched_user = item
            break

    if matched_user is None:
        pytest.fail("UI login principal missing from /users after setup")

    if str(matched_user.get("role", "")).strip().lower() != "admin" or not bool(
        matched_user.get("enabled", True)
    ):
        promote = requests.put(
            f"{base_url}/users/{int(matched_user['id'])}",
            headers={"X-API-Key": str(api_key)},
            json={"role": "admin", "enabled": True},
            timeout=timeout,
        )
        if promote.status_code != 200:
            pytest.fail(
                f"Failed to promote UI login user to admin: /users/{matched_user['id']} => {promote.status_code} {promote.text}"
            )

    yield


@pytest.fixture(autouse=True)
def tune_it220_async_chat_runtime(request, test_env_file):
    """
    Keep IT2.20 async job completion within polling budget.

    Without a cap, some LLM responses run long enough to exceed the test's
    20s polling window and leave the job in "processing".
    """
    node_id = str(request.node.nodeid)
    if "IT2.20_ChannelRESTAsyncSync" not in node_id:
        yield
        return

    key = "CLOUD_DOG__EXPERT__LLM__MAX_TOKENS"
    previous = os.environ.get(key)
    os.environ[key] = "256"
    from src.config.loader import load_config

    load_config.cache_clear()
    try:
        yield
    finally:
        if previous is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = previous
        load_config.cache_clear()


@pytest.fixture(autouse=True)
def normalize_placeholder_llm_test_values():
    """
    Replace placeholder token config values from env-test with usable numeric defaults.

    Several AT fixtures cast config values with raw int(...). The env baseline still
    contains placeholder strings like "changeme", which are configuration placeholders,
    not meaningful runtime values.
    """
    overrides = {
        "CLOUD_DOG__EXPERT__LLM__MAX_TOKENS": "1024",
        "CLOUD_DOG__EXPERT__TEST__LLM__UPDATE_MAX_TOKENS": "512",
        "CLOUD_DOG__EXPERT__TEST__AT1_10__SUMMARIZATION__MAX_TOKENS": "256",
        "CLOUD_DOG__EXPERT__TEST__AT1_12__SCENARIO_1__MAX_TOKENS": "256",
        "CLOUD_DOG__EXPERT__TEST__AT1_12__SCENARIO_2__MAX_TOKENS": "256",
        "CLOUD_DOG__EXPERT__TEST__AT1_12__SCENARIO_3__MAX_TOKENS": "256",
        "CLOUD_DOG__EXPERT__TEST__AT1_12__SCENARIO_4__MAX_TOKENS": "256",
        "CLOUD_DOG__EXPERT__TEST__USER__PASSWORD_NEW": "TestSecretValue2!",
        "TEST_USER_PASSWORD_NEW": "TestSecretValue2!",
        "CLOUD_DOG__EXPERT__TEST__USER__PASSWORD_RESET": "TestSecretValue3!",
        "TEST_USER_PASSWORD_RESET": "TestSecretValue3!",
        "CLOUD_DOG__EXPERT__TEST__USER__PASSWORD_WEAK": "short",
        "TEST_USER_PASSWORD_WEAK": "short",
    }
    previous: dict[str, str | None] = {}
    changed = False

    for key, fallback in overrides.items():
        current = os.environ.get(key)
        if current is not None and str(current).strip().lower() not in {"", "changeme", "none", "null"}:
            continue
        previous[key] = current
        os.environ[key] = fallback
        changed = True

    if changed:
        from src.config.loader import load_config

        load_config.cache_clear()
    try:
        yield
    finally:
        if changed:
            for key, original in previous.items():
                if original is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = original
            from src.config.loader import load_config

            load_config.cache_clear()


@pytest.fixture(scope="session")
def test_secrets_file(request, test_env_file):
    """Load secrets file corresponding to env file.

    Tries:
    1. {env_file}-secrets (e.g., env-test-qdrant-secrets)
    2. env-test-secrets (fallback for shared secrets)
    """
    env_file = request.config.getoption("--env")
    if env_file is None:
        return None
    env_path = _resolve_env_path(str(env_file))
    env_specific = Path(f"{str(env_path)}-secrets")
    if env_specific.exists():
        return env_specific

    shared = Path("private/env-test-secrets")
    if shared.exists():
        return shared

    return env_specific


@pytest.fixture
def test_config(test_env_file, test_secrets_file):
    """Load test configuration from env files."""
    from src.config.loader import load_config

    load_config.cache_clear()
    return load_config()


@pytest.fixture
def test_logger():
    """Create a test logger."""
    from src.utils.logger import get_logger

    return get_logger("test", pii_redaction=False)


@pytest.fixture
def webhook_receiver(test_config):
    """Start a local webhook receiver for async callback tests."""
    from src.config.loader import get_config
    from tests.fixtures.webhook_receiver import WebhookReceiver

    host = get_config("test.webhook_host")
    port = get_config("test.webhook_port")
    secret = get_config("test.webhook_secret")
    signature_header = get_config("test.webhook_signature_header")
    signature_prefix = get_config("test.webhook_signature_prefix")

    missing = [
        name
        for name, value in (
            ("test.webhook_host", host),
            ("test.webhook_port", port),
            ("test.webhook_secret", secret),
            ("test.webhook_signature_header", signature_header),
            ("test.webhook_signature_prefix", signature_prefix),
        )
        if value in (None, "")
    ]
    if missing:
        pytest.fail(f"Webhook receiver config missing: {', '.join(missing)}")

    receiver = WebhookReceiver(
        host=str(host),
        port=int(port),
        secret=str(secret),
        signature_header=str(signature_header),
        signature_prefix=str(signature_prefix),
    )
    receiver.start()
    try:
        yield receiver
    finally:
        receiver.stop()


@pytest.fixture(autouse=True)
def reset_environment(request, baseline_test_environment):
    """Reset environment variables between tests and provide visibility."""
    from src.config.loader import get_config

    verbose = bool(get_config("test.verbose"))
    test_name = request.node.name if hasattr(request, "node") else "unknown"
    if verbose:
        print(f"\n[TEST START] {test_name}", flush=True)

    yield

    if verbose:
        print(f"[TEST END] {test_name}", flush=True)

    # Restore baseline env loaded from --env
    os.environ.clear()
    os.environ.update(baseline_test_environment)


@pytest.fixture(autouse=True)
def check_required_config(request, test_env_file):
    """Check required configuration is available based on test markers."""
    markers = [m.name for m in request.node.iter_markers()]

    required = []
    missing = []

    # Integration/Application tests need real services
    if "integration" in markers or "application" in markers:
        from src.config.loader import get_config

        if not get_config("llm.base_url"):
            required.append("LLM_BASE_URL")
        if not get_config("db.uri"):
            required.append("DB_URI")

    # Vector store tests need vector store config
    if "vector_store" in markers or "integration" in markers:
        from src.config.loader import get_config

        if not get_config("vector.store.type"):
            required.append("VECTOR_STORE_TYPE")

    # Check each required item
    for item in required:
        from src.config.loader import get_config

        if item == "LLM_BASE_URL" and not get_config("llm.base_url"):
            missing.append("LLM_BASE_URL (llm.base_url)")
        elif item == "DB_URI" and not get_config("db.uri"):
            missing.append("DB_URI (db.uri)")
        elif item == "VECTOR_STORE_TYPE" and not get_config("vector.store.type"):
            missing.append("VECTOR_STORE_TYPE (vector.store.type)")

    if missing:
        pytest.fail(f"Required configuration missing: {', '.join(missing)}. Check your --env file.")


@pytest.fixture
def check_llm_available(test_config):
    """Check LLM service is available."""
    base_url = test_config.get("llm", {}).get("base_url")
    if not base_url:
        pytest.fail("LLM base URL not configured")

    # Optional: Try to connect and verify
    # For now, just check configuration exists
    return base_url


@pytest.fixture
def check_vector_store_available(test_config):
    """Check vector store is available."""
    from src.config.loader import get_config

    store_type = get_config("vector.store.type")
    if not store_type:
        pytest.fail("Vector store type not configured")

    # Check specific store configuration
    if store_type == "weaviate":
        weaviate_url = get_config("vector.stores.weaviate.default.url")
        weaviate_host = get_config("vector.stores.weaviate.default.host")
        if not weaviate_url and not weaviate_host:
            pytest.fail("Weaviate URL or host not configured")

    return store_type


@pytest.fixture
def check_weaviate_available(test_config):
    """Check Weaviate service configuration is available."""
    from src.config.loader import get_config

    weaviate_url = get_config("vector.stores.weaviate.default.url")
    weaviate_host = get_config("vector.stores.weaviate.default.host")
    weaviate_port = get_config("vector.stores.weaviate.default.port")

    if not weaviate_url and not weaviate_host:
        pytest.fail(
            "Weaviate configuration not found. Set CLOUD_DOG__EXPERT__VECTOR__STORES__WEAVIATE__DEFAULT__URL or HOST"
        )

    if not weaviate_url and weaviate_port is None:
        pytest.fail("Weaviate port not configured")

    return {
        "url": weaviate_url or f"http://{weaviate_host}:{int(weaviate_port)}",
        "api_key": get_config("vector.stores.weaviate.default.api_key"),
        "collection_name": get_config("vector.stores.weaviate.default.collection_name"),
    }


@pytest.fixture
def check_redis_available(test_config):
    """Check Redis is available."""
    host = test_config.get("redis", {}).get("host")
    if not host:
        pytest.fail("Redis host not configured")

    return host


@pytest.fixture
def db_session(test_config):
    """Create a database session for testing."""
    from src.database.connection import init_db, get_db, get_engine
    from src.database.models import Base
    import os
    import tempfile
    from pathlib import Path

    # Isolate in-process DB tests from any running servers by using a per-test sqlite DB.
    # This avoids clobbering the API server DB during System/Application tests.
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
    tmp_path = Path(tmp.name)
    tmp.close()
    db_uri = f"sqlite:///{tmp_path}"

    # Preserve any DB URI already loaded from --env (so we can restore it)
    previous_db_uri = os.environ.get("CLOUD_DOG__EXPERT__DB__URI")
    os.environ["CLOUD_DOG__EXPERT__DB__URI"] = db_uri

    # Clear config cache
    from src.config.loader import load_config

    load_config.cache_clear()

    # Initialize database
    init_db(force_reinit=True)
    engine = get_engine()

    # Drop all tables and recreate to ensure latest schema (AT1.11: includes session_key, history_key, summaries)
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)

    # Get session
    db_gen = get_db()
    db = next(db_gen)

    try:
        yield db
    finally:
        db.rollback()
        db.close()
        # Clean up: delete the temp sqlite file (no need to drop tables, and
        # importantly we must never risk touching the server DB).
        if previous_db_uri is None:
            os.environ.pop("CLOUD_DOG__EXPERT__DB__URI", None)
        else:
            os.environ["CLOUD_DOG__EXPERT__DB__URI"] = previous_db_uri
        load_config.cache_clear()
        # Rebind global engine/session factories back to the restored env DB.
        # Without this, later tests can keep using the per-test temp DB engine.
        init_db(force_reinit=True)
        try:
            tmp_path.unlink(missing_ok=True)
        except Exception:
            pass


@pytest.fixture
def mock_dns_resolution(monkeypatch, request):
    """Mock DNS resolution for external services (optional, only if explicitly requested)."""
    # Only apply if test explicitly requests it via marker
    if "mock_dns" not in [m.name for m in request.node.iter_markers()]:
        return

    import socket

    # Store original getaddrinfo
    original_getaddrinfo = socket.getaddrinfo

    def mock_getaddrinfo(host, port, *args, **kwargs):
        """Mock DNS resolution for test hosts."""
        # Map test hostnames to localhost (only for unit tests that need it)
        test_hosts = {
            "llm.example.com": "127.0.0.1",
            "vdb.example.com": "127.0.0.1",
            "valkey.example.com": "127.0.0.1",
            "test-llm.example.com": "127.0.0.1",
            "test-qdrant.example.com": "127.0.0.1",
            "test-redis.example.com": "127.0.0.1",
        }

        # If host is in test hosts, resolve to localhost
        if host in test_hosts:
            return original_getaddrinfo("127.0.0.1", port, *args, **kwargs)

        # Otherwise use original resolution
        return original_getaddrinfo(host, port, *args, **kwargs)

    monkeypatch.setattr(socket, "getaddrinfo", mock_getaddrinfo)


# --- PS-REQ-TEST-TRACE marker enforcement (added by rtt-2026-06-12 Instruction 3 uplift) ---
# See PS-REQ-TEST-TRACE v1.0 §6.2 — fails session if any test lacks tier + surface + req()/probe markers.

import sys

_PS_REQ_TIER_MARKERS = {"QT", "UT", "ST", "IT", "AT"}
_PS_REQ_SURFACE_MARKERS = {"api", "mcp", "a2a", "webui", "cli", "internal"}

# Canonical marker definitions per PS-REQ-TEST-TRACE §6 + W28C-1715 compliance.
# Belt-and-suspenders alongside pytest.ini markers = declarations are idempotent.
_CANONICAL_MARKERS = [
    # Tier markers (UPPER-CASE per PS-REQ-TEST-TRACE §6.1)
    "QT: quality-gate tier (static analysis, linting, package compliance)",
    "UT: unit-test tier (pure in-process, no external deps)",
    "ST: system-test tier (one running service, no downstream deps)",
    "IT: integration-test tier (two or more services wired together)",
    "AT: application-test tier (full stack, real browser / end-to-end)",
    # Surface markers (lower-case per PS-REQ-TEST-TRACE §6.1)
    "api: exercises the HTTP API surface",
    "mcp: exercises the MCP JSON-RPC surface",
    "a2a: exercises the A2A agent-to-agent surface",
    "webui: exercises the browser WebUI surface via Playwright",
    "cli: exercises CLI / in-process / internal-only surface",
    "internal: exercises internal library / helper logic",
    # Semantic markers
    "req(*ids): binds test to one or more requirement IDs (FR-NNN / CS-NNN / NF-NNN)",
    "probe: orphan test — not yet bound to a requirement; must be listed in probe-retention-register.tsv",
    "negative: test asserts a denied / error / rejection outcome",
    # Non-functional / environment markers
    "slow: test takes 10-120 seconds",
    "heavy: test takes >120 seconds",
    "llm: requires live LLM endpoint (Ollama / OpenRouter)",
    "vdb: requires vector database (Chroma / Qdrant / OpenSearch)",
    "db: requires relational database (MySQL / PostgreSQL)",
    "smtp: requires SMTP/IMAP service",
    "docker: requires Docker build/run capability",
]


def pytest_configure(config):
    """Register all canonical PS-REQ-TEST-TRACE markers (W28C-1715 compliance)."""
    for marker_def in _CANONICAL_MARKERS:
        config.addinivalue_line("markers", marker_def)


def pytest_collection_modifyitems(config, items):
    """PS-REQ-TEST-TRACE marker enforcement."""
    failures = []
    for item in items:
        marker_names = {m.name for m in item.iter_markers()}
        is_probe = "probe" in marker_names
        if not (marker_names & _PS_REQ_TIER_MARKERS):
            failures.append(f"{item.nodeid}: missing @pytest.mark.<tier> per PS-REQ-TEST-TRACE §6")
        if not (marker_names & _PS_REQ_SURFACE_MARKERS):
            failures.append(f"{item.nodeid}: missing @pytest.mark.<surface> per PS-REQ-TEST-TRACE §6")
        if not is_probe:
            req_marker = item.get_closest_marker("req")
            if req_marker is None or not req_marker.args:
                failures.append(
                    f"{item.nodeid}: missing @pytest.mark.req('FR-NNN') per PS-REQ-TEST-TRACE §6 "
                    "(or mark the test with the probe marker to flag it as an orphan)"
                )
    if failures:
        msg = "PS-REQ-TEST-TRACE marker enforcement failed for " + str(len(failures)) + " test(s):\n  " + "\n  ".join(failures[:20])
        if len(failures) > 20:
            msg += f"\n  ... and {len(failures) - 20} more"
        print(msg, file=sys.stderr)
        import pytest
        pytest.exit(msg, returncode=2)
