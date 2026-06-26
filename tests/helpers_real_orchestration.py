import json
import os
import ssl
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

import httpx
import pytest


def _parse_env_file(path: Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def _parse_mcp_payload(text: str) -> Dict[str, Any]:
    body = text.strip()
    if not body:
        raise ValueError("Empty MCP response body")
    if body.startswith("{"):
        return json.loads(body)
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if line.startswith("data:"):
            return json.loads(line[len("data:") :].strip())
    raise ValueError(f"Unsupported MCP response payload: {body[:200]}")


def write_evidence(test_name: str, stem: str, payload: Any) -> Path:
    out_dir = Path("working") / "AT1.124_TEST_OUTPUTS" / test_name
    out_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, (dict, list)):
        target = out_dir / f"{stem}.json"
        target.write_text(json.dumps(payload, indent=2, sort_keys=True))
        return target
    target = out_dir / f"{stem}.txt"
    target.write_text(str(payload))
    return target


def require_file_mcp() -> Dict[str, Any]:
    endpoint_url = (
        os.environ.get("CLOUD_DOG__EXPERT__TEST__AT1_124__FILE_MCP_MCP_URL", "").strip()
        or os.environ.get("CLOUD_DOG__EXPERT__TEST__AT1_124__FILE_MCP_URL", "").strip()
    )
    token = (
        os.environ.get("CLOUD_DOG__EXPERT__TEST__AT1_124__FILE_MCP_API_KEY", "").strip()
        or os.environ.get("CLOUD_DOG__EXPERT__TEST__AT1_124__FILE_MCP_TOKEN", "").strip()
    )
    health_url = os.environ.get("CLOUD_DOG__EXPERT__TEST__AT1_124__FILE_MCP_HEALTH_URL", "").strip()

    if not endpoint_url or not token:
        blob = _load_vault_json()
        value: Any = blob
        for part in ["dev", "services", "filemcpserver0"]:
            if not isinstance(value, dict) or part not in value:
                pytest.skip("filemcp not available: Vault path dev.services.filemcpserver0 missing")
            value = value[part]
        service = value if isinstance(value, dict) else {}
        endpoint_url = endpoint_url or str(service.get("mcp_url") or service.get("uri") or "").strip()
        token = token or str(service.get("api_key") or "").strip()
        if not health_url:
            health_base = str(service.get("api_url") or service.get("web_url") or "").strip().rstrip("/")
            health_url = f"{health_base}/health" if health_base else ""

    if not endpoint_url:
        pytest.skip("filemcp not available: MCP URL missing")
    if not token:
        pytest.skip("filemcp not available: API key missing")
    if not health_url and endpoint_url.rstrip("/").endswith("/mcp"):
        health_url = endpoint_url.rstrip("/")[: -len("/mcp")] + "/health"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
    }

    try:
        if health_url:
            response = httpx.get(health_url, headers={"Authorization": f"Bearer {token}"}, timeout=10.0, verify=False)
            response.raise_for_status()
        mcp_tools_list(endpoint_url, headers)
    except Exception as exc:
        pytest.skip(f"filemcp not available: {exc}")

    return {
        "endpoint_url": endpoint_url,
        "auth_config": {"type": "bearer", "value": token},
        "headers": headers,
    }


def _load_vault_json() -> Dict[str, Any]:
    addr = os.environ.get("VAULT_ADDR", "").strip()
    mount = os.environ.get("VAULT_MOUNT_POINT", "").strip()
    config_path = os.environ.get("VAULT_CONFIG_PATH", "").strip()
    token = os.environ.get("VAULT_TOKEN", "").strip()
    if not addr or not mount or not config_path or not token:
        return {}

    url = f"{addr}/v1/{mount}/data/{config_path}"
    request = urllib.request.Request(url, headers={"X-Vault-Token": token})
    with urllib.request.urlopen(request, context=ssl.create_default_context()) as response:
        payload = json.loads(response.read())
    blob = payload.get("data", {}).get("data", {}).get("json", {})
    if isinstance(blob, str):
        try:
            return json.loads(blob)
        except json.JSONDecodeError:
            return {}
    return blob if isinstance(blob, dict) else {}


def require_search_mcp() -> str:
    override = os.environ.get("CLOUD_DOG__EXPERT__TEST__AT1_124__SEARCH_MCP_URL", "").strip()
    if override:
        return override

    blob = _load_vault_json()
    value: Any = blob
    for part in ["dev", "services", "searchmcp", "uri"]:
        if not isinstance(value, dict) or part not in value:
            pytest.skip("searchmcp not available: Vault path dev.services.searchmcp.uri missing")
        value = value[part]
    uri = str(value).strip()
    if not uri:
        pytest.skip("searchmcp not available: Vault URI empty")
    return uri


def require_llm() -> None:
    base_url = os.environ.get("CLOUD_DOG__EXPERT__LLM__BASE_URL", "").strip()
    if not base_url:
        pytest.skip("LLM not available: CLOUD_DOG__EXPERT__LLM__BASE_URL missing")
    probe_url = base_url.rstrip("/") + "/api/tags"
    try:
        response = httpx.get(probe_url, timeout=15.0)
        response.raise_for_status()
    except Exception as exc:
        pytest.skip(f"LLM not available: {exc}")


def mcp_tools_list(url: str, headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    response = httpx.post(
        url,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            **(headers or {}),
        },
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        timeout=30.0,
        verify=False,
    )
    response.raise_for_status()
    return _parse_mcp_payload(response.text)


def mcp_call(url: str, tool_name: str, arguments: Dict[str, Any], headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    response = httpx.post(
        url,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            **(headers or {}),
        },
        json={
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "tools/call",
            "params": {"name": tool_name, "arguments": arguments},
        },
        timeout=60.0,
        verify=False,
    )
    response.raise_for_status()
    return _parse_mcp_payload(response.text)
