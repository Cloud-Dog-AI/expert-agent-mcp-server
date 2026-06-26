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

"""Service composition support for expert orchestration."""

from __future__ import annotations

import json
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy.orm import Session

from src.config.loader import get_config
from src.core.http import get_shared_async_client
from src.core.reliability.circuit_breaker import CircuitBreaker
from src.database.connection import get_db
from src.database.models import ExternalService, ServiceBinding, ServiceInvocationLog
from src.utils.logger import get_logger

logger = get_logger(__name__)


class ServiceCompositionManager:
    """Discover and invoke external services bound to experts."""

    _tool_cache: Dict[int, Tuple[float, List[Dict[str, Any]]]] = {}
    _circuit_breakers: Dict[int, CircuitBreaker] = {}

    def __init__(self, db: Optional[Session] = None, client: Optional[httpx.AsyncClient] = None):
        self.db = db
        self.client = client or get_shared_async_client(timeout=30.0)

    def _get_db(self) -> Session:
        if self.db:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    @staticmethod
    def _parse_json(raw: Optional[str]) -> Dict[str, Any]:
        if not raw:
            return {}
        try:
            return json.loads(raw) or {}
        except Exception:
            return {}

    def _get_circuit_breaker(self, binding: Optional[ServiceBinding]) -> CircuitBreaker:
        service_id = int(binding.service_id if binding else 0)
        threshold = int(
            (binding.circuit_breaker_threshold if binding else None)
            or get_config("service_composition.circuit_breaker_threshold")
            or 5
        )
        reset_timeout = int(get_config("service_composition.circuit_breaker_reset") or 60)
        breaker = self._circuit_breakers.get(service_id)
        if breaker is None:
            breaker = CircuitBreaker(
                failure_threshold=threshold,
                timeout_seconds=reset_timeout,
            )
            self._circuit_breakers[service_id] = breaker
        return breaker

    @staticmethod
    def _resolve_health_url(service: ExternalService) -> str:
        endpoint = str(service.endpoint_url).rstrip("/")
        if endpoint.endswith("/mcp"):
            return endpoint[: -len("/mcp")] + "/health"
        if endpoint.endswith("/a2a"):
            return endpoint[: -len("/a2a")] + "/a2a/health"
        if endpoint.endswith("/api"):
            return endpoint + "/health"
        return endpoint + "/health"

    @staticmethod
    def _tool_payload_to_list(payload: Any) -> List[Dict[str, Any]]:
        if isinstance(payload, dict):
            if isinstance(payload.get("tools"), list):
                return payload["tools"]
            if isinstance(payload.get("result"), dict) and isinstance(
                payload["result"].get("tools"), list
            ):
                return payload["result"]["tools"]
        return []

    @staticmethod
    def _parse_mcp_response(response: httpx.Response) -> Dict[str, Any]:
        content_type = str(response.headers.get("content-type") or "").lower()
        text = response.text.strip()

        if "application/json" in content_type:
            return response.json()

        if "text/event-stream" in content_type or text.startswith("data:") or "event:" in text:
            for raw_line in text.splitlines():
                line = raw_line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[len("data:") :].strip()
                if not payload:
                    continue
                return json.loads(payload)
            raise ValueError("MCP event stream did not contain a JSON data payload")

        return response.json()

    @staticmethod
    def _resolve_credential(service: ExternalService, auth_config: Dict[str, Any]) -> Optional[str]:
        """Resolve an outbound credential WITHOUT storing the secret in the DB (EA6).

        Precedence:
          1. an explicit literal ``value`` on the service's auth_config (legacy);
          2. a ``config_key`` on the auth_config, resolved via cloud_dog_config
             (so the value can be a ``${vault.dev.services.<svc>.api_key}`` expression);
          3. the per-service convention key ``service_credentials.<service_name>.api_key``
             (the deployment env maps these to ``${vault.dev.services.<svc>.api_key}``).
        This keeps the api_key in Vault (resolved at runtime) rather than in the
        expert_configs / external_services tables (RULES §2.3, §1.4).
        """
        literal = auth_config.get("value")
        if literal:
            return str(literal)
        config_key = auth_config.get("config_key")
        if config_key:
            resolved = get_config(str(config_key))
            if resolved:
                return str(resolved)
        if service.name:
            resolved = get_config(f"service_credentials.{service.name}.api_key")
            if resolved:
                return str(resolved)
        return None

    def _auth_headers(self, service: ExternalService, auth_context: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        auth_config = self._parse_json(service.auth_config_json)
        auth_type = str(auth_config.get("type") or auth_config.get("auth_type") or "").lower()
        resolved_value = self._resolve_credential(service, auth_config)
        if auth_type == "api_key" and resolved_value:
            headers["X-API-Key"] = resolved_value
        elif auth_type == "bearer" and resolved_value:
            headers["Authorization"] = f"Bearer {resolved_value}"
        if auth_type == "bearer" and auth_config.get("header_name") and resolved_value:
            header_name = str(auth_config["header_name"]).strip()
            header_scheme = str(auth_config.get("header_scheme") or "Bearer").strip()
            headers[header_name] = (
                resolved_value
                if not header_scheme
                else f"{header_scheme} {resolved_value}"
            )
        headers.setdefault("Accept", "application/json")
        if auth_context and auth_context.get("correlation_id"):
            headers["X-Correlation-ID"] = str(auth_context["correlation_id"])
        return headers

    def _binding_for_service(self, service_id: int) -> Optional[ServiceBinding]:
        db = self._get_db()
        return db.query(ServiceBinding).filter(ServiceBinding.service_id == service_id).first()

    def get_cached_tools(self, service_id: int) -> List[Dict[str, Any]]:
        """Return cached discovered tools without probing the remote service."""
        cached = self._tool_cache.get(service_id)
        if cached:
            return cached[1]

        db = self._get_db()
        service = db.query(ExternalService).filter(ExternalService.id == service_id).first()
        if not service:
            raise ValueError("Service not found")

        metadata = self._parse_json(service.metadata_json)
        tools = metadata.get("discovered_tools")
        if isinstance(tools, list):
            return tools
        return []

    async def health_check(self, service_id: int) -> Dict[str, Any]:
        db = self._get_db()
        service = db.query(ExternalService).filter(ExternalService.id == service_id).first()
        if not service:
            raise ValueError("Service not found")
        status = "unhealthy"
        detail = None
        try:
            response = await self.client.get(self._resolve_health_url(service), timeout=5.0)
            if response.status_code < 500:
                status = "healthy"
            detail = response.text[:200]
        except Exception as exc:
            detail = str(exc)
        service.health_status = status
        db.commit()
        return {"service_id": service_id, "health_status": status, "detail": detail}

    async def discover_tools(self, service_id: int) -> List[Dict[str, Any]]:
        now = time.time()
        ttl = int(get_config("service_composition.tool_discovery_cache_ttl") or 300)
        cached = self._tool_cache.get(service_id)
        if cached and now - cached[0] < ttl:
            return cached[1]

        db = self._get_db()
        service = db.query(ExternalService).filter(ExternalService.id == service_id).first()
        if not service:
            raise ValueError("Service not found")

        tools: List[Dict[str, Any]] = []
        metadata = self._parse_json(service.metadata_json)
        if service.type == "mcp":
            response = await self.client.post(
                service.endpoint_url,
                headers=self._auth_headers(service),
                json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
                timeout=10.0,
            )
            response.raise_for_status()
            tools = self._tool_payload_to_list(self._parse_mcp_response(response))
        else:
            tools = metadata.get("tools") or []

        metadata["discovered_tools"] = tools
        service.metadata_json = json.dumps(metadata)
        db.commit()
        self._tool_cache[service_id] = (now, tools)
        return tools

    async def get_available_tools(self, expert_config_id: int) -> List[Dict[str, Any]]:
        db = self._get_db()
        bindings = (
            db.query(ServiceBinding)
            .filter(
                ServiceBinding.expert_config_id == expert_config_id,
                ServiceBinding.enabled.is_(True),
            )
            .order_by(ServiceBinding.priority.asc(), ServiceBinding.id.asc())
            .all()
        )
        results: List[Dict[str, Any]] = []
        for binding in bindings:
            tools = await self.discover_tools(binding.service_id)
            results.append(
                {
                    "binding_id": binding.id,
                    "service_id": binding.service_id,
                    "service_name": binding.service.name if binding.service else None,
                    "service_type": binding.service.type if binding.service else None,
                    "tools": tools,
                    "timeout_seconds": binding.timeout_seconds,
                    "priority": binding.priority,
                }
            )
        return results

    async def invoke_tool(
        self,
        service_id: int,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        auth_context: Optional[Dict[str, Any]] = None,
        session_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        db = self._get_db()
        service = db.query(ExternalService).filter(ExternalService.id == service_id).first()
        if not service:
            raise ValueError("Service not found")

        binding = self._binding_for_service(service_id)
        breaker = self._get_circuit_breaker(binding)
        timeout = float(
            (binding.timeout_seconds if binding and binding.timeout_seconds else None)
            or get_config("service_composition.invocation_timeout")
            or 30
        )
        started = time.perf_counter()
        health = await self.health_check(service_id)
        if health["health_status"] != "healthy":
            return {
                "service_id": service_id,
                "tool_name": tool_name,
                "status": "skipped",
                "detail": "Service unhealthy",
            }

        headers = self._auth_headers(service, auth_context=auth_context)
        payload_args = arguments or {}
        status = "error"
        result: Dict[str, Any]
        try:
            breaker.call(lambda: None)
            if service.type == "mcp":
                response = await self.client.post(
                    service.endpoint_url,
                    headers=headers,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {"name": tool_name, "arguments": payload_args},
                    },
                    timeout=timeout,
                )
                response.raise_for_status()
                payload = self._parse_mcp_response(response)
                if payload.get("error"):
                    raise RuntimeError(str(payload["error"]))
                result = payload.get("result") or {}
            else:
                response = await self.client.post(
                    service.endpoint_url.rstrip("/") + f"/{tool_name}",
                    headers=headers,
                    json={"arguments": payload_args, "auth_context": auth_context or {}},
                    timeout=timeout,
                )
                response.raise_for_status()
                result = response.json()
            status = "ok"
        except Exception as exc:
            logger.warning("Service invocation failed: %s", exc)
            result = {"error": str(exc)}
            status = "failed"
            breaker._record_failure()

        duration_ms = int((time.perf_counter() - started) * 1000)
        log_row = ServiceInvocationLog(
            session_id=session_id,
            service_id=service_id,
            tool_name=tool_name,
            response_status=status,
            duration_ms=duration_ms,
            request_payload_json=json.dumps(payload_args),
            response_payload_json=json.dumps(result),
            tokens_used=result.get("tokens_used") if isinstance(result, dict) else None,
        )
        db.add(log_row)
        db.commit()

        return {
            "service_id": service_id,
            "service_name": service.name,
            "service_type": service.type,
            "tool_name": tool_name,
            "status": status,
            "duration_ms": duration_ms,
            "result": result,
        }
