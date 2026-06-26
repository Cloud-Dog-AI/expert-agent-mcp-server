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

"""W25A platform package adoption checks."""

from __future__ import annotations
import pytest

import ast
import re
from pathlib import Path
from typing import Dict, List, Set


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _rel(path: Path, project_root: Path) -> str:
    return str(path.relative_to(project_root))


def _imported_modules(src_python_files: List[Path]) -> Set[str]:
    imports: Set[str] = set()
    for path in src_python_files:
        try:
            tree = ast.parse(_read_text(path))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                imports.add((node.module or "").split(".")[0])
    return imports


def _declared_dependencies(project_root: Path) -> Set[str]:
    pyproject = project_root / "pyproject.toml"
    if pyproject.exists():
        text = _read_text(pyproject)
    else:
        text = _read_text(project_root / "requirements.txt")

    deps = set()
    for line in text.splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        deps.add(re.split(r"[<>=\[\] ]", s, maxsplit=1)[0].strip().replace("-", "_"))
    return deps


def _scan_paths(project_root: Path, src_python_files: List[Path], pattern: str) -> List[str]:
    expr = re.compile(pattern)
    hits = []
    for path in src_python_files:
        if expr.search(_read_text(path)):
            hits.append(_rel(path, project_root))
    return sorted(hits)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_config_uses_cloud_dog_config(project_root, src_python_files, allowlist):
    imports = _imported_modules(src_python_files)
    assert "cloud_dog_config" in imports or "src" in imports, (
        "Missing cloud_dog_config import usage; config migration incomplete"
    )

    bespoke_paths = _scan_paths(
        project_root,
        src_python_files,
        r"yaml\.(safe_load|load)\(|dotenv\.load_dotenv|os\.getenv|os\.environ",
    )
    non_allowlisted = [
        p
        for p in bespoke_paths
        if p not in allowlist["os_environ_config_paths"] and p not in allowlist["yaml_config_paths"]
    ]
    assert not non_allowlisted, "Bespoke config access found:\n- " + "\n- ".join(non_allowlisted)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_logging_uses_cloud_dog_logging(project_root, src_python_files, allowlist):
    imports = _imported_modules(src_python_files)
    if "cloud_dog_logging" not in imports:
        # Migration gap currently allowlisted at dependency declaration level.
        assert "cloud_dog_logging" in allowlist["missing_platform_packages"]

    hits = _scan_paths(project_root, src_python_files, r"logging\.(getLogger|basicConfig)\(")
    non_allowlisted = [p for p in hits if p not in allowlist["logging_stdlib_paths"]]
    assert not non_allowlisted, "Non-allowlisted stdlib logging setup:\n- " + "\n- ".join(
        non_allowlisted
    )
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_api_uses_cloud_dog_api_kit(project_root, src_python_files, allowlist):
    api_server_present = (project_root / "src" / "servers" / "api" / "server.py").exists()
    if not api_server_present:
        return

    hits = _scan_paths(project_root, src_python_files, r"\bFastAPI\(")
    non_allowlisted = [p for p in hits if p not in allowlist["raw_fastapi_paths"]]
    assert not non_allowlisted, "Raw FastAPI() found outside allowlist:\n- " + "\n- ".join(
        non_allowlisted
    )
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_auth_uses_cloud_dog_idam(project_root, src_python_files, allowlist):
    imports = _imported_modules(src_python_files)
    if "cloud_dog_idam" not in imports:
        assert "cloud_dog_idam" in allowlist["missing_platform_packages"]

    hits = _scan_paths(
        project_root, src_python_files, r"APIKeyHeader|jwt\.encode|jwt\.decode|verify_token"
    )
    non_allowlisted = [p for p in hits if p not in allowlist["bespoke_auth_paths"]]
    assert not non_allowlisted, "Bespoke auth paths outside allowlist:\n- " + "\n- ".join(
        non_allowlisted
    )
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_no_bespoke_db_access(project_root, src_python_files):
    hits = _scan_paths(project_root, src_python_files, r"create_engine\(|sqlite3\.connect\(")
    assert not hits, "Direct DB construction calls found:\n- " + "\n- ".join(hits)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_no_bespoke_llm_calls(project_root, src_python_files):
    hits = _scan_paths(project_root, src_python_files, r"openai\.OpenAI\(|ollama\.chat\(")
    assert not hits, "Direct LLM SDK calls found:\n- " + "\n- ".join(hits)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_no_bespoke_vdb_calls(project_root, src_python_files, allowlist):
    hits = _scan_paths(
        project_root,
        src_python_files,
        r"chromadb\.(Client|HttpClient|PersistentClient)\(|qdrant_client\.QdrantClient\(",
    )
    non_allowlisted = [p for p in hits if p not in allowlist["bespoke_vdb_paths"]]
    assert not non_allowlisted, (
        "Direct bespoke VDB client calls outside allowlist:\\n- " + "\\n- ".join(non_allowlisted)
    )
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-001")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_pyproject_declares_platform_packages(project_root, src_python_files, allowlist):
    declared = _declared_dependencies(project_root)
    imports = _imported_modules(src_python_files)

    required: Dict[str, bool] = {
        "cloud_dog_config": True,
        "cloud_dog_logging": True,
        "cloud_dog_api_kit": (project_root / "src" / "servers" / "api").exists(),
        "cloud_dog_idam": (project_root / "src" / "servers" / "api").exists(),
        "cloud_dog_db": True,
        "cloud_dog_jobs": "job" in " ".join(str(p) for p in src_python_files),
        "cloud_dog_llm": "llm" in " ".join(str(p) for p in src_python_files),
        "cloud_dog_vdb": "vector" in " ".join(str(p) for p in src_python_files),
    }

    missing = []
    for pkg, applicable in required.items():
        if not applicable:
            continue
        pkg_key = pkg.replace("-", "_")
        vendored_ok = pkg_key == "cloud_dog_db" and (project_root / "cloud_dog_db").exists()
        declared_ok = pkg_key in declared
        imported_ok = pkg_key in imports
        if not (vendored_ok or declared_ok or imported_ok):
            if pkg in allowlist["missing_platform_packages"]:
                continue
            missing.append(pkg)

    assert not missing, "Missing required platform package declarations/imports:\n- " + "\n- ".join(
        sorted(missing)
    )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.quality, pytest.mark.llm, pytest.mark.vdb, pytest.mark.db, pytest.mark.fast]

