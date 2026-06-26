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

"""Fixtures for QT compliance checks."""

from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set

import pytest


@pytest.fixture(scope="session")
def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


@pytest.fixture(scope="session")
def src_dir(project_root: Path) -> Path:
    return project_root / "src"


@pytest.fixture(scope="session")
def src_python_files(src_dir: Path) -> List[Path]:
    return sorted(p for p in src_dir.rglob("*.py") if "__pycache__" not in p.parts)


@pytest.fixture(scope="session")
def test_python_files(project_root: Path) -> List[Path]:
    tests_root = project_root / "tests"
    return sorted(p for p in tests_root.rglob("*.py") if "__pycache__" not in p.parts)


@pytest.fixture(scope="session")
def allowlist() -> Dict[str, Set[str]]:
    """Known migration gaps accepted for baseline compliance gating."""

    return {
        "hardcoded_url_paths": {
            # TODO: migration gap - vector provider defaults are still bespoke.
            "src/core/vector/providers.py",
            # TODO: migration gap - legacy default model URL remains in config model defaults.
            "src/config/models.py",
            # TODO: migration gap - loader doc/examples still include URL literal text.
            "src/config/loader.py",
        },
        "external_import_multi_module_libs": {
            # TODO: migration gap - requests/httpx still used outside a single adapter.
            "requests",
            "httpx",
        },
        "logging_stdlib_paths": {
            "src/utils/logger.py",
        },
        "raw_fastapi_paths": set(),
        "yaml_config_paths": {
            # No active allowlist entries.
        },
        "os_environ_config_paths": {
            # TODO: migration gap - env exposure/debugging still reads os.environ directly.
            "src/config/loader.py",
            "src/servers/api/routes/health.py",
            "src/servers/mcp/server.py",
            "src/servers/a2a/server.py",
            "src/servers/web/server.py",
            "src/core/session/summarizer.py",
            "src/core/audit/logger.py",
            "src/core/audit/manager.py",
        },
        "bespoke_auth_paths": set(),
        "bespoke_vdb_paths": set(),
        "missing_platform_packages": {
            # No active allowlist entries.
        },
        "env_vault_exempt_keys": {
            # TODO: dev/test fixture passwords are intentionally local constants.
            "CLOUD_DOG__EXPERT__TEST__USER__PASSWORD_NEW",
            "CLOUD_DOG__EXPERT__TEST__USER__PASSWORD_RESET",
            "CLOUD_DOG__EXPERT__TEST__USER__PASSWORD_WEAK",
            "CLOUD_DOG__EXPERT__TEST__API_KEY",
        },
        "requirements_without_tests_allowlist": {
            # TODO: traceability gap - requirement IDs not yet explicitly referenced in docs/tests.
            "SV1.2",
            "SV1.3",
            "BO1.1",
            "BO1.2",
            "BO1.3",
            "BO1.4",
            "BO1.5",
            "BO1.6",
            "BR1.1",
            "BR1.2",
            "BR1.3",
            "BR1.4",
            "UC1.4",
            "UC1.5",
            "UC1.24",
            "UC1.25",
            "CS1.5",
            "NF1.3",
            "NF1.7",
            "FR1.37",
            "FR1.38",
            "FR1.39",
            "FR1.40",
        },
        "tests_without_requirements_allowlist": {
            # TODO: traceability gap - docs/TESTS entries missing requirement refs.
            "AT1.14",
            "AT1.15",
            "AT1.16",
            "AT1.18",
            "AT1.19",
            "AT1.20",
            "AT1.21",
            "AT1.22",
            "AT1.23",
            "AT1.24",
            "AT1.25",
            "AT1.26",
            "AT1.27",
            "AT1.28",
            "AT1.29",
            "AT1.30",
            "AT1.31",
            "AT1.32",
            "AT1.33",
            "AT1.34",
            "AT1.35",
            "AT1.40",
            "AT1.41",
            "AT1.42",
            "AT1.43",
            "AT1.44",
            "AT1.45",
            "AT1.46",
            "AT1.47",
            "AT1.48",
            "AT1.49",
            "AT1.58",
            "AT1.59",
            "AT1.60",
            "AT1.95",
            "AT1.96",
            "AT1.98",
            "AT1.101",
            "AT1.115",
            "IT2.4",
        },
        "test_ids_missing_docs_allowlist": {
            # TODO: test catalogue drift - executable suites exist but docs entry missing.
            "AT1.117",
            "IT2.1",
            "IT2.3",
            "IT2.5",
            "UT1.44",
            "UT1.90",
            "UT1.91",
            "UT1.92",
            "UT1.93",
            "UT1.95",
        },
        "docs_traceability_ignored_prefixes": {
            # TODO: planned checklist sections in docs/TESTS.md are not executable test entries yet.
            "PT",
            "QT",
            "CT",
        },
        "orphan_test_file_allow_suffixes": {
            # Test support modules are intentionally not numbered catalogue entries.
            "tests/conftest.py",
            "tests/browser_helpers.py",
            "tests/application/test_helpers_common.py",
            "tests/application/AT1.10_ContextWindowManagement/at1_10_helpers.py",
            # TODO: test catalogue drift for new/extended UT suites.
            "tests/unit/UT1.93_KnowledgeVersioning/test_knowledge_versioning.py",
            "tests/unit/UT1.95_DbConformance/test_db_conformance.py",
            # Operational deploy-smoke (W28A-743 auth surface), QT-marked and
            # exercised in the smoke tier — not a requirement-bound catalogue ID.
            "tests/smoke/SM1.2_ExpertAuthSurface/test_expert_auth_surface.py",
        },
        "requirement_code_reference_prefix_allowlist": {
            # TODO: migration gap - requirement IDs are mostly not embedded in src comments/docstrings.
            "CM",
            "SV",
            "BO",
            "BR",
            "FR",
            "UC",
            "CS",
            "NF",
        },
    }
