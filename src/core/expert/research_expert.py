# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Research sub-expert registration and planning helpers for W28F-947."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from src.config.loader import get_config
from src.core.audit.manager import AuditManager
from src.core.service.composition import SEARCH_MCP_SERVICE_NAME, ServiceCompositionManager
from src.database.models import ExpertConfig, ServiceBinding, SubExpertBinding
from src.utils.logger import get_logger

logger = get_logger(__name__)

RESEARCH_EXPERT_NAME = "research-expert"
RESEARCH_EXPERT_TITLE = "Research Expert"

DEPTH_SELECTION_PROMPT = """Select a search-mcp research_stream depth for the user query.
Return one of: quick, standard, deep, exhaustive.
Use quick for narrow facts, standard for normal synthesis, deep for contested or multi-source
analysis, and exhaustive only when the user asks for a broad due-diligence style run or has
budgeted for a long research cycle."""

BACKEND_SELECTION_PROMPT = """Select search backends for the research cycle.
Prefer general web search for open-ended questions. Add news/current-event backends for recency,
image/multimodal backends when image references are present, and archival/specialist backends
when the query asks for historical, regulatory, or document-heavy evidence."""

ON_EVENT_UPDATE_PROMPT = """Update the expert's working context from one research_stream event.
Preserve event type, event id, correlation_id, source title/url when present, convergence or
entity findings, and partial/final synthesis. Do not discard earlier high-confidence facts."""


@dataclass(frozen=True)
class ResearchPlan:
    """Deterministic fallback plan that mirrors the LLM planning prompt contract."""

    depth: str
    max_results: int
    backends: List[str]
    depth_prompt: str
    backend_prompt: str


def _coerce_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return [value]


def _allowed_group_ids() -> List[int]:
    groups: List[int] = []
    for raw in _coerce_list(get_config("research.allowed_group_ids")):
        try:
            groups.append(int(raw))
        except (TypeError, ValueError):
            continue
    return groups


def _configured_backends() -> List[str]:
    configured = [str(v) for v in _coerce_list(get_config("research.default_backends")) if str(v)]
    return configured or ["searxng", "news", "web"]


def select_research_plan(
    query: str,
    *,
    budget: Optional[Dict[str, Any]] = None,
    image_refs: Optional[Iterable[str]] = None,
    requested_depth: Optional[str] = None,
) -> ResearchPlan:
    """Select depth/backends using the research-expert prompt contract.

    The prompts are surfaced to the expert config and tests. This function is a
    deterministic local fallback for runtimes where no LLM call is desired at
    planning time.
    """
    valid_depths = {"quick", "standard", "deep", "exhaustive"}
    if requested_depth and str(requested_depth).strip().lower() in valid_depths:
        depth = str(requested_depth).strip().lower()
    else:
        text = str(query or "").lower()
        budget = budget or {}
        max_minutes = budget.get("max_minutes")
        try:
            minutes = float(max_minutes) if max_minutes is not None else None
        except (TypeError, ValueError):
            minutes = None
        if any(term in text for term in ("exhaustive", "due diligence", "every source")):
            depth = "exhaustive"
        elif any(term in text for term in ("compare", "contested", "multi-source", "deep")):
            depth = "deep"
        elif any(term in text for term in ("quick", "briefly", "single fact")) or (
            minutes is not None and minutes <= 2
        ):
            depth = "quick"
        else:
            depth = "standard"

    max_results_by_depth = {"quick": 8, "standard": 20, "deep": 40, "exhaustive": 80}
    max_results = max_results_by_depth[depth]
    if budget and budget.get("max_results") is not None:
        try:
            max_results = max(1, min(100, int(budget["max_results"])))
        except (TypeError, ValueError):
            pass

    backends = _configured_backends()
    if image_refs:
        for backend in ("images", "vision"):
            if backend not in backends:
                backends.append(backend)
    if any(term in str(query or "").lower() for term in ("today", "latest", "breaking", "news")):
        if "news" not in backends:
            backends.append("news")

    return ResearchPlan(
        depth=depth,
        max_results=max_results,
        backends=backends,
        depth_prompt=DEPTH_SELECTION_PROMPT,
        backend_prompt=BACKEND_SELECTION_PROMPT,
    )


def build_research_expert_config() -> Dict[str, Any]:
    """Return the canonical research-expert row payload."""
    tools = [
        {"service": SEARCH_MCP_SERVICE_NAME, "tool": "research_stream"},
        {"service": SEARCH_MCP_SERVICE_NAME, "tool": "caption_image"},
        {"service": SEARCH_MCP_SERVICE_NAME, "tool": "extract_chart"},
    ]
    return {
        "name": RESEARCH_EXPERT_NAME,
        "title": RESEARCH_EXPERT_TITLE,
        "description": (
            "Research sub-expert that chooses search depth and backends, consumes "
            "search-mcp research_stream events, and folds image captions/chart data "
            "into expert context."
        ),
        "llm_provider": get_config("llm.provider"),
        "llm_model": get_config("llm.model"),
        "prompt_template": "\n\n".join(
            [DEPTH_SELECTION_PROMPT, BACKEND_SELECTION_PROMPT, ON_EVENT_UPDATE_PROMPT]
        ),
        "tools": tools,
        "access_control": {
            "type": "rbac",
            "roles": ["admin", "user"],
            "allowed_groups": _allowed_group_ids(),
        },
    }


