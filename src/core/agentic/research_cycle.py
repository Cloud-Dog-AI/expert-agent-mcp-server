# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""search-mcp research_stream consumer and chat-facing relay helpers."""

from __future__ import annotations

import asyncio
import inspect
import json
import time
import uuid
from typing import Any, AsyncIterator, Awaitable, Callable, Dict, Iterable, List, Optional

import httpx
from sqlalchemy.orm import Session

from src.config.loader import get_config
from src.core.audit.manager import AuditManager
from src.core.expert.research_expert import ensure_research_expert, select_research_plan
from src.core.service.composition import ServiceCompositionManager
from src.database.connection import get_db
from src.database.models import ExternalService
from src.utils.logger import get_logger

logger = get_logger(__name__)

ResearchEventCallback = Callable[[Dict[str, Any]], Optional[Awaitable[None]]]


def _normalise_stream_url(service: ExternalService) -> str:
    path = str(get_config("research.search_stream_path") or "/mcp/research/stream").strip()
    if not path.startswith("/"):
        path = "/" + path
    endpoint = str(service.endpoint_url).rstrip("/")
    if endpoint.endswith("/mcp") and path.startswith("/mcp/"):
        endpoint = endpoint[: -len("/mcp")]
    return endpoint + path


def _parse_mcp_payload(raw: Any) -> Any:
    """Unwrap MCP JSON/content/SSE envelopes into the inner tool payload."""
    value = raw
    for _ in range(5):
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("data:"):
                for line in text.splitlines():
                    if line.strip().startswith("data:"):
                        text = line.split(":", 1)[1].strip()
                        break
            try:
                value = json.loads(text)
                continue
            except Exception:
                return value
        if not isinstance(value, dict):
            return value
        if "result" in value and isinstance(value["result"], (dict, list, str)):
            value = value["result"]
            continue
        structured = value.get("structuredContent")
        if isinstance(structured, (dict, list, str)):
            value = structured
            continue
        blocks = value.get("content")
        if isinstance(blocks, list):
            next_value = None
            for block in blocks:
                if isinstance(block, dict) and "text" in block:
                    next_value = block["text"]
                    break
            if next_value is not None:
                value = next_value
                continue
        return value
    return value


def _sse_event_from_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    data = fields.get("data")
    payload: Dict[str, Any]
    if isinstance(data, dict):
        payload = dict(data)
    elif isinstance(data, str) and data.strip():
        try:
            parsed = json.loads(data)
            payload = parsed if isinstance(parsed, dict) else {"data": parsed}
        except json.JSONDecodeError:
            payload = {"data": data}
    else:
        payload = {}

    if fields.get("id") is not None and payload.get("id") is None:
        payload["id"] = fields["id"]
    if fields.get("event") and payload.get("type") is None:
        payload["type"] = fields["event"]
    return payload


def sse_frame(event: Dict[str, Any]) -> str:
    """Serialise a normalized research event as one SSE frame."""
    event_id = event.get("id") or event.get("sequence") or ""
    event_name = event.get("type") or "message"
    return (
        f"id: {event_id}\n"
        f"event: {event_name}\n"
        f"data: {json.dumps(event, default=str)}\n\n"
    )


async def _maybe_call(callback: Optional[ResearchEventCallback], event: Dict[str, Any]) -> None:
    if callback is None:
        return
    result = callback(event)
    if inspect.isawaitable(result):
        await result


def _config_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    return default


