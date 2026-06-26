# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Transactional execution mode for experts."""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

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


class TransactionalExecutor:
    """Execute a single expert interaction without requiring a long-lived session."""

    def __init__(
        self,
        db: Optional[Session] = None,
        llm_manager: Optional[LLMManager] = None,
    ):
        self.db = db
        self.llm_manager = llm_manager or LLMManager()
        self.expert_manager = ExpertManager(db)
        self.session_manager = SessionManager(db)
        self.prompt_manager = PromptManager(db)
        self.service_manager = ServiceCompositionManager(db)
        self.delegation_manager = DelegationManager(db)

    def _get_db(self) -> Session:
        if self.db:
            return self.db
        db_gen = get_db()
        return next(db_gen)

    @staticmethod
    def _coerce_float(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _coerce_int(value: Any, default: int) -> int:
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
        if isinstance(value, (dict, list)):
            return json.dumps(value, sort_keys=True)
        return "" if value is None else str(value)

    @staticmethod
    def _interpolate_value(value: Any, variables: Dict[str, Any]) -> Any:
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
                try:
                    return TransactionalExecutor._stringify_interpolation_value(
                        TransactionalExecutor._lookup_interpolation_path(
                            variables, match.group(1)
                        )
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
        return str(tool_name).strip().lower() in cls._GROUNDING_TOOLS

    @staticmethod
    def _build_tool_arguments(
        entry: Dict[str, Any], tool_name: str, input_text: str
    ) -> Dict[str, Any]:
        """Build invocation arguments for a bound grounding tool."""
        args: Dict[str, Any] = {}
        name = str(tool_name).strip().lower()
        if name in {"search", "retrieve", "query", "fetch", "lookup"}:
            args["query"] = input_text
        if entry.get("default_collection"):
            args["collection"] = entry["default_collection"]
        if entry.get("default_profile"):
            args["profile"] = entry["default_profile"]
        if entry.get("default_channel"):
            args["channel"] = entry["default_channel"]
        if isinstance(entry.get("arguments"), dict):
            args.update(entry["arguments"])
        return args

    @staticmethod
    def _expert_access_control(expert: Any) -> Dict[str, Any]:
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
            arguments = self._build_tool_arguments(entry, str(tool_name), input_text)
            try:
                result = await self.service_manager.invoke_tool(
                    service_id=int(service.id),
                    tool_name=str(tool_name),
                    arguments=arguments,
                    auth_context=auth_context,
                    session_id=session_obj.id if session_obj else None,
                )
                invoked.append(result)
            except Exception as exc:
                invoked.append(
                    {
                        "service_name": service_name,
                        "tool_name": tool_name,
                        "status": "failed",
                        "error": str(exc),
                    }
                )
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
        params = parameters or {}
        ctx = context or {}
        started = time.perf_counter()

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
            services_invoked.append(service_result)

        # EA4 (W28M-FIX-1615): auto-invoke the expert's own bound grounding tools
        # so the response is grounded in cross-service evidence even when the
        # caller passed no explicit service_tool_calls.
        expert_tool_results = await self._dispatch_expert_tools(
            expert, input_text, auth_context, session_obj
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

        await self.llm_manager.initialize(
            provider=expert.llm_provider,
            model=expert.llm_model,
            base_url=llm_params.get("base_url"),
            api_key=llm_params.get("api_key"),
        )

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

        response = await self.llm_manager.generate(
            messages=messages,
            temperature=self._coerce_float(
                params.get("temperature") or get_config("llm.temperature"), 0.7
            ),
            max_tokens=self._coerce_int(
                params.get("max_tokens") or get_config("llm.max_tokens"), 512
            ),
        )

        post_service_results: List[Dict[str, Any]] = []
        output_text = response.get("content", "")
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
            services_invoked.append(service_result)
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

        return {
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
