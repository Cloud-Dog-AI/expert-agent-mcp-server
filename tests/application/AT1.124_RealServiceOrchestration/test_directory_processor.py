import uuid

import pytest

from tests.helpers_orchestration import build_api_client, seed_admin
from tests.helpers_real_orchestration import (
    mcp_call,
    mcp_tools_list,
    require_file_mcp,
    require_llm,
    write_evidence,
)


pytestmark = [pytest.mark.application, pytest.mark.llm, pytest.mark.mcp, pytest.mark.slow, pytest.mark.heavy, pytest.mark.timeout(300)]
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_directory_processor_real_subexpert_delegation(db_session):
    test_name = "test_directory_processor_real_subexpert_delegation"
    require_llm()
    file_mcp = require_file_mcp()
    write_evidence(test_name, "file_mcp_tools", mcp_tools_list(file_mcp["endpoint_url"], file_mcp["headers"]))

    api_key = f"orch-dir-{uuid.uuid4().hex}"
    _, api_key = seed_admin(db_session, api_key=api_key)
    client = build_api_client(db_session, api_key=api_key)

    suffix = uuid.uuid4().hex[:8]
    service_id = None
    child_expert_id = None
    parent_expert_id = None
    test_dir = f"/workspace/w28a95d_real_orch/dir-{suffix}"
    markdown_paths = [
        f"{test_dir}/alpha.md",
        f"{test_dir}/beta.md",
        f"{test_dir}/gamma.md",
    ]
    markdown_contents = {
        markdown_paths[0]: "# Alpha\nAlpha discusses safe deployment controls and review gates.",
        markdown_paths[1]: "# Beta\nBeta covers delegated workflows and expert coordination.",
        markdown_paths[2]: "# Gamma\nGamma records file handling, summaries, and cleanup guarantees.",
    }

    try:
        mcp_call(
            file_mcp["endpoint_url"],
            "create_dir",
            {"path": test_dir, "parents": True, "exist_ok": True},
            file_mcp["headers"],
        )
        for path, content in markdown_contents.items():
            mcp_call(
                file_mcp["endpoint_url"],
                "write_file",
                {"path": path, "content": content, "overwrite": True},
                file_mcp["headers"],
            )

        service = client.post(
            "/services",
            json={
                "name": f"filemcp-dir-{suffix}",
                "service_type": "mcp",
                "endpoint_url": file_mcp["endpoint_url"],
                "auth_config": file_mcp["auth_config"],
            },
        )
        assert service.status_code == 200, service.text
        service_id = service.json()["id"]

        child = client.post(
            "/experts",
            json={
                "name": f"file_lister_{suffix}",
                "title": "File Lister",
                "description": "Lists markdown files and summarises their contents using the bound file MCP service.",
                "prompt_template": (
                    "You are a file-lister sub-expert. Use the file service results to list markdown files and "
                    "summarise each file in one sentence."
                ),
            },
        )
        assert child.status_code == 200, child.text
        child_expert_id = child.json()["id"]

        parent = client.post(
            "/experts",
            json={
                "name": f"file_processor_{suffix}",
                "title": "File Processor",
                "description": "Delegates file discovery to a sub-expert and returns a concise combined summary.",
                "prompt_template": (
                    "You are a supervising orchestration expert. Summarise the delegation results into a coherent "
                    "report about the markdown files."
                ),
            },
        )
        assert parent.status_code == 200, parent.text
        parent_expert_id = parent.json()["id"]

        assert client.post(
            f"/experts/{child_expert_id}/services",
            json={"service_id": service_id, "priority": 1},
        ).status_code == 200
        assert client.post(
            f"/experts/{parent_expert_id}/sub-experts",
            json={"sub_expert_id": child_expert_id, "max_depth": 2},
        ).status_code == 200

        delegation_parameters = {
            "service_tool_calls": [
                {
                    "service_id": service_id,
                    "tool_name": "list_dir",
                    "arguments": {"path": test_dir, "recursive": False},
                },
                *[
                    {
                        "service_id": service_id,
                        "tool_name": "read_file",
                        "arguments": {"path": path},
                    }
                    for path in markdown_paths
                ],
            ],
            "persist_session": True,
            "max_tokens": 256,
        }

        execute = client.post(
            f"/experts/{parent_expert_id}/execute",
            json={
                "input_text": "Process all markdown files in the test directory",
                "parameters": {
                    "max_tokens": 256,
                    "delegations": [
                        {
                            "sub_expert_id": child_expert_id,
                            "task": "List all markdown files and summarise each one",
                            "parameters": delegation_parameters,
                            "context": {
                                "directory": test_dir,
                                "documents": markdown_paths,
                            },
                        }
                    ],
                },
            },
        )
        assert execute.status_code == 200, execute.text
        body = execute.json()
        write_evidence(test_name, "execute_response", body)

        assert body["delegations"], body
        delegation = body["delegations"][0]
        assert delegation["sub_expert_id"] == child_expert_id
        assert delegation["depth"] == 1
        child_execution = delegation["execution"]
        child_tool_names = [item["tool_name"] for item in child_execution["services_invoked"]]
        assert "list_dir" in child_tool_names
        assert child_tool_names.count("read_file") >= 3
        assert child_execution["session_id"] is not None

        lowered = body["output_text"].lower()
        assert "alpha" in lowered
        assert "beta" in lowered
        assert "gamma" in lowered
    finally:
        for path in markdown_paths:
            try:
                mcp_call(
                    file_mcp["endpoint_url"],
                    "delete_file",
                    {"path": path, "missing_ok": True},
                    file_mcp["headers"],
                )
            except Exception:
                pass
        try:
            mcp_call(
                file_mcp["endpoint_url"],
                "delete_file",
                {"path": test_dir, "missing_ok": True},
                file_mcp["headers"],
            )
        except Exception:
            pass
        if parent_expert_id is not None:
            client.delete(f"/experts/{parent_expert_id}")
        if child_expert_id is not None:
            client.delete(f"/experts/{child_expert_id}")
        if service_id is not None:
            client.delete(f"/services/{service_id}")
        client.close()