class ResearchCycleManager:
    """Consumes search-mcp streaming research and enriches image inputs."""

    def __init__(
        self,
        db: Optional[Session] = None,
        composition: Optional[ServiceCompositionManager] = None,
    ) -> None:
        self.db = db
        self.composition = composition or ServiceCompositionManager(db)

    def _get_db(self) -> Session:
        if self.db is not None:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    def _emit_audit(
        self,
        event_type: str,
        *,
        action: str,
        outcome: str,
        correlation_id: Optional[str],
        tenant_id: str,
        target: Dict[str, Any],
        user_id: Optional[Any] = None,
        role: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        try:
            payload: Dict[str, Any] = {
                "action": action,
                "outcome": outcome,
                "subject": {
                    "tenant_id": tenant_id,
                    "user_id": user_id,
                    "role": role or "system",
                },
                "target": target,
                "source_ip": (details or {}).get("source_ip"),
                "request_id": (details or {}).get("request_id"),
                "correlation_id": correlation_id,
            }
            if details:
                payload.update({k: v for k, v in details.items() if k not in payload})
            AuditManager(self._get_db()).log_event(event_type, details=payload)
        except Exception as exc:  # pragma: no cover - audit cannot break streams
            logger.warning("research cycle audit failed: %s", exc)

    async def _iter_sse_response(
        self,
        response: httpx.Response,
    ) -> AsyncIterator[Dict[str, Any]]:
        fields: Dict[str, Any] = {}
        async for raw_line in response.aiter_lines():
            line = raw_line.rstrip("\r")
            if line == "":
                if fields:
                    yield _sse_event_from_fields(fields)
                    fields = {}
                continue
            if line.startswith(":") or ":" not in line:
                continue
            name, value = line.split(":", 1)
            fields[name.strip()] = value.strip()
        if fields:
            yield _sse_event_from_fields(fields)

    async def stream_research(
        self,
        query: str,
        *,
        depth: Optional[str] = None,
        tenant_id: str = "default",
        correlation_id: Optional[str] = None,
        max_results: Optional[int] = None,
        query_languages: Optional[Iterable[str]] = None,
        target_languages: Optional[Iterable[str]] = None,
        synthesise_in: Optional[str] = None,
        auth_context: Optional[Dict[str, Any]] = None,
        on_event: Optional[ResearchEventCallback] = None,
        last_event_id: Optional[int] = None,
    ) -> AsyncIterator[Dict[str, Any]]:
        """Consume search-mcp SSE and yield normalized per-event dicts."""
        if not str(query or "").strip():
            raise ValueError("query is required")
        correlation_id = correlation_id or str(uuid.uuid4())
        plan = select_research_plan(
            query,
            budget={"max_results": max_results} if max_results is not None else None,
            requested_depth=depth,
        )
        service = self.composition.ensure_search_mcp_service()
        url = _normalise_stream_url(service)
        timeout = float(get_config("research.stream_timeout_seconds") or 300)
        max_reconnects = int(get_config("research.stream_reconnect_attempts") or 2)
        backoff = float(get_config("research.stream_reconnect_backoff_seconds") or 0.25)
        headers = self.composition._auth_headers(  # Existing service auth path.
            service,
            auth_context={"correlation_id": correlation_id},
        )
        headers["Accept"] = "text/event-stream"
        params: Dict[str, Any] = {
            "query": query,
            "depth": plan.depth,
            "tenant_id": tenant_id,
            "correlation_id": correlation_id,
            "max_results": plan.max_results,
        }
        if query_languages:
            params["query_languages"] = ",".join(str(v) for v in query_languages)
        if target_languages:
            params["target_languages"] = ",".join(str(v) for v in target_languages)
        if synthesise_in:
            params["synthesise_in"] = str(synthesise_in)

        user_id = (auth_context or {}).get("user_id")
        role = (auth_context or {}).get("role")
        if _config_bool(get_config("research.search_availability_gate_enabled"), True):
            persona_id = str(
                get_config("research.search_availability_persona") or "uk-chrome"
            ).strip() or "uk-chrome"
            availability = await self.composition.search_availability(
                service,
                persona_id=persona_id,
                auth_context={"correlation_id": correlation_id},
            )
            if str(availability.get("status") or "").lower() == "unavailable":
                self._emit_audit(
                    "a2a.call",
                    action="research_stream.availability_gate",
                    outcome="denied",
                    correlation_id=correlation_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    role=role,
                    target={
                        "type": "external_service",
                        "id": str(service.id),
                        "name": service.name,
                    },
                    details={
                        "availability": availability,
                        "persona_id": persona_id,
                        "fallback_reason": availability.get("action"),
                    },
                )
                action = availability.get("action") or availability.get("status")
                raise RuntimeError(f"SearchMCP unavailable: {action}")

        current_last_id = last_event_id
        terminal_seen = False
        for attempt in range(max_reconnects + 1):
            request_params = dict(params)
            request_headers = dict(headers)
            if current_last_id is not None:
                request_params["last_event_id"] = int(current_last_id)
                request_headers["Last-Event-ID"] = str(current_last_id)

            started = time.perf_counter()
            try:
                self._emit_audit(
                    "a2a.call",
                    action="research_stream",
                    outcome="success",
                    correlation_id=correlation_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    role=role,
                    target={
                        "type": "external_service",
                        "id": str(service.id),
                        "name": service.name,
                    },
                    details={"url": url, "depth": plan.depth, "attempt": attempt},
                )
                async with self.composition.client.stream(
                    "GET",
                    url,
                    headers=request_headers,
                    params=request_params,
                    timeout=timeout,
                ) as response:
                    response.raise_for_status()
                    async for event in self._iter_sse_response(response):
                        event.setdefault("correlation_id", correlation_id)
                        event.setdefault("tenant_id", tenant_id)
                        if event.get("id") is not None:
                            try:
                                current_last_id = int(event["id"])
                            except (TypeError, ValueError):
                                pass
                        self._emit_audit(
                            "mcp.call",
                            action="chat_stream_relay",
                            outcome="success",
                            correlation_id=correlation_id,
                            tenant_id=tenant_id,
                            user_id=user_id,
                            role=role,
                            target={
                                "type": "mcp_stream",
                                "id": str(event.get("id") or event.get("sequence") or ""),
                                "name": str(event.get("type") or "research_stream"),
                            },
                            details={
                                "duration_ms": int((time.perf_counter() - started) * 1000),
                                "sequence": event.get("sequence"),
                                "stream_event_type": event.get("type"),
                            },
                        )
                        await _maybe_call(on_event, event)
                        yield event
                        if event.get("type") == "final_synthesis":
                            terminal_seen = True
                            return
                if terminal_seen:
                    return
                return
            except (httpx.HTTPError, httpx.TimeoutException) as exc:
                self._emit_audit(
                    "a2a.call",
                    action="research_stream",
                    outcome="failure",
                    correlation_id=correlation_id,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    role=role,
                    target={
                        "type": "external_service",
                        "id": str(service.id),
                        "name": service.name,
                    },
                    details={"error": str(exc), "attempt": attempt},
                )
                if attempt >= max_reconnects:
                    raise
                await asyncio.sleep(backoff * (attempt + 1))

    async def enrich_image_inputs(
        self,
        image_refs: Iterable[str],
        *,
        tenant_id: str = "default",
        correlation_id: Optional[str] = None,
        auth_context: Optional[Dict[str, Any]] = None,
        extract_charts: bool = True,
    ) -> List[Dict[str, Any]]:
        """Call search-mcp caption/chart tools for image URLs or file-mcp refs."""
        refs = [str(ref).strip() for ref in image_refs if str(ref).strip()]
        if not refs:
            return []
        service = self.composition.ensure_search_mcp_service()
        enriched: List[Dict[str, Any]] = []
        for ref in refs:
            base_args = {
                "image_url": ref,
                "tenant_id": tenant_id,
                "correlation_id": correlation_id,
            }
            caption_result = await self.composition.invoke_tool(
                service.id,
                "caption_image",
                base_args,
                auth_context=auth_context or {"correlation_id": correlation_id},
            )
            caption_payload = _parse_mcp_payload(caption_result.get("result", caption_result))
            item: Dict[str, Any] = {"image_ref": ref, "caption": caption_payload}
            if extract_charts:
                chart_result = await self.composition.invoke_tool(
                    service.id,
                    "extract_chart",
                    base_args,
                    auth_context=auth_context or {"correlation_id": correlation_id},
                )
                item["chart"] = _parse_mcp_payload(chart_result.get("result", chart_result))
            enriched.append(item)
        return enriched

    async def run_research_cycle(
        self,
        query: str,
        *,
        depth: Optional[str] = None,
        tenant_id: str = "default",
        correlation_id: Optional[str] = None,
        budget: Optional[Dict[str, Any]] = None,
        image_refs: Optional[Iterable[str]] = None,
        auth_context: Optional[Dict[str, Any]] = None,
        on_event: Optional[ResearchEventCallback] = None,
    ) -> Dict[str, Any]:
        """End-to-end helper used by MCP/A2A tools and tests."""
        correlation_id = correlation_id or str(uuid.uuid4())
        refs = list(image_refs or [])
        ensure_research_expert(self._get_db())
        image_context = await self.enrich_image_inputs(
            refs,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            auth_context=auth_context,
        )
        plan = select_research_plan(
            query,
            budget=budget,
            image_refs=refs,
            requested_depth=depth,
        )
        effective_query = str(query or "").strip()
        if image_context:
            effective_query += "\n\nImage context:\n" + "\n".join(
                f"- {item['image_ref']}: {json.dumps(item.get('caption'), default=str)}"
                for item in image_context
            )
        events: List[Dict[str, Any]] = []
        async for event in self.stream_research(
            effective_query,
            depth=plan.depth,
            tenant_id=tenant_id,
            correlation_id=correlation_id,
            max_results=plan.max_results,
            auth_context=auth_context,
            on_event=on_event,
        ):
            events.append(event)
        return {
            "status": "ok",
            "query": query,
            "effective_query": effective_query,
            "correlation_id": correlation_id,
            "plan": {
                "depth": plan.depth,
                "max_results": plan.max_results,
                "backends": plan.backends,
                "depth_prompt": plan.depth_prompt,
                "backend_prompt": plan.backend_prompt,
            },
            "image_context": image_context,
            "events": events,
            "final_event": events[-1] if events else None,
        }


__all__ = ["ResearchCycleManager", "ResearchEventCallback", "sse_frame"]
