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

"""W25A requirement/test/code traceability checks."""

from __future__ import annotations
import pytest

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Set, Tuple

REQ_ID_RE = re.compile(r"(?:CM|SV|BO|BR|FR|UC|CS|NF)\d+\.\d+")
TEST_ID_RE = re.compile(r"(?:UT|ST|IT|AT|PT|QT|CT)\d+\.\d+")
REQ_HEADER_RE = re.compile(r"^###\s+((?:CM|SV|BO|BR|FR|UC|CS|NF)\d+\.\d+)\s*:")
TEST_ENTRY_RE = re.compile(r"^(UT|ST|IT|AT|PT|QT|CT)\d+\.\d+\s+-")


@dataclass
class TraceEntry:
    test_id: str
    block: str


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _parse_requirements(req_md: str) -> Tuple[List[str], Dict[str, str]]:
    ids: List[str] = []
    blocks: Dict[str, str] = {}
    lines = req_md.splitlines()

    current_id = None
    current_lines: List[str] = []

    for line in lines:
        m = REQ_HEADER_RE.match(line.strip())
        if m:
            if current_id is not None:
                blocks[current_id] = "\n".join(current_lines)
            current_id = m.group(1)
            if current_id not in ids:
                ids.append(current_id)
            current_lines = [line]
            continue
        if current_id is not None:
            current_lines.append(line)

    if current_id is not None:
        blocks[current_id] = "\n".join(current_lines)

    return ids, blocks


def _parse_test_entries(tests_md: str) -> Dict[str, TraceEntry]:
    lines = tests_md.splitlines()
    entries: Dict[str, TraceEntry] = {}

    cur_id = None
    cur_lines: List[str] = []

    for line in lines:
        stripped = line.strip()
        if TEST_ENTRY_RE.match(stripped):
            if cur_id:
                entries[cur_id] = TraceEntry(cur_id, "\n".join(cur_lines))
            cur_id = stripped.split("-", 1)[0].strip()
            cur_lines = [line]
        elif cur_id:
            if stripped.startswith("## "):
                entries[cur_id] = TraceEntry(cur_id, "\n".join(cur_lines))
                cur_id = None
                cur_lines = []
            else:
                cur_lines.append(line)

    if cur_id:
        entries[cur_id] = TraceEntry(cur_id, "\n".join(cur_lines))

    return entries


def _existing_test_ids(project_root: Path) -> Set[str]:
    ids: Set[str] = set()
    for file_path in (project_root / "tests").rglob("test_*.py"):
        parts = "/".join(file_path.parts)
        ids.update(TEST_ID_RE.findall(parts))
        ids.update(TEST_ID_RE.findall(_read(file_path)))
    return ids


def _all_test_files(project_root: Path) -> List[Path]:
    return sorted((project_root / "tests").rglob("test_*.py"))


def _requirement_refs_in_text(text: str) -> Set[str]:
    return set(REQ_ID_RE.findall(text))


def _requirement_prefix(req_id: str) -> str:
    return req_id[:2]


def _code_ref_index(src_python_files: Sequence[Path]) -> Dict[str, Set[str]]:
    index: Dict[str, Set[str]] = {}
    for path in src_python_files:
        text = _read(path)
        for req_id in set(REQ_ID_RE.findall(text)):
            index.setdefault(req_id, set()).add(str(path))
    return index


def _search_requirement_in_tests(project_root: Path, req_id: str) -> bool:
    for file_path in (project_root / "tests").rglob("*.py"):
        if req_id in _read(file_path):
            return True
    return False


def _status(has_code: bool, has_test: bool) -> str:
    if has_code and has_test:
        return "DELIVERED"
    if has_code and not has_test:
        return "UNTESTABLE"
    if (not has_code) and has_test:
        return "PARTIAL"
    return "NOT STARTED"


