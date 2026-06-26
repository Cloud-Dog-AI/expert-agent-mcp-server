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

"""Unit coverage for the code-runner A2A consumer client (W28I-1218).

The HTTP call is mocked via ``httpx.MockTransport`` — no live network is used.
Asserts the outbound request shape (skill_id=code.execute, code/language in
input, X-API-Key + X-Correlation-Id headers) and that a completed response is
surfaced back to the caller.
"""

import asyncio
import json

import httpx
import pytest

from src.core.service.code_runner import CodeRunnerClient


def _make_client(captured, response):
    """Build a CodeRunnerClient whose transport records the request."""

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content.decode())
        return response

    transport = httpx.MockTransport(handler)
    return CodeRunnerClient(client=httpx.AsyncClient(transport=transport))
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_code_execute_request_shape_and_completed_response(test_config):
    captured = {}
    response = httpx.Response(
        200,
        json={
            "status": "completed",
            "result": {
                "stdout": "4\n",
                "stderr": "",
                "exit_code": 0,
                "duration_ms": 12,
            },
        },
    )
    client = _make_client(captured, response)

    result = asyncio.run(
        client.execute(
            code="print(2 + 2)",
            language="python",
            correlation_id="corr-abc-123",
        )
    )

    # --- request shape (A2A code.execute contract) ---
    assert captured["url"].endswith("/a2a/tasks")
    body = captured["body"]
    assert body["skill_id"] == "code.execute"
    assert body["input"]["code"] == "print(2 + 2)"
    assert body["input"]["language"] == "python"
    assert body["task_id"]  # auto-generated, non-empty

    # --- auth + correlation propagation ---
    headers = {k.lower(): v for k, v in captured["headers"].items()}
    assert headers["x-api-key"] == "test-code-runner-key"
    assert headers["x-correlation-id"] == "corr-abc-123"

    # --- completed response surfaced ---
    assert result["status"] == "completed"
    assert result["result"]["stdout"] == "4\n"
    assert result["result"]["exit_code"] == 0
    assert result["correlation_id"] == "corr-abc-123"
    assert result["language"] == "python"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_code_execute_node_language_and_failed_status(test_config):
    captured = {}
    response = httpx.Response(
        200,
        json={
            "status": "failed",
            "result": {"stdout": "", "stderr": "boom", "exit_code": 1},
        },
    )
    client = _make_client(captured, response)

    result = asyncio.run(client.execute(code="console.log('x')", language="node"))

    assert captured["body"]["input"]["language"] == "node"
    assert captured["body"]["skill_id"] == "code.execute"
    assert result["status"] == "failed"
    assert result["result"]["stderr"] == "boom"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_code_execute_rejects_unsupported_language(test_config):
    client = CodeRunnerClient(client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))))
    with pytest.raises(ValueError):
        asyncio.run(client.execute(code="print(1)", language="ruby"))
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_code_execute_rejects_empty_code(test_config):
    client = CodeRunnerClient(client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))))
    with pytest.raises(ValueError):
        asyncio.run(client.execute(code="   "))
