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
Shared helpers for AT1.9 session-history vector store tests.

This module provides an importable path for AT1.12 tests after removing the
legacy `tests/application/AT1_9_SessionHistory` directory.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType


def _load_helpers_module() -> ModuleType:
    helpers_path = Path(__file__).resolve().parent / "AT1.9_SessionHistory" / "test_helpers.py"
    spec = importlib.util.spec_from_file_location(
        "at1_9_session_history_test_helpers", helpers_path
    )
    if spec is None or spec.loader is None:
        raise ImportError(f"Failed to create import spec for: {helpers_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_helpers = _load_helpers_module()

create_test_vector_store = _helpers.create_test_vector_store
add_message_to_vector_store = _helpers.add_message_to_vector_store
query_vector_store = _helpers.query_vector_store
create_session_with_messages = _helpers.create_session_with_messages
