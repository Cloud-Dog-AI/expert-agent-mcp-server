#!/usr/bin/env python3
"""W28A-743 live preprod Thread-B T0-T3 verifier.

The script reads the expert-agent admin API key from either
EXPERTAGENT0_ADMIN_API_KEY or the configured Vault JSON blob, exercises the
live public host, and prints redacted JSON evidence only. It creates temporary
user/group/API-key state and deletes/revokes it in a best-effort cleanup block.
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.request
from dataclasses import dataclass
from typing import Any

import requests


BASE_URL = os.environ.get("EXPERTAGENT0_BASE_URL", "https://expertagent0.cloud-dog.net").rstrip("/")
API_PREFIX = "/api/v1"
TIMEOUT = float(os.environ.get("EXPERT_THREAD_B_TIMEOUT_SECONDS", "20"))


@dataclass
class LiveState:
    user_id: int | None = None
    group_id: int | None = None
    key_id: int | None = None
    group_key: str | None = None
    member_added: bool = False


def _vault_admin_key() -> str:
    explicit = os.environ.get("EXPERTAGENT0_ADMIN_API_KEY", "").strip()
    if explicit:
        return explicit

    addr = os.environ.get("VAULT_ADDR", "").strip()
    mount = os.environ.get("VAULT_MOUNT_POINT", "").strip()
    path = os.environ.get("VAULT_CONFIG_PATH", "").strip()
    token = os.environ.get("VAULT_TOKEN", "").strip()
    if not (addr and mount and path and token):
        raise RuntimeError(
            "EXPERTAGENT0_ADMIN_API_KEY or VAULT_ADDR/VAULT_MOUNT_POINT/"
            "VAULT_CONFIG_PATH/VAULT_TOKEN is required"
        )

    req = urllib.request.Request(f"{addr}/v1/{mount}/data/{path}", headers={"X-Vault-Token": token})
    with urllib.request.urlopen(req, context=ssl.create_default_context(), timeout=TIMEOUT) as resp:
        payload = json.loads(resp.read())
    blob: Any = payload.get("data", {}).get("data", {}).get("json", {})
    if isinstance(blob, str):
        blob = json.loads(blob)
    key = blob["dev"]["services"]["expertagent0"]["api_key"]
    if not key:
        raise RuntimeError("Vault dev.services.expertagent0.api_key resolved empty")
    return str(key)


def _session(api_key: str | None = None) -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": "W28A-743-thread-b-live-verifier"})
    if api_key:
        session.headers.update({"X-API-Key": api_key})
    return session


def _request(session: requests.Session, method: str, path: str, **kwargs: Any) -> requests.Response:
    return session.request(method, f"{BASE_URL}{path}", timeout=TIMEOUT, **kwargs)


def _json(response: requests.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return {"_raw": response.text[:240]}


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in {"key", "api_key", "x_api_key", "password", "token", "secret"}:
                redacted[key] = "<redacted>"
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _record(records: list[dict[str, Any]], name: str, response: requests.Response) -> None:
    body = _json(response)
    body_for_sample = _redact(body)
    records.append(
        {
            "name": name,
            "status_code": response.status_code,
            "body_keys": sorted(body.keys()) if isinstance(body, dict) else [],
            "body_sample": str(body_for_sample)[:180],
        }
    )


def _expect_status(records: list[dict[str, Any]], name: str, response: requests.Response, expected: int | set[int]) -> Any:
    _record(records, name, response)
    expected_set = {expected} if isinstance(expected, int) else expected
    if response.status_code not in expected_set:
        raise AssertionError(f"{name}: expected {sorted(expected_set)}, got {response.status_code}: {response.text[:240]}")
    return _json(response)


def _cleanup(admin: requests.Session, state: LiveState, records: list[dict[str, Any]]) -> None:
    cleanup: list[dict[str, Any]] = []
    if state.member_added and state.group_id and state.user_id:
        response = _request(admin, "DELETE", f"{API_PREFIX}/groups/{state.group_id}/members/{state.user_id}")
        cleanup.append({"name": "cleanup_remove_member", "status_code": response.status_code})
    if state.key_id:
        response = _request(admin, "DELETE", f"{API_PREFIX}/api-keys/{state.key_id}")
        cleanup.append({"name": "cleanup_revoke_api_key", "status_code": response.status_code})
    if state.group_id:
        response = _request(admin, "DELETE", f"{API_PREFIX}/groups/{state.group_id}")
        cleanup.append({"name": "cleanup_delete_group", "status_code": response.status_code})
    if state.user_id:
        response = _request(admin, "DELETE", f"{API_PREFIX}/users/{state.user_id}")
        cleanup.append({"name": "cleanup_delete_user", "status_code": response.status_code})
    records.append({"name": "cleanup", "items": cleanup})


def main() -> int:
    records: list[dict[str, Any]] = []
    state = LiveState()
    admin = _session(_vault_admin_key())
    anonymous = _session()
    suffix = str(int(time.time()))

    try:
        _expect_status(records, "t0_health", _request(anonymous, "GET", "/health"), 200)
        _expect_status(records, "t0_web_shell", _request(anonymous, "GET", "/"), 200)
        _expect_status(records, "t0_a2a_health", _request(anonymous, "GET", "/a2a/health"), 200)
        card = _expect_status(records, "t0_a2a_agent_card", _request(anonymous, "GET", "/.well-known/agent.json"), 200)
        if "list_experts" not in json.dumps(card):
            raise AssertionError("t0_a2a_agent_card: list_experts skill missing")
        a2a_task = _expect_status(
            records,
            "t3_a2a_list_experts_task",
            _request(
                anonymous,
                "POST",
                "/a2a/tasks",
                json={"id": f"w28a743-a2a-{suffix}", "skill_id": "list_experts", "input": {"text": ""}},
            ),
            200,
        )
        if a2a_task.get("status") != "completed":
            raise AssertionError(f"t3_a2a_list_experts_task: expected completed, got {a2a_task}")

        _expect_status(records, "t1_api_anon_experts_denied", _request(anonymous, "GET", f"{API_PREFIX}/experts"), 401)
        _expect_status(
            records,
            "t1_mcp_anon_tools_denied",
            _request(
                anonymous,
                "POST",
                "/mcp",
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
            ),
            401,
        )

        user = _expect_status(
            records,
            "setup_create_viewer_user",
            _request(
                admin,
                "POST",
                f"{API_PREFIX}/users",
                json={
                    "username": f"w28a743_live_{suffix}",
                    "email": f"w28a743_live_{suffix}@example.invalid",
                    "password": f"W28a743-live-{suffix}!",
                    "display_name": "W28A-743 live verifier",
                    "role": "viewer",
                },
            ),
            200,
        )
        state.user_id = int(user["id"])

        group = _expect_status(
            records,
            "setup_create_group",
            _request(
                admin,
                "POST",
                f"{API_PREFIX}/groups",
                json={"name": f"w28a743_live_group_{suffix}", "description": "W28A-743 live verifier"},
            ),
            200,
        )
        state.group_id = int(group["id"])

        key = _expect_status(
            records,
            "setup_create_group_bound_key",
            _request(
                admin,
                "POST",
                f"{API_PREFIX}/api-keys",
                json={
                    "user_id": state.user_id,
                    "group_id": state.group_id,
                    "name": f"w28a743_live_key_{suffix}",
                    "read_logs": True,
                    "read_histories": True,
                    "read_channels": True,
                },
            ),
            200,
        )
        state.key_id = int(key["id"])
        state.group_key = str(key["key"])
        group_session = _session(state.group_key)

        _expect_status(records, "t3_api_before_membership_denied", _request(group_session, "GET", f"{API_PREFIX}/experts"), 401)
        _expect_status(
            records,
            "t3_mcp_before_membership_denied",
            _request(
                group_session,
                "POST",
                "/mcp",
                json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
            ),
            401,
        )

        _expect_status(
            records,
            "setup_add_group_member",
            _request(admin, "POST", f"{API_PREFIX}/groups/{state.group_id}/members", json={"user_id": state.user_id, "role": "member"}),
            200,
        )
        state.member_added = True

        experts_after = _expect_status(records, "t3_api_after_membership_experts_allowed", _request(group_session, "GET", f"{API_PREFIX}/experts"), 200)
        if "experts" not in experts_after:
            raise AssertionError("t3_api_after_membership_experts_allowed: experts key missing")
        channels_after = _expect_status(records, "t3_api_after_membership_channels_allowed", _request(group_session, "GET", f"{API_PREFIX}/channels"), 200)
        if "channels" not in channels_after:
            raise AssertionError("t3_api_after_membership_channels_allowed: channels key missing")
        _expect_status(
            records,
            "t2_viewer_write_denied",
            _request(
                group_session,
                "POST",
                f"{API_PREFIX}/experts",
                json={
                    "name": f"w28a743_forbidden_{suffix}",
                    "title": "Forbidden",
                    "description": "Viewer write must be denied",
                    "llm_provider": "ollama",
                    "llm_model": "llama3.1",
                },
            ),
            403,
        )

        mcp_after = _expect_status(
            records,
            "t3_mcp_after_membership_list_experts_allowed",
            _request(
                group_session,
                "POST",
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "list_experts", "arguments": {}},
                },
            ),
            200,
        )
        if "result" not in mcp_after or "error" in mcp_after:
            raise AssertionError(f"t3_mcp_after_membership_list_experts_allowed: bad MCP payload {mcp_after}")

        _expect_status(
            records,
            "setup_remove_group_member",
            _request(admin, "DELETE", f"{API_PREFIX}/groups/{state.group_id}/members/{state.user_id}"),
            200,
        )
        state.member_added = False
        _expect_status(records, "t3_api_after_membership_removal_denied", _request(group_session, "GET", f"{API_PREFIX}/experts"), 401)
        _expect_status(
            records,
            "t3_mcp_after_membership_removal_denied",
            _request(
                group_session,
                "POST",
                "/mcp",
                json={"jsonrpc": "2.0", "id": 4, "method": "tools/list", "params": {}},
            ),
            401,
        )

        _cleanup(admin, state, records)
        print(json.dumps({"passed": True, "base_url": BASE_URL, "records": records}, indent=2, sort_keys=True))
        print("LIVE_THREAD_B_T0_T3: PASS")
        return 0
    except Exception as exc:  # noqa: BLE001 - evidence script should report exact failure
        records.append({"name": "exception", "type": type(exc).__name__, "message": str(exc)})
        try:
            _cleanup(admin, state, records)
        except Exception as cleanup_exc:  # noqa: BLE001
            records.append(
                {
                    "name": "cleanup_exception",
                    "type": type(cleanup_exc).__name__,
                    "message": str(cleanup_exc),
                }
            )
        print(json.dumps({"passed": False, "base_url": BASE_URL, "records": records}, indent=2, sort_keys=True))
        print("LIVE_THREAD_B_T0_T3: FAIL")
        return 1


if __name__ == "__main__":
    sys.exit(main())
