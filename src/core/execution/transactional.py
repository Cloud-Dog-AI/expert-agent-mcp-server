# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Transactional execution mode for experts."""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from src.common.reasoning_boundary import clean_final_content
from src.config.loader import get_config
from src.core.audit.context import get_current_principal_id
from src.core.expert.access_control import is_authorized
from src.core.expert.delegation import DelegationManager
from src.core.expert.manager import ExpertManager
from src.core.llm.manager import LLMManager
from src.core.prompt.manager import PromptManager
from src.core.service.composition import ServiceCompositionManager
from src.core.session.manager import SessionManager
from src.database.connection import get_db


def _strip_think(text: Any) -> str:
    """Remove qwen3-style ``<think>...</think>`` chain-of-thought blocks from model
    output (and a leading unmatched ``<think>`` when the budget truncated the close
    tag), so reasoning never leaks into documents, JSON envelopes or deliveries."""
    return clean_final_content(text)


class TransactionalExecutor:
    """Execute a single expert interaction without requiring a long-lived session."""

    def __init__(
        self,
        db: Optional[Session] = None,
        llm_manager: Optional[LLMManager] = None,
    ):
        """Create the transactional executor and bind service managers."""
        self.db = db
        self.llm_manager = llm_manager or LLMManager()
        self.expert_manager = ExpertManager(db)
        self.session_manager = SessionManager(db)
        self.prompt_manager = PromptManager(db)
        self.service_manager = ServiceCompositionManager(db)
        self.delegation_manager = DelegationManager(db)

    def _get_db(self) -> Session:
        """Return the bound DB session or open one from the configured provider."""
        if self.db:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    @staticmethod
    def _coerce_float(value: Any, default: float) -> float:
        """Coerce ``value`` to float, falling back to ``default`` on bad input."""
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int:
        """Coerce ``value`` to int, falling back to ``default`` on bad input."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _lookup_interpolation_path(variables: Dict[str, Any], expression: str) -> Any:
        """Resolve ``name.path[0]`` expressions against interpolation variables."""
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)(.*)$", expression)
        if not match:
            raise KeyError(expression)
        key, remainder = match.groups()
        value: Any = variables[key]
        token_pattern = re.compile(r"(?:\.([A-Za-z_][A-Za-z0-9_]*))|(?:\[(\d+)\])")
        pos = 0
        while pos < len(remainder):
            token_match = token_pattern.match(remainder, pos)
            if not token_match:
                raise KeyError(expression)
            attr, index = token_match.groups()
            # Auto-parse a JSON string when navigating INTO it, so a tool result carried as a
            # JSON string (e.g. an MCP `content[0].text` or an execute_code `stdout`) can be
            # navigated like a structure: `...content[0].text.data.items[0]`. Pure whole-token
            # references (no further navigation) are unaffected and still return the raw string.
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except (ValueError, TypeError):
                    pass
            if attr is not None:
                if not isinstance(value, dict) or attr not in value:
                    raise KeyError(expression)
                value = value[attr]
            else:
                if not isinstance(value, list):
                    raise KeyError(expression)
                value = value[int(index)]
            pos = token_match.end()
        return value

    @staticmethod
    def _stringify_interpolation_value(value: Any) -> str:
        """Render interpolation results as deterministic strings."""
        if isinstance(value, (dict, list)):
            return json.dumps(value, sort_keys=True)
        return "" if value is None else str(value)

    @staticmethod
    def _interpolate_value(value: Any, variables: Dict[str, Any]) -> Any:
        """Resolve ``${...}`` placeholders in JSON-like service-call arguments."""
        if isinstance(value, dict):
            return {
                str(k): TransactionalExecutor._interpolate_value(v, variables)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [TransactionalExecutor._interpolate_value(item, variables) for item in value]
        if isinstance(value, str):
            whole_token = re.fullmatch(r"\$\{([^}]+)\}", value)
            if whole_token:
                try:
                    return TransactionalExecutor._lookup_interpolation_path(
                        variables, whole_token.group(1)
                    )
                except (KeyError, IndexError, TypeError, ValueError):
                    return value

            def replace(match: re.Match[str]) -> str:
                """Replace one embedded interpolation token, preserving unknown tokens."""
                try:
                    return TransactionalExecutor._stringify_interpolation_value(
                        TransactionalExecutor._lookup_interpolation_path(variables, match.group(1))
                    )
                except (KeyError, IndexError, TypeError, ValueError):
                    return match.group(0)

            return re.sub(r"\$\{([^}]+)\}", replace, value)
        return value

    # EA4 (W28M-FIX-1615): the expert's bound grounding tools (read-only
    # context-gathering) are auto-invoked to ground the response; action tools
    # (write/send) are surfaced as available but never auto-fired.
    _GROUNDING_TOOLS = {
        "search",
        "retrieve",
        "query",
        "read_file",
        "read",
        "get",
        "list",
        "fetch",
        "lookup",
    }

    @staticmethod
    def _parse_expert_tools(expert: Any) -> List[Dict[str, Any]]:
        """Parse ``expert.tools_json`` into normalised tool entries.

        Accepts the legacy ``"service.tool"`` string form (e.g.
        ``"indexretriever0.search"``) and the structured object form
        ``{"service": ..., "tool": ..., "default_collection|default_profile|default_channel": ...}``.
        """
        raw = getattr(expert, "tools_json", None)
        if not raw:
            return []
        try:
            items = json.loads(raw)
        except Exception:
            return []
        if not isinstance(items, list):
            return []
        parsed: List[Dict[str, Any]] = []
        for item in items:
            if isinstance(item, str):
                if "." in item:
                    service, tool = item.split(".", 1)
                    parsed.append({"service": service, "tool": tool})
                continue
            if isinstance(item, dict) and item.get("service") and item.get("tool"):
                parsed.append(dict(item))
        return parsed

    @classmethod
    def _is_grounding_tool(cls, tool_name: Any) -> bool:
        """Return true when a tool name is safe for automatic grounding."""
        return str(tool_name).strip().lower() in cls._GROUNDING_TOOLS

    @staticmethod
    def _brief_type_from_request(
        input_text: str, parameters: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        params = parameters or {}
        for key in ("type", "brief_type", "intel_type", "collection_type"):
            value = params.get(key)
            if isinstance(value, str) and value.strip().lower() in {
                "military",
                "financial",
                "political",
                "uk",
            }:
                return value.strip().lower()
        lowered = str(input_text or "").lower()
        for value in ("military", "financial", "political", "uk"):
            if re.search(rf"\b{re.escape(value)}\b", lowered):
                return value
        return None

    @classmethod
    def _resolve_collection_template(
        cls,
        template: Optional[str],
        input_text: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        if not template:
            return None
        resolved = str(template)
        brief_type = cls._brief_type_from_request(input_text, parameters)
        if "${type}" in resolved:
            if not brief_type:
                return resolved
            resolved = resolved.replace("${type}", brief_type)
        return resolved

    @staticmethod
    def _safe_argument_metadata(arguments: Dict[str, Any]) -> Dict[str, Any]:
        return {
            key: arguments[key]
            for key in ("profile", "collection", "channel", "query")
            if arguments.get(key) not in (None, "")
        }

    @staticmethod
    def _normalise_result_payload(value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            if text.startswith("data:"):
                text = "\n".join(
                    line[5:].strip()
                    for line in text.splitlines()
                    if line.strip().startswith("data:")
                ).strip()
            if text and text[:1] in "[{":
                try:
                    return json.loads(text)
                except Exception:
                    return value
        return value

    @classmethod
    def _extract_invocation_summary(cls, result: Any) -> Dict[str, Any]:
        payload = cls._normalise_result_payload(result)
        if isinstance(payload, dict):
            for key in ("result", "structuredContent", "data"):
                if key in payload:
                    nested = cls._extract_invocation_summary(payload[key])
                    if nested:
                        return nested
            if isinstance(payload.get("content"), list):
                for block in payload["content"]:
                    if isinstance(block, dict) and "text" in block:
                        nested = cls._extract_invocation_summary(block["text"])
                        if nested:
                            return nested

        containers: List[Any] = []
        if isinstance(payload, dict):
            for key in ("chunks", "items", "results", "documents", "matches"):
                if isinstance(payload.get(key), list):
                    containers.append(payload[key])
        elif isinstance(payload, list):
            containers.append(payload)

        result_count = None
        chunk_ids: List[str] = []
        source_ids: List[str] = []
        for items in containers:
            if result_count is None:
                result_count = len(items)
            for item in items:
                if not isinstance(item, dict):
                    continue
                for key, target in (
                    ("chunk_id", chunk_ids),
                    ("chunk_ids", chunk_ids),
                    ("source_id", source_ids),
                    ("source_ids", source_ids),
                    ("document_id", source_ids),
                ):
                    value = item.get(key)
                    if value is None:
                        continue
                    values = value if isinstance(value, list) else [value]
                    for v in values:
                        text = str(v)
                        if text and text not in target:
                            target.append(text)
        summary: Dict[str, Any] = {}
        if result_count is not None:
            summary["result_count"] = result_count
        if chunk_ids:
            summary["chunk_ids"] = chunk_ids[:20]
        if source_ids:
            summary["source_ids"] = source_ids[:20]
        return summary

    @classmethod
    def _build_tool_arguments(
        cls,
        entry: Dict[str, Any],
        tool_name: str,
        input_text: str,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Build invocation arguments for a bound grounding tool."""
        args: Dict[str, Any] = {}
        name = str(tool_name).strip().lower()
        if name in {"search", "retrieve", "query", "fetch", "lookup"}:
            args["query"] = input_text
        collection_template = entry.get("collection_template") or entry.get("default_collection")
        collection = cls._resolve_collection_template(collection_template, input_text, parameters)
        if collection:
            args["collection"] = collection
        if entry.get("default_profile"):
            args["profile"] = entry["default_profile"]
        if entry.get("default_channel"):
            args["channel"] = entry["default_channel"]
        if isinstance(entry.get("arguments"), dict):
            args.update(entry["arguments"])
        return args

    @classmethod
    def _enrich_service_invocation(
        cls,
        result: Any,
        service_name: str,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        record: Dict[str, Any] = dict(result) if isinstance(result, dict) else {"result": result}
        record.setdefault("service_name", service_name)
        record.setdefault("tool_name", tool_name)
        record.setdefault("status", "ok")
        safe_args = cls._safe_argument_metadata(arguments)
        if safe_args:
            record["arguments"] = safe_args
        for key in ("profile", "collection", "channel"):
            if arguments.get(key) not in (None, ""):
                record[key] = arguments[key]
        record.update(
            {k: v for k, v in cls._extract_invocation_summary(result).items() if k not in record}
        )
        return record

    @classmethod
    def _enrich_explicit_service_invocation(
        cls,
        result: Any,
        service_id: int,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        record: Dict[str, Any] = dict(result) if isinstance(result, dict) else {"result": result}
        record.setdefault("service_id", service_id)
        record.setdefault("tool_name", tool_name)
        record.setdefault("status", "ok")
        safe_args = cls._safe_argument_metadata(arguments)
        if safe_args:
            record["arguments"] = safe_args
        for key in ("profile", "collection", "channel"):
            if arguments.get(key) not in (None, ""):
                record[key] = arguments[key]
        record.update(cls._extract_invocation_summary(result))
        return record

    @staticmethod
    def _expert_access_control(expert: Any) -> Dict[str, Any]:
        """Decode an expert's access-control JSON as a dictionary."""
        raw = getattr(expert, "access_control_json", None)
        if not raw:
            return {}
        try:
            return json.loads(raw) or {}
        except Exception:
            return {}

    async def _dispatch_expert_tools(
        self,
        expert: Any,
        input_text: str,
        auth_context: Optional[Dict[str, Any]],
        session_obj: Any,
        parameters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """EA4: auto-invoke the expert's bound grounding tools (cross-service fan-out).

        Resolves each tool's service by name, validates the caller against the
        unified access_control schema (EA7), invokes read/search/retrieve/query
        grounding tools, and returns the invocation results (surfaced back to the
        LLM as ``services_invoked``). Action tools (write/send) are listed as
        available but not auto-invoked.
        """
        invoked: List[Dict[str, Any]] = []
        tools = self._parse_expert_tools(expert)
        if not tools:
            return invoked

        user_role = auth_context.get("role") if isinstance(auth_context, dict) else None
        if not is_authorized(
            self._expert_access_control(expert), user_role=user_role, user_group_ids=None
        ):
            return invoked

        from src.core.service.manager import ServiceManager

        svc_lookup = ServiceManager(self._get_db())
        for entry in tools:
            service_name = entry.get("service")
            tool_name = entry.get("tool")
            if not service_name or not tool_name:
                continue
            if not self._is_grounding_tool(tool_name):
                invoked.append(
                    {
                        "service_name": service_name,
                        "tool_name": tool_name,
                        "status": "available",
                    }
                )
                continue
            service = svc_lookup.get_service(name=str(service_name))
            if not service:
                invoked.append(
                    {
                        "service_name": service_name,
                        "tool_name": tool_name,
                        "status": "unregistered",
                    }
                )
                continue
            arguments = self._build_tool_arguments(entry, str(tool_name), input_text, parameters)
            try:
                result = await self.service_manager.invoke_tool(
                    service_id=int(service.id),
                    tool_name=str(tool_name),
                    arguments=arguments,
                    auth_context=auth_context,
                    session_id=session_obj.id if session_obj else None,
                )
                invoked.append(
                    self._enrich_service_invocation(
                        result,
                        str(service_name),
                        str(tool_name),
                        arguments,
                    )
                )
            except Exception as exc:
                failure = {
                    "service_name": service_name,
                    "tool_name": tool_name,
                    "status": "failed",
                    "error": str(exc),
                }
                failure.update(self._safe_argument_metadata(arguments))
                invoked.append(failure)
        return invoked

    @staticmethod
    def _summarise_service(result: Any) -> Dict[str, Any]:
        """Compact, content-free summary of a service-tool result for audit."""
        if not isinstance(result, dict):
            return {}
        summary: Dict[str, Any] = {}
        for key in ("service", "service_id", "service_name", "tool", "tool_name"):
            if result.get(key) not in (None, ""):
                summary[key] = result.get(key)
        if "error" in result:
            summary["error"] = True
        return summary

    def _emit_execute_audit(
        self,
        *,
        expert_id: int,
        principal_id: Optional[int],
        session_id: Optional[int],
        outcome: str,
        output_text: str,
        services_invoked: List[Dict[str, Any]],
        delegations: List[Dict[str, Any]],
        token_usage: Any,
        duration_ms: Optional[int],
        llm_model: Optional[str],
        error: Optional[str],
    ) -> None:
        """Emit a PS-40 ``expert.execute`` audit event (EA3/EA8).

        Audit emission MUST NOT break execution: any failure here is swallowed
        and logged, never raised.
        """
        try:
            from src.core.audit.manager import AuditManager
            from src.utils.logger import get_logger

            details: Dict[str, Any] = {
                "action": "execute",
                "outcome": outcome,
                "mode": "transactional",
                "expert_id": expert_id,
                "llm_model": llm_model,
                "output_sha256": (
                    hashlib.sha256((output_text or "").encode("utf-8")).hexdigest()
                    if outcome == "success"
                    else None
                ),
                "services_invoked": [
                    self._summarise_service(item) for item in (services_invoked or [])
                ],
                "services_invoked_count": len(services_invoked or []),
                "delegations_count": len(delegations or []),
                "token_usage": token_usage,
                "execution_time_ms": duration_ms,
            }
            if error:
                details["error"] = error
            AuditManager(self._get_db()).log_event(
                event_type="expert.execute",
                user_id=int(principal_id) if principal_id is not None else None,
                expert_id=expert_id,
                session_id=session_id,
                details=details,
            )
        except Exception as exc:  # pragma: no cover - audit must never break execute
            try:
                from src.utils.logger import get_logger

                get_logger(__name__).warning(f"expert.execute audit emit failed: {exc}")
            except Exception:
                pass

    async def execute(
        self,
        expert_id: int,
        input_text: str,
        parameters: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        auth_context: Optional[Dict[str, Any]] = None,
        existing_session_id: Optional[int] = None,
        delegation_depth: int = 0,
    ) -> Dict[str, Any]:
        """Execute an expert interaction, emitting an ``expert.execute`` audit event.

        EA3/EA8 (W28M-FIX-1614): wraps the execution pipeline in audit emission.
        The authenticated principal is taken from ``auth_context['user_id']`` or,
        failing that, the request-scoped principal context-var. The success path
        emits ``outcome=success`` with ``output_sha256``, ``services_invoked``,
        ``delegations``, and ``token_usage``; the failure path emits
        ``outcome=failure`` with the error and re-raises.
        """
        started = time.perf_counter()
        principal_id: Optional[int] = None
        if isinstance(auth_context, dict) and auth_context.get("user_id") is not None:
            principal_id = auth_context.get("user_id")
        if principal_id is None:
            principal_id = get_current_principal_id()

        try:
            result = await self._execute_inner(
                expert_id=expert_id,
                input_text=input_text,
                parameters=parameters,
                context=context,
                auth_context=auth_context,
                existing_session_id=existing_session_id,
                delegation_depth=delegation_depth,
            )
        except Exception as exc:
            self._emit_execute_audit(
                expert_id=expert_id,
                principal_id=principal_id,
                session_id=None,
                outcome="failure",
                output_text="",
                services_invoked=[],
                delegations=[],
                token_usage=None,
                duration_ms=int((time.perf_counter() - started) * 1000),
                llm_model=None,
                error=str(exc),
            )
            raise

        self._emit_execute_audit(
            expert_id=expert_id,
            principal_id=principal_id,
            session_id=result.get("session_id"),
            outcome="success",
            output_text=result.get("output_text", ""),
            services_invoked=result.get("services_invoked", []),
            delegations=result.get("delegations", []),
            token_usage=result.get("token_usage"),
            duration_ms=result.get("execution_time_ms"),
            llm_model=result.get("llm_model"),
            error=None,
        )
        return result

    async def _execute_inner(
        self,
        expert_id: int,
        input_text: str,
        parameters: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
        auth_context: Optional[Dict[str, Any]] = None,
        existing_session_id: Optional[int] = None,
        delegation_depth: int = 0,
    ) -> Dict[str, Any]:
        """Run the transactional execution after audit wrapping has been set up."""
        params = parameters or {}
        ctx = context or {}
        started = time.perf_counter()
        # PS-96 §3: a non-simple agent_strategy means the cloud_dog_agent loop drives
        # the expert's bound tools itself, so the single-shot grounding helpers
        # (EA4 auto-invoke of bound tools, prior-turn assembly) must NOT pre-fire.
        agent_strategy = str(params.get("agent_strategy") or "simple").strip().lower()
        is_agent_run = bool(agent_strategy and agent_strategy != "simple")

        expert = self.expert_manager.get_expert(expert_id=expert_id)
        if not expert:
            raise ValueError("Expert configuration not found")

        user_ctx = auth_context or {}
        prompt = self.prompt_manager.render_expert_prompt(
            expert_id,
            user=user_ctx,
            session={"mode": "transactional"},
            extra_variables=ctx,
        )

        services_invoked: List[Dict[str, Any]] = []
        delegations: List[Dict[str, Any]] = []

        persist = bool(
            params.get("persist_session")
            if "persist_session" in params
            else get_config("service_composition.transactional_session_persist")
        )
        session_obj = None
        if existing_session_id:
            session_obj = self.session_manager.get_session(int(existing_session_id))
        elif persist and user_ctx.get("user_id"):
            session_obj, _ = self.session_manager.create_session(
                user_id=int(user_ctx["user_id"]),
                expert_config_id=expert_id,
                title="Transactional execution",
                check_limits=False,
            )

        for item in params.get("service_tool_calls", []) or []:
            resolved_arguments = self._interpolate_value(
                item.get("arguments") or {},
                {
                    "input_text": input_text,
                    "expert_id": expert_id,
                    "session_id": session_obj.id if session_obj else "",
                    "services_invoked": services_invoked,
                    "service_results": services_invoked,
                },
            )
            service_result = await self.service_manager.invoke_tool(
                service_id=int(item["service_id"]),
                tool_name=str(item["tool_name"]),
                arguments=resolved_arguments,
                auth_context=auth_context,
                session_id=session_obj.id if session_obj else None,
            )
            services_invoked.append(
                self._enrich_explicit_service_invocation(
                    service_result,
                    int(item["service_id"]),
                    str(item["tool_name"]),
                    resolved_arguments,
                )
            )

        # EA4 (W28M-FIX-1615): auto-invoke the expert's own bound grounding tools
        # so the response is grounded in cross-service evidence even when the
        # caller passed no explicit service_tool_calls. Skipped for agent runs —
        # there the loop decides which bound tools to call, with what arguments.
        if not is_agent_run:
            expert_tool_results = await self._dispatch_expert_tools(
                expert, input_text, auth_context, session_obj, params
            )
            if expert_tool_results:
                services_invoked.extend(expert_tool_results)

        for item in params.get("delegations", []) or []:
            if not session_obj:
                if not user_ctx.get("user_id"):
                    raise ValueError("Delegation requires an authenticated user context")
                session_obj, _ = self.session_manager.create_session(
                    user_id=int(user_ctx["user_id"]),
                    expert_config_id=expert_id,
                    title="Transactional delegation root",
                    check_limits=False,
                )
            delegation = self.delegation_manager.delegate(
                parent_session_id=int(session_obj.id),
                sub_expert_id=int(item["sub_expert_id"]),
                task=str(item["task"]),
                context=item.get("context") or ctx,
                depth=int(item.get("depth") or delegation_depth),
            )
            child_execution = await self.execute(
                expert_id=int(item["sub_expert_id"]),
                input_text=str(item["task"]),
                parameters=item.get("parameters") or {},
                context=item.get("context") or ctx,
                auth_context=auth_context,
                existing_session_id=int(delegation["child_session_id"]),
                delegation_depth=delegation["depth"],
            )
            delegation["execution"] = child_execution
            delegations.append(delegation)

        llm_params = {}
        if expert.llm_params_json:
            try:
                llm_params = json.loads(expert.llm_params_json) or {}
            except Exception:
                llm_params = {}

        raw_timeout = (
            params.get("timeout")
            if params.get("timeout") is not None
            else params.get("llm_timeout")
            if params.get("llm_timeout") is not None
            else llm_params.get("timeout")
            if llm_params.get("timeout") is not None
            else llm_params.get("llm_timeout")
        )
        configured_timeout = self._coerce_int(get_config("llm.timeout"), 300)
        eff_timeout = self._coerce_int(
            raw_timeout,
            configured_timeout,
        )
        if eff_timeout <= 0:
            eff_timeout = configured_timeout
        if is_agent_run and raw_timeout is None:
            agent_wall_seconds = self._coerce_int(
                params.get("max_wall_time_seconds"),
                self._coerce_int(get_config("agent.max_wall_time_seconds"), 600),
            )
            agent_llm_timeout = self._coerce_int(
                get_config("agent.llm_timeout_seconds"),
                900,
            )
            if agent_wall_seconds > eff_timeout and agent_llm_timeout > eff_timeout:
                eff_timeout = min(agent_wall_seconds, agent_llm_timeout)

        await self.llm_manager.initialize(
            provider=expert.llm_provider,
            model=expert.llm_model,
            base_url=llm_params.get("base_url"),
            api_key=llm_params.get("api_key"),
            timeout=eff_timeout,
        )

        # Per-expert LLM config (each agent carries its OWN context window, output
        # budget, temperature and think mode). Without an adequate num_ctx / num_predict
        # a reasoning model (qwen3) silently truncates the prompt or spends its whole
        # budget thinking and returns empty/garbage. Call-time `parameters` override
        # the expert defaults; the expert defaults override the service config.
        def _llm_opt(*keys: str, default: Any = None) -> Any:
            """Resolve an LLM option from call parameters, expert params, then default."""
            for k in keys:
                if params.get(k) is not None:
                    return params.get(k)
            for k in keys:
                if llm_params.get(k) is not None:
                    return llm_params.get(k)
            return default

        eff_temperature = self._coerce_float(
            _llm_opt("temperature", default=get_config("llm.temperature")), 0.7
        )
        eff_max_tokens = self._coerce_int(
            _llm_opt("max_tokens", "num_predict", default=get_config("llm.max_tokens")), 1024
        )
        eff_num_ctx = _llm_opt("num_ctx", default=get_config("llm.num_ctx"))
        eff_think = bool(_llm_opt("think", default=llm_params.get("think") or False))
        llm_extra: Dict[str, Any] = {"num_predict": eff_max_tokens}
        # Qwen3 defaults to its reasoning path unless the Ollama request
        # explicitly carries ``think: false``. Preserve the caller/expert
        # setting in both directions for Ollama: omitting the false value
        # silently makes long, model-authored document jobs spend most of their
        # governed wall time in hidden reasoning and risks job cancellation.
        # Keep provider-specific fields away from providers that do not expose
        # the Ollama ``think`` option.
        if str(expert.llm_provider or "").strip().lower() == "ollama":
            llm_extra["think"] = eff_think
        elif eff_think:
            llm_extra["think"] = True
        if eff_num_ctx:
            llm_extra["num_ctx"] = self._coerce_int(eff_num_ctx, 8192)
        self._llm_cfg = {
            "temperature": eff_temperature,
            "max_tokens": eff_max_tokens,
            "num_ctx": llm_extra.get("num_ctx"),
            "think": eff_think,
            "timeout": eff_timeout,
        }

        messages = []
        if prompt:
            messages.append({"role": "system", "content": prompt})
        for prior in ctx.get("messages", []) or []:
            if isinstance(prior, dict) and prior.get("role") and prior.get("content"):
                messages.append({"role": str(prior["role"]), "content": str(prior["content"])})
        if ctx.get("documents"):
            messages.append(
                {
                    "role": "system",
                    "content": f"Document references: {json.dumps(ctx['documents'])}",
                }
            )
        if services_invoked:
            messages.append(
                {
                    "role": "system",
                    "content": "Service invocation results: " + json.dumps(services_invoked),
                }
            )
        if delegations:
            messages.append(
                {
                    "role": "system",
                    "content": "Delegation results: " + json.dumps(delegations),
                }
            )
        messages.append({"role": "user", "content": input_text})

        # PS-96 §3: an opt-in `agent_strategy` DATA parameter selects a
        # cloud_dog_agent strategy loop instead of the default single shot.
        # Omitted / "simple" preserves the existing behaviour exactly.
        if is_agent_run:
            from src.core.execution.strategy import run_agent_strategy

            max_wall_seconds = self._coerce_int(
                params.get("max_wall_time_seconds"),
                self._coerce_int(get_config("agent.max_wall_time_seconds"), 600),
            )
            if max_wall_seconds <= 0:
                raise ValueError("max_wall_time_seconds must be positive")
            try:
                async with asyncio.timeout(max_wall_seconds) as wall_timeout:
                    response = await run_agent_strategy(
                        strategy=agent_strategy,
                        db=self._get_db(),
                        executor=self,
                        expert=expert,
                        system_prompt=prompt,
                        input_text=input_text,
                        params=params,
                        auth_context=auth_context,
                        llm_cfg=self._llm_cfg,
                    )
            except TimeoutError as exc:
                if not wall_timeout.expired():
                    raise
                raise TimeoutError(
                    f"Agent strategy exceeded governed wall time of {max_wall_seconds} seconds"
                ) from exc
        else:
            try:
                response = await asyncio.wait_for(
                    self.llm_manager.generate(
                        messages=messages,
                        temperature=eff_temperature,
                        max_tokens=eff_max_tokens,
                        **{k: v for k, v in llm_extra.items() if k != "num_predict"},
                    ),
                    timeout=eff_timeout,
                )
            except asyncio.TimeoutError as exc:
                raise TimeoutError(
                    f"LLM generation exceeded governed timeout of {eff_timeout} seconds"
                ) from exc
        if response.get("services_invoked"):
            services_invoked.extend(response.get("services_invoked") or [])

        post_service_results: List[Dict[str, Any]] = []
        output_text = _strip_think(response.get("content", ""))
        interpolation_vars = {
            "input_text": input_text,
            "output_text": output_text,
            "expert_id": expert_id,
            "session_id": session_obj.id if session_obj else "",
            "services_invoked": services_invoked,
            "service_results": services_invoked,
            "post_service_results": post_service_results,
        }
        for item in params.get("post_service_tool_calls", []) or []:
            resolved_arguments = self._interpolate_value(
                item.get("arguments") or {},
                interpolation_vars,
            )
            service_result = await self.service_manager.invoke_tool(
                service_id=int(item["service_id"]),
                tool_name=str(item["tool_name"]),
                arguments=resolved_arguments,
                auth_context=auth_context,
                session_id=session_obj.id if session_obj else None,
            )
            services_invoked.append(
                self._enrich_explicit_service_invocation(
                    service_result,
                    int(item["service_id"]),
                    str(item["tool_name"]),
                    resolved_arguments,
                )
            )
            post_service_results.append(service_result)
            interpolation_vars["services_invoked"] = services_invoked
            interpolation_vars["service_results"] = services_invoked
            interpolation_vars["post_service_results"] = post_service_results

        duration_ms = int((time.perf_counter() - started) * 1000)
        if session_obj:
            self.session_manager.add_message(session_obj.id, "user", input_text)
            self.session_manager.add_message(
                session_obj.id,
                "assistant",
                output_text,
                tokens_used=response.get("tokens_used"),
                metadata={"transactional": True},
            )

        result = {
            "expert_id": expert_id,
            "output_text": output_text,
            "token_usage": response.get("tokens_used"),
            "llm_model": expert.llm_model,
            "services_invoked": services_invoked,
            "post_service_results": post_service_results,
            "delegations": delegations,
            "execution_time_ms": duration_ms,
            "session_id": session_obj.id if session_obj else None,
            "mode": "transactional",
        }
        if is_agent_run:
            result["agent_strategy"] = agent_strategy
            result["agent_trace"] = response.get("agent_trace") or {"strategy": agent_strategy}
            if response.get("warnings"):
                result["warnings"] = response.get("warnings")
        return result
