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

"""W25A rules-compliance static checks (RC-01..RC-10 subset)."""

from __future__ import annotations
import pytest

import ast
import re
from pathlib import Path
from typing import Dict, List, Tuple

URL_PATTERN = re.compile(r"http://|https://|\blocalhost\b|127\.0\.0\.1")
CREDENTIAL_PATTERN = re.compile(
    r"\b(password|token|api_key|secret)\s*=\s*([\"\'])[^\"\']+\2",
    re.IGNORECASE,
)


def _read_lines(path: Path) -> List[str]:
    return path.read_text(encoding="utf-8", errors="ignore").splitlines()


def _is_python_comment(line: str) -> bool:
    return line.strip().startswith("#")


def _rel(path: Path, project_root: Path) -> str:
    return str(path.relative_to(project_root))


def _format_violations(violations: List[Tuple[str, int, str]]) -> str:
    return "\n".join(f"- {f}:{ln}: {msg}" for f, ln, msg in violations)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-004")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_no_hardcoded_urls(project_root, src_python_files, allowlist):
    violations: List[Tuple[str, int, str]] = []

    for file_path in src_python_files:
        rel = _rel(file_path, project_root)
        if rel in allowlist["hardcoded_url_paths"]:
            continue
        for idx, line in enumerate(_read_lines(file_path), start=1):
            if _is_python_comment(line):
                continue
            if URL_PATTERN.search(line):
                violations.append((rel, idx, "hardcoded URL/host token"))

    assert not violations, "Hardcoded URL violations:\n" + _format_violations(violations)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-004")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_no_hardcoded_credentials(project_root, src_python_files):
    violations: List[Tuple[str, int, str]] = []

    for file_path in src_python_files:
        rel = _rel(file_path, project_root)
        for idx, line in enumerate(_read_lines(file_path), start=1):
            if _is_python_comment(line):
                continue
            if CREDENTIAL_PATTERN.search(line):
                violations.append((rel, idx, "hardcoded credential-like assignment"))

    assert not violations, "Hardcoded credential violations:\n" + _format_violations(violations)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-004")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_no_direct_external_imports(project_root, src_python_files, allowlist):
    """Each forbidden direct external library should be routed via one adapter module."""

    target_libs = {
        "requests",
        "httpx",
        "smtplib",
        "chromadb",
        "openai",
        "ollama",
        "qdrant_client",
        "weaviate",
        "elasticsearch",
        "opensearchpy",
    }
    import_map: Dict[str, set[str]] = {name: set() for name in target_libs}

    for file_path in src_python_files:
        rel = _rel(file_path, project_root)
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    lib = alias.name.split(".")[0]
                    if lib in target_libs:
                        import_map[lib].add(rel)
            elif isinstance(node, ast.ImportFrom):
                lib = (node.module or "").split(".")[0]
                if lib in target_libs:
                    import_map[lib].add(rel)

    violations = []
    for lib, paths in sorted(import_map.items()):
        if len(paths) > 1 and lib not in allowlist["external_import_multi_module_libs"]:
            violations.append(f"{lib}: {sorted(paths)}")

    assert not violations, "External import fan-out violations:\n- " + "\n- ".join(violations)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-004")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_no_pytest_skip_in_it_at(project_root):
    violations: List[Tuple[str, int, str]] = []
    for test_dir in [
        project_root / "tests" / "integration",
        project_root / "tests" / "application",
    ]:
        for file_path in sorted(test_dir.rglob("*.py")):
            rel = _rel(file_path, project_root)
            for idx, line in enumerate(_read_lines(file_path), start=1):
                if "pytest.skip(" in line:
                    violations.append((rel, idx, "pytest.skip forbidden in IT/AT"))

    assert not violations, "pytest.skip violations:\n" + _format_violations(violations)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-004")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_no_mock_in_it_at(project_root):
    violations: List[Tuple[str, int, str]] = []
    token_re = re.compile(r"MagicMock|MockTransport|local_mode\s*=\s*True")

    for test_dir in [
        project_root / "tests" / "integration",
        project_root / "tests" / "application",
    ]:
        for file_path in sorted(test_dir.rglob("*.py")):
            rel = _rel(file_path, project_root)
            for idx, line in enumerate(_read_lines(file_path), start=1):
                if token_re.search(line):
                    violations.append((rel, idx, "mock/local_mode usage in IT/AT"))

    assert not violations, "Mock/local_mode violations:\n" + _format_violations(violations)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-004")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_file_headers_present(project_root, src_python_files):
    violations = []

    for file_path in src_python_files:
        rel = _rel(file_path, project_root)
        text = file_path.read_text(encoding="utf-8", errors="ignore")
        head = "\n".join(text.splitlines()[:10]).lower()

        try:
            has_module_docstring = bool(ast.get_docstring(ast.parse(text)))
        except SyntaxError:
            has_module_docstring = False

        has_header = (
            has_module_docstring or "copyright" in head or "licence" in head or "license" in head
        )
        if not has_header:
            violations.append(rel)

    assert not violations, "Missing file header/module docstring:\n- " + "\n- ".join(
        sorted(violations)
    )
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-004")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_functions_have_docstrings(src_python_files):
    total = 0
    documented = 0

    for file_path in src_python_files:
        try:
            tree = ast.parse(file_path.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                total += 1
                if ast.get_docstring(node):
                    documented += 1

    ratio = (documented / total) if total else 1.0
    assert ratio >= 0.80, f"Docstring coverage below threshold: {documented}/{total} ({ratio:.2%})"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.quality, pytest.mark.llm, pytest.mark.vdb, pytest.mark.smtp, pytest.mark.fast]

