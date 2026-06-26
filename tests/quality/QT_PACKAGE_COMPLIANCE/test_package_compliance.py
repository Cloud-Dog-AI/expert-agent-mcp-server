"""
Automated package compliance test.
This test FAILS if any bespoke code exists that should use a platform package.
It runs as part of QT - every CI/test run enforces compliance automatically.

[TEST:QT1.99]
[REQ:SV-1.3]
"""

from __future__ import annotations

import ast
import pathlib
import subprocess

import pytest

PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[3]
SRC_DIR = PROJECT_ROOT / "src"


def _grep_count(pattern: str, exclude_pattern: str | None = None) -> list[str]:
    """Grep src/ for a pattern, return matching file:line entries."""
    cmd = f"grep -rnE '{pattern}' {SRC_DIR} --include='*.py'"
    if exclude_pattern:
        cmd += f" | grep -v '{exclude_pattern}'"
    cmd += " | grep -v __pycache__"
    result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=False)
    return [line for line in result.stdout.strip().split("\n") if line]


def _resolve_module_path(module_name: str) -> pathlib.Path | None:
    if not module_name.startswith("src."):
        return None

    rel_path = pathlib.Path(*module_name.split("."))
    candidates = [
        PROJECT_ROOT / f"{rel_path}.py",
        PROJECT_ROOT / rel_path / "__init__.py",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _module_tree_uses_cloud_dog_idam(module_path: pathlib.Path, seen: set[pathlib.Path] | None = None) -> bool:
    if seen is None:
        seen = set()
    if module_path in seen or not module_path.exists():
        return False

    seen.add(module_path)
    content = module_path.read_text(encoding="utf-8", errors="ignore")
    if "cloud_dog_idam" in content:
        return True

    try:
        tree = ast.parse(content)
    except SyntaxError:
        return False

    for node in ast.walk(tree):
        module_name = None
        if isinstance(node, ast.ImportFrom):
            module_name = node.module
        elif isinstance(node, ast.Import) and node.names:
            module_name = node.names[0].name
        if not module_name:
            continue
        target_path = _resolve_module_path(module_name)
        if target_path and _module_tree_uses_cloud_dog_idam(target_path, seen):
            return True
    return False


def _is_relevant_auth_import(module_name: str, imported_names: list[str]) -> bool:
    module_name = module_name or ""
    auth_symbols = {
        "verify_api_key",
        "verify_admin",
        "get_current_user",
        "APIKeyAuth",
        "TokenManager",
        "APIKeyManager",
        "hash_password",
        "verify_password",
        "validate_password_policy",
    }
    auth_modules = {
        "src.servers.api.auth",
        "src.core.security.auth_middleware",
        "src.core.auth.password",
        "src.core.auth.token",
        "src.core.auth.api_key_manager",
        "src.core.auth.user_manager",
    }
    if module_name in auth_modules:
        return True
    if any(name in auth_symbols for name in imported_names):
        return True
    return False


def _auth_hits_not_delegating() -> list[str]:
    hits: list[str] = []
    for path in sorted(SRC_DIR.rglob("*.py")):
        content = path.read_text(encoding="utf-8", errors="ignore")
        try:
            tree = ast.parse(content)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            module_name = ""
            imported_names: list[str] = []
            if isinstance(node, ast.ImportFrom):
                module_name = node.module or ""
                imported_names = [alias.name for alias in node.names]
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    module_name = alias.name
                    imported_names = [alias.asname or alias.name.split(".")[-1]]
                    if module_name.startswith("src.") and _is_relevant_auth_import(module_name, imported_names):
                        target_path = _resolve_module_path(module_name)
                        if target_path and _module_tree_uses_cloud_dog_idam(target_path):
                            continue
                        line = content.splitlines()[node.lineno - 1].strip()
                        hits.append(f"{path}:{node.lineno}:{line}")
                continue
            else:
                continue

            if not module_name.startswith("src."):
                continue
            if not _is_relevant_auth_import(module_name, imported_names):
                continue
            target_path = _resolve_module_path(module_name)
            if target_path and _module_tree_uses_cloud_dog_idam(target_path):
                continue
            line = content.splitlines()[node.lineno - 1].strip()
            hits.append(f"{path}:{node.lineno}:{line}")
    return hits


class TestPackageCompliance:
    """Every test here MUST pass. Zero bespoke code allowed."""
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("FR-042")

    def test_no_bespoke_logging(self):
        """All logging must use cloud_dog_logging. Zero logging.getLogger calls."""
        hits = _grep_count(r"logging\.getLogger", "cloud_dog")
        assert len(hits) == 0, (
            f"FAIL: {len(hits)} bespoke logging calls found. "
            f"Replace with cloud_dog_logging:\n" + "\n".join(hits[:10])
        )
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("FR-042")

    def test_no_bespoke_config_manager(self):
        """Config must use cloud_dog_config. Zero bespoke ConfigManager."""
        hits = _grep_count(r"ConfigManager|config_manager", "cloud_dog")
        real_hits = [h for h in hits if "cloud_dog_config" not in h]
        assert len(real_hits) == 0, (
            f"FAIL: {len(real_hits)} bespoke config calls found:\n" + "\n".join(real_hits[:10])
        )
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("FR-042")

    def test_no_bespoke_auth(self):
        """Auth must use cloud_dog_idam. Zero bespoke auth imports outside the package."""
        real_hits = _auth_hits_not_delegating()
        assert len(real_hits) == 0, (
            "FAIL: "
            f"{len(real_hits)} bespoke auth imports not delegating to cloud_dog_idam:\n"
            + "\n".join(real_hits[:10])
        )
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("FR-042")

    def test_no_memory_queue(self):
        """Jobs must use cloud_dog_jobs. Zero MemoryQueue/ThreadPoolExecutor."""
        hits = _grep_count(r"MemoryQueue|ThreadPoolExecutor|asyncio\.Queue", "cloud_dog")
        assert len(hits) == 0, (
            f"FAIL: {len(hits)} bespoke queue/thread calls found:\n" + "\n".join(hits[:10])
        )
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("FR-042")

    def test_no_direct_llm_calls(self):
        """LLM calls must use cloud_dog_llm. Zero direct httpx to ollama/openai."""
        hits = _grep_count(
            r"httpx\.AsyncClient.*ollama|requests\.post.*ollama|openai\.ChatCompletion",
            "cloud_dog",
        )
        assert len(hits) == 0, (
            f"FAIL: {len(hits)} direct LLM calls found:\n" + "\n".join(hits[:10])
        )
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("FR-042")

    def test_no_hardcoded_secrets(self):
        """Zero hardcoded passwords or secrets in source."""
        hits = _grep_count(r"password.*=.*['\"]|secret.*=.*['\"]|api_key.*=.*['\"]")
        real_hits = [
            h
            for h in hits
            if not any(
                x in h.lower()
                for x in ["test", "example", "placeholder", "changeme", "12345", "os.environ", "config.get"]
            )
        ]
        assert len(real_hits) == 0, (
            f"FAIL: {len(real_hits)} hardcoded secrets found:\n" + "\n".join(real_hits[:10])
        )
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("FR-042")

    def test_no_internal_hostnames(self):
        """Zero internal hostnames in source (must use config/vault)."""
        hits = _grep_count(r"cloud-dog\.net|viewdeck\.com|vault0\.|server0\.|db1\.app")
        real_hits = [
            h
            for h in hits
            if not any(x in h for x in ["#", '"""', "vault.", "test", "PREPROD", "example", "docs/"])
        ]
        assert len(real_hits) == 0, (
            f"FAIL: {len(real_hits)} internal hostnames in source:\n" + "\n".join(real_hits[:10])
        )
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("FR-042")

    def test_ui_dist_exists(self):
        """PS-30: ui/dist/ must exist (SPA built and wired)."""
        ui_dist = PROJECT_ROOT / "ui" / "dist"
        if not (PROJECT_ROOT / "src" / "servers" / "web").exists():
            pytest.skip("No web server - UI not applicable")
        assert ui_dist.exists(), "FAIL: ui/dist/ not found. SPA must be built."
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("FR-042")

    def test_runtime_config_endpoint(self):
        """PS-30: /runtime-config.js must be served by the web server."""
        web_files = list(SRC_DIR.rglob("*.py"))
        has_runtime_config = any(
            "runtime-config" in f.read_text(encoding="utf-8", errors="ignore")
            or "runtime_config" in f.read_text(encoding="utf-8", errors="ignore")
            for f in web_files
            if f.stat().st_size < 100000
        )
        if not (PROJECT_ROOT / "src" / "servers" / "web").exists():
            pytest.skip("No web server - runtime-config not applicable")
        assert has_runtime_config, "FAIL: No /runtime-config.js endpoint found in web server."
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("FR-042")

    def test_server_control_exists(self):
        """server_control.sh must exist."""
        assert (PROJECT_ROOT / "server_control.sh").exists(), "FAIL: server_control.sh missing."
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("FR-042")

    def test_licence_exists(self):
        """LICENCE file must exist."""
        assert (PROJECT_ROOT / "LICENCE").exists(), "FAIL: LICENCE file missing."
    @pytest.mark.QT
    @pytest.mark.mcp
    @pytest.mark.req("FR-042")

    def test_readme_exists(self):
        """README.md must exist."""
        assert (PROJECT_ROOT / "README.md").exists(), "FAIL: README.md missing."
