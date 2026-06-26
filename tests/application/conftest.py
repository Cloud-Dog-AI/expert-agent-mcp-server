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

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))

from test_helpers_common import (
    TestOutputStorage,
    assert_all_validations_passed,
    get_current_output_store,
    print_summary_table,
    reset_current_output_store,
    set_current_output_store,
)


TARGET_SUITES = {
    "AT1.10_ContextWindowManagement",
    "AT1.11_MCPToolWorkflows",
    "AT1.12_MultiTurnConversation",
    "AT1.121_SummarizationArchival",
    "AT1.15_GroupManagement",
    "AT1.16_ExpertConfigManagement",
    "AT1.17_VectorStoreManagement",
    "AT1.18_AuditLogViewing",
}


@pytest.fixture(autouse=True)
def output_store(request):
    suite_name = Path(str(request.fspath)).parent.name
    if suite_name not in TARGET_SUITES:
        yield None
        return

    store = TestOutputStorage(suite_name, request.node.name)
    token = set_current_output_store(store)
    try:
        yield store
    finally:
        reset_current_output_store(token)
        report_setup = getattr(request.node, "rep_setup", None)
        report_call = getattr(request.node, "rep_call", None)
        if report_setup and report_setup.failed:
            return
        if report_call and report_call.failed:
            print_summary_table(store)
            return
        if report_call and report_call.passed and not store.metadata.get("validations"):
            pytest.fail(f"No validations logged for {suite_name}.{request.node.name}")
        print_summary_table(store)
        assert_all_validations_passed(store)


def _next_validation_name(store: TestOutputStorage, base: str) -> str:
    count = len(store.metadata.get("validations", [])) + 1
    return f"{base}_{count:03d}"


def pytest_assertion_pass(item, lineno, orig, expl):
    store = get_current_output_store()
    if not store:
        return
    name = _next_validation_name(store, "assert_pass")
    store.save_validation(
        name,
        {
            "file": str(item.fspath),
            "line": lineno,
            "expression": orig,
            "explanation": expl,
        },
        True,
    )


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    setattr(item, f"rep_{report.when}", report)
    if report.when != "call":
        return
    if report.outcome == "skipped":
        return
    store = get_current_output_store()
    if not store:
        return
    if call.excinfo is None:
        if not store.metadata.get("validations"):
            name = _next_validation_name(store, "test_passed")
            store.save_validation(
                name,
                {"nodeid": item.nodeid},
                True,
            )
        return
    name = _next_validation_name(store, "assert_fail")
    store.save_validation(
        name,
        {
            "file": str(item.fspath),
            "error": str(call.excinfo.value),
            "traceback": str(call.excinfo.traceback),
        },
        False,
    )
