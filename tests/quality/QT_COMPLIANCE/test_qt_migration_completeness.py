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

"""W25A migration completeness static checks."""

from __future__ import annotations
import pytest

import re
from pathlib import Path
from typing import List, Tuple


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _rel(path: Path, project_root: Path) -> str:
    return str(path.relative_to(project_root))


def _scan(
    project_root: Path, src_python_files: List[Path], pattern: str
) -> List[Tuple[str, int, str]]:
    expr = re.compile(pattern)
    hits: List[Tuple[str, int, str]] = []
    for file_path in src_python_files:
        rel = _rel(file_path, project_root)
        for idx, line in enumerate(_read_text(file_path).splitlines(), start=1):
            if expr.search(line):
                hits.append((rel, idx, line.strip()))
    return hits
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-003")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_no_yaml_safe_load_for_config(project_root, src_python_files, allowlist):
    hits = _scan(project_root, src_python_files, r"yaml\.(safe_load|load)\(")
    hits = [h for h in hits if h[0] not in allowlist["yaml_config_paths"]]
    assert not hits, "yaml.load/safe_load config usage outside allowlist:\n" + "\n".join(
        f"- {p}:{ln}: {line}" for p, ln, line in hits
    )
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-003")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_no_raw_fastapi(project_root, src_python_files, allowlist):
    hits = _scan(project_root, src_python_files, r"\bFastAPI\(")
    hits = [h for h in hits if h[0] not in allowlist["raw_fastapi_paths"]]
    assert not hits, "Raw FastAPI() usage outside allowlist:\n" + "\n".join(
        f"- {p}:{ln}: {line}" for p, ln, line in hits
    )
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-003")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_no_bespoke_auth(project_root, src_python_files, allowlist):
    hits = _scan(
        project_root, src_python_files, r"APIKeyHeader|jwt\.encode|jwt\.decode|verify_token"
    )
    hits = [h for h in hits if h[0] not in allowlist["bespoke_auth_paths"]]
    assert not hits, "Bespoke auth usage outside allowlist:\n" + "\n".join(
        f"- {p}:{ln}: {line}" for p, ln, line in hits
    )
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-003")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_no_os_environ_for_config(project_root, src_python_files, allowlist):
    hits = _scan(project_root, src_python_files, r"os\.(environ|getenv)")
    hits = [h for h in hits if h[0] not in allowlist["os_environ_config_paths"]]
    assert not hits, "os.environ/os.getenv config reads outside allowlist:\n" + "\n".join(
        f"- {p}:{ln}: {line}" for p, ln, line in hits
    )

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.quality, pytest.mark.pure, pytest.mark.fast]