def ensure_research_expert(
    db: Session,
    *,
    parent_expert_id: Optional[int] = None,
) -> ExpertConfig:
    """Create/update the research-expert config and optional parent binding."""
    ServiceCompositionManager(db).ensure_search_mcp_service()
    payload = build_research_expert_config()
    tools_json = json.dumps(payload["tools"])
    access_json = json.dumps(payload["access_control"])
    expert = db.query(ExpertConfig).filter(ExpertConfig.name == RESEARCH_EXPERT_NAME).first()
    if expert:
        expert.title = payload["title"]
        expert.description = payload["description"]
        expert.llm_provider = payload["llm_provider"]
        expert.llm_model = payload["llm_model"]
        expert.prompt_template = payload["prompt_template"]
        expert.tools_json = tools_json
        expert.access_control_json = access_json
        expert.enabled = True
    else:
        expert = ExpertConfig(
            name=payload["name"],
            title=payload["title"],
            description=payload["description"],
            llm_provider=payload["llm_provider"],
            llm_model=payload["llm_model"],
            prompt_template=payload["prompt_template"],
            tools_json=tools_json,
            access_control_json=access_json,
            enabled=True,
        )
        db.add(expert)
    db.commit()
    db.refresh(expert)

    service = ServiceCompositionManager(db).ensure_search_mcp_service()
    binding = (
        db.query(ServiceBinding)
        .filter(
            ServiceBinding.expert_config_id == expert.id,
            ServiceBinding.service_id == service.id,
        )
        .first()
    )
    if not binding:
        db.add(
            ServiceBinding(
                expert_config_id=expert.id,
                service_id=service.id,
                enabled=True,
                priority=10,
                metadata_json=json.dumps({"lane": "W28F-947", "purpose": "research-expert"}),
            )
        )
        db.commit()

    if parent_expert_id is not None and int(parent_expert_id) != int(expert.id):
        sub_binding = (
            db.query(SubExpertBinding)
            .filter(
                SubExpertBinding.parent_expert_id == int(parent_expert_id),
                SubExpertBinding.child_expert_id == expert.id,
            )
            .first()
        )
        if not sub_binding:
            db.add(
                SubExpertBinding(
                    parent_expert_id=int(parent_expert_id),
                    child_expert_id=expert.id,
                    enabled=True,
                    delegation_prompt=ON_EVENT_UPDATE_PROMPT,
                )
            )
            db.commit()
    return expert


def _parse_payload(payload: Any) -> Dict[str, Any]:
    if isinstance(payload, dict):
        return dict(payload)
    if isinstance(payload, str):
        try:
            parsed = json.loads(payload)
            return parsed if isinstance(parsed, dict) else {"text": payload}
        except json.JSONDecodeError:
            return {"text": payload}
    return {"payload": payload}


async def on_match_event(
    payload: Any,
    *,
    correlation_id: Optional[str] = None,
    db: Optional[Session] = None,
) -> Dict[str, Any]:
    """Triage a streaming-watch match event sent over A2A."""
    event = _parse_payload(payload)
    corr = correlation_id or event.get("correlation_id")
    score = event.get("score", event.get("match_score", event.get("quality_score", 0)))
    try:
        numeric_score = float(score)
    except (TypeError, ValueError):
        numeric_score = 0.0
    priority = "high" if numeric_score >= 0.85 or event.get("severity") == "high" else "normal"
    action = "chain_research_cycle" if priority == "high" else "record_match"
    result = {
        "status": "accepted",
        "action": action,
        "priority": priority,
        "correlation_id": corr,
        "matched": {
            "title": event.get("title"),
            "url": event.get("url"),
            "score": numeric_score,
        },
    }
    if db is not None:
        try:
            AuditManager(db).log_event(
                "a2a.call",
                details={
                    "action": "research_expert.on_match_event",
                    "outcome": "success",
                    "subject": {
                        "tenant_id": event.get("tenant_id", "default"),
                        "user_id": event.get("user_id"),
                        "role": event.get("role", "system"),
                    },
                    "target": {
                        "type": "a2a_skill",
                        "id": "research_expert.on_match_event",
                        "name": "research-expert match event",
                    },
                    "source_ip": event.get("source_ip"),
                    "request_id": event.get("request_id"),
                    "correlation_id": corr,
                    "priority": priority,
                },
            )
        except Exception as exc:  # pragma: no cover - audit must not break dispatch
            logger.warning("research_expert.on_match_event audit failed: %s", exc)
    return result


__all__ = [
    "BACKEND_SELECTION_PROMPT",
    "DEPTH_SELECTION_PROMPT",
    "ON_EVENT_UPDATE_PROMPT",
    "RESEARCH_EXPERT_NAME",
    "ResearchPlan",
    "build_research_expert_config",
    "ensure_research_expert",
    "on_match_event",
    "select_research_plan",
]