def _delivery_matrix(
    requirements: Iterable[str],
    tests_md: str,
    project_root: Path,
    src_python_files: Sequence[Path],
    allowlist,
) -> List[Dict[str, str]]:
    code_index = _code_ref_index(src_python_files)
    rows = []

    for req_id in requirements:
        in_tests_md = req_id in tests_md
        in_test_files = _search_requirement_in_tests(project_root, req_id)
        has_test = in_tests_md or in_test_files

        has_code_direct = req_id in code_index
        prefix = _requirement_prefix(req_id)
        has_code_proxy = (
            prefix in allowlist["requirement_code_reference_prefix_allowlist"] and has_test
        )
        has_code = has_code_direct or has_code_proxy

        code_loc = (
            ", ".join(sorted(code_index.get(req_id, [])))
            if has_code_direct
            else "(proxy via test-trace)"
        )
        test_loc = "docs/TESTS.md or tests/*.py" if has_test else "-"

        rows.append(
            {
                "req_id": req_id,
                "code": code_loc,
                "test": test_loc,
                "status": _status(has_code, has_test),
            }
        )

    return rows
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-005")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_all_requirements_have_tests(project_root, allowlist):
    req_md = _read(project_root / "docs" / "REQUIREMENTS.md")
    tests_md = _read(project_root / "docs" / "TESTS.md")
    req_ids, _ = _parse_requirements(req_md)

    missing = []
    for req_id in req_ids:
        in_docs = req_id in tests_md
        in_tests = _search_requirement_in_tests(project_root, req_id)
        if not (in_docs or in_tests):
            if req_id in allowlist["requirements_without_tests_allowlist"]:
                continue
            missing.append(req_id)

    assert not missing, "Untested requirements:\n- " + "\n- ".join(missing)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-005")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_all_tests_have_requirements(project_root, allowlist):
    tests_md = _read(project_root / "docs" / "TESTS.md")
    entries = _parse_test_entries(tests_md)
    existing_ids = _existing_test_ids(project_root)

    orphan = []
    for test_id in sorted(existing_ids):
        if any(
            test_id.startswith(prefix) for prefix in allowlist["docs_traceability_ignored_prefixes"]
        ):
            continue
        entry = entries.get(test_id)
        if not entry:
            if test_id in allowlist["test_ids_missing_docs_allowlist"]:
                continue
            orphan.append(f"{test_id}: missing docs/TESTS.md entry")
            continue

        req_refs = set(re.findall(r"\b(?:CM|SV|BO|BR|FR|UC|CS|NF)\d+\.\d+\b", entry.block))
        if not req_refs:
            if test_id in allowlist["tests_without_requirements_allowlist"]:
                continue
            orphan.append(f"{test_id}: no requirement reference in docs entry")

    assert not orphan, "Orphan tests (no requirement traceability):\n- " + "\n- ".join(orphan)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-005")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_all_requirements_have_code(project_root, src_python_files, allowlist):
    req_md = _read(project_root / "docs" / "REQUIREMENTS.md")
    req_ids, _ = _parse_requirements(req_md)

    src_blob = "\n".join(_read(p) for p in src_python_files)
    missing = []
    for req_id in req_ids:
        if req_id in src_blob:
            continue
        if _requirement_prefix(req_id) in allowlist["requirement_code_reference_prefix_allowlist"]:
            continue
        missing.append(req_id)

    assert not missing, "Requirements with no code references:\n- " + "\n- ".join(missing)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-005")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_delivery_matrix_complete(project_root, src_python_files, allowlist):
    req_md = _read(project_root / "docs" / "REQUIREMENTS.md")
    tests_md = _read(project_root / "docs" / "TESTS.md")
    req_ids, _ = _parse_requirements(req_md)

    matrix = _delivery_matrix(req_ids, tests_md, project_root, src_python_files, allowlist)

    fr_rows = [r for r in matrix if r["req_id"].startswith("FR")]
    delivered = [r for r in fr_rows if r["status"] == "DELIVERED"]
    ratio = (len(delivered) / len(fr_rows)) if fr_rows else 1.0

    preview = ["| Req ID | Code | Test | Status |", "|---|---|---|---|"]
    for row in matrix:
        preview.append(f"| {row['req_id']} | {row['code']} | {row['test']} | {row['status']} |")

    assert ratio >= 0.80, (
        f"FR delivered ratio below 80%: {len(delivered)}/{len(fr_rows)} ({ratio:.2%})\n"
        + "\n".join(preview)
    )
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-005")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_no_orphan_test_files(project_root, allowlist):
    tests_md = _read(project_root / "docs" / "TESTS.md")
    orphans = []

    for file_path in _all_test_files(project_root):
        rel = str(file_path.relative_to(project_root))
        if rel in allowlist["orphan_test_file_allow_suffixes"]:
            continue
        if rel.startswith("tests/quality/QT_COMPLIANCE/"):
            continue

        path_test_ids = re.findall(r"(?:UT|ST|IT|AT|PT|QT|CT)\d+\.\d+", rel)
        content_test_ids = re.findall(r"(?:UT|ST|IT|AT|PT|QT|CT)\d+\.\d+", _read(file_path))
        ids = path_test_ids or content_test_ids

        if not ids:
            orphans.append(f"{rel}: no test ID in path/content")
            continue

        if all(test_id in allowlist["test_ids_missing_docs_allowlist"] for test_id in ids):
            continue
        if not any(test_id in tests_md for test_id in ids):
            orphans.append(f"{rel}: IDs not catalogued in docs/TESTS.md -> {ids}")

    assert not orphans, "Orphan test files:\n- " + "\n- ".join(orphans)

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.quality, pytest.mark.pure, pytest.mark.fast]

