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
MCP Server Implementation

License: Apache 2.0
Ownership: Cloud Dog
Description: Model Context Protocol server for agent-to-agent interactions

Related Requirements: FR1.7, FR1.25
Related Tasks: T039, T063
Related Architecture: CC1.1.3
Related Tests: ST1.2, AT1.23

Recent Changes:
- Initial implementation
"""

import asyncio
import json
import sys
import time
import uuid
from typing import Optional, Dict, Any, List
from cloud_dog_api_kit import create_app
from cloud_dog_api_kit.mcp import InMemoryAsyncJobStore, LegacySSEConfig, register_mcp_routes
from cloud_dog_api_kit.mcp import transport as mcp_transport
from cloud_dog_api_kit.middleware.timeout import TimeoutMiddleware
from fastapi import Request

from src.servers.base import BaseServer
from src.config.loader import get_config
from src.core.session.manager import SessionManager
from src.core.llm.manager import LLMManager
from src.servers.mcp.tools import MCPTools
from src.utils.logger import get_logger

logger = get_logger(__name__)


class MCPToolAuthMiddleware:
    """EA1 (W28C-1704 / 1601-C): authentication gate for MCP tool dispatch.

    Before W28C-1704 the MCP server had NO auth middleware: an anonymous caller
    reached ``_run_tool_call`` and ``_resolve_auth_role`` defaulted the missing
    principal to role ``user`` (which holds expert:tool:read+execute), so every
    non-admin tool was reachable anonymously (the 340-session anon leak).

    This pure-ASGI middleware authenticates every MCP request
    (the JSON-RPC ``/mcp`` endpoint and the bespoke ``/mcp/<tool>``
    REST routes) via ``X-API-Key`` — a valid user key (DB) OR the configured
    expert-agent service/admin key. Anonymous callers receive ``401`` BEFORE any
    tool runs. Health stays open; MCP transport POSTs require authentication
    before discovery or tool dispatch.
    """

    _OPEN_PATHS = {"/health", "/mcp/health", "/mcp/tools"}

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope.get("type") != "http":
            return await self.app(scope, receive, send)
        path = (scope.get("path") or "/").rstrip("/") or "/"
        if path in self._OPEN_PATHS:
            return await self.app(scope, receive, send)

        is_jsonrpc = path == "/mcp" or path.endswith("/mcp")
        is_bespoke_tool = path.startswith("/mcp/")
        if not (is_jsonrpc or is_bespoke_tool):
            return await self.app(scope, receive, send)

        method = scope.get("method", "GET")
        body = b""
        if method in ("POST", "PUT", "PATCH"):
            more = True
            while more:
                message = await receive()
                body += message.get("body", b"")
                more = message.get("more_body", False)

        if self._requires_auth(is_jsonrpc, body) and not self._authenticate(scope):
            return await self._send_401(send)

        if method in ("POST", "PUT", "PATCH"):
            replayed = {"sent": False}

            async def _replay():
                if not replayed["sent"]:
                    replayed["sent"] = True
                    return {"type": "http.request", "body": body, "more_body": False}
                return {"type": "http.disconnect"}

            return await self.app(scope, _replay, send)
        return await self.app(scope, receive, send)

    @staticmethod
    def _requires_auth(is_jsonrpc: bool, body: bytes) -> bool:
        if is_jsonrpc:
            return True
        # bespoke /mcp/<tool> dispatch route (already filtered to /mcp/* non-open)
        return True

    @staticmethod
    def _authenticate(scope) -> bool:
        headers = {
            k.decode("latin-1").lower(): v.decode("latin-1")
            for k, v in scope.get("headers", [])
        }
        api_key = headers.get("x-api-key")
        if not api_key:
            return False
        # 1) configured expert-agent service/admin key(s)
        for cfg_key in ("api_key", "api_server.api_key", "mcp_server.api_key", "client_api.admin_api_key"):
            try:
                configured = get_config(cfg_key)
            except Exception:
                configured = None
            if configured and str(configured) == api_key:
                return True
        # 2) DB-backed user API key
        try:
            from src.database.connection import get_db
            from src.servers.api.auth import _validate_api_key_user

            db_gen = get_db()
            db = next(db_gen)
            try:
                user = _validate_api_key_user(str(api_key), db)
            finally:
                db.close()
            return bool(user and getattr(user, "enabled", False))
        except Exception as exc:  # pragma: no cover - auth resolution must fail closed
            logger.warning("MCP auth resolution error (failing closed): %s", exc)
            return False

    @staticmethod
    async def _send_401(send) -> None:
        payload = json.dumps(
            {
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32001,
                    "message": "Unauthorized: authentication required for MCP tool calls",
                },
            }
        ).encode("utf-8")
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(payload)).encode("latin-1")),
                ],
            }
        )
        await send({"type": "http.response.body", "body": payload})


# --- PS-50 MCP compliance: per-tool RBAC permission map ---
_TOOL_PERMISSION_MAP: Dict[str, str] = {
    # Read/query tools — all authenticated roles
    "chat": "expert:tool:execute",
    "start_session": "expert:tool:execute",
    "resume_session": "expert:tool:execute",
    "end_session": "expert:tool:execute",
    "list_sessions": "expert:tool:read",
    "session_status": "expert:tool:read",
    "get_history": "expert:tool:read",
    "list_experts": "expert:tool:read",
    "get_expert": "expert:tool:read",
    "vector_search": "expert:tool:read",
    "vector_add": "expert:tool:execute",
    "get_session_by_key": "expert:tool:read",
    "get_history_by_key": "expert:tool:read",
    "share_session": "expert:tool:execute",
    "unshare_session": "expert:tool:execute",
    "summarize_session": "expert:tool:execute",
    "get_summaries": "expert:tool:read",
    "execute_tool": "expert:tool:execute",
    "run_research_cycle": "expert:tool:execute",
    "run_research_document": "expert:tool:execute",
    "get_research_document_status": "expert:tool:read",
    "list_services": "expert:tool:read",
    "invoke_service_tool": "expert:tool:execute",
    "code_execute": "expert:tool:execute",
    # Admin tools — admin role only
    "admin_list_experts": "expert:admin:*",
    "admin_create_expert": "expert:admin:*",
    "admin_update_expert": "expert:admin:*",
    "admin_delete_expert": "expert:admin:*",
    "admin_list_users": "expert:admin:*",
    "admin_create_api_key": "expert:admin:*",
    "admin_revoke_api_key": "expert:admin:*",
}


class MCPServer(BaseServer):
    """Model Context Protocol server."""

    def __init__(self):
        super().__init__("MCP Server", "mcp_server")
        self.transport = get_config("mcp_server.transport")  # sse or stdio
        if not self.transport:
            raise RuntimeError("mcp_server.transport not configured")
        self.protocol_version = str(get_config("mcp_server.protocol_version") or "2024-11-05")
        self.app = self._create_platform_app()
        # EA1 (W28C-1704 / 1601-C): gate anonymous MCP tool dispatch before any
        # tool runs. Must wrap the app before the transport routes are registered.
        self.app.add_middleware(MCPToolAuthMiddleware)
        self._remove_platform_health_routes()
        self._configure_platform_timeout()
        self.session_manager = SessionManager()
        self.llm_manager = LLMManager()
        self.tools = MCPTools()
        self._server_task: Optional[asyncio.Task] = None
        self._stopping = False
        self._async_job_store = InMemoryAsyncJobStore()
        # Keep stdio JSON-RPC state local to the stdio transport helper.
        self._rpc_sessions: Dict[str, Dict[str, Any]] = {}
        self._async_jobs: Dict[str, Dict[str, Any]] = {}
        self._register_routes()
        self._register_platform_transport()
        self._register_mcp_contract()

    def _create_platform_app(self):
        """Create MCP app via cloud_dog_api_kit across package versions."""
        kwargs = {
            "title": "Expert Agent MCP Server",
            "version": "0.1.0",
            "description": "Model Context Protocol server for Expert Agent",
            "cors_origins": ["*"],
        }
        try:
            return create_app(**kwargs, register_signal_handlers_on_startup=False)
        except TypeError as exc:
            if "register_signal_handlers_on_startup" not in str(exc):
                raise
            return create_app(**kwargs)

    def _remove_platform_health_routes(self) -> None:
        """Keep existing /health and /mcp/health contracts stable."""
        health_paths = {"/health", "/ready", "/live", "/status"}
        self.app.router.routes = [
            route
            for route in self.app.router.routes
            if getattr(route, "path", None) not in health_paths
        ]

    def _configure_platform_timeout(self) -> None:
        """Align API kit timeout middleware with project timeout settings."""
        raw_timeout = get_config("expert.test.http_timeout_seconds")
        if raw_timeout is None:
            raw_timeout = get_config("test.http_timeout_seconds")
        try:
            timeout_seconds = float(raw_timeout)
        except (TypeError, ValueError):
            timeout_seconds = 300.0
        if timeout_seconds <= 0:
            timeout_seconds = 300.0

        for middleware in self.app.user_middleware:
            if middleware.cls is TimeoutMiddleware:
                middleware.kwargs["timeout_seconds"] = timeout_seconds
                return

    def _tool_catalog(self) -> List[Dict[str, Any]]:
        return [
            {"name": "chat", "description": "Chat tool for conversation initiation"},
            {"name": "start_session", "description": "Start a new session"},
            {"name": "resume_session", "description": "Resume an existing session"},
            {"name": "end_session", "description": "End a session"},
            {"name": "list_sessions", "description": "List sessions"},
            {"name": "session_status", "description": "Get session status"},
            {"name": "get_history", "description": "Get session history"},
            {"name": "list_experts", "description": "List expert configurations"},
            {"name": "get_expert", "description": "Get expert configuration"},
            {"name": "admin_list_experts", "description": "Admin list expert configurations"},
            {"name": "admin_create_expert", "description": "Admin create expert configuration"},
            {"name": "admin_update_expert", "description": "Admin update expert configuration"},
            {"name": "admin_delete_expert", "description": "Admin delete expert configuration"},
            {"name": "admin_list_users", "description": "Admin list users"},
            {"name": "admin_create_api_key", "description": "Admin create API key"},
            {"name": "admin_revoke_api_key", "description": "Admin revoke API key"},
            {"name": "vector_search", "description": "Search vector store"},
            {"name": "vector_add", "description": "Add documents to vector store"},
            {"name": "get_session_by_key", "description": "Get session by session key (AT1.11)"},
            {"name": "get_history_by_key", "description": "Get history by history key (AT1.11)"},
            {"name": "share_session", "description": "Share session with users/groups (AT1.11)"},
            {
                "name": "unshare_session",
                "description": "Unshare session with users/groups (AT1.11)",
            },
            {"name": "summarize_session", "description": "Trigger session summarization (AT1.11)"},
            {"name": "get_summaries", "description": "Get all summaries for a session (AT1.11)"},
            {"name": "execute_tool", "description": "Transactional expert execution"},
            {"name": "run_research_cycle",
             "description": "Web-grounded, self-pruning daily research loop for a topic "
                            "(search->crawl->ingest->rank->prune->grounded brief->deliver)"},
            {"name": "run_research_document",
             "description": "Layered scheduled validated demo: deterministic per-day target -> "
                            "web-research source pool -> full-depth W28M-1604 grounded report "
                            "(>=0.9x depth, tables, [S] citations, 26->27 correction) -> Drive+notify+git "
                            "(async by default; returns run_id)"},
            {"name": "get_research_document_status",
             "description": "Poll the status/result of an async run_research_document run by run_id"},
            {"name": "list_services", "description": "List bound services for an expert"},
            {
                "name": "invoke_service_tool",
                "description": "Invoke a tool on a bound external service",
            },
            {
                "name": "code_execute",
                "description": "Run code on the code-runner service over A2A (analyst reasoning tool)",
            },
        ]

    def _register_mcp_contract(self) -> None:
        """Register tools via cloud_dog_api_kit.mcp for PS-50 compliance."""
        try:
            from cloud_dog_api_kit.mcp.contract import register_mcp_contract
            tool_registry = {
                tool["name"]: {"description": tool["description"], "handler": lambda **kw: kw}
                for tool in self._tool_catalog()
            }
            transport = str(self.transport).strip().lower()
            contract_modes = ["stdio"] if transport == "stdio" else self._transport_modes()
            register_mcp_contract(self.app, tool_registry, transport_modes=contract_modes)
            logger.info(f"MCP contract registered via cloud_dog_api_kit ({len(tool_registry)} tools)")
        except Exception as exc:
            logger.warning("cloud_dog_api_kit MCP contract registration skipped: %s", exc)

    def _transport_modes(self) -> List[str]:
        """Return the service's supported MCP transport modes."""
        return ["streamable_http", "http_jsonrpc", "legacy_sse"]

    def _build_tool_registry(self) -> Dict[str, Dict[str, Any]]:
        """Expose the MCP tool dispatch through the shared transport helper."""

        def _make_handler(tool_name: str):
            async def _handler(payload: Dict[str, Any], request: Request) -> Dict[str, Any]:
                if not isinstance(payload, dict):
                    payload = {}
                return await self._run_tool_call(tool_name, payload)

            return _handler

        registry: Dict[str, Dict[str, Any]] = {}
        for tool in self._tool_catalog():
            registry[tool["name"]] = {
                "description": tool["description"],
                "handler": _make_handler(tool["name"]),
                "input_schema": {"type": "object", "properties": {}},
            }
        return registry

    def _register_platform_transport(self) -> None:
        """Adopt the shared API-kit MCP transport routes for HTTP/SSE modes."""
        self._patch_platform_tool_payload_contract()
        register_mcp_routes(
            self.app,
            self._build_tool_registry(),
            transport_modes=self._transport_modes(),
            async_job_store=self._async_job_store,
            async_job_status_path="/jobs/{job_id}",
            legacy_sse=LegacySSEConfig(
                sse_path="/sse",
                message_path="/message",
                session_header="Mcp-Session-Id",
            ),
            session_termination_mode="200_json",
            error_response_mode="jsonrpc_200",
            capabilities_override={"tools": {}},
        )

    @staticmethod
    def _patch_platform_tool_payload_contract() -> None:
        """Backfill structuredContent on older API-kit MCP transport builds."""
        formatter = getattr(mcp_transport, "_mcp_tool_call_payload", None)
        if formatter is None or getattr(formatter, "_expert_agent_patched", False):
            return

        def _patched_tool_payload(result: Any) -> Dict[str, Any]:
            payload = formatter(result)
            if not isinstance(payload, dict) or "structuredContent" in payload:
                return payload

            data: Any = result
            if isinstance(result, dict):
                if result.get("data") is not None:
                    data = result.get("data")
                elif result.get("result") is not None:
                    data = result.get("result")
                elif result.get("error") is not None:
                    data = result.get("error")

            if isinstance(data, (dict, list)):
                payload = dict(payload)
                payload["structuredContent"] = data
            return payload

        setattr(_patched_tool_payload, "_expert_agent_patched", True)
        mcp_transport._mcp_tool_call_payload = _patched_tool_payload

    @staticmethod
    def _jsonrpc_error(request_id: Any, code: int, message: str) -> Dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": {"code": int(code), "message": str(message)},
        }

    @staticmethod
    def _jsonrpc_result(request_id: Any, result: Dict[str, Any]) -> Dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _resolve_auth_role(self, arguments: Dict[str, Any]) -> tuple[str, str]:
        """Resolve MCP auth context to a principal and effective role."""
        auth_context = (arguments or {}).get("auth_context") or {}
        requested_role = str(auth_context.get("role") or "user").strip().lower() or "user"
        api_key = auth_context.get("x_api_key") or auth_context.get("api_key")
        if api_key:
            try:
                from src.database.connection import get_db
                from src.servers.api.auth import _validate_api_key_user

                db_gen = get_db()
                db = next(db_gen)
                try:
                    user = _validate_api_key_user(str(api_key), db)
                finally:
                    db.close()
                if user and getattr(user, "enabled", False):
                    principal = str(getattr(user, "id", None) or getattr(user, "username", "") or api_key)
                    role = str(getattr(user, "role", None) or requested_role).strip().lower() or "user"
                    return principal, role
            except Exception as exc:
                logger.warning("Failed to resolve MCP auth role from API key: %s", exc)

        principal = str(
            auth_context.get("user_id")
            or auth_context.get("x_api_key")
            or auth_context.get("api_key")
            or f"role:{requested_role}"
        )
        return principal, requested_role

    def _enforce_tool_rbac(self, tool_name: str, arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """PS-50: Per-tool RBAC enforcement via cloud_dog_idam.rbac.RBACEngine."""
        required_permission = _TOOL_PERMISSION_MAP.get(tool_name)
        if not required_permission:
            return None  # Unknown tool — will be caught later
        from cloud_dog_idam.rbac import RBACEngine
        engine = RBACEngine(role_permissions={
            "admin": {"expert:admin:*", "expert:tool:read", "expert:tool:execute"},
            "owner": {"expert:tool:read", "expert:tool:execute", "expert:config:write"},
            "user": {"expert:tool:read", "expert:tool:execute"},
            "viewer": {"expert:tool:read"},
        })
        principal, role = self._resolve_auth_role(arguments)
        engine.assign_role_to_user(principal, role)
        if not engine.has_permission(principal, required_permission):
            logger.warning("RBAC denied: tool=%s permission=%s role=%s", tool_name, required_permission, role)
            return {"error": f"Permission denied: {required_permission}", "code": -32603}
        return None

    def _audit_tool_call(self, tool_name: str, arguments: Dict[str, Any], result: Dict[str, Any], duration_ms: float) -> None:
        """PS-50: Audit log every MCP tool call."""
        try:
            from cloud_dog_logging import get_audit_logger
            audit = get_audit_logger("mcp_tool_audit")
            auth_context = (arguments or {}).get("auth_context") or {}
            audit.info(
                "mcp_tool_call",
                extra={
                    "service": "expert-agent",
                    "tool_name": tool_name,
                    "actor": str(auth_context.get("user_id") or auth_context.get("x_api_key") or "anonymous"),
                    "outcome": "error" if "error" in result else "success",
                    "duration_ms": round(duration_ms, 1),
                },
            )
        except Exception:
            pass  # Audit failure must not break tool execution

    async def _run_tool_call(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatch with RBAC + audit wrapping (PS-50)."""
        # PS-50: Per-tool RBAC enforcement
        rbac_denial = self._enforce_tool_rbac(tool_name, arguments)
        if rbac_denial is not None:
            self._audit_tool_call(tool_name, arguments, rbac_denial, 0)
            return rbac_denial
        _t0 = time.monotonic()
        result = await self._dispatch_tool(tool_name, arguments)
        self._audit_tool_call(tool_name, arguments, result, (time.monotonic() - _t0) * 1000)
        return result

    async def _dispatch_tool(self, tool_name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        args = arguments or {}
        if tool_name == "chat":
            return await self.tools.chat_tool(
                session_id=args.get("session_id"),
                message=args.get("message"),
                temperature=args.get("temperature"),
                top_k=args.get("top_k"),
                top_p=args.get("top_p"),
                max_tokens=args.get("max_tokens"),
                response_format=args.get("response_format"),
                language=args.get("language"),
                system_prompt=args.get("system_prompt"),
            )
        if tool_name == "start_session":
            return self.tools.start_session_tool(
                user_id=args.get("user_id"),
                expert_config_id=args.get("expert_config_id"),
                title=args.get("title"),
                channel_id=args.get("channel_id"),
            )
        if tool_name == "resume_session":
            return self.tools.resume_session_tool(args.get("session_id"))
        if tool_name == "end_session":
            return self.tools.end_session_tool(args.get("session_id"))
        if tool_name == "list_sessions":
            return self.tools.list_sessions_tool(
                user_id=args.get("user_id"), status=args.get("status")
            )
        if tool_name == "session_status":
            return self.tools.session_status_tool(args.get("session_id"))
        if tool_name == "get_history":
            return self.tools.get_history_tool(args.get("session_id"), limit=args.get("limit"))
        if tool_name == "list_experts":
            return self.tools.list_experts_tool()
        if tool_name == "get_expert":
            return self.tools.get_expert_tool(args.get("expert_id"))
        if tool_name == "admin_list_experts":
            return self.tools.admin_list_experts_tool(
                auth_context=args.get("auth_context"),
                enabled_only=bool(args.get("enabled_only", False)),
                skip=int(args.get("skip", 0) or 0),
                limit=int(args.get("limit", 100) or 100),
            )
        if tool_name == "admin_create_expert":
            return self.tools.admin_create_expert_tool(
                name=args.get("name"),
                title=args.get("title"),
                description=args.get("description"),
                auth_context=args.get("auth_context"),
                llm_provider=args.get("llm_provider"),
                llm_model=args.get("llm_model"),
                llm_base_url=args.get("llm_base_url"),
                llm_params=args.get("llm_params"),
                prompt_template=args.get("prompt_template"),
                tools=args.get("tools"),
                enabled=bool(args.get("enabled", True)),
                access_control=args.get("access_control"),
            )
        if tool_name == "admin_update_expert":
            update_args = dict(args)
            update_args.pop("auth_context", None)
            update_args.pop("expert_id", None)
            return self.tools.admin_update_expert_tool(
                args.get("expert_id"),
                auth_context=args.get("auth_context"),
                **update_args,
            )
        if tool_name == "admin_delete_expert":
            return self.tools.admin_delete_expert_tool(
                args.get("expert_id"), auth_context=args.get("auth_context")
            )
        if tool_name == "admin_list_users":
            return self.tools.admin_list_users_tool(
                auth_context=args.get("auth_context"),
                enabled_only=bool(args.get("enabled_only", False)),
                role=args.get("role"),
            )
        if tool_name == "admin_create_api_key":
            return self.tools.admin_create_api_key_tool(
                auth_context=args.get("auth_context"),
                user_id=args.get("user_id"),
                name=args.get("name"),
                expires_days=args.get("expires_days"),
                read_logs=bool(args.get("read_logs", True)),
                read_histories=bool(args.get("read_histories", True)),
                read_channels=bool(args.get("read_channels", True)),
            )
        if tool_name == "admin_revoke_api_key":
            return self.tools.admin_revoke_api_key_tool(
                args.get("key_id"), auth_context=args.get("auth_context")
            )
        if tool_name == "vector_search":
            return await self.tools.search_vector_tool(
                query=args.get("query"),
                collection=args.get("collection"),
                n_results=args.get("n_results", 5),
                vector_store_name=args.get("vector_store_name") or args.get("store_name") or args.get("store_id") or "_DEFAULT_",
            )
        if tool_name == "vector_add":
            return await self.tools.add_to_vector_tool(
                documents=args.get("documents"),
                collection=args.get("collection"),
                vector_store_name=args.get("vector_store_name") or args.get("store_name") or args.get("store_id") or "_DEFAULT_",
                metadatas=args.get("metadatas"),
            )
        if tool_name == "get_session_by_key":
            return self.tools.get_session_by_key_tool(args.get("session_key"))
        if tool_name == "get_history_by_key":
            return self.tools.get_history_by_key_tool(args.get("history_key"))
        if tool_name == "share_session":
            return self.tools.share_session_tool(
                session_id=args.get("session_id"),
                user_ids=args.get("user_ids"),
                group_ids=args.get("group_ids"),
            )
        if tool_name == "unshare_session":
            return self.tools.unshare_session_tool(
                session_id=args.get("session_id"),
                user_ids=args.get("user_ids"),
                group_ids=args.get("group_ids"),
            )
        if tool_name == "summarize_session":
            return await self.tools.summarize_session_tool(
                session_id=args.get("session_id"),
                preserve_recent=args.get("preserve_recent", 5),
                max_tokens=args.get("max_tokens"),
            )
        if tool_name == "get_summaries":
            return self.tools.get_summaries_tool(args.get("session_id"))
        if tool_name == "execute_tool":
            return await self.tools.execute_tool(
                expert_id=args.get("expert_id"),
                input_text=args.get("input_text"),
                parameters=args.get("parameters"),
                context=args.get("context"),
                auth_context=args.get("auth_context"),
            )
        if tool_name == "run_research_cycle":
            from src.core.agentic.research_cycle import run_research_cycle
            return await run_research_cycle(
                topic=args.get("topic"),
                deliver=bool(args.get("deliver", True)),
                dry_run=bool(args.get("dry_run", False)),
                actor=args.get("actor") or "research-loop",
                slack_endpoint=args.get("slack_endpoint"),
            )
        if tool_name == "run_research_document":
            from src.core.agentic.research_document import run_research_document
            return await run_research_document(
                topic=args.get("topic"),
                target=args.get("target"),
                deliver=bool(args.get("deliver", True)),
                async_mode=bool(args.get("async_mode", True)),
                slack_endpoint=args.get("slack_endpoint"),
                date_str=args.get("date_str"),
                refresh_sources=bool(args.get("refresh_sources", True)),
                actor=args.get("actor") or "research-document",
            )
        if tool_name == "get_research_document_status":
            from src.core.agentic.research_document import get_run_status
            return get_run_status(args.get("run_id"))
        if tool_name == "list_services":
            return await self.tools.list_services_tool(args.get("expert_id"))
        if tool_name == "invoke_service_tool":
            return await self.tools.invoke_service_tool(
                service_id=args.get("service_id"),
                tool_name=args.get("tool_name"),
                arguments=args.get("arguments"),
                auth_context=args.get("auth_context"),
                session_id=args.get("session_id"),
            )
        if tool_name == "code_execute":
            return await self.tools.code_execute_tool(
                code=args.get("code"),
                language=args.get("language"),
                task_id=args.get("task_id"),
                auth_context=args.get("auth_context"),
            )

        return {"error": f"Unknown tool: {tool_name}"}

    async def _execute_jsonrpc(
        self, payload: Dict[str, Any], session_id: Optional[str]
    ) -> Dict[str, Any]:
        request_id = payload.get("id")
        if payload.get("jsonrpc") != "2.0":
            return self._jsonrpc_error(request_id, -32600, "Invalid Request: jsonrpc must be '2.0'")
        method = payload.get("method")
        params = payload.get("params") or {}
        if not method:
            return self._jsonrpc_error(request_id, -32600, "Invalid Request: method is required")

        # Notification path
        if method == "notifications/initialized":
            if session_id and session_id in self._rpc_sessions:
                self._rpc_sessions[session_id]["initialized"] = True
            return {}

        if method == "initialize":
            negotiated = str(params.get("protocolVersion") or self.protocol_version)
            return self._jsonrpc_result(
                request_id,
                {
                    "protocolVersion": negotiated,
                    "capabilities": {"tools": {}, "resources": {}},
                    "serverInfo": {"name": "expert-agent-mcp-server", "version": "0.1.0"},
                },
            )

        if session_id and session_id not in self._rpc_sessions:
            return self._jsonrpc_error(request_id, -32001, "Invalid or expired MCP session")

        if method == "tools/list":
            tools = []
            for item in self._tool_catalog():
                tools.append(
                    {
                        "name": item["name"],
                        "description": item["description"],
                        "inputSchema": {"type": "object", "properties": {}},
                    }
                )
            return self._jsonrpc_result(request_id, {"tools": tools})

        if method == "tools/call":
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if not name:
                return self._jsonrpc_error(request_id, -32602, "Missing required param: name")

            # Async job mode: wait=false returns a reference and resolves through /jobs/{job_id}
            if arguments.get("wait") is False:
                job_id = f"job-{uuid.uuid4().hex[:12]}"
                guid = uuid.uuid4().hex[:8]
                self._async_jobs[job_id] = {"status": "running", "result": None, "error": None}

                async def _resolve_job():
                    try:
                        tool_result = await self._run_tool_call(name, arguments)
                        if isinstance(tool_result, dict) and tool_result.get("error"):
                            self._async_jobs[job_id] = {
                                "status": "failed",
                                "error": tool_result.get("error"),
                                "result": None,
                            }
                            return
                        self._async_jobs[job_id] = {
                            "status": "completed",
                            "error": None,
                            "result": {
                                "content": [{"type": "text", "text": json.dumps(tool_result)}],
                                "structuredContent": tool_result,
                            },
                        }
                    except Exception as exc:
                        self._async_jobs[job_id] = {
                            "status": "failed",
                            "error": str(exc),
                            "result": None,
                        }

                asyncio.create_task(_resolve_job())
                return self._jsonrpc_result(request_id, {"job_id": job_id, "guid": guid})

            tool_result = await self._run_tool_call(name, arguments)
            if isinstance(tool_result, dict) and tool_result.get("error"):
                return self._jsonrpc_error(request_id, -32602, str(tool_result.get("error")))

            return self._jsonrpc_result(
                request_id,
                {
                    "content": [{"type": "text", "text": json.dumps(tool_result)}],
                    "structuredContent": tool_result,
                },
            )

        return self._jsonrpc_error(request_id, -32601, f"Method not found: {method}")

    def _register_routes(self):
        """Register MCP routes."""

        @self.app.post("/mcp/chat")
        async def mcp_chat(request: Request):
            """MCP chat tool endpoint."""
            data = await request.json()
            session_id = data.get("session_id")
            message = data.get("message")

            if not session_id or not message:
                return {"error": "session_id and message required"}

            # Extract LLM parameters
            temperature = data.get("temperature")
            top_k = data.get("top_k")
            top_p = data.get("top_p")
            max_tokens = data.get("max_tokens")
            response_format = data.get("response_format")
            language = data.get("language")
            system_prompt = data.get("system_prompt")

            return await self.tools.chat_tool(
                session_id=session_id,
                message=message,
                temperature=temperature,
                top_k=top_k,
                top_p=top_p,
                max_tokens=max_tokens,
                response_format=response_format,
                language=language,
                system_prompt=system_prompt,
            )

        @self.app.post("/mcp/start_session")
        async def mcp_start_session(request: Request):
            """MCP start session tool."""
            data = await request.json()
            return self.tools.start_session_tool(
                user_id=data.get("user_id"),
                expert_config_id=data.get("expert_config_id"),
                title=data.get("title"),
                channel_id=data.get("channel_id"),
            )

        @self.app.post("/mcp/resume_session")
        async def mcp_resume_session(request: Request):
            """MCP resume session tool."""
            data = await request.json()
            return self.tools.resume_session_tool(data.get("session_id"))

        @self.app.post("/mcp/end_session")
        async def mcp_end_session(request: Request):
            """MCP end session tool."""
            data = await request.json()
            return self.tools.end_session_tool(data.get("session_id"))

        @self.app.get("/mcp/sessions")
        async def mcp_list_sessions(user_id: int = None, status: str = None):
            """MCP list sessions tool."""
            return self.tools.list_sessions_tool(user_id=user_id, status=status)

        @self.app.get("/mcp/session/{session_id}/status")
        async def mcp_session_status(session_id: int):
            """MCP session status tool."""
            return self.tools.session_status_tool(session_id)

        @self.app.get("/mcp/session/{session_id}/history")
        async def mcp_get_history(session_id: int, limit: int = None):
            """MCP get history tool."""
            return self.tools.get_history_tool(session_id, limit=limit)

        @self.app.get("/mcp/experts")
        async def mcp_list_experts():
            """MCP list experts tool."""
            return self.tools.list_experts_tool()

        @self.app.get("/mcp/expert/{expert_id}")
        async def mcp_get_expert(expert_id: int):
            """MCP get expert tool."""
            return self.tools.get_expert_tool(expert_id)

        @self.app.post("/mcp/vector/search")
        async def mcp_vector_search(request: Request):
            """MCP vector search tool."""
            data = await request.json()
            return await self.tools.search_vector_tool(
                query=data.get("query"),
                collection=data.get("collection"),
                n_results=data.get("n_results", 5),
                vector_store_name=data.get("vector_store_name") or data.get("store_name") or data.get("store_id") or "_DEFAULT_",
            )

        @self.app.post("/mcp/vector/add")
        async def mcp_vector_add(request: Request):
            """MCP vector add tool."""
            data = await request.json()
            return await self.tools.add_to_vector_tool(
                documents=data.get("documents"),
                collection=data.get("collection"),
                vector_store_name=data.get("vector_store_name") or data.get("store_name") or data.get("store_id") or "_DEFAULT_",
                metadatas=data.get("metadatas"),
            )

        @self.app.get("/mcp/health")
        async def mcp_health():
            """MCP health check."""
            return {
                "status": "healthy",
                "service": "mcp",
                "application": "expert-agent-mcp-server",
                "version": "0.1.0",
                "transport": self.transport,
                "protocol_version": self.protocol_version,
                "env": {
                    "config_env_file": get_config("expert.env_file"),
                    "secrets_env_files": get_config("expert.env_secrets_files"),
                    "testing": get_config("test.enabled"),
                },
            }

        @self.app.get("/health")
        async def health():
            """Compatibility health check (server root)."""
            return await mcp_health()

        # AT1.11: Session key and history key endpoints

        @self.app.get("/mcp/session/key/{session_key}")
        async def mcp_get_session_by_key(session_key: str):
            """MCP get session by key tool."""
            return self.tools.get_session_by_key_tool(session_key)

        @self.app.get("/mcp/history/key/{history_key}")
        async def mcp_get_history_by_key(history_key: str):
            """MCP get history by key tool."""
            return self.tools.get_history_by_key_tool(history_key)

        @self.app.post("/mcp/session/{session_id}/share")
        async def mcp_share_session(session_id: int, request: Request):
            """MCP share session tool."""
            data = await request.json()
            return self.tools.share_session_tool(
                session_id=session_id,
                user_ids=data.get("user_ids"),
                group_ids=data.get("group_ids"),
            )

        @self.app.post("/mcp/session/{session_id}/unshare")
        async def mcp_unshare_session(session_id: int, request: Request):
            """MCP unshare session tool."""
            data = await request.json()
            return self.tools.unshare_session_tool(
                session_id=session_id,
                user_ids=data.get("user_ids"),
                group_ids=data.get("group_ids"),
            )

        @self.app.post("/mcp/session/{session_id}/summarize")
        async def mcp_summarize_session(session_id: int, request: Request):
            """MCP summarize session tool."""
            data = await request.json()
            return await self.tools.summarize_session_tool(
                session_id=session_id,
                preserve_recent=data.get("preserve_recent", 5),
                max_tokens=data.get("max_tokens"),
            )

        @self.app.get("/mcp/session/{session_id}/summaries")
        async def mcp_get_summaries(session_id: int):
            """MCP get summaries tool."""
            return self.tools.get_summaries_tool(session_id)

        @self.app.get("/mcp/tools")
        async def mcp_list_tools():
            """List available MCP tools."""
            return {"tools": self._tool_catalog()}

    async def _run_stdio_loop(self) -> None:
        """
        Minimal stdio JSON-RPC loop for MCP clients.
        Reads one JSON-RPC payload per line from stdin and writes one JSON response line to stdout.
        """
        session_id = "stdio-session"
        self._rpc_sessions.setdefault(session_id, {"initialized": False})
        while not self._shutdown_event.is_set():
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                await asyncio.sleep(0.05)
                continue
            raw = line.strip()
            if not raw:
                continue
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError:
                response = self._jsonrpc_error(None, -32700, "Parse error")
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
                continue

            response = await self._execute_jsonrpc(payload, session_id)
            if response:
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()

    async def start(self):
        """Start the MCP server."""
        import uvicorn

        logger.info(
            f"Starting MCP server with {self.transport} transport on {self.host}:{self.port}"
        )
        self._stopping = False
        if str(self.transport).lower() == "stdio":
            self._stdio_task = asyncio.create_task(self._run_stdio_loop())
            return
        config = uvicorn.Config(app=self.app, host=self.host, port=int(self.port), log_level="info")
        self._server = uvicorn.Server(config)
        self._server_task = asyncio.create_task(self._server.serve())
        self._server_task.add_done_callback(self._on_server_task_done)
        await asyncio.sleep(0.5)
        if self._server_task.done():
            exc = self._server_task.exception()
            raise RuntimeError(f"MCP server failed during startup: {exc}")

    def _on_server_task_done(self, task: asyncio.Task) -> None:
        """Detect unexpected uvicorn task termination."""
        if self._stopping:
            return
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            exc = None
        if exc:
            logger.error(f"MCP server task exited unexpectedly: {exc}", exc_info=True)
        else:
            logger.error("MCP server task exited unexpectedly without error")
        self._shutdown_event.set()

    async def stop(self):
        """Stop the MCP server."""
        self._stopping = True
        if hasattr(self, "_stdio_task") and self._stdio_task:
            self._stdio_task.cancel()
        if hasattr(self, "_server") and self._server:
            self._server.should_exit = True
        if self._server_task and not self._server_task.done():
            try:
                await asyncio.wait_for(self._server_task, timeout=15)
            except asyncio.TimeoutError:
                logger.warning("Timed out waiting for MCP server task shutdown; cancelling task")
                self._server_task.cancel()
        logger.info("Stopping MCP server")

    async def health_check(self) -> bool:
        """Check if server is healthy."""
        return self.is_running()
