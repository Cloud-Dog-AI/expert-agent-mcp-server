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

"""W25A vault/config/secret contract checks."""

from __future__ import annotations
import pytest

import re
from pathlib import Path
from typing import List, Tuple

SECRET_VALUE_RE = re.compile(
    r"\b(password|passwd|token|api[_-]?key|secret)\b\s*[:=]\s*['\"]?([^'\"\n#]+)",
    re.IGNORECASE,
)
VAULT_EXPR_RE = re.compile(r"\$\{vault\.dev\.[^}]+\}")
SOURCE_SECRET_LITERAL_RE = re.compile(
    r"\b(password|passwd|token|api[_-]?key|secret)\b\s*=\s*([\"'])[^\"']+\2",
    re.IGNORECASE,
)


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="ignore")


def _iter_env_entries(path: Path):
    for idx, line in enumerate(_read_text(path).splitlines(), start=1):
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key, value = s.split("=", 1)
        yield idx, key.strip(), value.strip()
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-002")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_defaults_yaml_exists(project_root):
    assert (project_root / "defaults.yaml").exists(), "defaults.yaml missing"
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-002")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_defaults_yaml_no_secrets(project_root):
    defaults = project_root / "defaults.yaml"
    text = _read_text(defaults)
    violations: List[str] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        if line.strip().startswith("#"):
            continue
        m = SECRET_VALUE_RE.search(line)
        if not m:
            continue
        value = m.group(2).strip()
        if value and value.lower() not in {
            "",
            "none",
            "null",
            "changeme",
            "example",
            "placeholder",
        }:
            violations.append(f"{defaults}:{idx}: {line.strip()}")

    assert not violations, "defaults.yaml contains secret-like literals:\n- " + "\n- ".join(
        violations
    )
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-002")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_config_yaml_no_secrets(project_root):
    config_yaml = project_root / "config" / "config.yaml"
    if not config_yaml.exists():
        return

    violations = []
    for idx, line in enumerate(_read_text(config_yaml).splitlines(), start=1):
        if line.strip().startswith("#"):
            continue
        m = SECRET_VALUE_RE.search(line)
        if not m:
            continue
        value = m.group(2).strip()
        if value and not VAULT_EXPR_RE.search(value):
            violations.append(f"{config_yaml}:{idx}: {line.strip()}")

    assert not violations, "config.yaml contains secret-like literals:\n- " + "\n- ".join(
        violations
    )
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-002")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_env_files_use_vault_expressions(project_root, allowlist):
    """Credential-like entries in IT/AT env files must use vault expressions unless allowlisted."""

    env_files = [project_root / "tests" / "env-IT", project_root / "tests" / "env-AT"]

    violations: List[Tuple[str, int, str]] = []
    for env_file in env_files:
        for idx, key, value in _iter_env_entries(env_file):
            upper_segments = key.upper().split("__")
            is_credential = any(
                seg.startswith("PASSWORD")
                or seg.startswith("API_KEY")
                or seg == "TOKEN"
                or seg.startswith("SECRET")
                for seg in upper_segments
            )
            if not is_credential:
                continue
            if key in allowlist["env_vault_exempt_keys"]:
                continue
            if VAULT_EXPR_RE.search(value):
                continue
            violations.append((str(env_file), idx, f"{key}={value}"))

    assert not violations, "IT/AT env credentials missing vault expressions:\n" + "\n".join(
        f"- {f}:{ln}: {msg}" for f, ln, msg in violations
    )
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-002")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_no_secrets_in_source(project_root, src_python_files):
    violations = []
    for file_path in src_python_files:
        for idx, line in enumerate(_read_text(file_path).splitlines(), start=1):
            if line.strip().startswith("#"):
                continue
            m = SOURCE_SECRET_LITERAL_RE.search(line)
            if not m:
                continue
            violations.append(f"{file_path}:{idx}: {line.strip()}")

    assert not violations, "Secret-like literals found in src/:\n- " + "\n- ".join(violations)
@pytest.mark.QT
@pytest.mark.mcp
@pytest.mark.req("NF-002")  # W28E-1809A: rebound from legacy orphan marker to semantic requirement


def test_env_files_exist_per_tier(project_root):
    for env_name in ("env-UT", "env-ST", "env-IT", "env-AT"):
        path = project_root / "tests" / env_name
        assert path.exists(), f"Missing required env file: {path}"

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.quality, pytest.mark.pure, pytest.mark.fast]

