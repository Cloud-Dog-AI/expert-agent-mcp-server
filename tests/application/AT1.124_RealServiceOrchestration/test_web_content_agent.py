import json
import uuid

import pytest

from tests.helpers_orchestration import build_api_client, seed_admin
from tests.helpers_real_orchestration import (
    mcp_call,
    mcp_tools_list,
    require_file_mcp,
    require_llm,
    require_search_mcp,
    write_evidence,
)


pytestmark = [pytest.mark.application, pytest.mark.llm, pytest.mark.mcp, pytest.mark.slow, pytest.mark.heavy, pytest.mark.timeout(300)]
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_web_content_agent_real_services(db_session):
    test_name = "test_web_content_agent_real_services"
    require_llm()
    file_mcp = require_file_mcp()
    search_mcp_url = require_search_mcp()

    write_evidence(test_name, "file_mcp_tools", mcp_tools_list(file_mcp["endpoint_url"], file_mcp["headers"]))
    write_evidence(test_name, "search_mcp_tools", mcp_tools_list(search_mcp_url))

    api_key = f"orch-web-{uuid.uuid4().hex}"
    _, api_key = seed_admin(db_session, api_key=api_key)
    client = build_api_client(db_session, api_key=api_key)

    suffix = uuid.uuid4().hex[:8]
    search_service_id = None
    file_service_id = None
    expert_id = None
    output_file = f"/workspace/w28a95d_real_orch/web-content-{suffix}.md"

    try:
        search_service = client.post(
            "/services",
            json={
                "name": f"searchmcp-{suffix}",
                "service_type": "mcp",
                "endpoint_url": search_mcp_url,
            },
        )
        assert search_service.status_code == 200, search_service.text
        search_service_id = search_service.json()["id"]

        file_service = client.post(
            "/services",
            json={
                "name": f"filemcp-{suffix}",
                "service_type": "mcp",
                "endpoint_url": file_mcp["endpoint_url"],
                "auth_config": file_mcp["auth_config"],
            },
        )
        assert file_service.status_code == 200, file_service.text
        file_service_id = file_service.json()["id"]

        expert = client.post(
            "/experts",
            json={
                "name": f"web_content_agent_{suffix}",
                "title": "Web Content Agent",
                "description": "Search recent articles about a topic, summarise the findings, and save the summary to the file service.",
                "prompt_template": (
                    "You are a web content synthesis expert. Summarise the service results into a concise report "
                    "with 3 bullet points and a short conclusion."
                ),
            },
        )
        assert expert.status_code == 200, expert.text
        expert_id = expert.json()["id"]

        assert client.post(
            f"/experts/{expert_id}/services",
            json={"service_id": search_service_id, "priority": 1},
        ).status_code == 200
        assert client.post(
            f"/experts/{expert_id}/services",
            json={"service_id": file_service_id, "priority": 2},
        ).status_code == 200

        execute = client.post(
            f"/experts/{expert_id}/execute",
            json={
                "input_text": "Find 3 recent articles about AI safety",
                "parameters": {
                    "max_tokens": 256,
                    "service_tool_calls": [
                        {
                            "service_id": search_service_id,
                            "tool_name": "search",
                            "arguments": {
                                "query": "AI safety latest articles",
                                "max_results": "3",
                            },
                        }
                    ],
                    "post_service_tool_calls": [
                        {
                            "service_id": file_service_id,
                            "tool_name": "write_file",
                            "arguments": {
                                "path": output_file,
                                "content": "${output_text}",
                                "overwrite": True,
                            },
                        }
                    ],
                },
            },
        )
        assert execute.status_code == 200, execute.text
        body = execute.json()
        write_evidence(test_name, "execute_response", body)

        tool_names = [item["tool_name"] for item in body["services_invoked"]]
        assert "search" in tool_names
        assert "write_file" in tool_names
        assert body["output_text"]
        assert len(body["output_text"]) > 60
        lowered = body["output_text"].lower()
        assert "ai" in lowered or "safety" in lowered

        file_read = mcp_call(
            file_mcp["endpoint_url"],
            "read_file",
            {"path": output_file},
            file_mcp["headers"],
        )
        write_evidence(test_name, "file_read", file_read)
        file_text = (
            file_read.get("result", {})
            .get("structuredContent", {})
            .get("value")
            or file_read.get("result", {})
            .get("structuredContent", {})
            .get("result")
            or "\n".join(
                str(item.get("text", ""))
                for item in file_read.get("result", {}).get("content", [])
                if isinstance(item, dict)
            )
            or ""
        )
        assert file_text
        assert body["output_text"][:40] in file_text
    finally:
        try:
            mcp_call(
                file_mcp["endpoint_url"],
                "delete_file",
                {"path": output_file, "missing_ok": True},
                file_mcp["headers"],
            )
        except Exception:
            pass
        if expert_id is not None:
            client.delete(f"/experts/{expert_id}")
        if search_service_id is not None:
            client.delete(f"/services/{search_service_id}")
        if file_service_id is not None:
            client.delete(f"/services/{file_service_id}")
        client.close()
