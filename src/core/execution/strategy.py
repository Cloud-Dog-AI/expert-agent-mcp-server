# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""PS-96 agent-strategy integration for transactional execution.

This module is **integration glue only** (PS-96 §14, §14.1): it does NOT define
any agent loop, memory store, prompt template store or sandbox executor. The loops
live in the ``cloud_dog_agent`` platform package; this module supplies the two thin
protocol implementations the package requires —

  * :class:`AgentLLMAdapter`  — a ``cloud_dog_agent.protocols.LLMCaller`` over the
    service's existing :class:`LLMManager`. One LLM round-trip per call; no looping.
  * :class:`AgentToolAdapter` — a ``cloud_dog_agent.protocols.ToolExecutor`` over the
    service's existing ``ServiceCompositionManager`` (MCP tool calls) and the
    ``TransactionalExecutor`` (sub-expert delegation, the platform execution primitive).

``run_agent_strategy`` selects a strategy by the ``agent_strategy`` DATA parameter
(PS-96 §3) and runs the corresponding ``cloud_dog_agent`` loop. Behaviour is entirely
data-driven: the expert's rendered prompt drives reasoning, and the expert's bound
tools / sub-experts (``tools_json`` + ``SubExpertBinding``) define the action space.
No task-specific code lives here.

Large tool/sub-agent outputs (e.g. a generated document section) are spilled into a
request-scoped artifact store and replaced in the reasoning transcript by a small
``ref`` token; later tool arguments referencing that token are rehydrated server-side
before dispatch. Content therefore never transits the LLM envelope — eliminating the
tool-argument truncation failure mode — without any task-specific assembly logic.

Recent Changes:
- 2026-07-23: Route legacy document selection through ReAct; fail closed on deterministic content repair
- 2026-07-16: Expand reporting-date front matter and harden structured logging
"""

from __future__ import annotations

import asyncio
import base64
from collections.abc import Iterable
import datetime as _datetime
import hashlib
import json
import re
from threading import Thread
import unicodedata
import uuid
from urllib.parse import urlsplit
from typing import Any, Callable, Dict, List, Optional

from cloud_dog_agent import (
    AgentStrategy,
    ReActConfig,
    ReActLoop,
    ReflexionConfig,
    ReflexionWrapper,
    RLMConfig,
    RLMRunner,
)
from cloud_dog_llm.domain.errors import (
    InvalidRequestError,
    ProviderUnavailableError,
    RateLimitError,
    TimeoutError as PlatformTimeoutError,
)
from cloud_dog_api_kit.clients import ClientTimeout, create_http_client
from src.common.reasoning_boundary import clean_final_content, strip_private_reasoning_tags

from src.config.loader import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)

# Strategies this service can run today. ``simple`` is handled by the caller's
# existing single-shot path and never reaches this module.
_SUPPORTED = {
    AgentStrategy.REACT.value,
    AgentStrategy.RLM.value,
    AgentStrategy.REFLEXION.value,
    "document",   # deterministic template-driven research-document pipeline (reliable depth)
}

_SPILL_THRESHOLD = 600  # chars; results larger than this are stored and referenced
_REF_PREFIX = "art:"
_MAX_AGENT_LLM_GENERATION_RETRIES = 2


# --------------------------------------------------------------------------- #
# Artifact store (request-scoped; NOT an agent memory store — pure tool I/O)
# --------------------------------------------------------------------------- #
class _ArtifactStore:
    """Holds large tool results for the lifetime of a single execution.

    This is transient per-call plumbing for tool outputs, not a durable or
    cross-session agent memory store (which PS-96 §14.1 reserves for
    ``cloud_dog_cache.agent_memory``)."""

    def __init__(self) -> None:
        """Create an empty per-execution artifact map."""
        self._items: Dict[str, Any] = {}
        self._n = 0

    def put(self, value: Any) -> str:
        """Store ``value`` and return its short artifact reference."""
        self._n += 1
        ref = f"{_REF_PREFIX}{self._n}"
        self._items[ref] = value
        return ref

    def get(self, ref: str) -> Any:
        """Return a stored artifact by reference, or ``None`` when absent."""
        return self._items.get(ref)

    def resolve(self, value: Any) -> Any:
        """Recursively replace ref tokens in tool arguments with stored content.

        A string that IS a ref returns the stored value verbatim (any type). A string
        that merely CONTAINS one or more ref tokens (e.g. an assembled document body
        ``"# Title\n\nart:1\n\nart:2"``) has each token expanded in place, so a multi-
        section document can be assembled by reference in a single tool argument
        without the content ever passing through the LLM."""
        if isinstance(value, str):
            if value in self._items:
                return self._items[value]
            if _REF_PREFIX in value and self._items:
                out = value
                for ref in sorted(self._items, key=len, reverse=True):
                    if ref in out:
                        rep = self._items[ref]
                        rep = rep if isinstance(rep, str) else json.dumps(rep, default=str)
                        out = re.sub(re.escape(ref) + r"(?![0-9])", lambda _m, r=rep: r, out)
                return out
            return value
        if isinstance(value, dict):
            return {k: self.resolve(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.resolve(v) for v in value]
        return value


# --------------------------------------------------------------------------- #
# LLMCaller adapter (cloud_dog_agent.protocols.LLMCaller)
# --------------------------------------------------------------------------- #
class AgentLLMAdapter:
    """One LLM round-trip returning the ReAct envelope. No loop, no direct HTTP."""

    def __init__(
        self,
        llm_manager: Any,
        system_prompt: str,
        tools: List[Dict[str, Any]],
        temperature: float = 0.4,
        max_tokens: int = 1200,
        num_ctx: Optional[int] = None,
        think: bool = False,
        allow_markdown_final: bool = False,
        markdown_completion_marker: str = "FINAL_REPORT",
        marked_final_payload_description: str = "the complete reader-ready Markdown report",
        allow_bare_json_final: bool = False,
        before_generate: Optional[Callable[[], None]] = None,
    ) -> None:
        """Bind the service LLM manager and generation defaults for one agent call."""
        self._llm = llm_manager
        self._system = system_prompt or ""
        self._tools = tools or []
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._num_ctx = num_ctx
        self._think = think
        # Long reports encoded inside a JSON string are unreliable on smaller
        # local models because escaping thousands of Markdown characters can
        # invalidate an otherwise complete model-authored answer. This opt-in
        # completion form is limited to the agentic-document path.
        self._allow_markdown_final = allow_markdown_final
        self._markdown_completion_marker = str(markdown_completion_marker or "FINAL_REPORT").strip()
        self._marked_final_payload_description = str(
            marked_final_payload_description or "the complete final payload"
        ).strip()
        self._allow_bare_json_final = bool(allow_bare_json_final)
        # A transactional executor can record local service/audit state before
        # waiting on a long model response. Release that transaction first so
        # the durable MCP lease heartbeat is not blocked behind model latency.
        self._before_generate = before_generate

    def _protocol_block(self) -> str:
        """Render the ReAct protocol appended to the system prompt."""
        lines = [
            "",
            "## Operating protocol (ReAct)",
            "Respond with ONE action and nothing else. To call a tool, use one JSON object:",
            '  {"reasoning": "<brief>", "tool_call": {"name": "<tool>", "arguments": {<small>}}}',
        ]
        if self._allow_markdown_final:
            lines += [
                "To finish the agentic document, start exactly with "
                f"`{self._markdown_completion_marker}` on its own line,",
                f"then place {self._marked_final_payload_description} on the following lines.",
            ]
        else:
            lines += [
                "or finish:",
                '  {"reasoning": "<brief>", "final_answer": "<short summary>"}',
            ]
        lines += ["", "Available tools:"]
        if self._tools:
            for t in self._tools:
                lines.append(f"  - {t.get('name')}: {t.get('description', '')}")
        else:
            lines.append("  (none)")
        lines += [
            "",
            "Rules: keep tool arguments SMALL. Never paste large content (document "
            'sections, file bodies) into arguments — pass a "ref" token (e.g. "art:3") '
            "returned by a previous tool instead."
            + (f" The report completion uses {self._markdown_completion_marker}, never a JSON string."
               if self._allow_markdown_final
               else " Output ONLY the JSON object."),
        ]
        return "\n".join(lines)

    async def call(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Call the configured LLM and parse a tool-call or final-answer envelope."""
        base: List[Dict[str, str]] = [
            {"role": "system", "content": self._system + "\n" + self._protocol_block()}
        ]
        for m in messages:
            role = str(m.get("role", "user"))
            if role == "tool":
                base.append({"role": "user", "content": f"[observation] {m.get('content', '')}"})
            else:
                base.append({"role": role, "content": str(m.get("content", ""))})

        # Smaller open models drift out of the JSON contract after a few turns
        # (emitting prose). Retry with an escalating JSON-only nudge until the
        # reply is a valid action envelope, so one stray turn cannot end the loop.
        for attempt in range(3):
            msgs = list(base)
            if attempt:
                completion_instruction = (
                    "or start exactly `" + self._markdown_completion_marker
                    + "` on its own line followed by "
                    + self._marked_final_payload_description
                    + "."
                    if self._allow_markdown_final
                    else 'or {"reasoning":"...","final_answer":"..."}. No prose, no markdown fences.'
                )
                msgs.append({
                    "role": "user",
                    "content": (
                        "Your previous reply did not match the required action protocol. "
                        "Reply NOW with either ONLY one JSON tool action object "
                        '{"reasoning":"...","tool_call":{"name":"<tool>","arguments":{...}}} '
                        + completion_instruction
                    ),
                })
            extra: Dict[str, Any] = {}
            if self._num_ctx:
                extra["num_ctx"] = int(self._num_ctx)
            if self._think:
                extra["think"] = True
            generation_retries, generation_grace, generation_backoff, retry_timeouts = (
                _agent_llm_generation_retry_policy()
            )
            generation_timeout_seconds = _agent_llm_generation_timeout_seconds()
            for generation_attempt in range(1, generation_retries + 2):
                if self._before_generate is not None:
                    self._before_generate()
                try:
                    response = await asyncio.wait_for(
                        self._llm.generate(
                            messages=msgs,
                            temperature=self._temperature,
                            max_tokens=self._max_tokens,
                            **extra,
                        ),
                        timeout=generation_timeout_seconds,
                    )
                    break
                except Exception as exc:
                    if (
                        generation_attempt > generation_retries
                        or not _is_retryable_llm_generation_error(exc, retry_timeouts)
                    ):
                        raise
                    delay = generation_grace + (generation_backoff * (generation_attempt - 1))
                    logger.warning(
                        f"Transient agent LLM generation error on attempt "
                        f"{generation_attempt}/{generation_retries + 1}: {exc}; "
                        f"replaying the same model checkpoint in {delay:.1f}s"
                    )
                    if delay > 0:
                        await asyncio.sleep(delay)
            raw = (response.get("content") if isinstance(response, dict) else str(response)) or ""
            text = _strip_think(raw)  # qwen3 reasoning must not reach the JSON parser
            parsed = self._parse(
                text,
                allow_markdown_final=self._allow_markdown_final,
                markdown_completion_marker=self._markdown_completion_marker,
                allow_bare_json_final=self._allow_bare_json_final,
            )
            if parsed.get("tool_call") or parsed.get("final_answer") is not None:
                return parsed
        # Unvalidated prose may contain private reasoning; never surface it as
        # the final answer after the bounded structured-action attempts.
        raise RuntimeError("LLM did not return a valid structured ReAct action after 3 attempts")

    @staticmethod
    def _parse(
        text: str,
        *,
        allow_markdown_final: bool = False,
        markdown_completion_marker: str = "FINAL_REPORT",
        allow_bare_json_final: bool = False,
    ) -> Dict[str, Any]:
        """Extract the ReAct envelope from model text. Robust to fences/prose."""
        if allow_markdown_final:
            marker = str(markdown_completion_marker or "FINAL_REPORT").strip() + "\n"
            candidate = text.lstrip()
            if candidate.startswith(marker):
                report = candidate[len(marker):].strip()
                if report:
                    return {"reasoning": "", "tool_call": None, "final_answer": report}
        obj = _first_json_object(text)
        if isinstance(obj, dict):
            tc = obj.get("tool_call") or obj.get("action")
            reasoning = str(obj.get("reasoning") or obj.get("thought") or "")
            if isinstance(tc, dict) and tc.get("name"):
                return {
                    "reasoning": reasoning,
                    "tool_call": {"name": str(tc["name"]), "arguments": tc.get("arguments") or tc.get("args") or {}},
                    "final_answer": None,
                }
            fa = obj.get("final_answer", obj.get("answer"))
            if fa is not None:
                return {"reasoning": reasoning, "tool_call": None, "final_answer": fa}
            if allow_bare_json_final:
                return {
                    "reasoning": "",
                    "tool_call": None,
                    "final_answer": json.dumps(obj, ensure_ascii=False),
                }
            return {"reasoning": reasoning, "tool_call": None, "final_answer": None}
        # No parseable envelope (prose drift): signal "no action" so the caller
        # can retry for a structured reply rather than ending the loop on prose.
        return {"reasoning": "", "tool_call": None, "final_answer": None}


def _parse_model_authored_visual_plan(raw: Any, requirements: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a complete model-authored visual plan without changing it.

    The report model, rather than runtime code, owns candidate selection, values,
    map focus, visual rationale and captions.  This function only enforces the
    product's declared render contract before a plan can reach GeoMCP/ChartMCP.
    It deliberately does not fill missing fields, score candidates, or repair a
    rejected plan; the caller asks the model for a complete replacement instead.
    """
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("MODEL_AUTHORED_VISUAL_PLAN_INVALID: model returned no visual plan")
    try:
        plan = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("MODEL_AUTHORED_VISUAL_PLAN_INVALID: plan is not JSON") from exc
    if not isinstance(plan, dict):
        raise ValueError("MODEL_AUTHORED_VISUAL_PLAN_INVALID: plan must be a JSON object")

    maps = plan.get("maps")
    charts = plan.get("charts")
    if not isinstance(maps, list) or not isinstance(charts, list):
        raise ValueError("MODEL_AUTHORED_VISUAL_PLAN_INVALID: maps and charts must be arrays")
    if not all(isinstance(item, dict) for item in [*maps, *charts]):
        raise ValueError("MODEL_AUTHORED_VISUAL_PLAN_INVALID: every map and chart must be an object")

    allowed_basemaps = {
        str(value).strip()
        for value in requirements.get("allowed_basemaps", [])
        if str(value).strip()
    }
    required_map_fields = [
        str(field).strip()
        for field in (requirements.get("required_map_fields") or [])
        if str(field).strip()
    ]
    forbidden_map_fields = {
        str(field).strip()
        for field in (requirements.get("forbidden_map_fields") or [])
        if str(field).strip()
    }
    for index, item in enumerate(maps, 1):
        required = tuple(dict.fromkeys((
            "id", "kind", "title", "caption", "after", "bbox", "basemap", "map_date", "attribution", "source_urls",
            *required_map_fields,
        )))
        missing = [field for field in required if not item.get(field)]
        if missing:
            raise ValueError(
                "MODEL_AUTHORED_VISUAL_PLAN_INVALID: map %d missing %s"
                % (index, ", ".join(missing))
            )
        forbidden = sorted(field for field in forbidden_map_fields if item.get(field))
        if forbidden:
            raise ValueError(
                "MODEL_AUTHORED_VISUAL_PLAN_INVALID: map %d includes forbidden field(s) %s"
                % (index, ", ".join(forbidden))
            )
        bbox = item.get("bbox")
        if not (
            isinstance(bbox, list)
            and len(bbox) == 4
            and all(isinstance(value, (int, float)) for value in bbox)
            and bbox[0] < bbox[2]
            and bbox[1] < bbox[3]
        ):
            raise ValueError("MODEL_AUTHORED_VISUAL_PLAN_INVALID: map %d has an invalid bbox" % index)
        if allowed_basemaps and str(item.get("basemap")) not in allowed_basemaps:
            raise ValueError("MODEL_AUTHORED_VISUAL_PLAN_INVALID: map %d uses an unapproved basemap" % index)
        source_urls = item.get("source_urls")
        if not isinstance(source_urls, list) or not source_urls or not all(
            isinstance(url, str) and url.startswith("https://") for url in source_urls
        ):
            raise ValueError("MODEL_AUTHORED_VISUAL_PLAN_INVALID: map %d needs public HTTPS source URLs" % index)
        # These fields feed iterable renderer inputs.  A boolean such as
        # ``\"legend\": true`` is not a shorthand: it crashes the renderer and
        # would leave the declared map contract unfulfilled.  Reject the model
        # plan before rendering so the model can re-author the complete plan
        # with actual overlays/furniture; never substitute visual data here.
        for field in ("highlight", "neighbours", "control", "lines", "markers", "legend"):
            if field in item and not isinstance(item.get(field), list):
                raise ValueError(
                    "MODEL_AUTHORED_VISUAL_PLAN_INVALID: map %d field %s must be an array, not %s"
                    % (index, field, type(item.get(field)).__name__)
                )
        if "legend" in required_map_fields and not item.get("legend"):
            raise ValueError(
                "MODEL_AUTHORED_VISUAL_PLAN_INVALID: map %d needs a non-empty legend array" % index
            )

        # A map which names an axis, movement or strike but supplies no model-authored
        # evidence marks is only an orientation basemap.  Products can opt into a
        # per-kind overlay contract so the model must provide the actual, cited
        # features for the visual it selected.  This validates shape and presence
        # only: it never invents coordinates, labels, routes, targets or rationale.
        overlay_requirements = requirements.get("minimum_overlay_entries_by_kind") or {}
        if isinstance(overlay_requirements, dict):
            kind_requirements = overlay_requirements.get(str(item.get("kind"))) or {}
            if isinstance(kind_requirements, dict):
                for field, minimum in kind_requirements.items():
                    try:
                        minimum_count = max(0, int(minimum))
                    except (TypeError, ValueError) as exc:
                        raise ValueError(
                            "MODEL_AUTHORED_VISUAL_PLAN_INVALID: overlay requirement for %s.%s must be an integer"
                            % (item.get("kind"), field)
                        ) from exc
                    if minimum_count and (
                        not isinstance(item.get(str(field)), list)
                        or len(item[str(field)]) < minimum_count
                    ):
                        observed = len(item.get(str(field)) or []) if isinstance(item.get(str(field)), list) else 0
                        raise ValueError(
                            "MODEL_AUTHORED_VISUAL_PLAN_INVALID: %s map %d needs at least %d %s item(s), received %d"
                            % (item.get("kind"), index, minimum_count, field, observed)
                        )

    allowed_chart_types = {"bar", "hbar", "grouped_bar", "line", "radar"}
    for index, item in enumerate(charts, 1):
        required = ("id", "kind", "title", "caption", "after", "chart_type", "source_urls")
        missing = [field for field in required if not item.get(field)]
        if missing:
            raise ValueError(
                "MODEL_AUTHORED_VISUAL_PLAN_INVALID: chart %d missing %s"
                % (index, ", ".join(missing))
            )
        if str(item.get("chart_type")).lower() not in allowed_chart_types:
            raise ValueError("MODEL_AUTHORED_VISUAL_PLAN_INVALID: chart %d uses an unsupported type" % index)
        source_urls = item.get("source_urls")
        if not isinstance(source_urls, list) or not source_urls or not all(
            isinstance(url, str) and url.startswith("https://") for url in source_urls
        ):
            raise ValueError("MODEL_AUTHORED_VISUAL_PLAN_INVALID: chart %d needs public HTTPS source URLs" % index)
        chart_type = str(item.get("chart_type")).lower()
        if chart_type == "radar":
            categories = item.get("categories")
            series = item.get("series")
            if not isinstance(categories, list) or not isinstance(series, dict):
                raise ValueError("MODEL_AUTHORED_VISUAL_PLAN_INVALID: radar chart %d needs categories and series" % index)
            if not categories or any(isinstance(value, (dict, list)) for value in categories):
                raise ValueError("MODEL_AUTHORED_VISUAL_PLAN_INVALID: radar chart %d needs scalar categories" % index)
            if not series or any(
                not isinstance(values, list)
                or len(values) != len(categories)
                or any(isinstance(value, (dict, list, bool)) for value in values)
                for values in series.values()
            ):
                raise ValueError(
                    "MODEL_AUTHORED_VISUAL_PLAN_INVALID: radar chart %d needs scalar series values aligned to categories"
                    % index
                )
        else:
            rows = item.get("rows") or item.get("data")
            x_field, y_field = item.get("x"), item.get("y")
            if not isinstance(rows, list) or not rows:
                raise ValueError("MODEL_AUTHORED_VISUAL_PLAN_INVALID: chart %d needs model-authored data rows" % index)
            if not isinstance(x_field, str) or not x_field.strip() or not isinstance(y_field, str) or not y_field.strip():
                raise ValueError(
                    "MODEL_AUTHORED_VISUAL_PLAN_INVALID: chart %d x and y must each be one non-empty field-name string"
                    % index
                )
            for row_number, row in enumerate(rows, 1):
                if not isinstance(row, dict) or x_field not in row or y_field not in row:
                    raise ValueError(
                        "MODEL_AUTHORED_VISUAL_PLAN_INVALID: chart %d row %d needs the declared x and y fields"
                        % (index, row_number)
                    )
                if isinstance(row[x_field], (dict, list)) or isinstance(row[y_field], (dict, list, bool)):
                    raise ValueError(
                        "MODEL_AUTHORED_VISUAL_PLAN_INVALID: chart %d row %d values must be scalar"
                        % (index, row_number)
                    )
                try:
                    float(row[y_field])
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "MODEL_AUTHORED_VISUAL_PLAN_INVALID: chart %d row %d y value must be numeric"
                        % (index, row_number)
                    ) from exc

    min_maps = max(0, int(requirements.get("minimum_maps") or 0))
    min_charts = max(0, int(requirements.get("minimum_charts") or 0))
    if len(maps) < min_maps or len(charts) < min_charts:
        raise ValueError(
            "MODEL_AUTHORED_VISUAL_PLAN_INVALID: required maps=%d/charts=%d, received maps=%d/charts=%d"
            % (min_maps, min_charts, len(maps), len(charts))
        )
    for kind, minimum in (requirements.get("minimum_map_kinds") or {}).items():
        observed = sum(1 for item in maps if str(item.get("kind")) == str(kind))
        if observed < int(minimum):
            raise ValueError(
                "MODEL_AUTHORED_VISUAL_PLAN_INVALID: required %s map count=%d, received=%d"
                % (kind, int(minimum), observed)
            )
    for kind, minimum in (requirements.get("minimum_chart_kinds") or {}).items():
        observed = sum(1 for item in charts if str(item.get("kind")) == str(kind))
        if observed < int(minimum):
            raise ValueError(
                "MODEL_AUTHORED_VISUAL_PLAN_INVALID: required %s chart count=%d, received=%d"
                % (kind, int(minimum), observed)
            )

    visual_classes = requirements.get("required_visual_classes") or []
    if isinstance(visual_classes, dict):
        visual_classes = [
            dict({"id": key}, **(value if isinstance(value, dict) else {}))
            for key, value in visual_classes.items()
        ]
    for requirement in visual_classes if isinstance(visual_classes, list) else []:
        if isinstance(requirement, str):
            requirement = {"id": requirement}
        if not isinstance(requirement, dict):
            continue
        visual_class = str(requirement.get("id") or requirement.get("visual_class") or "").strip()
        if not visual_class:
            continue
        expected_kind = str(requirement.get("kind") or "").strip().lower()
        minimum = max(1, int(requirement.get("minimum") or 1))
        candidates = [
            item for item in maps
            if str(item.get("quality_class") or "").strip() == visual_class
            and (not expected_kind or expected_kind == "map")
        ] + [
            item for item in charts
            if str(item.get("quality_class") or "").strip() == visual_class
            and (not expected_kind or expected_kind == "chart")
        ]
        minimum_source_urls = max(0, int(requirement.get("minimum_source_urls") or 0))
        required_metadata_fields = [
            str(field).strip()
            for field in (requirement.get("required_metadata_fields") or [])
            if str(field).strip()
        ]
        candidates = [
            item for item in candidates
            if (
                len([
                    url for url in (item.get("source_urls") or [])
                    if isinstance(url, str) and url.startswith("https://")
                ]) >= minimum_source_urls
                and all(item.get(field) not in (None, "", [], {}) for field in required_metadata_fields)
            )
        ]
        if len(candidates) < minimum:
            raise ValueError(
                "MODEL_AUTHORED_VISUAL_PLAN_INVALID: required visual class %s count=%d, received=%d"
                % (visual_class, minimum, len(candidates))
            )

    # The visual-plan contract may carry a presentation cap shared by all of
    # the model-selected figures.  This is configuration-only layout plumbing:
    # the model still owns every map/chart and its caption, rationale and data.
    result = {"maps": maps, "charts": charts, "require_all_rendered": True}
    if requirements.get("max_width"):
        result["max_width"] = str(requirements["max_width"])
    return result


def _parse_model_authored_quality_assessment(raw: Any, requirements: Dict[str, Any]) -> Dict[str, Any]:
    """Validate the model's self-assessment schema without scoring or repairing it."""
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError("MODEL_AUTHORED_QUALITY_ASSESSMENT_INVALID: model returned no self-assessment")
    try:
        assessment = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("MODEL_AUTHORED_QUALITY_ASSESSMENT_INVALID: self-assessment is not JSON") from exc
    if not isinstance(assessment, dict) or not isinstance(assessment.get("sections"), list):
        raise ValueError("MODEL_AUTHORED_QUALITY_ASSESSMENT_INVALID: sections must be a JSON array")
    required_titles = [
        re.sub(r"\s+", " ", str(title)).strip()
        for title in (requirements.get("required_section_titles") or [])
        if str(title).strip()
    ]
    seen: set[str] = set()
    for item in assessment["sections"]:
        if not isinstance(item, dict):
            raise ValueError("MODEL_AUTHORED_QUALITY_ASSESSMENT_INVALID: each section must be an object")
        title = re.sub(r"\s+", " ", str(item.get("title") or "")).strip()
        if not title or title in seen:
            raise ValueError("MODEL_AUTHORED_QUALITY_ASSESSMENT_INVALID: section titles must be unique and non-empty")
        seen.add(title)
        try:
            score = float(item.get("score"))
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "MODEL_AUTHORED_QUALITY_ASSESSMENT_INVALID: every section score must be numeric"
            ) from exc
        if not 0.0 <= score <= 100.0:
            raise ValueError("MODEL_AUTHORED_QUALITY_ASSESSMENT_INVALID: section score must be in 0..100")
        if str(item.get("regeneration_action") or "").strip().lower() not in {"accept", "regenerate"}:
            raise ValueError(
                "MODEL_AUTHORED_QUALITY_ASSESSMENT_INVALID: regeneration_action must be accept or regenerate"
            )
    if set(required_titles) != seen:
        raise ValueError(
            "MODEL_AUTHORED_QUALITY_ASSESSMENT_INVALID: section inventory does not match the report contract"
        )
    return assessment


def _build_model_authored_quality_assessment_prompt(
    *,
    content: str,
    contract: Dict[str, Any],
    required_titles: List[str],
    minimum_score: float,
    rejected: str = "",
    last_error: str = "",
) -> str:
    """Build an explicit, model-owned quality-assessment schema contract."""
    schema_example = {
        "sections": [
            {
                "title": title,
                "score": 0,
                "regeneration_action": "regenerate",
            }
            for title in required_titles
        ]
    }
    retry_contract = ""
    if rejected:
        retry_contract = (
            "\n\nTHE PREVIOUS SELF-ASSESSMENT WAS REJECTED.\n"
            f"Validation deficit: {last_error}\n"
            "Return a newly authored complete assessment. The `sections` value MUST be a JSON array: "
            "it must begin with `[` and end with `]`. A JSON object/map keyed by section title is invalid. "
            "Do not omit, rename, or add section entries.\n"
            "PREVIOUS REJECTED SELF-ASSESSMENT:\n"
            f"{rejected}\n"
        )
    return (
        "Return exactly FINAL_QUALITY_SELF_ASSESSMENT on its own line followed by one JSON object. "
        "Do not use Markdown fences. The object must contain only `sections`. Its value MUST be a JSON "
        "array of objects; never return an object/map keyed by section title. Every array item must have "
        "exactly the keys `title`, `score`, and `regeneration_action`. Preserve every title in the exact "
        "order shown. Replace every example score and action with your honest assessment; do not copy the "
        "placeholder values. Each score must be numeric from 0 to 100 and each action must be `accept` or "
        f"`regenerate`. A score below {minimum_score:.1f} or an action of regenerate means the candidate "
        "must be re-authored before persistence. Score depth, source grounding, specificity, and "
        "non-repetition from the actual candidate.\n\n"
        "EXACT REQUIRED JSON SHAPE:\n"
        f"{json.dumps(schema_example, ensure_ascii=False)}\n\n"
        "QUALITY CONTRACT:\n"
        f"{json.dumps(contract, ensure_ascii=False, sort_keys=True)}\n\n"
        "COMPLETED MODEL-AUTHORED REPORT:\n"
        f"{content}"
        f"{retry_contract}"
        "\nFINAL REMINDER: `sections` must be the JSON array shown in EXACT REQUIRED JSON SHAPE."
    )


def _source_register_rows_for_markers(register: str, markers: Iterable[int]) -> str:
    """Return exact governed source rows for a requested marker set."""
    wanted = {int(marker) for marker in markers}
    rows: List[str] = []
    for raw_line in str(register or "").splitlines():
        line = raw_line.strip()
        match = re.match(r"^\[(\d+)\]\s+.+", line)
        if match and int(match.group(1)) in wanted:
            rows.append(line)
    return "\n".join(rows)


def _selected_citation_prompt_boundary(text: str, markers: Iterable[int]) -> str:
    """Hide unselected numeric citation tokens from a selected-source model turn."""
    allowed = {int(marker) for marker in markers}

    def replace(match: re.Match[str]) -> str:
        return (
            match.group(0)
            if int(match.group(1)) in allowed
            else "<unselected-citation-marker-omitted>"
        )

    return re.sub(r"\[(\d+)\]", replace, str(text or ""))


def _build_model_authored_citation_selection_prompt(
    *,
    titles: Iterable[str],
    required_count: int,
    source_rows: str,
    rejected: str = "",
    last_error: str = "",
) -> str:
    """Build the fail-closed source-selection checkpoint for one report chunk."""
    retry = ""
    if rejected or last_error:
        retry = (
            "\nTHE PREVIOUS SELECTION WAS REJECTED. Return a new complete selection.\n"
            f"VALIDATION ERROR: {last_error or 'invalid marker selection'}\n"
            f"REJECTED OUTPUT: {rejected or '(empty)'}\n"
        )
    return (
        "Select the governed evidence that directly supports the report sections below. "
        "This is source selection only: do not write report prose, claims, analysis, URLs, "
        "JSON, or commentary. Return exactly `FINAL_CITATION_SELECTION` on its own line, "
        f"followed by exactly {required_count} distinct bracketed marker token(s) on one line, "
        "for example `[2] [7]`. Select only markers shown in the exact current-run source rows. "
        "The selected markers become mandatory citations in the subsequent model-authored chunk.\n\n"
        "REQUIRED REPORT SECTIONS:\n- "
        + "\n- ".join(str(title).strip() for title in titles if str(title).strip())
        + "\n\nEXACT CURRENT-RUN GOVERNED SOURCE ROWS:\n"
        + source_rows
        + retry
    )


def _validate_model_authored_citation_selection(
    selection: str,
    *,
    allowed_markers: Iterable[int],
    required_count: int,
) -> tuple[List[int], List[str]]:
    """Validate a model-selected marker list without choosing or repairing it."""
    text = str(selection or "").strip()
    allowed = {int(marker) for marker in allowed_markers}
    failures: List[str] = []
    if not re.fullmatch(r"(?:\[\d+\]\s*)+", text):
        failures.append("selection must contain bracketed marker tokens only")
    markers: List[int] = []
    for raw_marker in re.findall(r"\[(\d+)\]", text):
        marker = int(raw_marker)
        if marker not in markers:
            markers.append(marker)
    invalid = [marker for marker in markers if marker not in allowed]
    if invalid:
        failures.append(
            "selection contains marker(s) outside the offered governed set: "
            + ", ".join(f"[{marker}]" for marker in invalid)
        )
    if len(markers) != required_count:
        failures.append(
            f"selection contains {len(markers)} distinct marker(s); exactly {required_count} required"
        )
    return markers, failures


def _strip_think(text: Any) -> str:
    """Strip qwen3 ``<think>...</think>`` chain-of-thought (and an unclosed leading
    think block when the token budget truncated the close tag) from model output."""
    return strip_private_reasoning_tags(text)


def _is_retryable_llm_generation_error(exc: Exception, retry_on_timeout: bool) -> bool:
    """Return true when an agent model checkpoint can be safely replayed."""
    if isinstance(exc, PlatformTimeoutError):
        return retry_on_timeout
    class_name = exc.__class__.__name__.lower()
    message = str(exc).lower()
    if "timeout" in class_name or "timeout" in message:
        return retry_on_timeout
    if isinstance(exc, InvalidRequestError):
        return any(code in message for code in (" 500", " 502", " 503", " 504"))
    if isinstance(exc, (ProviderUnavailableError, RateLimitError)):
        return True
    return False


def _first_configured_value(*keys: str, default: Any = None) -> Any:
    """Return the first configured value, preserving explicit zero values."""
    for key in keys:
        value = get_config(key)
        if value is not None:
            return value
    return default


def _agent_llm_generation_retry_policy() -> tuple[int, float, float, bool]:
    """Resolve the bounded retry policy for one agent model checkpoint."""
    retries = max(
        0,
        min(
            _as_int(
                _first_configured_value(
                    "agent.llm_generation_retries",
                    "llm.generation_retries",
                    default=2,
                ),
                2,
            ),
            _MAX_AGENT_LLM_GENERATION_RETRIES,
        ),
    )
    grace = max(
        0.0,
        _as_float(
            _first_configured_value(
                "agent.llm_generation_retry_grace_seconds",
                "llm.retry_grace_seconds",
                default=1.0,
            ),
            1.0,
        ),
    )
    backoff = max(
        0.0,
        _as_float(
            _first_configured_value(
                "agent.llm_generation_retry_backoff_seconds",
                "llm.retry_backoff_seconds",
                default=2.0,
            ),
            2.0,
        ),
    )
    retry_on_timeout = _as_bool(
        _first_configured_value(
            "agent.llm_generation_retry_on_timeout",
            "llm.retry_on_read_timeout",
            default=True,
        ),
        True,
    )
    return retries, grace, backoff, retry_on_timeout


def _agent_llm_generation_timeout_seconds() -> float:
    """Resolve one bounded model-checkpoint deadline.

    A provider/client timeout is not sufficient on its own: a coroutine can
    remain pending beneath the client boundary and strand an otherwise durable
    document job.  This guard is deliberately generic and configuration-led;
    it neither supplies nor alters report content.  The agent retries the same
    model-owned checkpoint through the existing retry policy, or fails closed.
    """
    configured = _first_configured_value(
        "agent.llm_generation_timeout_seconds",
        "llm.generation_timeout_seconds",
        "llm.timeout",
        default=300.0,
    )
    return max(30.0, min(_as_float(configured, 300.0), 900.0))


def _configured_forbidden_content_hits(content: str, controls: Dict[str, Any]) -> List[Dict[str, str]]:
    """Evaluate caller-supplied forbidden content policy.

    The policy is entirely data-driven. This function deliberately carries no
    task-specific phrase list; callers provide categories and terms in
    ``quality_controls.forbidden_content``.
    """
    policy = controls.get("forbidden_content")
    if not isinstance(policy, dict):
        return []
    top_level_terms = _configured_forbidden_terms(policy)
    categories = policy.get("categories") or []
    if isinstance(categories, dict):
        categories = [
            {"id": category_id, **(category_policy if isinstance(category_policy, dict) else {})}
            for category_id, category_policy in categories.items()
        ]
    elif not isinstance(categories, list):
        categories = []
    if top_level_terms:
        category_id = str(policy.get("id") or policy.get("name") or "forbidden_content").strip() or "forbidden_content"
        categories = [{"id": category_id, "terms": top_level_terms}, *categories]
    normalised = unicodedata.normalize("NFKC", content or "").casefold()
    hits: List[Dict[str, str]] = []
    for category in categories:
        if not isinstance(category, dict):
            continue
        category_id = str(category.get("id") or category.get("name") or "forbidden").strip() or "forbidden"
        terms = _configured_forbidden_terms(category)
        for term in terms:
            term_text = str(term or "").strip()
            if not term_text:
                continue
            needle = unicodedata.normalize("NFKC", term_text).casefold()
            if _configured_forbidden_term_present(normalised, needle):
                hits.append({"category": category_id, "term": term_text})
    return hits


def _configured_forbidden_terms(policy: Dict[str, Any]) -> List[Any]:
    """Return caller-supplied forbidden terms without treating strings as iterables."""
    terms = policy.get("terms") or policy.get("phrases") or []
    if isinstance(terms, str):
        return [terms]
    if isinstance(terms, (list, tuple, set)):
        return list(terms)
    return []


def _configured_forbidden_term_present(normalised_content: str, normalised_term: str) -> bool:
    """Match a configured term on word-ish boundaries after NFKC/casefold normalisation."""
    if not normalised_term:
        return False
    pattern = r"(?<![\w])" + re.escape(normalised_term) + r"(?![\w])"
    return re.search(pattern, normalised_content, re.IGNORECASE) is not None


def _forbidden_content_generation_discipline(controls: Dict[str, Any]) -> str:
    """Return generation guidance for a configured fail-closed forbidden policy.

    The exact policy terms are intentionally not copied into the generation prompt:
    repeating excluded terms teaches small local models to reuse them. The
    deterministic gate below remains the source of truth and checks the exact
    caller-supplied terms before any write or send side effect.
    """
    policy = controls.get("forbidden_content") if isinstance(controls, dict) else None
    if not isinstance(policy, dict):
        return ""
    return (
        "CONFIGURED FORBIDDEN-CONTENT DISCIPLINE: a fail-closed pre-delivery "
        "gate will reject caller-policy-breaching prose before persistence or "
        "send. Write only the affirmative subject matter requested by the caller. "
        "Do not explain, restate, quote or work around the caller's forbidden "
        "policy controls."
    )


def _model_authored_sources_required(controls: Dict[str, Any]) -> bool:
    """True when the caller requires the final Sources section to remain model-authored."""
    if not isinstance(controls, dict):
        return False
    return bool(
        controls.get("model_authored_sources_required")
        or controls.get("model_authored_sources")
        or controls.get("sources_model_authored")
    )


def _caller_governed_source_register(defaults: Dict[str, Any]) -> tuple[str, Dict[int, str]]:
    """Build a citation register/URL allow-list from caller-supplied source data.

    Some governed products perform their own deep research and pass a vetted
    ``source_families`` / ``grounding.citable_sources`` register to Expert.  For
    model-authored Sources, that register is already the allowed citation
    namespace; do not let a secondary generic web preflight replace it with
    unrelated but live URLs.
    """
    if not isinstance(defaults, dict):
        return "", {}

    rows: List[Dict[str, Any]] = []
    for key in ("source_families", "sources", "citable_sources"):
        value = defaults.get(key)
        if isinstance(value, list):
            rows.extend(item for item in value if isinstance(item, dict))

    grounding = defaults.get("grounding") if isinstance(defaults.get("grounding"), dict) else {}
    for key in ("citable_sources", "collected_sources", "source_families"):
        value = grounding.get(key)
        if isinstance(value, list):
            rows.extend(item for item in value if isinstance(item, dict))

    entries: Dict[int, tuple[str, str]] = {}
    used_numbers: set[int] = set()
    next_number = 1
    for row in rows:
        raw_url = (
            row.get("url")
            or row.get("source_url")
            or row.get("source_uri")
            or row.get("document_url")
            or row.get("link")
        )
        url = _public_url(raw_url).rstrip("/")
        if not url:
            continue
        if re.search(r"(?i)://(?:localhost|127\.0\.0\.1|[^/]*\.cloud-dog\.net)(?:[/:]|$)", url):
            continue
        try:
            number = int(row.get("number") or row.get("n") or 0)
        except (TypeError, ValueError):
            number = 0
        if number <= 0 or number in used_numbers:
            while next_number in used_numbers:
                next_number += 1
            number = next_number
        used_numbers.add(number)
        title = str(
            row.get("description")
            or row.get("title")
            or row.get("name")
            or row.get("id")
            or f"Source {number}"
        ).strip()
        entries[number] = (title, url)

    if not entries:
        return "", {}
    ordered = sorted(entries.items())
    register = "\n".join(
        f"[{number}] {title} — URL: {url}"
        for number, (title, url) in ordered
    )
    return register, {number: url for number, (_title, url) in ordered}


def _deterministic_content_repair_allowed(controls: Dict[str, Any]) -> bool:
    """Enable fail-closed model-only output for an explicitly agentic report."""
    if not isinstance(controls, dict):
        return True
    return (
        controls.get("deterministic_content_repair_allowed", True) is not False
        and not bool(controls.get("prohibit_deterministic_report_body_or_repair"))
        and not bool(controls.get("agentic_document_required"))
    )


def _run_scoped_artifact_path(path: Any, run_id: str) -> str:
    """Return a distinct storage path for one immutable report execution.

    This is storage identity only: it never alters model-authored report bytes.
    A product must opt into it through ``immutable_run_artifact_required`` so
    legacy products retain their configured filename behaviour.
    """
    source_path = str(path or "").strip()
    if not source_path:
        raise RuntimeError(
            "IMMUTABLE_RUN_ARTIFACT_REQUIRED: working_path is required for a run-scoped artifact"
        )
    token = re.sub(r"[^A-Za-z0-9_-]", "", str(run_id or ""))
    if not token:
        raise RuntimeError(
            "IMMUTABLE_RUN_ARTIFACT_REQUIRED: run identity is required for a run-scoped artifact"
        )
    directory, separator, filename = source_path.rpartition("/")
    stem, dot, extension = filename.rpartition(".")
    if not separator:
        directory = ""
    if not dot or not stem:
        stem, extension = filename, ""
    scoped_filename = f"{stem}-{token}" + (f".{extension}" if extension else "")
    return f"{directory}{separator}{scoped_filename}" if separator else scoped_filename


# Heading regex for a TOP-LEVEL (#/##, never ###) "Sources"/"References" section heading.
_TOP_SOURCES_RE = re.compile(r"\n#{1,2}[ \t]+(?:Sources|References)\b", re.IGNORECASE)
_AS_OF_TEMPORAL_FRAMING_RE = re.compile(
    r"(?im)^\s*(?:\*\*\s*)?(?:reporting\s+period\s*:\s*)?(?:\*\*\s*)?as of\b"
)


def _as_of_temporal_framing_hits(text: str) -> List[str]:
    """Find prohibited report datelines without treating a source title as prose."""
    return [match.group(0).strip() for match in _AS_OF_TEMPORAL_FRAMING_RE.finditer(text)]


def _select_rotated_theme(rotation: Any, day_of_year: int) -> Optional[Dict[str, Any]]:
    """Deterministically pick today's per-theme template + zone from a ``theme_rotation`` config.

    ``rotation`` = ``{"themes": [{"name","target","title","sections":[{title,brief,target_words}]}],
    "zones": [...]}``. Returns ``{name, zone, target, title, sections}`` for ``day_of_year`` with any
    ``{zone}`` placeholders (in target/title/section briefs) interpolated, or ``None`` if empty.
    This is what lets the Transparent Borders researcher carry a *tailored* section structure per
    theme (planning→build→enhance) instead of one generic template, with no per-demo code."""
    if not isinstance(rotation, dict):
        return None
    themes = [t for t in (rotation.get("themes") or []) if isinstance(t, dict)]
    if not themes:
        return None
    zones = [str(z) for z in (rotation.get("zones") or [""])] or [""]
    th = themes[day_of_year % len(themes)]
    zone = zones[day_of_year % len(zones)]
    def fz(value: Any) -> str:
        """Interpolate the selected zone into one scalar template value."""
        return str(value).replace("{zone}", zone)
    sections = [dict(s, brief=fz(s.get("brief", ""))) for s in (th.get("sections") or []) if isinstance(s, dict)]
    # Per-theme charts (so each rotated theme carries its OWN data chart: a real sql-agent chart
    # where the dataset covers the theme, or a web-extracted chart where it does not). {zone} is
    # interpolated through every string of each chart spec (titles, SQL questions, web topics).
    def fz_deep(o: Any) -> Any:
        """Interpolate the selected zone through a nested JSON-like object."""
        if isinstance(o, str):
            return o.replace("{zone}", zone)
        if isinstance(o, list):
            return [fz_deep(x) for x in o]
        if isinstance(o, dict):
            return {k: fz_deep(v) for k, v in o.items()}
        return o
    theme_charts = [fz_deep(c) for c in (th.get("charts") or []) if isinstance(c, dict)]
    # Per-zone geopolitical map (so a themed researcher whose zone rotates still carries a map of
    # the relevant region). {zone} placeholders in the map's title/caption are interpolated.
    zone_map = (rotation.get("zone_maps") or {}).get(zone)
    if isinstance(zone_map, dict):
        zone_map = dict(zone_map)
        if zone_map.get("title"):
            zone_map["title"] = fz(zone_map["title"])
        if zone_map.get("caption"):
            zone_map["caption"] = fz(zone_map["caption"])
    return {
        "name": th.get("name"),
        "zone": zone,
        "target": fz(th["target"]) if th.get("target") else None,
        "title": fz(th["title"]) if th.get("title") else None,
        "sections": sections,
        "zone_map": zone_map if isinstance(zone_map, dict) else None,
        "charts": theme_charts,
    }


def _select_rotated_country(rotation: Any, day_of_year: int) -> Optional[Dict[str, Any]]:
    """Deterministically pick today's country from a ``country_rotation`` config so the TB
    country report rotates through countries ('next at random' = next in the deterministic
    daily cycle) instead of always Hungary.

    ``rotation`` = ``{"countries": [{"name": "Hungary", "bbox": [minx,miny,maxx,maxy]}, ...]}``.
    Returns ``{name, bbox}`` for ``day_of_year`` (cycled), or ``None`` if empty."""
    if not isinstance(rotation, dict):
        return None
    countries = [c for c in (rotation.get("countries") or []) if isinstance(c, dict) and c.get("name")]
    if not countries:
        return None
    c = countries[day_of_year % len(countries)]
    bbox = c.get("bbox")
    return {"name": str(c["name"]), "bbox": list(bbox) if isinstance(bbox, (list, tuple)) else None}


_RUN_ROUND_ROBIN_TOKEN = re.compile(
    r"\{\{run\.round_robin:(\d{4}-\d{2}-\d{2}):([^{}]+?)\}\}"
)


def _interp_round_robin_tokens(obj: Any, run_date: "_datetime.date") -> Any:
    """Resolve schedule-owned daily round-robin tokens in a report configuration.

    The Scheduler persists its source template unchanged, including
    ``{{run.round_robin:<anchor>:a|b|...}}`` tokens.  Resolve that runtime
    selection before the model sees the report configuration so the target,
    map focus, captions and SQL specification identify the same country.  This
    is data/configuration interpolation only; it never authors report prose.
    Malformed tokens are deliberately preserved for the existing unresolved-
    placeholder quality gate to reject.
    """

    if isinstance(obj, str):
        def replace(match: re.Match[str]) -> str:
            try:
                anchor = _datetime.date.fromisoformat(match.group(1))
            except ValueError:
                return match.group(0)
            choices = [part.strip() for part in match.group(2).split("|") if part.strip()]
            if not choices:
                return match.group(0)
            return choices[(run_date - anchor).days % len(choices)]

        return _RUN_ROUND_ROBIN_TOKEN.sub(replace, obj)
    if isinstance(obj, list):
        return [_interp_round_robin_tokens(value, run_date) for value in obj]
    if isinstance(obj, dict):
        return {key: _interp_round_robin_tokens(value, run_date) for key, value in obj.items()}
    return obj


def _country_from_visual_focus(rotation: Any, visuals: Any) -> Optional[Dict[str, Any]]:
    """Select a configured country whose resolved map focus names it exactly."""

    if not isinstance(rotation, dict) or not isinstance(visuals, dict):
        return None
    countries = [country for country in (rotation.get("countries") or [])
                 if isinstance(country, dict) and country.get("name")]
    focuses = {
        str(map_spec.get("focus_country") or "").strip()
        for map_spec in (visuals.get("maps") or [])
        if isinstance(map_spec, dict) and isinstance(map_spec.get("focus_country"), str)
    }
    for country in countries:
        if str(country["name"]).strip() in focuses:
            bbox = country.get("bbox")
            return {
                "name": str(country["name"]),
                "bbox": list(bbox) if isinstance(bbox, (list, tuple)) else None,
            }
    return None


def _interp_country(obj: Any, country: str) -> Any:
    """Recursively replace the ``{country}`` placeholder in every string of a JSON-like
    structure (used to specialise the rotating TB country report's title, section briefs,
    map and SQL-chart questions to the selected country)."""
    if isinstance(obj, str):
        return obj.replace("{country}", country)
    if isinstance(obj, list):
        return [_interp_country(x, country) for x in obj]
    if isinstance(obj, dict):
        return {k: _interp_country(v, country) for k, v in obj.items()}
    return obj


def _interp_run_date(obj: Any, run_date: "_datetime.date") -> Any:
    """Expand schedule-owned run-date tokens throughout a JSON-like report spec.

    Client-facing prose uses a readable date, while machine-oriented ``$RUN_DATE``
    fields such as map timestamps use ISO format. Expanding the complete spec before
    composition keeps subjects, headings, captions and reporting periods aligned.
    """
    readable = f"{run_date.day} {run_date.strftime('%B %Y')}"
    iso = run_date.isoformat()

    def expand(value: str) -> str:
        return (
            value.replace("{run_date}", readable)
            .replace("{current_date}", iso)
            .replace("{report_date}", iso)
            .replace("$RUN_DATE", iso)
            .replace("$CURRENT_DATE", iso)
            .replace("$REPORT_DATE", iso)
        )

    if isinstance(obj, str):
        return expand(obj)
    if isinstance(obj, list):
        return [_interp_run_date(item, run_date) for item in obj]
    if isinstance(obj, dict):
        return {key: _interp_run_date(value, run_date) for key, value in obj.items()}
    return obj


def _strip_trailing_sources(text: str) -> str:
    """Remove the document's trailing top-level Sources/References section (the LAST one) so it
    can be replaced with the real captured links. Crucially this cuts only at a top-level ``#``/
    ``##`` heading and at the LAST such heading — an inline ``### Sources``/``### References``
    sub-heading the generator emits *inside* an early section therefore never truncates the
    document. (The previous ``\\n#+\\s*Sources\\b.*$`` with DOTALL matched the FIRST heading at any
    level and deleted every section after it — collapsing deep multi-section reports to just the
    opening section.)"""
    matches = list(_TOP_SOURCES_RE.finditer(text))
    if not matches:
        return text.rstrip()
    # Cut at the FIRST top-level Sources/References heading (not the last): a research report's
    # references are always its final section, so everything from the first such heading onward is
    # reference material. Cutting at the last one left an earlier duplicate behind — the cause of
    # "References appear twice". Removing from the first collapses ALL trailing Sources/References
    # blocks so the pipeline can append exactly ONE canonical Sources section.
    return text[:matches[0].start()].rstrip()


def _consolidate_sources(text: str) -> tuple:
    """Remove EVERY bare Sources/References section — top-level ``##`` AND per-section ``###`` — but
    COLLECT the citation lines they contained, so the pipeline can emit exactly ONE consolidated
    Sources section at the very end WITHOUT losing the links.

    Small models sprinkle a ``### Sources``/``### References`` block inside many individual sections
    (the "we still have multiple Sources sections" defect). Simply deleting them dropped every link
    when the separately-captured research block happened to be empty (a report with 0 links). Here
    each such section's body is removed from the flow but its list-item / URL / ``[n]`` citation
    lines are gathered and returned. Only a BARE "Sources"/"References" heading matches — a real
    section like "Methodology and Evidence Basis" is preserved. Returns (body_without_sources,
    collected_citation_lines)."""
    lines = text.split("\n")
    out: List[str] = []
    collected: List[str] = []
    i, n = 0, len(lines)
    while i < n:
        # A TOP-LEVEL (##) heading must be a BARE "Sources"/"References" (so "Methodology and
        # Evidence Basis" — the real methodology section — is preserved). A SUB-heading (###) that
        # merely CONTAINS the word (e.g. "Data Collection and Sources", "Notes and References")
        # is also removed: it is the second, differently-formatted citation set the model tucks
        # inside the methodology section, which duplicates the single canonical Sources list.
        _h2 = re.match(
            r"##[ \t]+(?:(?:numbered[ \t]+)?(?:sources|references)|source[ \t]+register)[ \t]*:?[ \t]*$",
            lines[i],
            re.IGNORECASE,
        )
        _h3 = re.match(
            r"###[ \t]+.*\b(?:sources|references|source[ \t]+register)\b",
            lines[i],
            re.IGNORECASE,
        )
        if _h2 or _h3:
            lvl = 2 if _h2 else 3
            i += 1
            while i < n:
                mh = re.match(r"(#{1,6})[ \t]+", lines[i])
                if mh and len(mh.group(1)) <= lvl:
                    break
                _l = lines[i]
                # keep only real citation lines (list items, URLs, or [n] markers) — not blank/prose
                if _l.strip() and (re.match(r"\s*(?:[-*]|\d+[.)])\s+", _l) or "http" in _l or re.search(r"\[\d+\]", _l)):
                    collected.append(_l.strip())
                i += 1
            continue
        out.append(lines[i])
        i += 1
    return "\n".join(out).rstrip(), collected


def _canonical_numbered_sources(sources: Any) -> str:
    """Return one fail-closed, numbered Markdown Sources section.

    ``compose_report`` already normalises its captured sources, but
    ``publish_document`` may replace that tail with the original research pack.
    Search providers legitimately return bullets, bracket numbers, or plain URLs;
    normalise that final replacement too so the rendered report and quality gate
    evaluate the same canonical source list.
    """
    text = str(sources or "")
    entries: List[str] = []
    seen: set = set()
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate or re.match(r"^#{1,6}\s+(?:numbered\s+)?(?:sources|references)\s*:?[ \t]*$", candidate, re.I):
            continue
        if not re.search(r"https?://", candidate):
            continue
        candidate = re.sub(
            r"^\s*(?:(?:[-*]|\[\d+\]|\d+[.)])\s*)+",
            "",
            candidate,
        ).strip()
        key_match = re.search(r"https?://[^)\s\]]+", candidate)
        key = (key_match.group(0).rstrip(".,;:") if key_match else candidate).lower()
        if candidate and key not in seen:
            seen.add(key)
            entries.append(candidate)
    if not entries:
        return ""
    return "## Sources\n\n" + "\n".join(
        f"{index}. {entry}" for index, entry in enumerate(entries, start=1)
    )


def _merge_canonical_sources(content: str, sources: Any) -> str:
    """Merge researched and model-cited URLs into one canonical source tail."""
    body, generated = _consolidate_sources(content)
    combined = str(sources or "").rstrip()
    trusted_urls = {
        match.group(0).rstrip(".,;:")
        for match in re.finditer(r"https?://[^)\s\]]+", combined)
    }
    # A model may invent direct URLs in prose or evidence tables even when the
    # final Sources register is replaced with the validated research pack.  Keep
    # link text, but remove any body URL that is not an exact member of that pack.
    # This preserves grounded citations while preventing a plausible-looking
    # hallucinated URL from bypassing the canonical source boundary.
    def _trusted_markdown_link(match: re.Match[str]) -> str:
        label, url = match.group(1), match.group(2).rstrip(".,;:")
        return match.group(0) if url in trusted_urls else label

    body = re.sub(
        r"\[([^\]]+)\]\((https?://[^)\s]+)\)",
        _trusted_markdown_link,
        body,
    )

    def _trusted_plain_url(match: re.Match[str]) -> str:
        url = match.group(0).rstrip(".,;:")
        suffix = match.group(0)[len(url):]
        return match.group(0) if url in trusted_urls else suffix

    body = re.sub(r"https?://[^\s)\]]+", _trusted_plain_url, body)
    # A descriptive title does not make a model-invented URL real. Preserve only
    # generated citations whose exact URL was present in the validated research pack.
    generated = [
        line for line in generated
        if re.search(r"\[[^\]]*[A-Za-z][^\]]*\]\(https?://", line)
        and any(url in trusted_urls for url in re.findall(r"https?://[^)\s\]]+", line))
    ]
    if generated:
        combined = (combined + "\n" if combined else "") + "\n".join(generated)
    canonical = _canonical_numbered_sources(combined)
    return body.rstrip() + (("\n\n" + canonical) if canonical else "")


def _deacc(s: str) -> str:
    """Drop combining diacritics so configured entity aliases compare equal."""
    return "".join(c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c))


def _bare_city(hub: str) -> str:
    """Return the leading place/entity name before optional parenthetical/comma detail."""
    h = re.sub(r"\*+", "", hub or "").strip()
    return re.split(r"\s*[\(,]", h)[0].strip()


def _parse_ranking_hubs(md: str) -> List[str]:
    """Return the ordered Hub column of the report's ranking table (full 'City (Country)' cells),
    or [] when the document has no rank+hub table (W28M-1636 R4)."""
    lines = md.split("\n")
    for i, ln in enumerate(lines):
        if "|" in ln and re.search(r"\brank\b", ln, re.I) and re.search(r"\bhub\b", ln, re.I):
            cols = [c.strip().lower() for c in ln.strip().strip("|").split("|")]
            hub_idx = next((k for k, c in enumerate(cols) if "hub" in c), None)
            if hub_idx is None:
                continue
            out: List[str] = []
            for j in range(i + 1, len(lines)):
                if "|" not in lines[j] or not lines[j].strip().startswith("|"):
                    break
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                if hub_idx < len(cells) and not re.match(r"^[-:\s]+$", cells[0]):
                    hub = re.sub(r"\*+", "", cells[hub_idx]).strip()
                    if hub:
                        out.append(hub)
            return out
    return []


# Prose (any level heading OR sentence) that MAKES a primary team-placement recommendation. This
# deliberately does NOT match a bare "Executive Summary" heading: the paragraph after that heading
# is a brand/scope preamble that enumerates all hubs in ranking order, which would MASK the actual
# (possibly inconsistent) recommendation that follows (W28M-1636 R4, msg-7127).
_REC_CUE_RE = re.compile(
    r"we\s+recommend"
    r"|recommends?\s+(?:anchoring|placing|basing|establishing|siting|locating|headquartering|the\s+team|the\s+delivery)"
    r"|bottom.line recommendation|top recommendation|final recommendation|primary recommendation"
    r"|the\s+recommendation\s+is\b|recommendation\s+is\s+to\b",
    re.I,
)


def _recommendation_named(text: str, ranking: List[str]) -> List[str]:
    """First two distinct ranked hubs named in the report's RECOMMENDATION prose (diacritic-
    insensitive). Anchors each 400-char window on an actual recommendation cue (never a section
    heading or a hub enumeration) and returns the first window that names >=2 ranked hubs, matching
    the builder's fail-closed gate so the two never disagree (W28M-1636 R4)."""
    # drop markdown table rows so a nearby ranking/comparison table cannot pollute a window
    plain = _deacc(re.sub(r"\s+", " ", re.sub(r"(?m)^\s*\|.*$", "", text)))
    for cue in _REC_CUE_RE.finditer(plain):
        window = plain[cue.start(): cue.start() + 400]
        hits: List[tuple] = []
        for hub in ranking:
            city = _bare_city(hub)
            if not city:
                continue
            m = re.search(r"\b" + re.escape(_deacc(city)) + r"\b", window, re.I)
            if m:
                hits.append((m.start(), city))
        out: List[str] = []
        for _, city in sorted(hits):
            if city not in out:
                out.append(city)
        if len(out) >= 2:
            return out[:2]
    return []


def _bluf_ranking_status(md: str):
    """(consistent, ranking, named_first_two). Consistent when the report has no ranking table OR
    its recommendation names no >=2 ranked hubs OR the first two named hubs equal the ranking's
    top-2 (diacritic-insensitive). W28M-1636 R4."""
    ranking = _parse_ranking_hubs(md)
    if len(ranking) < 2:
        return True, ranking, []
    named = _recommendation_named(md, ranking)
    if len(named) < 2:
        return True, ranking, named
    top2 = [_deacc(_bare_city(ranking[0])).lower(), _deacc(_bare_city(ranking[1])).lower()]
    got = [_deacc(named[0]).lower(), _deacc(named[1]).lower()]
    return got == top2, ranking, named[:2]


def _report_content_defects(
    md: str,
    controls: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """W28M-1636 R5: content-fidelity defects the LOCAL AGENT must not emit. The quality gate REJECTS
    these fail-closed (it never repairs them — deterministic repair of content is forbidden), so a
    defective report is never delivered and the offending section is regenerated by the model.
    Works on markdown or HTML. Returns human-readable defect strings; empty means clean."""
    defects: List[str] = []

    def _snip(m) -> str:
        s = max(0, m.start() - 25)
        return re.sub(r"\s+", " ", md[s:m.end() + 25]).strip()[:80]

    for m in re.finditer(r"\[\s*[nN]\s*/?\s*[aA]\.?\s*\]", md):
        defects.append(f"unresolved [n/a] citation near: '{_snip(m)}' — DELETE the '[n/a]'")
        break
    m = re.search(r"(?<!\w)\[\s*\](?!\w)", md)
    if m:
        defects.append(f"empty [] citation bracket near: '{_snip(m)}' — DELETE the '[]'")
    m = re.search(r"\[[^\]]*(?:…|\.\.\.)[^\]]*\]\(", md) or re.search(r">[^<]*(?:…|\.\.\.)\s*</a>", md)
    if m:
        defects.append(f"ellipsis-truncated reference/link label near: '{_snip(m)}' — write a COMPLETE label")
    m = re.search(r"SHA[\- ]?256[^0-9a-fA-F]{0,4}[0-9a-fA-F]{16,}", md)
    if m:
        defects.append(f"printed row SHA-256 digest near: '{_snip(m)}' — replace the hex with 'recorded in the run contract'")
    m = re.search(r"\[\s*SQL[-_ ]?\d{4}[-_ ]?[0-9A-Fa-f]{8,}", md)
    if m:
        defects.append(f"fabricated [SQL-YYYY-hash] token near: '{_snip(m)}' — remove it")
    # local-currency SALARY figures are a body-prose defect; a currency string INSIDE a source/link
    # LABEL (e.g. a Glassdoor page title "... Salary R$16,917 - Glassdoor") is a citation title, not
    # a salary claim, so strip markdown/HTML link labels before checking.
    _prose = re.sub(r"\[[^\]]*\]\([^)]*\)", " ", md)
    _prose = re.sub(r"<a\b[^>]*>.*?</a>", " ", _prose, flags=re.S | re.I)
    m = re.search(r"\b(?:CLP|COP|ARS|BRL|MXN|PEN|UYU)\s?[\d.,]+|R\$\s?[\d.,]+|[\d.,]+\s*(?:pesos|reais|reales)\b", _prose, re.I)
    if m:
        defects.append(f"local-currency salary figure '{m.group(0).strip()[:30]}' — restate as an annual US-DOLLAR figure only")
    m = re.search(
        r"SQL[^.]{0,50}(?:was not executed|were not executed|not executed in this run|"
        r"execution[^.]{0,15}pending|disclosure[^.]{0,15}pending)", md, re.I,
    )
    if m:
        defects.append(f"claims SQL not executed/pending near: '{_snip(m)}' — the SQL WAS executed; state it was executed")
    for bad in ("economic_stability", "tech_finance_ecosystem"):
        if re.search(r"\b" + re.escape(bad) + r"\b", md):
            defects.append(f"invented SQL table name '{bad}' — use only the real indicator tables")
    # Product profiles that deliver an English reader-facing report can opt in to a
    # script-integrity check.  A stray CJK code point is neither a citation marker
    # nor an approved English punctuation mark: it is almost always token-stream
    # contamination (for example, "number端"), which must be returned to the model
    # as a fail-closed authoring deficit rather than silently carried into PDF/email.
    # This is validation only; it neither removes nor rewrites model-authored prose.
    if isinstance(controls, dict) and controls.get("unexpected_cjk_forbidden"):
        m = re.search(r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]", md)
        if m:
            defects.append(
                f"unexpected CJK glyph '{m.group(0)}' near: '{_snip(m)}' — re-author the affected English prose"
            )
    return defects


def _markdown_h2_sections(content: str) -> List[Dict[str, str]]:
    """Return exact H2 sections and their bodies without changing report prose."""
    matches = list(re.finditer(r"(?m)^##\s+([^\n#]+?)\s*$", content))
    sections: List[Dict[str, str]] = []
    for index, match in enumerate(matches):
        title = re.sub(r"\s+", " ", match.group(1)).strip()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        sections.append({"title": title, "body": content[match.end():end]})
    return sections


def _normalise_quality_prose(value: str) -> str:
    """Normalise prose for comparison only; never return it to a reader."""
    text = re.sub(r"\[[^\]]*\]\([^)]*\)", " ", value)
    text = re.sub(r"\[\d+\]", " ", text)
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[`*_>#]", " ", text)
    return " ".join(re.findall(r"[A-Za-z0-9]+", text.lower()))


def _configured_repetition_metrics(content: str, controls: Dict[str, Any]) -> Dict[str, Any]:
    """Measure configured repeated prose without making product-specific assertions."""
    contract = controls.get("repetition") if isinstance(controls.get("repetition"), dict) else {}
    if not contract or not contract.get("required"):
        return {"enabled": False, "duplicate_paragraphs": [], "repeated_ngrams": [], "affected_sections": []}

    minimum_words = max(3, int(contract.get("minimum_phrase_words") or 12))
    ngram_words = max(3, int(contract.get("ngram_words") or minimum_words))
    maximum_occurrences = max(1, int(contract.get("maximum_occurrences") or 1))
    excluded_titles = {
        re.sub(r"\s+", " ", str(title)).strip().lower()
        for title in (contract.get("exclude_section_titles") or ["Sources", "References"])
        if str(title).strip()
    }
    paragraphs: List[Dict[str, Any]] = []
    for section in _markdown_h2_sections(content):
        if section["title"].lower() in excluded_titles:
            continue
        for block in re.split(r"\n\s*\n", section["body"]):
            stripped = block.strip()
            if not stripped or stripped.startswith("|") or stripped.startswith("-") or stripped.startswith("*"):
                continue
            normalised = _normalise_quality_prose(stripped)
            tokens = normalised.split()
            if len(tokens) >= minimum_words:
                paragraphs.append({"section": section["title"], "normalised": normalised, "tokens": tokens})

    by_paragraph: Dict[str, List[str]] = {}
    by_ngram: Dict[str, List[str]] = {}
    for paragraph in paragraphs:
        by_paragraph.setdefault(paragraph["normalised"], []).append(paragraph["section"])
        tokens = paragraph["tokens"]
        for offset in range(0, len(tokens) - ngram_words + 1):
            phrase = " ".join(tokens[offset:offset + ngram_words])
            by_ngram.setdefault(phrase, []).append(paragraph["section"])

    duplicate_paragraphs = [
        {"occurrences": len(sections), "sections": sorted(set(sections)), "words": len(paragraph.split())}
        for paragraph, sections in by_paragraph.items()
        if len(sections) > maximum_occurrences
    ]
    repeated_ngrams = [
        {
            "occurrences": len(sections),
            "sections": sorted(set(sections)),
            "words": len(phrase.split()),
            "phrase": phrase,
        }
        for phrase, sections in by_ngram.items()
        if len(sections) > maximum_occurrences
    ]
    duplicate_paragraphs.sort(key=lambda item: (-item["occurrences"], -item["words"], item["sections"]))
    repeated_ngrams.sort(key=lambda item: (-item["occurrences"], -item["words"], item["sections"]))
    affected_sections = sorted({
        section
        for item in [*duplicate_paragraphs, *repeated_ngrams]
        for section in item["sections"]
    })
    return {
        "enabled": True,
        "minimum_phrase_words": minimum_words,
        "ngram_words": ngram_words,
        "maximum_occurrences": maximum_occurrences,
        "duplicate_paragraphs": duplicate_paragraphs[:20],
        "repeated_ngrams": repeated_ngrams[:20],
        "affected_sections": affected_sections,
    }


def _configured_section_quality_metrics(
    content: str,
    controls: Dict[str, Any],
    repetition: Dict[str, Any],
) -> Dict[str, Any]:
    """Score configured H2 sections from observable depth and grounding signals."""
    contract = controls.get("section_quality") if isinstance(controls.get("section_quality"), dict) else {}
    if not contract or not contract.get("required"):
        return {"enabled": False, "sections": {}, "minimum_score": None, "failures": []}

    defaults = {
        "minimum_words": max(1, int(contract.get("minimum_words") or 1)),
        "minimum_paragraphs": max(1, int(contract.get("minimum_paragraphs") or 1)),
        "minimum_citation_markers": max(0, int(contract.get("minimum_citation_markers") or 0)),
        "minimum_concrete_facts": max(0, int(contract.get("minimum_concrete_facts") or 0)),
    }
    overrides = contract.get("section_overrides") if isinstance(contract.get("section_overrides"), dict) else {}
    weights = contract.get("weights") if isinstance(contract.get("weights"), dict) else {}
    score_weights = {
        "depth": max(0.0, float(weights.get("depth") or 40)),
        "citations": max(0.0, float(weights.get("citations") or 25)),
        "facts": max(0.0, float(weights.get("facts") or 20)),
        "originality": max(0.0, float(weights.get("originality") or 15)),
    }
    total_weight = sum(score_weights.values()) or 100.0
    minimum_score = float(contract.get("minimum_score") or 0)
    required_titles = [
        re.sub(r"\s+", " ", str(title)).strip()
        for title in (controls.get("required_section_titles") or [])
        if str(title).strip()
    ]
    found = {section["title"]: section["body"] for section in _markdown_h2_sections(content)}
    section_metrics: Dict[str, Dict[str, Any]] = {}
    failures: List[str] = []
    for title in required_titles:
        body = found.get(title, "")
        override = overrides.get(title) if isinstance(overrides.get(title), dict) else {}
        limits = {
            key: max(0 if key.startswith("minimum_") and key != "minimum_words" else 1, int(override.get(key, defaults[key])))
            for key in defaults
        }
        words = len(re.findall(r"\w+", body))
        prose_blocks = [
            block for block in re.split(r"\n\s*\n", body)
            if _normalise_quality_prose(block).strip() and not block.lstrip().startswith("|")
        ]
        citations = sorted(set(re.findall(r"\[(\d+)\]", body)))
        concrete_facts = len(re.findall(r"\b\d[\d,.]*%?\b", body))
        depth_ratio = min(1.0, words / limits["minimum_words"]) * 0.7 + min(
            1.0, len(prose_blocks) / limits["minimum_paragraphs"]
        ) * 0.3
        citation_ratio = 1.0 if not limits["minimum_citation_markers"] else min(
            1.0, len(citations) / limits["minimum_citation_markers"]
        )
        fact_ratio = 1.0 if not limits["minimum_concrete_facts"] else min(
            1.0, concrete_facts / limits["minimum_concrete_facts"]
        )
        original = 0.0 if title in set(repetition.get("affected_sections") or []) else 1.0
        components = {
            "depth": round(score_weights["depth"] * depth_ratio, 1),
            "citations": round(score_weights["citations"] * citation_ratio, 1),
            "facts": round(score_weights["facts"] * fact_ratio, 1),
            "originality": round(score_weights["originality"] * original, 1),
        }
        score = round(100.0 * sum(components.values()) / total_weight, 1)
        failures_for_section: List[str] = []
        if words < limits["minimum_words"]:
            failures_for_section.append(f"words={words}<{limits['minimum_words']}")
        if len(prose_blocks) < limits["minimum_paragraphs"]:
            failures_for_section.append(f"paragraphs={len(prose_blocks)}<{limits['minimum_paragraphs']}")
        if len(citations) < limits["minimum_citation_markers"]:
            failures_for_section.append(f"citations={len(citations)}<{limits['minimum_citation_markers']}")
        if concrete_facts < limits["minimum_concrete_facts"]:
            failures_for_section.append(f"concrete_facts={concrete_facts}<{limits['minimum_concrete_facts']}")
        if score < minimum_score:
            failures_for_section.append(f"score={score}<{minimum_score}")
        section_metrics[title] = {
            "score": score,
            "components": components,
            "words": words,
            "paragraphs": len(prose_blocks),
            "citation_markers": len(citations),
            "concrete_facts": concrete_facts,
            "limits": limits,
            "failures": failures_for_section,
        }
        if failures_for_section:
            failures.append(title + ": " + ", ".join(failures_for_section))
    return {
        "enabled": True,
        "minimum_score": minimum_score,
        "sections": section_metrics,
        "failures": failures,
    }


def _configured_required_visual_classes(controls: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalise caller-owned visual-class requirements for the delivery gate."""
    raw = controls.get("required_visual_classes") or []
    if isinstance(raw, dict):
        raw = [dict({"id": key}, **(value if isinstance(value, dict) else {})) for key, value in raw.items()]
    classes: List[Dict[str, Any]] = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, str):
            item = {"id": item}
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("id") or item.get("visual_class") or "").strip()
        if identifier:
            classes.append({
                "id": identifier,
                "minimum": max(1, int(item.get("minimum") or 1)),
                "source_backed": bool(item.get("source_backed")),
                "minimum_source_urls": max(0, int(item.get("minimum_source_urls") or 0)),
                "required_metadata_fields": [
                    str(field).strip()
                    for field in (item.get("required_metadata_fields") or [])
                    if str(field).strip()
                ],
            })
    return classes


def _configured_required_source_family_metrics(
    sources_tail: str,
    controls: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate caller-owned source families against the final numbered register.

    The gate only observes model-authored source rows. It never selects a source,
    inserts a citation, or repairs report prose.
    """
    raw = controls.get("required_source_families") or []
    if isinstance(raw, dict):
        raw = [
            {"id": family_id, **(value if isinstance(value, dict) else {})}
            for family_id, value in raw.items()
        ]
    rows = [
        line.strip()
        for line in (sources_tail or "").splitlines()
        if re.match(r"^\s*(?:\[\d+\]|\d+[.)])\s+", line)
        and re.search(r"https?://", line)
    ]
    families: List[Dict[str, Any]] = []
    failures: List[str] = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, str):
            item = {"id": item, "names": [item]}
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("id") or item.get("name") or "").strip()
        if not identifier:
            continue
        names = [
            str(value).strip()
            for value in (item.get("names") or item.get("terms") or [])
            if str(value).strip()
        ]
        domains = [
            str(value).strip().casefold().lstrip(".")
            for value in (item.get("domains") or [])
            if str(value).strip()
        ]
        minimum = max(1, int(item.get("minimum") or 1))
        matching_rows: List[str] = []
        for row in rows:
            row_folded = unicodedata.normalize("NFKC", row).casefold()
            name_match = any(
                re.search(r"(?<![\w])" + re.escape(name.casefold()) + r"(?![\w])", row_folded)
                for name in names
            )
            urls = re.findall(r"https?://[^\s)>]+", row)
            domain_match = False
            for url in urls:
                try:
                    hostname = (urlsplit(url.rstrip(".,;]")).hostname or "").casefold()
                except ValueError:
                    hostname = ""
                if any(hostname == domain or hostname.endswith("." + domain) for domain in domains):
                    domain_match = True
                    break
            if name_match or domain_match:
                matching_rows.append(row)
        families.append({
            "id": identifier,
            "minimum": minimum,
            "names": names,
            "domains": domains,
            "matches": len(matching_rows),
        })
        if len(matching_rows) < minimum:
            failures.append(f"{identifier} ({len(matching_rows)} of {minimum})")
    return {"families": families, "failures": failures}


def _configured_required_topic_coverage_metrics(
    narrative_content: str,
    controls: Dict[str, Any],
) -> Dict[str, Any]:
    """Measure caller-owned topic guards in the model-authored narrative."""
    raw = controls.get("required_topic_coverage") or []
    if isinstance(raw, dict):
        raw = [
            {"id": topic_id, **(value if isinstance(value, dict) else {})}
            for topic_id, value in raw.items()
        ]
    blocks = [
        block.strip()
        for block in re.split(r"\n\s*\n", narrative_content or "")
        if block.strip()
    ]
    topics: List[Dict[str, Any]] = []
    failures: List[str] = []
    for item in raw if isinstance(raw, list) else []:
        if isinstance(item, str):
            item = {"id": item, "terms": [item]}
        if not isinstance(item, dict):
            continue
        identifier = str(item.get("id") or item.get("name") or "").strip()
        terms = [
            str(term).strip()
            for term in (item.get("terms") or item.get("names") or [])
            if str(term).strip()
        ]
        if not identifier or not terms:
            continue
        minimum = max(1, int(item.get("minimum") or 1))
        citation_required = bool(item.get("citation_required"))
        matching_blocks: List[str] = []
        for block in blocks:
            normalised = unicodedata.normalize("NFKC", block).casefold()
            if not any(
                re.search(r"(?<![\w])" + re.escape(term.casefold()) + r"(?![\w])", normalised)
                for term in terms
            ):
                continue
            if citation_required and not re.search(r"\[\d+\]", block):
                continue
            matching_blocks.append(block)
        topics.append({
            "id": identifier,
            "minimum": minimum,
            "citation_required": citation_required,
            "matches": len(matching_blocks),
        })
        if len(matching_blocks) < minimum:
            qualifier = " cited" if citation_required else ""
            failures.append(f"{identifier} ({len(matching_blocks)} of {minimum}{qualifier})")
    return {"topics": topics, "failures": failures}


def _model_authored_quality_assessment_metrics(
    assessment: Any,
    controls: Dict[str, Any],
) -> Dict[str, Any]:
    """Validate the optional model-authored self-assessment contract."""
    contract = (
        controls.get("model_authored_quality_assessment")
        if isinstance(controls.get("model_authored_quality_assessment"), dict)
        else {}
    )
    if not contract or not contract.get("required"):
        return {"required": False, "sections": {}, "failures": []}
    expected_titles = [
        re.sub(r"\s+", " ", str(title)).strip()
        for title in (controls.get("required_section_titles") or [])
        if str(title).strip()
    ]
    threshold = float(contract.get("minimum_score") or 0)
    failures: List[str] = []
    if not isinstance(assessment, dict):
        return {
            "required": True,
            "sections": {},
            "failures": ["model-authored quality self-assessment is missing or malformed"],
        }
    rows = assessment.get("sections")
    if not isinstance(rows, list):
        return {
            "required": True,
            "sections": {},
            "failures": ["model-authored quality self-assessment has no sections array"],
        }
    values: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            failures.append("model-authored quality self-assessment contains a non-object section")
            continue
        title = re.sub(r"\s+", " ", str(row.get("title") or "")).strip()
        try:
            score = float(row.get("score"))
        except (TypeError, ValueError):
            failures.append(f"model-authored quality self-assessment has non-numeric score for {title or 'unnamed section'}")
            continue
        action = str(row.get("regeneration_action") or "").strip().lower()
        if not title or title in values:
            failures.append("model-authored quality self-assessment has duplicate or blank section title")
            continue
        if not 0.0 <= score <= 100.0:
            failures.append(f"model-authored quality self-assessment score outside 0..100 for {title}")
        if action not in {"accept", "regenerate"}:
            failures.append(f"model-authored quality self-assessment has invalid regeneration action for {title}")
        if score < threshold:
            failures.append(f"model-authored quality self-assessment score={score}<{threshold} for {title}")
        if action == "regenerate":
            failures.append(f"model-authored quality self-assessment requests regeneration for {title}")
        values[title] = {"score": score, "regeneration_action": action}
    missing = [title for title in expected_titles if title not in values]
    unexpected = [title for title in values if title not in expected_titles]
    if missing:
        failures.append("model-authored quality self-assessment missing section(s): " + "; ".join(missing))
    if unexpected:
        failures.append("model-authored quality self-assessment has unexpected section(s): " + "; ".join(unexpected))
    return {"required": True, "minimum_score": threshold, "sections": values, "failures": failures}


def _salary_consistency_defects(md: str, controls: Dict[str, Any]) -> List[str]:
    """Data-driven salary consistency gate.

    The caller supplies entity names and plausibility bounds in ``quality_controls``.
    This shared strategy code deliberately contains no demo-specific hubs or salary
    values; it only rejects inconsistent or implausible annual-USD figures that the
    model authored.
    """
    salary_control = controls.get("salary_consistency")
    if not isinstance(salary_control, dict) or not salary_control.get("required"):
        return []

    import html as _html

    content = md or ""
    entities_raw = salary_control.get("entities") or salary_control.get("hubs") or []
    entities: List[Dict[str, str]] = []
    for item in entities_raw:
        if isinstance(item, str):
            name = item.strip()
            if name:
                entities.append({"name": name, "country": ""})
        elif isinstance(item, dict):
            name = str(item.get("name") or item.get("city") or "").strip()
            if name:
                entities.append({"name": name, "country": str(item.get("country") or "").strip()})

    if not entities:
        return ["salary_consistency: required but no entities were supplied"]

    min_usd: int | None
    max_usd: int | None
    try:
        min_usd = int(salary_control["min_usd"]) if salary_control.get("min_usd") is not None else None
    except (TypeError, ValueError):
        min_usd = None
    try:
        max_usd = int(salary_control["max_usd"]) if salary_control.get("max_usd") is not None else None
    except (TypeError, ValueError):
        max_usd = None
    require_each = bool(salary_control.get("require_each_entity", True))
    try:
        window_chars = int(salary_control["window_chars"]) if salary_control.get("window_chars") is not None else None
    except (TypeError, ValueError):
        window_chars = None
    if window_chars is not None and window_chars < 1:
        window_chars = None
    try:
        backward_window_chars = (
            int(salary_control["backward_window_chars"])
            if salary_control.get("backward_window_chars") is not None
            else 0
        )
    except (TypeError, ValueError):
        backward_window_chars = 0
    if backward_window_chars < 0:
        backward_window_chars = 0

    money_re = re.compile(
        r"(?<![A-Za-z])(?:US\$|USD\s*\$?|\$)\s*([0-9]{2,3}(?:,[0-9]{3})+|[0-9]{2,3}(?:\.[0-9])?\s*k)\s*(?:/yr|per\s+year|annually|annual)?"
        r"|([0-9]{2,3}(?:,[0-9]{3})+|[0-9]{2,3}(?:\.[0-9])?\s*k)\s*(?:USD|US\s+dollars)\s*(?:/yr|per\s+year|annually|annual)?",
        re.I,
    )

    def _normalise(match: re.Match[str]) -> tuple[str, int, str] | None:
        raw_match = re.sub(r"\s+", " ", match.group(0)).strip()
        raw = (match.group(1) or match.group(2) or "").strip().lower().replace(" ", "")
        try:
            if raw.endswith("k"):
                value = int(round(float(raw[:-1]) * 1000))
            else:
                value = int(raw.replace(",", ""))
        except ValueError:
            return None
        return (f"US${value:,.0f}/yr", value, raw_match)

    def _fold(text: str) -> str:
        return "".join(
            ch
            for ch in unicodedata.normalize("NFKD", text)
            if not unicodedata.combining(ch)
        )

    def _visible_text(text: str) -> str:
        text = re.sub(r"<h[1-6]\b[^>]*>", "\n# ", text, flags=re.I)
        text = re.sub(r"</h[1-6]>", "\n", text, flags=re.I)
        text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
        text = re.sub(
            r"</(?:p|div|li|ul|ol|section|figure|figcaption)>\s*",
            "\n",
            text,
            flags=re.I,
        )
        text = _html.unescape(re.sub(r"<[^>]+>", " ", text))
        lines = [re.sub(r"[ \t\f\v]+", " ", line).strip() for line in text.splitlines()]
        return "\n".join(line for line in lines if line).strip()

    def _entity_hits(text: str) -> List[tuple[int, Dict[str, str]]]:
        folded = _fold(text)
        hits: List[tuple[int, Dict[str, str]]] = []
        seen: set[str] = set()
        for entity in entities:
            name = entity["name"]
            m = re.search(r"\b" + re.escape(_fold(name)) + r"\b", folded, re.I)
            if m and name not in seen:
                hits.append((m.start(), entity))
                seen.add(name)
        return sorted(hits, key=lambda item: item[0])

    require_token_format = str(
        salary_control.get("required_token_format")
        or salary_control.get("required_format")
        or ""
    ).strip().lower()
    require_canonical_token = bool(salary_control.get("require_canonical_token")) or (
        require_token_format in {
            "us_dollar_annual_token",
            "annual_usd_token",
            "us$/yr",
        }
    )
    reject_unscoped = bool(salary_control.get("reject_unscoped_salary_values"))
    reject_ambiguous = bool(salary_control.get("reject_ambiguous_multi_entity_salary"))

    def _canonical_token(raw: str) -> bool:
        return bool(re.fullmatch(r"US\$[0-9]{2,3}(?:,[0-9]{3})+/yr", raw.strip()))

    observed: Dict[str, List[tuple[str, int, str, str]]] = {entity["name"]: [] for entity in entities}
    format_issues: List[str] = []
    ambiguous_issues: List[str] = []
    unscoped_issues: List[str] = []

    def _add(entity: Dict[str, str], parsed: tuple[str, int, str], context: str) -> None:
        display, value, raw = parsed
        name = entity["name"]
        item = (display, value, raw, context)
        if item not in observed[name]:
            observed[name].append(item)
        if require_canonical_token and not _canonical_token(raw):
            format_issues.append(
                f"salary_consistency: {name} salary token {raw!r} is not canonical annual USD token format"
            )

    def _assign_money_in_text(text: str, context: str) -> None:
        visible = _visible_text(text)
        if not visible:
            return
        visible = re.sub(r"[*_`]+", "", visible)
        entity_hits = _entity_hits(visible)
        money_hits = [
            (m.start(), m.end(), parsed)
            for m in money_re.finditer(visible)
            for parsed in [_normalise(m)]
            if parsed
        ]
        if not money_hits:
            return
        if not entity_hits:
            if reject_unscoped:
                for _, _, parsed in money_hits:
                    unscoped_issues.append(
                        f"salary_consistency: unscoped salary token {parsed[2]!r} in {context}"
                    )
            return
        if len(entity_hits) == 1:
            for _, _, parsed in money_hits:
                _add(entity_hits[0][1], parsed, context)
            return

        if len(entity_hits) == len(money_hits):
            if re.search(r"\brespectively\b", visible, re.I) and entity_hits[-1][0] < money_hits[0][0]:
                for (_, entity), (_, _, parsed) in zip(entity_hits, money_hits):
                    _add(entity, parsed, context)
                return
            used_money: set[int] = set()
            for idx, (_, entity) in enumerate(entity_hits):
                start = entity_hits[idx][0]
                end = entity_hits[idx + 1][0] if idx + 1 < len(entity_hits) else len(visible)
                matches = [
                    (midx, parsed)
                    for midx, (mstart, _, parsed) in enumerate(money_hits)
                    if midx not in used_money and start <= mstart < end
                ]
                if len(matches) == 1:
                    midx, parsed = matches[0]
                    used_money.add(midx)
                    _add(entity, parsed, context)
                elif matches:
                    ambiguous_issues.append(
                        f"salary_consistency: {entity['name']} has ambiguous salary tokens in {context}"
                    )
            if len(used_money) == len(money_hits):
                return

        if reject_ambiguous:
            names = ", ".join(entity["name"] for _, entity in entity_hits)
            values = ", ".join(parsed[2] for _, _, parsed in money_hits)
            ambiguous_issues.append(
                f"salary_consistency: ambiguous multi-entity salary statement in {context}: {names} / {values}"
            )

    # Treat table rows as structured units first. This prevents one rendered HTML
    # table from collapsing into a large prose sentence where neighbouring hub
    # salaries are incorrectly counted against each other.
    for idx, row in enumerate(re.findall(r"<tr\b.*?</tr>", content, re.S | re.I), start=1):
        cells = re.findall(r"<t[dh]\b.*?</t[dh]>", row, re.S | re.I)
        if not cells:
            continue
        _assign_money_in_text(" | ".join(cells), f"html table row {idx}")

    for idx, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        if (
            stripped.startswith("|")
            and stripped.endswith("|")
            and stripped.count("|") >= 3
            and not re.fullmatch(r"\|[\s:\-|]+\|", stripped)
        ):
            _assign_money_in_text(stripped, f"markdown table row {idx}")

    prose = re.sub(r"<table\b.*?</table>", "\n", content, flags=re.S | re.I)
    prose = "\n".join(
        line for line in prose.splitlines()
        if not (line.strip().startswith("|") and line.strip().endswith("|") and line.count("|") >= 3)
    )
    plain = _visible_text(prose)
    issues: List[str] = []
    plain_lines = plain.splitlines()
    section_scoped_lines: set[int] = set()
    current_section_entity: Dict[str, str] | None = None
    section_entity_stack: List[tuple[int, Dict[str, str] | None]] = []
    for line_idx, line in enumerate(plain_lines, start=1):
        heading_match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", line)
        if heading_match:
            level = len(heading_match.group(1))
            while section_entity_stack and section_entity_stack[-1][0] >= level:
                section_entity_stack.pop()
            heading_hits = _entity_hits(heading_match.group(2))
            if len(heading_hits) == 1:
                current_section_entity = heading_hits[0][1]
            elif not heading_hits and section_entity_stack:
                current_section_entity = section_entity_stack[-1][1]
            else:
                current_section_entity = None
            section_entity_stack.append((level, current_section_entity))
            continue
        label_probe = re.sub(r"[*_`]+", "", line)
        salary_label_line = re.match(
            r"^\s*(?:[-*]\s*)?(?:annual\s+(?:usd\s+)?salary|salary|compensation)\s*:",
            label_probe,
            re.I,
        )
        if (
            current_section_entity
            and money_re.search(line)
            and not _entity_hits(line)
            and salary_label_line
        ):
            _assign_money_in_text(
                f"{current_section_entity['name']} {line}",
                f"section line {line_idx}",
            )
            section_scoped_lines.add(line_idx)

    segments: List[tuple[int, str]] = []
    for line_idx, line in enumerate(plain_lines, start=1):
        if line_idx in section_scoped_lines:
            continue
        segments.extend(
            (line_idx, seg)
            for seg in re.split(r"(?<=[.!?])\s+", line)
            if seg.strip()
        )
    for idx, (line_idx, segment) in enumerate(segments, start=1):
        if not money_re.search(segment):
            continue
        hits = _entity_hits(segment)
        if len(hits) <= 1 or not window_chars:
            _assign_money_in_text(segment, f"prose line {line_idx} segment {idx}")
            continue
        # Preserve the old locality control for dense prose: each entity gets only
        # salary tokens near its own mention, not every salary in a long paragraph.
        folded_segment = _fold(segment)
        for _, entity in hits:
            name = entity["name"]
            name_re = re.compile(r"\b" + re.escape(_fold(name)) + r"\b", re.I)
            for match in name_re.finditer(folded_segment):
                start = max(0, match.start() - backward_window_chars)
                end = min(len(segment), match.end() + window_chars)
                _assign_money_in_text(segment[start:end], f"prose line {line_idx} segment {idx}")

    issues.extend(dict.fromkeys(format_issues))
    issues.extend(dict.fromkeys(ambiguous_issues))
    issues.extend(dict.fromkeys(unscoped_issues))

    for entity in entities:
        name = entity["name"]
        entity_observed = observed.get(name) or []
        if not entity_observed:
            if require_each:
                issues.append(f"salary_consistency: {name} has no annual USD salary occurrence")
            continue
        display_values = sorted({v for v, _, _, _ in entity_observed})
        numeric_values = sorted({n for _, n, _, _ in entity_observed})
        if len(display_values) != 1 or len(numeric_values) != 1:
            issues.append(
                f"salary_consistency: {name} has multiple salary values "
                f"{', '.join(display_values)}"
            )
            continue
        value = numeric_values[0]
        if (min_usd is not None and value < min_usd) or (max_usd is not None and value > max_usd):
            bounds = []
            if min_usd is not None:
                bounds.append(f">={min_usd}")
            if max_usd is not None:
                bounds.append(f"<={max_usd}")
            issues.append(
                f"salary_consistency: {name} salary {display_values[0]} outside "
                f"configured annual USD range {' and '.join(bounds)}"
            )
    return issues


def _repair_required_front_matter(content: str, quality_controls: Dict[str, Any]) -> str:
    """Normalise required headings by reusing existing prose, never new report facts."""
    text = str(content or "")
    executive_re = re.compile(
        r"(?im)^##\s+(?:executive summary|key judgements|in brief)(?:\s+[-—:]\s+[^\n]+)?\s*$"
    )
    first_heading = re.search(r"(?m)^##\s+([^\n]+)\s*$", text)
    executive_required = quality_controls.get("executive_summary_required") or quality_controls.get(
        "require_executive_summary"
    )
    reporting_period_required = quality_controls.get(
        "reporting_period_required"
    ) or quality_controls.get("require_reporting_period")
    if executive_required and not executive_re.search(text):
        if first_heading:
            original = first_heading.group(1).strip()
            replacement = f"## Executive Summary — {original}"
            text = text[:first_heading.start()] + replacement + text[first_heading.end():]
    if reporting_period_required and not re.search(r"(?i)\breporting period\s*:", text):
        heading = executive_re.search(text) or re.search(r"(?m)^##\s+[^\n]+\s*$", text)
        if heading:
            declaration = "\n\nReporting period: the current run date and source cut-off stated in this report."
            text = text[:heading.end()] + declaration + text[heading.end():]
    return text


def _narrative_text_from_markdown_block(block: Any) -> str:
    """Return a block's prose after a leading Markdown heading, when present."""
    text = str(block or "").strip()
    return re.sub(r"\A#{1,6}\s+[^\n]*(?:\n|$)", "", text).strip()


def _is_relative_window_only_narrative(block: Any) -> bool:
    """Return whether a narrative block's only digits are relative time windows.

    A framing sentence such as ``Overall, the past 12 months have been marked
    by significant developments`` restates the section's configured reporting
    window (for example ``Key Developments (last 12 months)``); the digit is
    reader-orientation metadata, not an external factual assertion.  The
    exemption is deliberately narrow: after removing relative-window phrases
    of the form last/past/previous/next/coming N hours/days/weeks/months/years
    (including ``N-month``-style adjectives bound to window nouns), any
    remaining digit — a count, percentage, amount, year or date — keeps the
    inline [n] citation requirement fail-closed.
    """
    text = re.sub(r"[*_`]", "", str(block or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if not text or not re.search(r"\d", text):
        return False
    without = re.sub(
        r"(?i)\b(?:last|past|previous|next|coming)\s+\d+(?:\s*(?:-|–|to)\s*\d+)?\s+"
        r"(?:hours?|days?|weeks?|months?|years?)\b",
        " ",
        text,
    )
    without = re.sub(
        r"(?i)\b\d+(?:\s*(?:-|–|to)\s*\d+)?[-\s](?:hour|day|week|month|year)\s+"
        r"(?:outlook|window|period|horizon|view|reporting\s+window)\b",
        " ",
        without,
    )
    return not re.search(r"\d", without)


def _block_has_citable_numeric_claim(block: Any) -> bool:
    """Return whether a narrative block carries a concrete numeric claim.

    Mirrors the document-level depth rule ("figures = concrete numbers that are
    NOT bare years"): after removing relative reporting-window phrases, a block
    needs an inline [n] citation only when a remaining number token is not a
    bare year (percentages, counts, amounts, scores, dates-with-days).  A
    source-title year such as "the Freedom House 2025 report" or a bare
    temporal frame such as "since 2024" is reader-orientation context, not an
    external statistic; real figures remain fail-closed.
    """
    text = re.sub(r"[*_`]", "", str(block or ""))
    text = re.sub(r"\s+", " ", text).strip()
    if not text or not re.search(r"\d", text):
        return False
    without = re.sub(
        r"(?i)\b(?:last|past|previous|next|coming)\s+\d+(?:\s*(?:-|–|to)\s*\d+)?\s+"
        r"(?:hours?|days?|weeks?|months?|years?)\b",
        " ",
        text,
    )
    without = re.sub(
        r"(?i)\b\d+(?:\s*(?:-|–|to)\s*\d+)?[-\s](?:hour|day|week|month|year)\s+"
        r"(?:outlook|window|period|horizon|view|reporting\s+window)\b",
        " ",
        without,
    )
    tokens = re.findall(r"\d[\d,.]*%?", without)
    return any(not re.fullmatch(r"20[12][0-9]", token) for token in tokens)


def _is_reporting_window_table_leadin(block: Any) -> bool:
    """Return whether a digit only labels the time window of an adjacent table.

    A sentence such as ``The following table summarises the last 24–48 hours``
    is reader-navigation metadata, not an external factual assertion.  It is
    deliberately narrow: the block must introduce a table and its only
    number must be a relative reporting-window duration.  Actual facts,
    counts, dates, percentages, or any other numeric claim continue to need
    an inline resolving citation.
    """
    text = re.sub(r"[*_`]", "", str(block or ""))
    text = re.sub(r"\s+", " ", text).strip()
    # A model may precede the table cue with a reader-orientation clause
    # (for example, explaining that the table makes a complex pattern easier
    # to scan).  That remains navigation metadata when the only number is the
    # relative reporting window; do not turn it into a factual assertion just
    # because it does not begin with the literal words "The following table".
    if not re.match(
        r"(?i)^(?:(?:to|for)\s+[^.]{1,240}?[,;:]\s*)?"
        r"(?:the\s+)?(?:following|below|next)\s+table\b",
        text,
    ):
        return False
    if not re.search(
        r"(?i)\b(?:summari[sz]es|provides|sets out|covers|shows|outlines|lists|details)\b",
        text,
    ):
        return False
    window = re.search(
        r"(?i)\b(?:last|past|previous)\s+(\d+)(?:\s*(?:-|–|to)\s*\d+)?\s+"
        r"(?:hours?|days?|weeks?|months?)\b",
        text,
    )
    if not window:
        return False
    # The relative window must be the only numeric token in the lead-in.
    without_window = text[:window.start()] + text[window.end():]
    return not bool(re.search(r"\d", without_window))


def _repair_single_table_deficit(content: str, quality_controls: Dict[str, Any],
                                 inline_images: List[Dict[str, Any]]) -> str:
    """Add one measured output-control table only for an exact one-table deficit."""
    minimum = int(quality_controls.get("minimum_tables") or 0)
    current = len(re.findall(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|){2,}\s*$", content, re.MULTILINE))
    if minimum <= 0 or current + 1 != minimum:
        return content
    external_links = {
        link.rstrip(".,;:") for link in re.findall(r"https?://[^\s)\]]+", content)
        if not re.search(r"(?i)://(?:localhost|127\.0\.0\.1|[^/]*\.cloud-dog\.net)(?:[/:]|$)", link)
    }
    reporting_period = bool(re.search(r"(?i)\breporting period\s*:", content))
    table = (
        "## Evidence Coverage and Output Controls\n\n"
        "| Measured output property | Current output | Verification basis |\n"
        "|---|---:|---|\n"
        f"| Direct external references | {len(external_links)} | Canonical linked source register |\n"
        f"| Rendered inline visuals | {len(inline_images)} | Unique inline-image payloads |\n"
        f"| Reporting period declared | {'Yes' if reporting_period else 'No'} | Current-run front matter |"
    )
    return content.rstrip() + "\n\n" + table + "\n"


def _dedupe_visual_payloads(inline_images: List[Dict[str, Any]], figures: List[Dict[str, Any]]) -> tuple:
    """Deduplicate identical image bytes and their figure placements before rendering."""
    import hashlib
    unique_images: List[Dict[str, Any]] = []
    canonical_id: Dict[str, str] = {}
    seen_payloads: Dict[str, str] = {}
    seen_content_ids: set = set()
    for image in inline_images:
        cid = str(image.get("content_id") or "")
        payload = str(image.get("data") or "")
        if cid and cid in seen_content_ids:
            continue
        if cid:
            seen_content_ids.add(cid)
        digest = hashlib.sha256(payload.encode()).hexdigest() if payload else "cid:" + cid
        if digest in seen_payloads:
            canonical_id[cid] = seen_payloads[digest]
            continue
        seen_payloads[digest] = cid
        canonical_id[cid] = cid
        unique_images.append(image)
    unique_figures: List[Dict[str, Any]] = []
    seen_figure_ids: set = set()
    for figure in figures:
        updated = dict(figure)
        cid = canonical_id.get(str(updated.get("content_id") or ""), str(updated.get("content_id") or ""))
        updated["content_id"] = cid
        if not cid or cid in seen_figure_ids:
            continue
        seen_figure_ids.add(cid)
        unique_figures.append(updated)
    return unique_images, unique_figures


def _validate_direct_recipient_uniqueness(
    destinations: Any, quality_controls: Dict[str, Any]
) -> None:
    """Fail before side effects when one configured mailbox would receive duplicates.

    Exact duplicate delivery is allowed only for explicitly named variants.  Both
    rows must opt in and carry distinct variant IDs so a stray group/direct or
    case/whitespace duplicate cannot silently send twice.
    """
    if not quality_controls.get("direct_recipient_dedupe"):
        return
    if not isinstance(destinations, list):
        return

    seen: Dict[tuple[str, str], Dict[str, Any]] = {}
    for index, destination in enumerate(destinations):
        if not isinstance(destination, dict):
            continue
        address = str(destination.get("address") or "").strip().casefold()
        channel = str(destination.get("channel") or "").strip().casefold()
        if not address:
            continue
        key = (channel, address)
        preferences = (
            destination.get("preferences")
            if isinstance(destination.get("preferences"), dict)
            else {}
        )
        variant_id = str(
            preferences.get("recipient_variant_id")
            or preferences.get("delivery_variant")
            or ""
        ).strip()
        variant = {
            "index": index,
            "explicit": preferences.get("allow_duplicate_mailbox") is True
            and bool(variant_id),
            "variant_id": variant_id,
        }
        previous = seen.get(key)
        if previous is not None:
            explicit_distinct_variants = (
                previous["explicit"]
                and variant["explicit"]
                and previous["variant_id"] != variant["variant_id"]
            )
            if not explicit_distinct_variants:
                raise RuntimeError(
                    "DUPLICATE_RECIPIENT_MAILBOX: destination rows "
                    f"{previous['index']} and {index} normalize to "
                    f"{channel}:{address} without distinct explicit variants"
                )
        seen[key] = variant


def _freshen_as_of(text: str, current_year: Any = None) -> str:
    """Refresh the document's OWN ``As of <stale-date>`` framing to the current run date.

    Reasoning models often anchor a brief with "As of 2023, ..." even when the grounding
    sources are current. This rewrites only the document's temporal framing phrase
    (``As of [early/mid/late|Month] <year-before-now>``) to ``As of <Month Year>``. Factual
    year references like "the 2022 Strategic Concept" are NOT matched (no immediate "As of").
    """
    import datetime
    today = datetime.date.today()
    cy = int(current_year) if str(current_year or "").isdigit() else today.year
    date_str = "%d %s %d" % (today.day, today.strftime("%B"), today.year)  # "26 June 2026"
    stamp = "As of " + date_str
    s = str(text or "")

    # 1) Reformat model-invented concatenated dates "YYYYMMDD" -> "YYYY-MM-DD" (e.g. "20230405").
    s = re.sub(r"\b(20\d{2})(0[1-9]|1[0-2])(0[1-9]|[12]\d|3[01])\b", r"\1-\2-\3", s)

    # 2) Refresh the document's own stale "As of <date>" framing in ANY phrasing — including a day
    #    number ("As of 15 October 2023"), month-year, "early/mid/late <year>", markdown emphasis.
    #    The negative lookahead preserves genuine event references ("As of the 2022 Madrid Summit").
    def repl(m: "re.Match") -> str:
        """Replace stale As-of years while preserving current-year matches."""
        return stamp if int(m.group(1)) < cy else m.group(0)
    s = re.sub(
        r"\bAs of\s+(?!the\s+\d)(?:[\w*\-,]+\s+){0,5}?(20\d{2})\b",
        repl,
        s,
        flags=re.IGNORECASE,
    )

    # 3) Put the run date in the TITLE (H1) if it carries no date of its own.
    def _title_date(m: "re.Match") -> str:
        """Append the run date to an H1 only when it has no year."""
        line = m.group(1).rstrip("\n")
        return m.group(1) if re.search(r"20\d{2}", line) else line + " — " + date_str + "\n"
    s = re.sub(r"^(# .*\n)", _title_date, s, count=1)

    # 4) Guarantee a CURRENT opening with a render-safe (plain, no markdown emphasis) dateline.
    head = re.match(r"(# .*\n)", s)
    opening = s[(head.end() if head else 0):][:300]
    if str(today.year) not in opening:
        if head:
            s = s[:head.end()] + "\n" + stamp + ".\n" + s[head.end():]
        else:
            s = stamp + ".\n\n" + s
    return s


def _unwrap_sse(value: Any) -> Any:
    """Normalise an MCP tool result: if it is an SSE stream string ("data: {...}"),
    parse the JSON-RPC frame and surface the tool's structured/text content."""
    if not isinstance(value, str):
        return value
    s = value.strip()
    if s.startswith("data:"):
        frame = None
        for line in s.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                try:
                    frame = json.loads(line[5:].strip())
                except Exception:
                    frame = None
        if isinstance(frame, dict):
            result = frame.get("result", frame)
            if isinstance(result, dict):
                sc = result.get("structuredContent")
                if sc is not None:
                    return sc
                for blk in result.get("content", []) or []:
                    if isinstance(blk, dict) and "text" in blk:
                        try:
                            return json.loads(blk["text"])
                        except Exception:
                            return blk["text"]
            return result
    return value


def _search_results(raw: Any) -> List[dict]:
    """Extract the ``results`` list from a search tool result, whatever the wrapping.

    The injected service dispatcher may return any of: an SSE stream string, the MCP
    content envelope ``{"content":[{"text":"<json>"}]}``, a ``structuredContent`` dict, or
    an already-parsed ``{"results":[...]}``. Missing this unwrap silently drops grounding
    and the document falls back to stale training data with hallucinated links.
    """
    val = _unwrap_sse(raw)
    for _ in range(3):
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except Exception:
                return []
            continue
        if not isinstance(val, dict):
            return []
        if isinstance(val.get("results"), list):
            return [x for x in val["results"] if isinstance(x, dict)]
        if isinstance(val.get("structuredContent"), dict):
            val = val["structuredContent"]
            continue
        blocks = val.get("content")
        if isinstance(blocks, list):
            found = None
            for blk in blocks:
                if isinstance(blk, dict) and "text" in blk:
                    try:
                        found = json.loads(blk["text"])
                        break
                    except Exception:
                        continue
            if found is not None:
                val = found
                continue
        return []
    return val.get("results", []) if isinstance(val, dict) else []


def _mcp_payload(raw: Any) -> Any:
    """Unwrap a tool result (SSE / content[0].text JSON / structuredContent / result) to its
    inner value, then descend into an ``ok/result`` envelope (imap-mcp / index-retriever shape)."""
    val = _unwrap_sse(raw)
    for _ in range(4):
        if isinstance(val, str):
            try:
                val = json.loads(val)
            except Exception:
                return None
            continue
        if not isinstance(val, dict):
            return val
        if isinstance(val.get("structuredContent"), (dict, list)):
            val = val["structuredContent"]
            continue
        if isinstance(val.get("content"), list):
            nxt = None
            for blk in val["content"]:
                if isinstance(blk, dict) and "text" in blk:
                    try:
                        nxt = json.loads(blk["text"])
                        break
                    except Exception:
                        continue
            if nxt is not None:
                val = nxt
                continue
        return val
    return val


def _imap_headlines(raw: Any) -> List[Dict[str, Any]]:
    """Extract IMAP headline dictionaries from an MCP response envelope."""
    p = _mcp_payload(raw)
    if isinstance(p, dict):
        r = p.get("result") if isinstance(p.get("result"), dict) else p
        hl = (r or {}).get("headlines")
        if isinstance(hl, list):
            return [h for h in hl if isinstance(h, dict)]
    return []


def _raise_mcp_failure(raw: Any, operation: str) -> None:
    """Raise when a governed MCP response explicitly reports an operation failure.

    An empty successful result is valid, but an ``ok: false`` envelope (or errors with no
    result) must never be flattened into the same empty-list shape.  Keep the surfaced detail
    short and restricted to the service-provided error code/message so credentials or response
    bodies cannot leak into logs or job output.
    """
    payload = _mcp_payload(raw)
    for _ in range(3):
        if not isinstance(payload, dict):
            return
        errors = payload.get("errors")
        failed = payload.get("ok") is False or (
            payload.get("result") is None and isinstance(errors, list) and bool(errors)
        )
        if failed:
            details: List[str] = []
            for item in errors[:3] if isinstance(errors, list) else []:
                if not isinstance(item, dict):
                    continue
                code = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(item.get("code") or "error"))[:80]
                message = re.sub(r"\s+", " ", str(item.get("message") or "")).strip()[:200]
                details.append(f"{code}: {message}" if message else code)
            suffix = "; ".join(details) or "service returned ok=false"
            raise RuntimeError(f"{operation} failed: {suffix}")
        nested = payload.get("result")
        if not isinstance(nested, dict):
            return
        payload = nested


def _imap_body(raw: Any) -> str:
    """Extract a readable message body from an IMAP MCP response envelope."""
    p = _mcp_payload(raw)
    if isinstance(p, dict):
        r = p.get("result") if isinstance(p.get("result"), dict) else p
        for k in ("markdown", "content", "text", "body"):
            v = (r or {}).get(k)
            if isinstance(v, str) and v.strip():
                return v
    return ""


def _vdb_results(raw: Any) -> List[Dict[str, Any]]:
    """Extract vector-search match dictionaries from common response shapes."""
    p = _mcp_payload(raw)
    if isinstance(p, dict):
        for k in ("results", "matches", "hits"):
            v = p.get(k)
            if isinstance(v, list):
                return [m for m in v if isinstance(m, dict)]
        if isinstance(p.get("result"), dict):
            return _vdb_results(p["result"])
    if isinstance(p, list):
        return [m for m in p if isinstance(m, dict)]
    return []


def _first_url(text: str) -> str:
    """Return the first public-looking URL embedded in text."""
    m = re.search(r"View this post on the web at\s*(https?://\S+)", text)
    if m:
        return m.group(1).rstrip(").,")
    m = re.search(r"https?://[^\s)\]]+", text)
    return m.group(0).rstrip(").,") if m else ""


def _newsletter_label(sender: str) -> str:
    """A short citable label from a newsletter's From header, e.g.
    '"Phillips P. OBrien from Phillips's Newsletter" <x@substack.com>' -> 'Phillips P. OBrien'.
    Trims the publication suffix (' | Voices from the Front') and never returns a bare email
    address (an unlabelled From) — the caller then derives the name from the source URL."""
    s = str(sender or "").strip()
    name = s.split("<")[0].strip().strip('"').strip()
    name = re.split(r"\s+from\s+", name)[0].strip()
    name = re.split(r"\s*[|•·]\s*", name)[0].strip()  # drop ' | Voices from the Front' style suffixes
    if not name or "@" in name:  # email-only From -> let the URL/source supply the label
        return ""
    return name[:60]


def _newsletter_published_at(value: Any) -> str:
    """Normalise an IMAP publication/received date to an explicit UTC timestamp.

    Mail providers return either RFC 2822 dates or ISO-8601 strings.  An empty
    result is deliberate: callers must not replace an unknown publication time
    with collection time because that would make an old newsletter appear new.
    """
    import datetime as _dt
    import email.utils as _email_utils

    raw = str(value or "").strip()
    if not raw:
        return ""
    parsed = None
    try:
        parsed = _email_utils.parsedate_to_datetime(raw)
    except (TypeError, ValueError, OverflowError):
        pass
    if parsed is None:
        try:
            parsed = _dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed.astimezone(_dt.timezone.utc).isoformat().replace("+00:00", "Z")


def _newsletter_language(headline: Dict[str, Any], configured_default: Any = "") -> str:
    """Return the source-declared or explicitly configured ISO language code.

    We do not infer language from script alone: Cyrillic text, for example, is
    insufficient to distinguish Ukrainian from Russian.  ``und`` records that
    honest uncertainty and remains visible to downstream fail-closed gates.
    """
    raw = (
        headline.get("language")
        or headline.get("content_language")
        or headline.get("content-language")
        or configured_default
        or "und"
    )
    language = str(raw).strip().lower().replace("_", "-")
    return language if re.fullmatch(r"[a-z]{2,3}(?:-[a-z0-9]{2,8})*", language) else "und"


def _bracket_label(text: str) -> Optional[str]:
    """Return a leading bracketed label from a grounded snippet, if present."""
    m = re.match(r"\s*\[([^\]—\-]+?)(?:\s*[—-]\s*[^\]]*)?\]", text)
    return m.group(1).strip() if m else None


# Hosts that must never appear as a citable link in a published report — a link to one
# of these is dead for the reader (the localhost/internal-proxy links the operator flagged).
_PRIVATE_HOST_RE = re.compile(
    r"^(localhost|127\.|0\.0\.0\.0|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2[0-9]|3[01])\.|\[?::1\]?)",
    re.IGNORECASE)


def _markdown_link_urls(text: str) -> List[str]:
    """Extract Markdown destinations while preserving balanced URL parentheses.

    A simple ``[^)]`` pattern truncates legitimate URLs such as the governed
    NATO AJP path ``..._(1)_...``. This parser validates links only; it never
    selects, rewrites, or otherwise authors a citation.
    """
    urls: List[str] = []
    for match in re.finditer(r"\]\((https?://)", text):
        start = match.start(1)
        depth = 0
        for pos in range(start, len(text)):
            char = text[pos]
            if char.isspace():
                break
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    urls.append(text[start:pos])
                    break
                depth -= 1
    return urls


def _bare_url_urls(text: str) -> List[str]:
    """Extract bare http(s) URLs without truncating balanced parentheses.

    Source registers are allowed to render direct URLs as plain text as well as
    Markdown destinations.  A character-class extractor such as ``[^)]``
    falsely turns a valid public PDF URL containing ``(2024)`` into a different,
    unreachable URL at the final quality gate.  This is a parser/validation
    boundary only; it never selects, rewrites, or authors a citation URL.
    """
    urls: List[str] = []
    for match in re.finditer(r"(?<![\(\w])(https?://)", text):
        start = match.start(1)
        depth = 0
        end = len(text)
        for pos in range(start, len(text)):
            char = text[pos]
            if char.isspace() or (char == "]" and depth == 0):
                end = pos
                break
            if char == "(":
                depth += 1
            elif char == ")":
                if depth == 0:
                    end = pos
                    break
                depth -= 1
        url = text[start:end].rstrip(".,;:")
        if url:
            urls.append(url)
    return urls


def _public_url(u: Any) -> str:
    """Return ``u`` only if it is a public, clickable http(s) URL; else "". Drops the
    localhost / private-host / relative links that otherwise leak into the Sources block."""
    s = str(u or "").strip().rstrip(").,;]")
    # Whitespace is not valid inside an HTTP URL.  Passing such a value through
    # lets the HTTP client quote it during preflight, while the model-facing
    # source-register grammar later stops at the first space and exposes a
    # different, dead URL.  Reject the source before authoring instead of
    # rewriting or truncating its citation target.
    if re.search(r"\s", s):
        return ""
    m = re.match(r"https?://([^/\s:]+)", s, re.IGNORECASE)
    if not m:
        return ""
    host = m.group(1)
    host_lower = host.lower()
    if (
        _PRIVATE_HOST_RE.match(host)
        or "." not in host
        or host_lower.endswith(".local")
        or host_lower in {"example.com", "example.org", "example.net"}
        or host_lower.endswith((".example.com", ".example.org", ".example.net"))
    ):
        return ""
    return s


def _platform_http_get(
    url: str,
    *,
    timeout_seconds: int,
    headers: Dict[str, str],
    max_bytes: Optional[int] = None,
) -> tuple[int, str, bytes, Dict[str, str]]:
    """Retrieve a public source through the verified platform HTTP client.

    Strategy methods are synchronous at their policy boundary but can be called
    from an active event loop. The short-lived worker owns the client event loop
    so callers neither construct raw HTTP clients nor nest ``asyncio.run``.
    """
    result: list[tuple[int, str, bytes, Dict[str, str]]] = []
    errors: list[BaseException] = []

    async def _fetch() -> tuple[int, str, bytes, Dict[str, str]]:
        timeout = float(timeout_seconds)
        client_timeout = ClientTimeout(
            connect=min(5.0, timeout),
            read=timeout,
            total=timeout,
        )
        async with create_http_client(timeout=client_timeout) as client:
            async with client.stream(
                "GET",
                url,
                headers=headers,
                follow_redirects=True,
            ) as response:
                payload = b""
                if max_bytes is not None and max_bytes > 0:
                    chunks: list[bytes] = []
                    received = 0
                    async for chunk in response.aiter_bytes():
                        chunks.append(chunk)
                        received += len(chunk)
                        if received > max_bytes:
                            break
                    payload = b"".join(chunks)
                return (
                    int(response.status_code),
                    str(response.url),
                    payload,
                    {str(key).lower(): str(value) for key, value in response.headers.items()},
                )

    def _runner() -> None:
        try:
            result.append(asyncio.run(_fetch()))
        except BaseException as exc:  # propagate through the synchronous boundary
            errors.append(exc)

    worker = Thread(target=_runner, name="expert-agent-platform-http", daemon=True)
    worker.start()
    worker.join(float(timeout_seconds) + 5.0)
    if worker.is_alive():
        raise TimeoutError("Platform HTTP retrieval exceeded its timeout")
    if errors:
        raise errors[0]
    if not result:
        raise RuntimeError("Platform HTTP retrieval returned no result")
    return result[0]


def _external_url_retrievable(
    url: str,
    timeout: int = 12,
    *,
    require_public_access: bool = False,
) -> bool:
    """Check whether a citation URL is reachable under its product policy.

    Most existing products treat a real restricted response (401/403/405/406/
    429) as evidence that a source exists.  TB Country Report final-output
    validation opts into ``require_public_access``: every rendered citation
    must then return 2xx/3xx so a recipient can open it without credentials.
    404/410 always fail; transport and 5xx errors retry then fail closed.  This
    validates output only and never selects or authors a source.

    Reserved ``.test`` hosts remain deterministic unit-test fixtures.
    """
    host = (urlsplit(url).hostname or "").lower()
    if host.endswith(".test"):
        return True
    if not _public_url(url):
        return False

    restricted_codes = frozenset({401, 403, 405, 406, 429})

    def _probe() -> Optional[bool]:
        """True=allowed by policy, False=dead/inaccessible, None=transient."""
        code, _resolved_url, _payload, _response_headers = _platform_http_get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; Cloud-Dog-Quality-Gate/1.0)",
                "Accept": "text/html,application/json,*/*",
                "Range": "bytes=0-0",
            },
            timeout_seconds=timeout,
            max_bytes=0,
        )
        if 200 <= code < 400:
            return True
        if code in restricted_codes:
            return not require_public_access
        if 400 <= code < 500:
            return False
        return None  # 5xx / other -> transient, retry

    import time as _time
    for _attempt in range(3):
        try:
            verdict = _probe()
        except Exception:
            verdict = None  # DNS/refused/timeout -> transient
        if verdict is not None:
            return verdict
        if _attempt < 2:
            _time.sleep(1 + _attempt)
    return False  # exhausted retries on a transient failure -> treat as unreachable


def _clean_snippet(text: str) -> str:
    """A grounding snippet the model can quote safely: strip inline URLs (incl. the
    ``[ https://substack.com/redirect/... ]`` tracking wrappers) so no stray/broken link
    gets copied into the prose; the canonical link lives only in the Sources block."""
    t = re.sub(r"\[\s*https?://\S+\s*\]", " ", str(text or ""))
    t = re.sub(r"https?://\S+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


# Substack subdomain -> human analyst label, so a citation reads "Phillips O'Brien" even when
# the retrieved chunk is a mid-body chunk that no longer carries the "[label — subject]" prefix.
_KNOWN_NEWSLETTERS = {
    "phillipspobrien": "Phillips P. O'Brien",
    "ukrainesarmsmonitor": "Ukraine's Arms Monitor",
    "mickryan": "Mick Ryan",
    "professorbonk": "Prof. Bonk",
    "themalcontent": "Malcontent News",
    "malcontentnews": "Malcontent News",
    "missilematters": "Fabian Hoffmann — Missile Matters",
    "fabianhoffmann": "Fabian Hoffmann",
    "wesodonnell": "Wes O'Donnell",
    "shaunpinner": "Shaun Pinner",
}


def _label_from_url(u: Any) -> str:
    """Derive a citable analyst label from a newsletter URL (Substack subdomain), with a
    curated map for the known analysts and a title-cased fallback for the rest."""
    s = str(u or "")
    m = re.match(r"https?://([^./]+)\.substack\.com", s, re.IGNORECASE)
    if m:
        slug = m.group(1).lower()
        return _KNOWN_NEWSLETTERS.get(slug) or slug.replace("-", " ").replace("_", " ").title()
    m = re.match(r"https?://(?:www\.)?([^/]+)", s, re.IGNORECASE)
    return m.group(1) if m else "Analyst newsletter"


def _article_title_from_url(url: Any) -> str:
    """A human article title from a newsletter post URL slug, so a citation reads
    'Arms Trends in Ukraine 22-28 June' rather than just the analyst name. Substack/Ghost
    posts use '/p/<slug>'; otherwise take the last meaningful path segment."""
    s = str(url or "")
    m = re.search(r"/p/([^/?#]+)", s) or re.search(r"https?://[^/]+/([^/?#]+)/?$", s)
    if not m:
        return ""
    slug = re.sub(r"[?#].*$", "", m.group(1))
    slug = re.sub(r"-?\d{6,}$", "", slug)            # drop trailing id digits
    words = [w for w in re.split(r"[-_]+", slug) if w]
    if not words or len(words) < 2:
        return ""
    small = {"a", "an", "the", "of", "in", "on", "to", "and", "or", "for", "as", "at", "by", "is", "it"}
    out = [w.upper() if (len(w) <= 3 and w.isalpha() and w.isupper()) else
           (w if (w in small and i) else w.capitalize()) for i, w in enumerate(words)]
    return " ".join(out)[:80]


def _source_label(src: Any) -> str:
    """Derive an analyst label from a non-URL source string — the ``newsletter://<slug>``
    fallback we mint for newsletters without a clean public post URL (e.g. Patreon-delivered
    Malcontent News), or a stored ``Name — Newsletter`` source. Returns "" if none applies."""
    s = str(src or "").strip()
    if not s:
        return ""
    m = re.match(r"newsletter://(.+)$", s, re.IGNORECASE)
    if m:
        return _KNOWN_NEWSLETTERS.get(m.group(1).lower()) or m.group(1).replace("-", " ").replace("_", " ").title()
    if "://" not in s:  # a human-readable source like "Phillips O'Brien — Phillips's Newsletter"
        return re.split(r"\s+[—-]\s+", s)[0].strip()
    return ""


# A model designation like T-72, Su-34, S-400, TB2, Kh-101, F-16, MiG-31, 2S19 (hyphen or no
# separator — not a plain space, so it does not fire on prose like 'the 2nd').
_MODEL_CODE = re.compile(r"\b[0-9]?[A-Za-z]{1,5}[-‑]?\d{1,4}[A-Za-z]?\b")
# Named systems/brands that may be written without a code or in lower case — an allow-list backstop.
_NAMED_SYSTEMS = re.compile(
    r"\b(himars|atacms|nasams|iris[-\s]?t|patriot|storm\s?shadow|scalp|gmlrs|excalibur|caesar|"
    r"archer|krab|pzh|m777|m142|m270|bradley|abrams|leopard|challenger|stryker|marder|"
    r"bayraktar|switchblade|phoenix\s?ghost|shahed|geran|lancet|orlan|zala|"
    r"kalibr|iskander|kinzhal|oreshnik|zircon|tsirkon|neptune|harpoon|himars|"
    r"grad|smerch|uragan|tornado|tos|buk|pantsir|tor|kalibr|"
    r"sukhoi|tupolev|mig|kamov|patriot)\b", re.I)
_GENERIC_SUBJECT_WORD = {
    "tank", "tanks", "missile", "missiles", "weapon", "weapons", "munition", "munitions",
    "system", "systems", "drone", "drones", "aircraft", "jet", "jets", "fighter", "fighters",
    "artillery", "soldier", "soldiers", "troops", "vehicle", "vehicles", "gun", "guns", "rocket",
    "rockets", "shell", "shells", "bomb", "bombs", "ship", "ships", "boat", "boats", "equipment",
    "forces", "army", "navy", "infantry", "armour", "armor", "helicopter", "helicopters", "launcher",
    "launchers", "warhead", "warheads", "defence", "defense",
}


def _is_specific_subject(s: Any) -> bool:
    """HARD gate: True only when the image subject names a SPECIFIC system / person / brand,
    not a generic category. Rejects 'long-range missiles', 'air-defence systems', 'tank',
    'precision-guided munitions'; accepts 'HIMARS', 'T-72', 'Storm Shadow', 'Shahed-136',
    'Volodymyr Zelenskyy'. Deterministic — no model/LLM call."""
    s = str(s or "").strip()
    if not s:
        return False
    if _MODEL_CODE.search(s) or _NAMED_SYSTEMS.search(s):
        return True
    if re.search(r"\b[A-Z]{3,}\b", s):  # an acronym: HIMARS / ATACMS / NASAMS / JDAM
        return True
    # Two or more consecutive Capitalised words = a proper noun (a person / named place / brand),
    # e.g. 'Volodymyr Zelenskyy', 'Storm Shadow', 'Sea Baby'. A single sentence-initial capital
    # (e.g. 'Long-range missiles') does NOT qualify.
    if re.search(r"\b[A-Z][\w’'-]+\s+[A-Z][\w’'-]+\b", s):
        return True
    return False


def _valid_lonlat(p: Any) -> bool:
    """True when ``p`` has numeric lat/lon within valid earth ranges."""
    try:
        lat, lon = float(p["lat"]), float(p["lon"])
        return -90 <= lat <= 90 and -180 <= lon <= 180
    except (TypeError, ValueError, KeyError):
        return False


# Anchor coordinates (lon, lat, half-span°) for the places that recur in these briefs, so a
# detail map is pinned to the real location AND framed at a sensible zoom even from one name —
# cities get a tight span, regions/peninsulas/oblasts a wide one (so e.g. a 'Crimea' map shows
# the whole peninsula instead of one over-zoomed square).
_UA_GAZETTEER = {
    "kyiv": (30.52, 50.45, 0.6), "kharkiv": (36.23, 49.99, 0.6), "dnipro": (35.05, 48.46, 0.6),
    "zaporizhzhia": (35.14, 47.84, 0.7), "pokrovsk": (37.18, 48.28, 0.5), "bakhmut": (37.99, 48.59, 0.5),
    "donetsk": (37.80, 48.00, 0.7), "mariupol": (37.55, 47.10, 0.6), "kherson": (32.62, 46.64, 0.7),
    "odesa": (30.73, 46.48, 0.7), "odessa": (30.73, 46.48, 0.7), "sevastopol": (33.52, 44.60, 0.5),
    "lviv": (24.03, 49.84, 0.6), "kramatorsk": (37.55, 48.74, 0.5), "sloviansk": (37.60, 48.85, 0.5),
    "avdiivka": (37.75, 48.14, 0.4), "kupiansk": (37.62, 49.71, 0.5), "vuhledar": (37.25, 47.78, 0.4),
    "chasiv yar": (37.83, 48.59, 0.4), "kostiantynivka": (37.72, 48.53, 0.4), "robotyne": (35.84, 47.45, 0.4),
    "toretsk": (37.85, 48.40, 0.4), "kursk": (36.19, 51.73, 0.9), "belgorod": (36.59, 50.60, 0.7),
    "moscow": (37.62, 55.75, 0.8), "sumy": (34.80, 50.91, 0.7), "mykolaiv": (31.99, 46.97, 0.7),
    "melitopol": (35.37, 46.84, 0.5),
    # regions / large features — wide span so the whole area is visible
    "crimea": (34.30, 45.30, 1.9), "donbas": (37.90, 48.30, 1.8), "donetsk oblast": (37.50, 48.20, 1.9),
    "luhansk": (39.20, 48.60, 1.5), "luhansk oblast": (39.00, 48.80, 1.7), "zaporizhzhia oblast": (35.40, 47.30, 1.7),
    "kherson oblast": (33.20, 46.60, 1.6), "kharkiv oblast": (36.50, 49.80, 1.7), "black sea": (33.00, 44.50, 3.0),
    "sea of azov": (36.50, 46.20, 1.6), "kursk oblast": (35.50, 51.70, 1.8),
}


def _msg_items(raw: Any) -> List[Dict[str, Any]]:
    """Extract the message list from a notification-agent ``list_messages`` result."""
    p = _mcp_payload(raw)
    if isinstance(p, dict):
        for k in ("items", "messages", "results"):
            v = p.get(k)
            if isinstance(v, list):
                return [m for m in v if isinstance(m, dict)]
        if isinstance(p.get("result"), dict):
            return _msg_items(p["result"])
    if isinstance(p, list):
        return [m for m in p if isinstance(m, dict)]
    return []


def _first_json_object(text: str) -> Optional[dict]:
    """Return the first balanced top-level JSON object in ``text`` (or None)."""
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidates = []
    if fence:
        candidates.append(fence.group(1))
    start = text.find("{")
    while start != -1:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            c = text[i]
            if in_str:
                if esc:
                    esc = False
                elif c == "\\":
                    esc = True
                elif c == '"':
                    in_str = False
            else:
                if c == '"':
                    in_str = True
                elif c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        candidates.append(text[start : i + 1])
                        break
        break
    for cand in candidates:
        try:
            val = json.loads(cand)
            if isinstance(val, dict):
                return val
        except Exception:
            continue
    return None


# --------------------------------------------------------------------------- #
# ToolExecutor adapter (cloud_dog_agent.protocols.ToolExecutor)
# --------------------------------------------------------------------------- #
class AgentToolAdapter:
    """Routes a strategy's tool calls to MCP services and sub-experts.

    ``dispatch_service`` / ``dispatch_subexpert`` are injected so the routing is
    testable without a live database; in production they wrap the existing
    ``ServiceCompositionManager.invoke_tool`` and ``TransactionalExecutor.execute``.
    """

    def __init__(
        self,
        tools: List[Dict[str, Any]],
        dispatch_service: Callable[..., Any],
        dispatch_subexpert: Callable[..., Any],
        store: _ArtifactStore,
        spill_threshold: int = _SPILL_THRESHOLD,
        defaults: Optional[Dict[str, Any]] = None,
        llm: Optional[Any] = None,
        request_input: str = "",
        request_params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Build the tool registry and default delivery context for one agent run."""
        self._store = store
        self._dispatch_service = dispatch_service
        self._dispatch_subexpert = dispatch_subexpert
        self._spill = spill_threshold
        self._request_input = request_input or ""
        self._request_params = request_params or {}
        # LLM handle for the lightweight extraction passes (data points, section visuals).
        self._llm = llm
        # Captured by web_research and reliably reused so grounding always reaches the
        # generator and real source links always reach the published document, without
        # depending on the (small, drift-prone) model to thread reference tokens.
        self._research_grounding = ""
        self._research_sources_md = ""
        # Delivery defaults taken from the run's input spec (destinations / working_path /
        # title). publish_document FALLS BACK to these so the document is always delivered to
        # the configured recipients + path even when the (drift-prone) model omits them from
        # the tool call — the cause of demos writing to Drive but not emailing.
        _d = defaults or {}
        self._default_destinations = _d.get("destinations") or []
        self._default_working_path = _d.get("working_path")
        workspace = _d.get("file_mcp_workspace") if isinstance(_d.get("file_mcp_workspace"), dict) else {}
        guide_bundle = (
            _d.get("runtime_guide_bundle") if isinstance(_d.get("runtime_guide_bundle"), dict) else {}
        )
        # Product specs commonly scope FileMCP through the workspace or approved
        # guide bundle rather than a legacy top-level profile. Preserve explicit
        # top-level precedence before any generic service fallback.
        self._default_profile = _d.get("profile") or workspace.get("profile") or guide_bundle.get("profile")
        self._file_mcp_workspace = workspace
        self._file_mcp_mirror_evidence: List[Dict[str, Any]] = []
        self._default_title = _d.get("title")
        self._default_sections = _d.get("sections") or []
        self._default_target = _d.get("target")
        self._default_template_family = _d.get("template_family")
        self._default_quality_controls = (
            dict(_d.get("quality_controls")) if isinstance(_d.get("quality_controls"), dict) else {}
        )
        default_reporting_period = str(_d.get("reporting_period") or "").strip()
        if (
            default_reporting_period
            and self._default_quality_controls.get("reporting_period_required")
            and not self._default_quality_controls.get("required_reporting_period")
        ):
            self._default_quality_controls["required_reporting_period"] = default_reporting_period
        if str(self._default_quality_controls.get("required_reporting_period") or "").lstrip().lower().startswith("as at"):
            self._default_quality_controls.setdefault("as_at_reporting_period_required", True)
        default_introduction = str(_d.get("introduction") or "").strip()
        if (
            default_introduction
            and not self._default_quality_controls.get("required_classification")
            and re.search(r"(?i)\b(?:open source|unclassified|illustrative|demo)\b", default_introduction)
        ):
            self._default_quality_controls["required_classification"] = default_introduction
        if _d.get("quality_required_date") and not self._default_quality_controls.get("quality_required_date"):
            self._default_quality_controls["quality_required_date"] = _d.get("quality_required_date")
        self._default_brand = _d.get("brand") if isinstance(_d.get("brand"), dict) else {}
        self._default_runtime_guide_bundle = (
            _d.get("runtime_guide_bundle") if isinstance(_d.get("runtime_guide_bundle"), dict) else {}
        )
        self._agentic_document_required = bool(_d.get("agentic_document_required"))
        self.runtime_guide_bundle_evidence: Dict[str, Any] = {}
        self._default_grounding = _d.get("grounding")
        self._default_source_families = _d.get("source_families")
        self._default_vdb = _d.get("vdb") if isinstance(_d.get("vdb"), dict) else {}
        self._default_research_queries = [
            str(query).strip()
            for query in (_d.get("research_queries") or [])
            if str(query or "").strip()
        ]
        self._default_research_ingest = (
            _d.get("research_ingest")
            if isinstance(_d.get("research_ingest"), dict)
            else {}
        )
        self._research_ingest_records: List[Dict[str, Any]] = []
        self.invocations: List[Dict[str, Any]] = []
        self._registry: Dict[str, Dict[str, Any]] = {}
        for t in tools or []:
            name = str(t.get("name") or "")
            if not name:
                continue
            self._registry[name] = t
            self._registry.setdefault(name.split(".")[-1], t)  # short alias

    def _structured_grounding_text(self) -> str:
        """Serialise caller-provided data grounding for the document generator."""
        payload: Dict[str, Any] = {}
        if self._default_grounding:
            payload["grounding"] = self._default_grounding
        if self._default_source_families:
            payload["source_families"] = self._default_source_families
        if not payload:
            return ""
        source_register: List[str] = []
        for idx, source in enumerate((self._default_source_families or [])[:60], 1):
            if not isinstance(source, dict):
                continue
            url = str(source.get("url") or source.get("source_url") or "").strip()
            if not url.startswith(("http://", "https://")):
                continue
            number = source.get("number") or source.get("n") or idx
            title = str(
                source.get("title")
                or source.get("description")
                or source.get("id")
                or f"Source {number}"
            ).strip()
            source_register.append(f"[{number}] {title} — {url}")
        text = json.dumps(payload, ensure_ascii=False, default=str)
        if len(text) > 60000:
            text = text[:60000] + "\n...<structured grounding truncated for context budget>"
        register_text = ""
        if source_register:
            register_text = (
                "CALLER CITABLE SOURCE REGISTER (exact URL strings; cite using the shown "
                "bracketed numbers and preserve each URL byte-for-byte):\n"
                + "\n".join(source_register)
                + "\n\n"
            )
        return (
            register_text
            + "CALLER STRUCTURED GROUNDING (data only; do not invent beyond it):\n"
            + text
        )

    # Always-available presentation/quality/delivery utilities (generic; NOT
    # task-specific and NOT agent loops/memory — deterministic transforms + the
    # bound file/notify services).
    _BUILTINS = {"render_markdown", "quality_gate", "publish_document", "web_research", "compose_report"}

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        """Execute a built-in, service, or sub-expert tool and normalise its result."""
        short = str(tool_name).split(".")[-1]
        args = self._store.resolve(arguments or {})
        if self._agentic_document_required and short == "compose_report":
            return {"error": "compose_report is disabled for model-authored agentic document runs"}
        if short in self._BUILTINS:
            try:
                if short == "render_markdown":
                    return self._maybe_spill(self._render_markdown(args))
                if short == "compose_report":
                    return self._maybe_spill(await self._compose_report(args))
                if short == "publish_document":
                    return await self._publish_document(args)
                if short == "web_research":
                    research = await self._web_research(args)
                    # The model must see its agentic report's cited evidence. Spilling the
                    # source register hides it behind an opaque ref and causes a retry loop.
                    return research if self._agentic_document_required else self._maybe_spill(research)
                return self._quality_gate(args)  # small dict — never spilled
            except Exception as exc:
                logger.warning("builtin '%s' failed: %s", short, exc)
                return {"error": str(exc)[:300]}
        spec = self._registry.get(tool_name) or self._registry.get(short)
        if not spec:
            return {"error": f"unknown tool '{tool_name}'", "available": sorted(self._registry) + sorted(self._BUILTINS)}
        try:
            if spec.get("kind") == "subexpert":
                text = str(args.get("input") or args.get("task") or args.get("prompt") or json.dumps(args))
                # Reliably ground the generator: ensure the real current sources are in the
                # prompt even if the model failed to thread the SOURCES reference.
                if self._research_grounding and "CURRENT SOURCES" not in text and "art:" not in text:
                    text += ("\n\nCURRENT SOURCES (ground every claim in these; cite inline with each "
                             "source's real bracketed number, e.g. [2] — copy the actual digit, never "
                             "write the literal letter n):\n" + self._research_grounding)
                if args.get("timeout") is None and args.get("llm_timeout") is None:
                    timeout_override = (
                        self._request_params.get("subexpert_timeout")
                        or self._request_params.get("subexpert_timeout_seconds")
                        or self._request_params.get("llm_timeout")
                        or self._request_params.get("timeout")
                    )
                    if timeout_override is not None:
                        args = dict(args)
                        args["timeout"] = int(timeout_override)
                raw = await self._dispatch_subexpert(spec["child_id"], text, args)
            else:
                args = self._merge_default_arguments(spec, args)
                raw = await self._dispatch_service(spec["service"], spec["tool"], args)
                self._record_service_invocation(spec["service"], spec["tool"], args, raw)
        except Exception as exc:  # surface as an observation, do not crash the loop
            logger.warning("tool '%s' failed: %s", tool_name, exc)
            if spec.get("kind") == "service":
                self.invocations.append(
                    {
                        "service_name": spec.get("service"),
                        "tool_name": spec.get("tool"),
                        "status": "failed",
                        "error": str(exc)[:300],
                        **self._safe_argument_metadata(args),
                    }
                )
            return {"error": str(exc)[:300]}
        return self._maybe_spill(raw)

    @staticmethod
    def _brief_type_from_request(input_text: str, parameters: Optional[Dict[str, Any]] = None) -> Optional[str]:
        params = parameters or {}
        for key in ("type", "brief_type", "intel_type", "collection_type"):
            value = params.get(key)
            if isinstance(value, str) and value.strip().lower() in {"military", "financial", "political", "uk"}:
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

    def _merge_default_arguments(self, spec: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
        """Merge structured expert tool defaults into an agent-selected service call."""
        merged = dict(args or {})
        tool_name = str(spec.get("tool") or "").strip().lower()
        has_query_like_arg = any(merged.get(key) not in (None, "") for key in ("query", "q", "input", "prompt"))
        if (
            tool_name in {"search", "retrieve", "query", "fetch", "lookup"}
            and not has_query_like_arg
            and self._request_input
        ):
            merged["query"] = self._request_input
        if isinstance(spec.get("arguments"), dict):
            merged.update(spec["arguments"])
        collection_template = spec.get("collection_template") or spec.get("default_collection")
        collection = self._resolve_collection_template(
            collection_template,
            self._request_input,
            self._request_params,
        )
        if collection:
            merged["collection"] = collection
        if spec.get("default_profile"):
            merged["profile"] = spec["default_profile"]
        if spec.get("default_channel"):
            merged["channel"] = spec["default_channel"]
        return merged

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
    def _extract_retrieval_rows(cls, result: Any) -> List[Dict[str, Any]]:
        """Return vector-search rows from common index-retriever response envelopes."""
        payload = cls._normalise_result_payload(result)
        for _ in range(5):
            if isinstance(payload, dict):
                if isinstance(payload.get("content"), list):
                    next_payload = None
                    for block in payload["content"]:
                        if isinstance(block, dict) and "text" in block:
                            next_payload = cls._normalise_result_payload(block["text"])
                            break
                    if next_payload is not None:
                        payload = next_payload
                        continue
                for key in ("result", "structuredContent", "data"):
                    if key in payload:
                        payload = cls._normalise_result_payload(payload[key])
                        break
                else:
                    break
                continue
            break
        if isinstance(payload, dict):
            for key in ("chunks", "items", "results", "documents", "matches"):
                if isinstance(payload.get(key), list):
                    return [x for x in payload[key] if isinstance(x, dict)]
        if isinstance(payload, list):
            return [x for x in payload if isinstance(x, dict)]
        return []

    def _capture_retrieval_grounding(self, service_name: str, tool_name: str, result: Any) -> None:
        """Keep retrieved passages available to compose_report even if the LLM drops the observation."""
        if str(service_name) != "indexretriever0" or str(tool_name) not in {"search", "retrieve"}:
            return
        rows = self._extract_retrieval_rows(result)
        if not rows:
            return
        base = len(re.findall(r"(?m)^\[\d+\]", self._research_grounding or ""))
        grounding: List[str] = []
        sources: List[str] = []
        for row in rows[:12]:
            text = str(
                row.get("text")
                or row.get("content")
                or row.get("chunk_text")
                or row.get("document")
                or ""
            ).strip()
            if not text:
                continue
            source_id = str(
                row.get("source_id")
                or row.get("source")
                or row.get("source_uri")
                or row.get("document_id")
                or row.get("doc_id")
                or ""
            ).strip()
            chunk_id = str(row.get("chunk_id") or row.get("record_id") or "").strip()
            idx = base + len(grounding) + 1
            snippet = re.sub(r"\s+", " ", text)[:700]
            meta = " ".join(
                x
                for x in (
                    f"source_id={source_id}" if source_id else "",
                    f"chunk_id={chunk_id}" if chunk_id else "",
                )
                if x
            )
            # Internal retrieval identifiers may stay in the LLM grounding context, but they must
            # NEVER reach the reader-facing "## Sources" block (W28E-1885 D-004/D-005): the audit
            # found briefs whose Sources listed only source_id=/chunk_id=<hash>, which a reader can
            # neither use nor should see. Render a usable link/title instead, and omit the source
            # line entirely when no external attribution is available rather than leaking an id.
            grounding.append(f"[{idx}] {meta}: {snippet}" if meta else f"[{idx}] {snippet}")
            source_url = ""
            for _key in ("url", "source_url", "source_uri", "document_url", "link"):
                _val = str(row.get(_key) or "").strip()
                if _val.startswith("http"):
                    source_url = _val
                    break
            source_title = str(
                row.get("title")
                or row.get("document_title")
                or row.get("filename")
                or ""
            ).strip()
            if source_url and source_title:
                sources.append(f"- [{idx}] [{source_title}]({source_url})")
            elif source_url:
                sources.append(f"- [{idx}] {source_url}")
            elif source_title:
                sources.append(f"- [{idx}] {source_title}")
        if not grounding:
            return
        self._research_grounding = (
            (self._research_grounding.rstrip() + "\n") if self._research_grounding else ""
        ) + "\n".join(grounding)
        if sources:
            if not self._research_sources_md:
                self._research_sources_md = "## Sources\n\n"
            self._research_sources_md = self._research_sources_md.rstrip() + "\n" + "\n".join(sources)

    def _record_service_invocation(
        self,
        service_name: str,
        tool_name: str,
        args: Dict[str, Any],
        result: Any,
    ) -> None:
        record: Dict[str, Any] = {
            "service_name": service_name,
            "tool_name": tool_name,
            "status": "ok",
        }
        safe_args = self._safe_argument_metadata(args)
        if safe_args:
            record["arguments"] = safe_args
        for key in ("profile", "collection", "channel"):
            if args.get(key) not in (None, ""):
                record[key] = args[key]
        record.update(self._extract_invocation_summary(result))
        self.invocations.append(record)
        self._capture_retrieval_grounding(service_name, tool_name, result)

    @staticmethod
    def _file_text(raw: Any) -> str:
        """Extract text returned by FileMCP's read_file response shapes."""
        payload = _mcp_payload(raw)
        if isinstance(payload, str):
            return payload
        for _ in range(3):
            if not isinstance(payload, dict):
                return ""
            for key in ("value", "content", "text", "body", "markdown"):
                value = payload.get(key)
                if isinstance(value, str):
                    return value
            # Some compliant MCP composition layers return a plain text content
            # block without also materialising structuredContent.  This is a
            # transport shape, not document authoring: preserve the tool result
            # so the required workspace-artifact sync does not falsely fail.
            content = payload.get("content")
            if isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and isinstance(block.get("text"), str):
                        return block["text"]
            payload = payload.get("result")
        return ""

    async def load_runtime_guide_bundle(self) -> str:
        """Load the latest compatible approved FileMCP guide bundle for an agentic run.

        This is configuration/tool loading only.  The LLM remains the sole author of
        report prose, citations, recommendations, and quality assessment.
        """
        bundle = self._default_runtime_guide_bundle
        if not bundle:
            return ""
        profile = str(bundle.get("profile") or self._default_profile or "").strip()
        configured_manifest = str(bundle.get("manifest_path") or "").strip()
        compatible_demo = str(bundle.get("compatible_demo") or "").strip()
        required = bool(bundle.get("required"))
        if not profile or not configured_manifest:
            if required:
                raise RuntimeError("RUNTIME_GUIDE_BUNDLE_REQUIRED: profile and manifest_path are required")
            return ""

        guide_dir = configured_manifest.rsplit("/", 1)[0] if "/" in configured_manifest else ""
        file_service = self._svc_for("read_file", "filemcpserver0")

        async def read(path: str) -> str:
            # FileMCP is multi-profile.  The approved bundle declares the storage
            # profile that owns its workspace, so every lookup must carry it rather
            # than relying on a process-local default profile.
            args = {"path": path, "profile": profile}
            raw = await self._dispatch_service(file_service, "read_file", args)
            self._record_service_invocation(file_service, "read_file", args, raw)
            text = self._file_text(raw)
            if not text:
                raise RuntimeError(f"RUNTIME_GUIDE_BUNDLE_REQUIRED: FileMCP read_file returned no content for {path}")
            return text

        # Select by the newest dated approved manifest in the configured directory.
        # The configured manifest is retained as a fallback for FileMCP backends that do
        # not expose directory listing, but an explicitly required bundle fails closed if
        # neither route yields a compatible approved manifest.
        candidates = [configured_manifest]
        if guide_dir:
            try:
                raw_listing = await self._dispatch_service(
                    self._svc_for("list_dir", "filemcpserver0"),
                    "list_dir", {"path": guide_dir, "profile": profile},
                )
                self._record_service_invocation(
                    self._svc_for("list_dir", "filemcpserver0"),
                    "list_dir", {"path": guide_dir, "profile": profile}, raw_listing,
                )
                listing = _mcp_payload(raw_listing)
                entries = listing.get("entries", []) if isinstance(listing, dict) else []
                names = []
                for entry in entries if isinstance(entries, list) else []:
                    value = str(entry or "")
                    name = value.rsplit("/", 1)[-1]
                    if re.fullmatch(r"approved-guide-bundle-20\d{2}-\d{2}-\d{2}\.json", name):
                        names.append(f"{guide_dir}/{name}")
                candidates = sorted(set(names + candidates), reverse=True)
            except Exception as exc:
                logger.warning("runtime guide bundle: directory listing failed: %s", exc)

        selected_path = ""
        selected_manifest: Dict[str, Any] = {}
        selected_manifest_text = ""
        for candidate in candidates:
            try:
                manifest_text = await read(candidate)
                manifest = json.loads(manifest_text)
            except Exception as exc:
                logger.warning("runtime guide bundle: manifest %s unavailable: %s", candidate, exc)
                continue
            if not isinstance(manifest, dict) or str(manifest.get("status") or "").lower() != "approved":
                continue
            scope = manifest.get("scope") if isinstance(manifest.get("scope"), dict) else {}
            if compatible_demo and str(scope.get("demo") or "") != compatible_demo:
                continue
            selected_path, selected_manifest, selected_manifest_text = candidate, manifest, manifest_text
            break
        if not selected_path:
            raise RuntimeError("RUNTIME_GUIDE_BUNDLE_REQUIRED: no compatible approved guide manifest is available")

        guide_context: List[str] = []
        guide_hashes: List[Dict[str, str]] = []
        guides = selected_manifest.get("guides") if isinstance(selected_manifest.get("guides"), list) else []
        if not guides:
            raise RuntimeError("RUNTIME_GUIDE_BUNDLE_REQUIRED: approved manifest has no guides")
        # The selected manifest and its approved guides are configuration
        # artifacts.  Mirror their exact FileMCP values before the model sees
        # them, so the configured secondary workspace can be read back without
        # giving code any role in report authorship.
        await self._mirror_file_mcp_artifact(
            source_profile=profile,
            source_path=selected_path,
            content=selected_manifest_text,
        )
        for guide in guides:
            if not isinstance(guide, dict) or not str(guide.get("path") or "").strip():
                raise RuntimeError("RUNTIME_GUIDE_BUNDLE_REQUIRED: approved manifest contains an invalid guide entry")
            path = str(guide["path"])
            text = await read(path)
            value_digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
            # FileMCP's text read surface deliberately omits one terminal LF.  Bundle
            # manifests are generated from source-file bytes, which retain that LF;
            # accept only that narrowly defined transport normalization and record both
            # forms for replay.  Any substantive content drift still fails closed.
            source_text = text if text.endswith("\n") else text + "\n"
            source_digest = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
            expected = str(guide.get("sha256") or "").lower()
            if expected and expected not in {value_digest, source_digest}:
                raise RuntimeError(f"RUNTIME_GUIDE_BUNDLE_REQUIRED: checksum mismatch for {path}")
            await self._mirror_file_mcp_artifact(
                source_profile=profile,
                source_path=path,
                content=text,
            )
            guide_hashes.append({
                "path": path,
                "manifest_sha256": expected,
                "filemcp_value_sha256": value_digest,
                "source_sha256": source_digest,
                "terminal_newline_normalized": source_digest == expected and value_digest != expected,
            })
            guide_context.append(f"### Runtime guide: {path}\n\n{text.strip()}")

        self.runtime_guide_bundle_evidence = {
            "bundle_id": selected_manifest.get("bundle_id"),
            "manifest_path": selected_path,
            "guide_hashes": guide_hashes,
            "scope": selected_manifest.get("scope"),
        }
        workspace_profile = str(
            self._file_mcp_workspace.get("profile") or profile
        ).strip()
        if workspace_profile:
            await self._sync_file_mcp_workspace_artifacts(profile=workspace_profile)
        return "\n\n".join(guide_context)

    # ---- builtins -------------------------------------------------------- #
    def _generator_child_id(self) -> Optional[int]:
        """The bound document-generator sub-expert used to write each section in depth."""
        for spec in self._registry.values():
            if spec.get("kind") == "subexpert" and spec.get("child_id") is not None:
                return int(spec["child_id"])
        return None

    async def _fetch_template(self, family: str) -> Optional[Dict[str, Any]]:
        """Fetch the LATEST index-retriever structure template for ``family`` and return its
        ordered content sections. The template folder (index-retriever's template intelligence)
        is the source of truth for report structure — generated/enhanced from the example
        document corpus — so the document run is template-driven, not hard-coded."""
        try:
            raw = await self._dispatch_service(
                self._svc_for("structure_template_list", "indexretriever0"),
                "structure_template_list", {"limit": 100})
        except Exception as exc:
            logger.warning("fetch_template: list failed: %s", exc)
            return None
        # Unwrap whatever envelope the service returns: {templates:[...]} OR {ok,data:{templates}}
        # OR {structuredContent:{...}} OR an MCP content block — find the templates list.
        templates: List[Dict[str, Any]] = []
        val: Any = _unwrap_sse(raw)
        for _ in range(4):
            if isinstance(val, str):
                try:
                    val = json.loads(val)
                except Exception:
                    break
                continue
            if not isinstance(val, dict):
                break
            if isinstance(val.get("templates"), list):
                templates = val["templates"]
                break
            nxt = (val.get("data") if isinstance(val.get("data"), dict) else None) \
                or (val.get("structuredContent") if isinstance(val.get("structuredContent"), dict) else None) \
                or (val.get("result") if isinstance(val.get("result"), dict) else None)
            if nxt is None and isinstance(val.get("content"), list):
                for blk in val["content"]:
                    if isinstance(blk, dict) and "text" in blk:
                        try:
                            nxt = json.loads(blk["text"])
                            break
                        except Exception:
                            continue
            if nxt is None:
                break
            val = nxt
        if not templates:
            logger.warning("fetch_template: no templates list in response shape %s",
                           list(raw.keys()) if isinstance(raw, dict) else type(raw).__name__)
            return None
        fam = str(family).lower()
        matches = [t for t in templates
                   if fam in (str(t.get("name", "")) + " " + str(t.get("corpus_id", ""))).lower()]
        if not matches:
            return None

        def _ts(t: Dict[str, Any]) -> str:
            """Sort templates by embedded corpus timestamp and creation time."""
            m = re.search(r"20\d{6}[Tt]\d{6}", str(t.get("corpus_id", "")) + str(t.get("name", "")))
            return (m.group(0).upper() if m else "") + str(t.get("created_at", ""))
        matches.sort(key=_ts, reverse=True)
        tpl = matches[0]
        sections: List[Dict[str, Any]] = []
        for s in (tpl.get("sections") or []):
            title = str(s.get("title") or "").strip()
            stype = str(s.get("section_type") or "")
            if not title:
                continue
            # skip the document-title section (order 0 / a title-typed heading naming the report)
            if s.get("order") == 0 or stype.startswith(fam.replace(" ", "_")[:20]) or "country_report_" in stype:
                continue
            sections.append({"title": title, "brief": "", "section_type": stype})
        if not sections:
            return None
        return {"template_id": tpl.get("template_id"), "name": tpl.get("name"), "sections": sections}

    async def _compose_report(self, args: Dict[str, Any]) -> Any:
        """Build a LONG, deep report by generating EACH section in full, one at a time, via the
        document-generator sub-expert (each call writes ~target_words of substantive prose), then
        assembling them. This reproduces the depth of the template-driven reports — a single
        gen-all call is shallow; section-by-section with per-section word budgets is what gives a
        multi-page, evidence-rich document. Returns the assembled Markdown (spilled to a ref)."""
        sections = args.get("sections") or self._default_sections or []
        if not sections:
            return {"error": "compose_report needs a 'sections' list (title/brief per section)"}
        title = str(args.get("title") or self._default_title or "Research Report")
        target = str(args.get("target") or self._default_target or "")
        gen_id = self._generator_child_id()
        if gen_id is None and self._llm is None:
            return {"error": "compose_report needs either a document-generator sub-expert or an LLM"}
        default_words = int(args.get("target_words") or 850)
        grounding = self._research_grounding or "(no external sources retrieved — rely on well-established, verifiable facts)"
        quality_controls = (
            args.get("quality_controls") if isinstance(args.get("quality_controls"), dict)
            else self._default_quality_controls
        )
        structured_grounding = self._structured_grounding_text()
        model_authored_sources = _model_authored_sources_required(quality_controls)
        repair_allowed = _deterministic_content_repair_allowed(quality_controls)
        min_external_links = int(quality_controls.get("minimum_external_links") or 0)
        forbidden_discipline = _forbidden_content_generation_discipline(quality_controls)
        salary_control = (
            quality_controls.get("salary_consistency")
            if isinstance(quality_controls.get("salary_consistency"), dict)
            else {}
        )
        carry_salary_context = bool(salary_control.get("required"))

        def _prior_section_context(generated_parts: List[str]) -> str:
            """Compact cross-section context for values the model must copy forward."""

            if not generated_parts:
                return ""
            carry_terms = [
                r"\brank(?:ing)?\b",
                r"\brecommend(?:ation|ed)?\b",
                r"\bpick\b",
                r"\bverdict\b",
            ]
            if carry_salary_context:
                carry_terms.extend([r"\bsalary\b", r"\bcompensation\b", r"\bpay\b", r"US\$", r"\bUSD\b"])
            carry_re = re.compile("|".join(carry_terms), re.I)
            kept: List[str] = []
            for part in generated_parts:
                for line in str(part or "").splitlines():
                    stripped = line.strip()
                    if not stripped:
                        continue
                    is_heading = bool(re.match(r"^\s{0,3}#{2,6}\s+", line))
                    is_table = stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2
                    if is_heading or is_table or carry_re.search(stripped):
                        kept.append(line.rstrip()[:600])
            context = "\n".join(kept)
            if len(context) > 12000:
                context = context[-12000:]
            return context

        # Date & reporting-window anchor. A reasoning model with a training cut-off otherwise
        # confabulates plausible-but-wrong event dates ("On 5 September …") and presents stale or
        # invented events as "this week". Pin it to the run date and, for change/period briefs,
        # to an explicit window, and forbid dates not supported by the live sources.
        import datetime as _cdt
        _cd = args.get("current_date")
        try:
            _today = _cdt.date.fromisoformat(str(_cd)[:10]) if _cd else _cdt.date.today()
        except Exception:
            _today = _cdt.date.today()
        _recency = args.get("recency_days")
        _date_ctx = f"Today's date is {_today.strftime('%d %B %Y')}. "
        if _recency:
            try:
                _start = _today - _cdt.timedelta(days=int(_recency))
                _date_ctx += (f"This is a CHANGE brief covering ONLY the period {_start.strftime('%d %B %Y')} "
                              f"to {_today.strftime('%d %B %Y')}. Report ONLY developments dated within this "
                              f"window; do NOT present older events as if they happened this period. ")
            except Exception:
                pass
        _discipline = (
            _date_ctx +
            "SOURCING DISCIPLINE: you have NO reliable knowledge of events after your training cut-off, so "
            "every factual claim — and in particular EVERY date, named event, place, person and figure — MUST be "
            "supported by one of the CURRENT SOURCES below and cited inline using that source's real bracketed "
            "number — e.g. [2] or [5], copying the actual digit shown; NEVER write the literal placeholder [n]. "
            "Do NOT state any event or date "
            "that is not in the sources, and do NOT fall back on prior/training knowledge for current events. If "
            "the sources do not establish a relevant recent development, say so plainly (e.g. \"no major verified "
            "change was reported in this period\") rather than inventing one. Never write a specific calendar date "
            "unless that exact date appears in a source."
        )

        parts: List[str] = []
        for i, sec in enumerate(sections, 1):
            if isinstance(sec, dict):
                stitle = str(sec.get("title") or f"Section {i}")
                brief = str(sec.get("brief") or "")
                words = int(sec.get("target_words") or default_words)
            else:
                stitle, brief, words = str(sec), "", default_words
            prior_context = _prior_section_context(parts)
            prompt = (
                f"You are writing ONE section of a long, detailed professional report titled "
                f"\"{title}\"" + (f" about {target}" if target else "") + ".\n\n"
                f"Write the FULL \"{stitle}\" section: about {words} words of substantive, specific, "
                "well-evidenced UK-English prose — concrete facts, figures, named entities, dates and "
                "examples; use short paragraphs, ### sub-headings where helpful, and a Markdown table "
                "where it adds value. Write the complete section body — NOT a summary, NOT placeholders.\n\n"
                f"Section brief: {brief}\n\n"
                + (forbidden_discipline + "\n\n" if forbidden_discipline else "")
                + (
                    "ALREADY AUTHORED PRIOR-SECTIONS CONTEXT (for cross-section consistency only):\n"
                    + prior_context
                    + "\n\nWhen this section brief tells you to reuse, repeat or copy a value from an "
                    "earlier section or table, copy the exact visible token from the context above. "
                    "Do not choose a second value for the same entity.\n\n"
                    if prior_context
                    else ""
                )
                + _discipline +
                "\n\nCURRENT SOURCES (the ONLY admissible basis for facts and dates):\n"
                + grounding
                + ("\n\n" + structured_grounding if structured_grounding else "")
                + (
                    "\n\nSOURCES AUTHORSHIP: author the final top-level \"## Sources\" section yourself "
                    "from the cited source register and caller grounding. The final heading must be exactly "
                    "\"## Sources\". Include at least "
                    f"{min_external_links} numbered entries when that many registered URLs are available, "
                    "one per line like \"[1] [Title](https://example.test/path)\". Prefer the CALLER "
                    "CITABLE SOURCE REGISTER, copy individual URL strings exactly, and do not invent, "
                    "truncate, wrap or reformat URLs. Include only real URLs cited in the report."
                    if model_authored_sources
                    else ""
                ) +
                f"\n\nOutput ONLY this section, beginning with the heading \"## {stitle}\"."
            )
            # Local models occasionally time out or transiently error on a section
            # (cumulative load over a long multi-section run) — retry with backoff so
            # one hiccup does not leave a "_(section generation failed)_" hole. On the
            # final attempt, retry once with a smaller output budget; only if EVERY
            # attempt fails do we emit a graceful placeholder.
            import asyncio as _aio
            raw = ""
            _last_exc = None
            for _attempt in range(3):
                try:
                    _section_tokens = max(700, int(words * 2))
                    if _attempt >= 2:
                        _section_tokens = max(500, int(words * 1.5))
                    _sub_args = {"max_tokens": _section_tokens}
                    if gen_id is not None:
                        raw = await self._dispatch_subexpert(gen_id, prompt, _sub_args)
                    else:
                        response = await self._llm.generate(
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.2,
                            max_tokens=max(700, int(words * 2)),
                        )
                        raw = response.get("content", "") if isinstance(response, dict) else str(response)
                    if clean_final_content(raw if isinstance(raw, str) else str(raw)).strip():
                        _last_exc = None
                        break
                    _last_exc = "empty response"
                except Exception as exc:
                    _last_exc = exc
                    raw = ""
                if _attempt < 2:
                    await _aio.sleep(2 + _attempt * 3)
            if _last_exc is not None and not clean_final_content(raw if isinstance(raw, str) else str(raw)).strip():
                raw = (f"## {stitle}\n\n_This section could not be generated in this run "
                       f"(the local model did not return content after 3 attempts). It will "
                       f"be included on the next scheduled run._")
            body = clean_final_content(raw if isinstance(raw, str) else str(raw)).strip()
            # Force a single canonical "## <title>" heading per section: strip whatever heading
            # level/text the generator opened with (it often emits ### or repeats the title) and
            # demote any other top-level (#/##) headings it produced to ### so the section count
            # and outline are correct — each compose_report section is exactly one ## section.
            body = re.sub(r"^\s*#{1,6}\s+.*(?:\n|$)", "", body, count=1)
            body = re.sub(r"^(#{1,2})(\s+)", r"###\2", body, flags=re.M)  # demote stray #/## to ###
            parts.append(f"## {stitle}\n\n" + body.strip())

        # Cross-section BLUF <-> ranking consistency. Sections are generated in
        # isolation, so the model can give a bottom-line recommendation that the
        # report's own ranking table contradicts. Regenerate only the recommendation
        # section from the same grounding; residual mismatch is caught fail-closed by
        # _quality_gate before delivery.
        try:
            _sec_meta = {
                str(s.get("title") or "").strip().lower():
                    (str(s.get("brief") or ""), int(s.get("target_words") or default_words))
                for s in sections if isinstance(s, dict)
            }
            _tbl_sep = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|){2,}\s*$", re.M)
            # W28M-1636 R5: content-defect self-repair by RE-AUTHORING (never deterministic string
            # mutation). For each section the local agent emitted a forbidden defect in ([n/a],
            # ellipsis-truncated label, printed SHA-256, local-currency salary, "SQL not executed",
            # invented table), regenerate THAT section with the defect list called out so the model
            # authors it clean; bounded retries; residual defects are caught fail-closed by _quality_gate.
            if repair_allowed and gen_id is not None:
                for _pi, _p in enumerate(parts):
                    if not _report_content_defects(_p):
                        continue
                    _m = re.match(r"^##\s+([^\n]+)", _p.strip())
                    _rt = _m.group(1).strip() if _m else f"Section {_pi + 1}"
                    _orig_tbl = len(_tbl_sep.findall(_p))
                    # SURGICAL self-repair: hand the model its OWN draft and have it correct ONLY the
                    # quoted defects, keeping everything else verbatim (a full regen just re-introduces
                    # the same errors). Accept a candidate only when it REDUCES the defect count, so
                    # each bounded attempt makes progress toward a clean, model-authored section.
                    _best = _p
                    try:
                        _max_repair_attempts = int(
                            quality_controls.get("content_defect_repair_attempts") or 3
                        )
                    except Exception:
                        _max_repair_attempts = 3
                    _max_repair_attempts = max(1, min(6, _max_repair_attempts))
                    _seen_repair_candidates: set[str] = set()
                    _non_improving_repair_attempts = 0
                    for _ca in range(_max_repair_attempts):
                        _cur = _report_content_defects(_best)
                        if not _cur:
                            break
                        _fixp = (
                            f"Below is the \"{_rt}\" section of a professional report. Return the SAME "
                            "section text with ONLY these specific defect(s) corrected, changing nothing "
                            "else and keeping every table, heading, figure, citation number and sentence "
                            "otherwise identical:\n- " + "\n- ".join(_cur) + "\n\n"
                            "Rules while correcting: DELETE every '[n/a]' and empty '[]' (keep the figure, "
                            "drop the empty bracket); write COMPLETE source labels (no '...'/'…'); never "
                            "print a SHA-256 hex value (write 'recorded in the run contract'); convert "
                            "EVERY local-currency salary (CLP/COP/ARS/BRL/R$/pesos/reais) to an annual "
                            "US-DOLLAR figure - use the US-dollar salary already shown for that hub in the "
                            "ranking/salary table; the four live SQL indicators WERE executed this run "
                            "(never write 'not executed' or 'pending').\n\n"
                            f"SECTION TO CORRECT:\n{_best}\n\n"
                            f"Output ONLY the corrected section, beginning with the heading \"## {_rt}\"."
                        )
                        try:
                            _new = await self._dispatch_subexpert(gen_id, _fixp, {})
                        except Exception:
                            _new = ""
                        _nb = clean_final_content(_new if isinstance(_new, str) else str(_new)).strip()
                        if not _nb:
                            continue
                        _nb = re.sub(r"^\s*#{1,6}\s+.*(?:\n|$)", "", _nb, count=1)
                        _nb = re.sub(r"^(#{1,2})(\s+)", r"###\2", _nb, flags=re.M)
                        _cand = f"## {_rt}\n\n" + _nb.strip()
                        _cand_key = re.sub(r"\s+", " ", _cand).strip()
                        if _cand_key in _seen_repair_candidates:
                            logger.warning(
                                "compose_report: stopping repeated content-defect repair output "
                                "in section %r after %s attempt(s)",
                                _rt,
                                _ca + 1,
                            )
                            break
                        _seen_repair_candidates.add(_cand_key)
                        _cand_defects = _report_content_defects(_cand)
                        if len(_tbl_sep.findall(_cand)) >= _orig_tbl and \
                                len(_cand_defects) < len(_cur):
                            _best = _cand
                            _non_improving_repair_attempts = 0
                        else:
                            _non_improving_repair_attempts += 1
                            if _non_improving_repair_attempts >= 2:
                                logger.warning(
                                    "compose_report: stopping non-improving content-defect repair "
                                    "in section %r after %s attempt(s)",
                                    _rt,
                                    _ca + 1,
                                )
                                break
                    parts[_pi] = _best
                    _left = _report_content_defects(_best)
                    if _left:
                        logger.warning("compose_report: could NOT fully clear content defects in section "
                                       "%r (%s); _quality_gate will block delivery", _rt, _left)
                    else:
                        logger.info("compose_report: surgically cleared content defects in section %r", _rt)
            _consistent, _ranking, _ = _bluf_ranking_status("\n\n".join(parts))
            if repair_allowed and not _consistent and gen_id is not None and len(_ranking) >= 2:
                _r1b, _r2b = _bare_city(_ranking[0]), _bare_city(_ranking[1])
                _rank_list = "; ".join(f"{n + 1}. {_bare_city(h)}" for n, h in enumerate(_ranking))
                _top2 = [_deacc(_r1b).lower(), _deacc(_r2b).lower()]
                for _pi, _p in enumerate(parts):
                    # only regenerate a section whose OWN recommendation is inconsistent — never a
                    # section (e.g. the ranking's "Final Recommendation") that already matches.
                    _named_sec = _recommendation_named(_p, _ranking)
                    if len(_named_sec) < 2:
                        continue
                    if [_deacc(_named_sec[0]).lower(), _deacc(_named_sec[1]).lower()] == _top2:
                        continue
                    _m = re.match(r"^##\s+([^\n]+)", _p.strip())
                    _rt = _m.group(1).strip() if _m else "Executive Summary"
                    _rbrief, _rwords = _sec_meta.get(_rt.lower(), ("", default_words))
                    # the report sits at the minimum-tables floor (one table per section), so the
                    # regenerated section MUST keep at least as many tables as the original.
                    _orig_tables = len(_tbl_sep.findall(_p))
                    _fixprompt = (
                        f"You are re-writing ONE section of a long, detailed professional report titled "
                        f"\"{title}\"" + (f" about {target}" if target else "") + ".\n\n"
                        f"Write the FULL \"{_rt}\" section: about {_rwords} words of substantive, specific, "
                        "well-evidenced UK-English prose — concrete facts, figures, named entities and dates; "
                        "use short paragraphs, ### sub-headings where helpful, and KEEP the same Markdown "
                        "table(s) the section calls for (do NOT drop any table).\n\n"
                        f"The report's own team-placement ranking orders the candidate hubs as: {_rank_list}.\n"
                        f"HARD CONSISTENCY REQUIREMENT: the bottom-line recommendation MUST recommend "
                        f"anchoring the team in the TOP TWO ranked hubs — {_r1b} (rank 1) and {_r2b} "
                        f"(rank 2) — and in NO other hub. Justify BOTH {_r1b} and {_r2b} using their own "
                        f"figures from the sources. Do NOT name, recommend or build the recommendation "
                        f"around any lower-ranked hub.\n\n"
                        f"Section brief: {_rbrief}\n\n" + _discipline +
                        "\n\nCURRENT SOURCES (the ONLY admissible basis for facts and dates):\n" + grounding +
                        f"\n\nOutput ONLY this section, beginning with the heading \"## {_rt}\"."
                    )
                    for _ratt in range(4):
                        try:
                            _new = await self._dispatch_subexpert(gen_id, _fixprompt, {})
                        except Exception:
                            _new = ""
                        _nb = clean_final_content(_new if isinstance(_new, str) else str(_new)).strip()
                        if not _nb:
                            continue
                        _nb = re.sub(r"^\s*#{1,6}\s+.*(?:\n|$)", "", _nb, count=1)
                        _nb = re.sub(r"^(#{1,2})(\s+)", r"###\2", _nb, flags=re.M)
                        _cand = f"## {_rt}\n\n" + _nb.strip()
                        _named2 = _recommendation_named(_cand, _ranking)
                        _ok_bluf = (len(_named2) >= 2
                                    and [_deacc(_named2[0]).lower(), _deacc(_named2[1]).lower()] == _top2)
                        _ok_tbl = len(_tbl_sep.findall(_cand)) >= _orig_tables
                        if _ok_bluf and _ok_tbl:
                            parts[_pi] = _cand
                            logger.info("compose_report: reconciled BLUF section %r to ranking top-2 "
                                        "(%s, %s), kept %s table(s), after %s attempt(s)",
                                        _rt, _r1b, _r2b, _orig_tables, _ratt + 1)
                            break
                    else:
                        logger.warning("compose_report: could NOT reconcile BLUF section %r to ranking "
                                       "top-2 (%s, %s) while preserving %s table(s); _quality_gate will "
                                       "block delivery", _rt, _r1b, _r2b, _orig_tables)
        except Exception as _exc:  # never let the consistency pass break report assembly
            logger.warning("compose_report: BLUF/ranking reconciliation skipped: %s", _exc)

        doc = f"# {title}\n\n" + "\n\n".join(parts)
        if not model_authored_sources:
            # Consolidate references into exactly ONE Sources section at the very end: remove every
            # per-section and top-level bare Sources/References block but COLLECT their citation lines,
            # then emit a single "## Sources" built from the real research links (preferred) plus those
            # collected lines, de-duplicated. This resolves "multiple Sources sections … move to the end,
            # have one" WITHOUT dropping the links (deleting them outright left reports with 0 links).
            doc, _collected_src = _consolidate_sources(doc)
            _src_lines: List[str] = []
            if self._research_sources_md:
                for _l in self._research_sources_md.split("\n"):
                    if _l.strip() and not re.match(r"\s*#{1,3}\s", _l):
                        _src_lines.append(_l.strip())
            _src_lines.extend(_collected_src)
            _seen_src: set = set()
            _uniq_src: List[str] = []
            for _l in _src_lines:
                _k = re.sub(r"^\s*(?:[-*]|\d+[.)])\s*", "", _l).strip().lower()
                if _k and _k not in _seen_src:
                    _seen_src.add(_k)
                    _uniq_src.append(_l if re.match(r"\s*(?:[-*]|\d+[.)])\s+", _l) else "- " + _l)
            # Fallback: when web research yields no links (the SearXNG backend is intermittent) a
            # governance/transparency country brief should still cite the standard institutional
            # indices it is built around, rather than ship with an empty Sources section (which the
            # quality gate rejects). Emit the canonical index sources, country-parameterised where the
            # provider supports a per-country page.
            if not _uniq_src and re.search(r"country risk brief|transparent borders|country report", str(title), re.I):
                _cc = re.split(r"\s+[—\-:]\s+", str(title).strip(), 1)[0].strip()
                _q = _cc.replace(" ", "+")
                _uniq_src = [
                    f"- Transparency International — Corruption Perceptions Index (country profile): https://www.transparency.org/en/countries?query={_q}",
                    "- World Justice Project — Rule of Law Index: https://worldjusticeproject.org/rule-of-law-index/",
                    "- Reporters Without Borders (RSF) — World Press Freedom Index: https://rsf.org/en/index",
                    "- Freedom House — Freedom in the World: https://freedomhouse.org/countries/freedom-world/scores",
                    "- World Bank — Worldwide Governance Indicators: https://info.worldbank.org/governance/wgi/",
                    "- V-Dem Institute — Democracy Report & indicators: https://v-dem.net/",
                    "- U.S. Department of State — Country Reports on Human Rights Practices: https://www.state.gov/reports-bureau-of-democracy-human-rights-and-labor/country-reports-on-human-rights-practices/",
                    "- Economist Intelligence Unit — Democracy Index: https://www.eiu.com/n/campaigns/democracy-index-2024/",
                ]
                logger.info("document pipeline: web research returned no links; used canonical index-source fallback for %r", _cc)
            if _uniq_src:
                # The client-ready quality contract requires a single, explicitly numbered
                # source list. Research backends and section generators variously return
                # bullets, ``[n]`` markers, or already-numbered lines; normalise all of them
                # here so the rendered document and deterministic gate agree.
                _numbered_src: List[str] = []
                for _index, _line in enumerate(_uniq_src, start=1):
                    _source = re.sub(
                        r"^\s*(?:(?:[-*]|\[\d+\]|\d+[.)])\s*)+",
                        "",
                        _line,
                    ).strip()
                    if _source:
                        _numbered_src.append(f"{_index}. {_source}")
                doc = doc.rstrip() + "\n\n## Sources\n\n" + "\n".join(_numbered_src)
        if repair_allowed:
            doc = _freshen_as_of(doc, args.get("current_year"))
            # Safety net: if the generator copied the literal placeholder "[n]" (or "[n, n]") instead
            # of a real source number, strip it rather than ship a broken citation marker.
            doc = re.sub(r"[ \t]*\[[nN](?:\s*,\s*[nN])*\]", "", doc)
            doc = re.sub(r"[ \t]+([.,;:)])", r"\1", doc)
        return doc

    def _svc_for(self, tool_suffix: str, default_service: str) -> str:
        """Resolve the bound service name that exposes ``tool_suffix`` (e.g. write_file,
        send_notification), falling back to the platform default.

        More than one bound service can expose the same short tool name.  In
        particular, both Index Retriever and Search MCP expose ``search``.  The
        document pipeline's live web-research path names Search MCP as its
        default owner, so prefer an exact service-name match before considering
        another provider.  Selecting the first suffix match routed web queries
        to Index Retriever with an incompatible argument contract and produced
        HTTP 422 responses while Search MCP itself remained healthy.
        """
        for spec in self._registry.values():
            if (
                spec.get("kind") == "service"
                and str(spec.get("tool")) == tool_suffix
                and str(spec.get("service")) == default_service
            ):
                return default_service
        for name, spec in self._registry.items():
            if spec.get("kind") == "service" and str(spec.get("tool")) == tool_suffix:
                return str(spec.get("service"))
        return default_service

    def _file_mcp_mirrors_for(
        self, *, source_profile: str, source_path: str
    ) -> List[Dict[str, str | bool]]:
        """Return configured storage mirrors matching one FileMCP artifact.

        This is storage plumbing only: a mirror preserves the exact bytes the
        model authored or the product configuration supplied.  It never alters
        report prose, citations, visual rationale, or any other report content.
        """
        configured = self._file_mcp_workspace.get("mirrors")
        if not isinstance(configured, list):
            return []
        matches: List[Dict[str, str | bool]] = []
        for raw in configured:
            if not isinstance(raw, dict):
                continue
            mirror_source_profile = str(raw.get("source_profile") or source_profile).strip()
            source_prefix = str(raw.get("source_prefix") or "").strip().rstrip("/")
            target_profile = str(raw.get("target_profile") or raw.get("profile") or "").strip()
            target_prefix = str(raw.get("target_prefix") or "").strip().rstrip("/")
            required = bool(raw.get("required"))
            if mirror_source_profile != source_profile:
                continue
            if not source_prefix or not target_profile or not target_prefix:
                if required:
                    raise RuntimeError(
                        "FILEMCP_MIRROR_CONFIGURATION_INVALID: required mirror needs "
                        "source_prefix, target_profile and target_prefix"
                    )
                continue
            if source_path != source_prefix and not source_path.startswith(source_prefix + "/"):
                continue
            relative_path = source_path[len(source_prefix):].lstrip("/")
            if not relative_path:
                if required:
                    raise RuntimeError(
                        "FILEMCP_MIRROR_CONFIGURATION_INVALID: a mirror source path must name a file"
                    )
                continue
            matches.append(
                {
                    "target_profile": target_profile,
                    "target_path": f"{target_prefix}/{relative_path}",
                    "required": required,
                }
            )
        return matches

    @staticmethod
    def _file_mcp_result_error(raw: Any) -> str:
        """Return a compact FileMCP failure message, if the response carries one."""
        payload = _mcp_payload(raw)
        for _ in range(3):
            if not isinstance(payload, dict):
                return ""
            error = payload.get("error")
            if isinstance(error, dict):
                return str(error.get("message") or error.get("code") or "FileMCP error")
            if error:
                return str(error)
            structured = payload.get("structuredContent")
            if isinstance(structured, dict) and structured.get("error"):
                return str(structured["error"])
            if payload.get("isError"):
                content = payload.get("content")
                if isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("text"):
                            return str(item["text"])
            nested = payload.get("result")
            if not isinstance(nested, dict):
                return ""
            payload = nested
        return ""

    async def _mirror_file_mcp_artifact(
        self,
        *,
        source_profile: str,
        source_path: str,
        content: str,
    ) -> None:
        """Persist and byte-verify configured FileMCP storage mirrors.

        Required mirror failures stop the normal product path before delivery;
        optional mirrors are recorded and do not weaken primary persistence.
        """
        for mirror in self._file_mcp_mirrors_for(
            source_profile=source_profile, source_path=source_path
        ):
            target_profile = str(mirror["target_profile"])
            target_path = str(mirror["target_path"])
            required = bool(mirror["required"])
            write_service = self._svc_for("write_file", "filemcpserver0")
            write_args = {
                "profile": target_profile,
                "path": target_path,
                "content": content,
                "overwrite": True,
            }
            try:
                written = await self._dispatch_service(
                    write_service, "write_file", write_args
                )
                self._record_service_invocation(
                    write_service, "write_file", write_args, written
                )
                write_error = self._file_mcp_result_error(written)
                if write_error:
                    raise RuntimeError(write_error)
                read_service = self._svc_for("read_file", "filemcpserver0")
                read_args = {"profile": target_profile, "path": target_path}
                loaded = await self._dispatch_service(
                    read_service, "read_file", read_args
                )
                self._record_service_invocation(
                    read_service, "read_file", read_args, loaded
                )
                if self._file_text(loaded) != content:
                    raise RuntimeError("mirror readback differed from source content")
                self._file_mcp_mirror_evidence.append(
                    {
                        "source_profile": source_profile,
                        "source_path": source_path,
                        "target_profile": target_profile,
                        "target_path": target_path,
                        "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
                        "verified": True,
                    }
                )
            except Exception as exc:
                self._file_mcp_mirror_evidence.append(
                    {
                        "source_profile": source_profile,
                        "source_path": source_path,
                        "target_profile": target_profile,
                        "target_path": target_path,
                        "verified": False,
                        "error": str(exc)[:200],
                    }
                )
                if required:
                    raise RuntimeError(
                        "FILEMCP_REQUIRED_MIRROR_FAILED: "
                        f"{source_profile}:{source_path} -> {target_profile}:{target_path}"
                    ) from exc
                logger.warning(
                    "optional FileMCP mirror failed for %s:%s -> %s:%s: %s",
                    source_profile,
                    source_path,
                    target_profile,
                    target_path,
                    exc,
                )

    async def _sync_file_mcp_workspace_artifacts(self, *, profile: str) -> None:
        """Mirror configured static workspace artifacts before model generation."""
        paths = self._file_mcp_workspace.get("artifact_paths")
        if not isinstance(paths, list):
            return
        read_service = self._svc_for("read_file", "filemcpserver0")
        for raw_path in paths:
            path = str(raw_path or "").strip()
            if not path:
                continue
            read_args = {"profile": profile, "path": path}
            try:
                loaded = await self._dispatch_service(
                    read_service, "read_file", read_args
                )
                self._record_service_invocation(
                    read_service, "read_file", read_args, loaded
                )
                text = self._file_text(loaded)
                if not text:
                    raise RuntimeError("FileMCP returned no artifact content")
                await self._mirror_file_mcp_artifact(
                    source_profile=profile, source_path=path, content=text
                )
            except Exception as exc:
                raise RuntimeError(
                    f"FILEMCP_WORKSPACE_ARTIFACT_SYNC_FAILED: {profile}:{path}"
                ) from exc

    async def _web_research(self, args: Dict[str, Any]) -> str:
        """Search the web (bound search service) and return a CITABLE source pack: numbered
        grounding snippets (title, date, content) plus a ready-made '## Sources' Markdown
        block of real links. This is what gives the document current facts, figures and
        links instead of vague generalities."""
        import asyncio
        query = str(args.get("query") or "")
        max_results = int(args.get("max_results") or 6)
        max_queries = max(1, min(int(args.get("max_queries") or 5), 12))
        max_sources = max(1, min(int(args.get("max_sources") or max(max_results, 18)), 60))
        engines = [str(value).strip() for value in (args.get("engines") or []) if str(value).strip()]
        forbidden_policy = args.get("forbidden_content") if isinstance(args.get("forbidden_content"), dict) else None
        forbidden_rejected = 0
        # Run the model-selected main query plus any model-selected facet queries (e.g. one per
        # section topic) and MERGE the results, de-duplicated by URL. A configured agentic
        # document source contract may require more URLs than a small-model tool action asks
        # for, so extend the normal scheduled query set just enough to reach that contract.
        # This is retrieval configuration only: the model still authors the report, selects the
        # citations it uses, and produces the final source entries.
        required_sources = max(
            0,
            int(self._default_quality_controls.get("minimum_external_links") or 0),
        )
        # Run the main query plus any facet queries (e.g. one per section topic) and MERGE the
        # results, de-duplicated by URL — and retry empties, because the SearXNG backend is
        # intermittent and a single failed call would otherwise leave the brief with no web
        # sources (the cause of thin, under-sourced reports).
        queries = [query] + [str(q) for q in (args.get("extra_queries") or []) if str(q or "").strip()]
        queries = [candidate.strip() for candidate in queries if candidate and candidate.strip()]
        if self._agentic_document_required and required_sources:
            max_results = max(max_results, min(required_sources, 15))
            max_sources = max(max_sources, required_sources)
            for configured_query in self._default_research_queries:
                if configured_query not in queries:
                    queries.append(configured_query)
            # Search APIs often return fewer than their requested page size. Retain the
            # model's query and one schedule-owned facet so the configured source minimum
            # does not fail solely because an action omitted optional tool arguments.
            max_queries = max(max_queries, min(len(queries), 2))
        svc = self._svc_for("search", "searchmcp0")
        seen: set = set()
        merged: List[Dict[str, Any]] = []
        for q in queries[:max_queries]:
            res: List[Dict[str, Any]] = []
            for _attempt in range(3):
                try:
                    search_args: Dict[str, Any] = {"query": q, "max_results": max_results}
                    if engines:
                        search_args["engines"] = engines
                    raw = await self._dispatch_service(svc, "search", search_args)
                    self._record_service_invocation(svc, "search", search_args, raw)
                    _raise_mcp_failure(raw, "search")
                    res = _search_results(raw)
                except Exception as exc:
                    logger.warning("web_research: search attempt failed (%s): %s", q[:40], exc)
                    res = []
                if res:
                    break
                await asyncio.sleep(1.2)  # brief backoff — SearXNG often recovers on retry
            for r in res:
                if not isinstance(r, dict):
                    continue
                u = (str(r.get("url") or "")).strip()
                key = u or str(r.get("title") or "")
                if not key or key in seen:
                    continue
                if forbidden_policy:
                    blob = " ".join(str(r.get(k) or "") for k in ("title", "content", "snippet", "url"))
                    if _configured_forbidden_content_hits(blob, {"forbidden_content": forbidden_policy}):
                        forbidden_rejected += 1
                        continue
                seen.add(key)
                merged.append(r)
        # A governed ingest contract is stricter than a generic source register:
        # candidates below its authority threshold cannot be persisted or used as
        # traceable research evidence.  Filter them before deciding whether the
        # normal Index-Retriever corpus fallback is required.  Counting raw
        # search hits here previously let an acronym collision satisfy the
        # fallback predicate even though every candidate would be rejected by
        # ``_persist_research_ingest`` later in the run.
        ingest_policy = self._default_research_ingest
        if ingest_policy and bool(ingest_policy.get("download_permitted_sources_to_file_mcp")):
            quality_threshold = float(ingest_policy.get("quality_threshold") or 80)
            governed_candidates: List[Dict[str, Any]] = []
            for candidate in merged:
                candidate_url = _public_url(candidate.get("url"))
                if candidate_url and self._research_source_quality(candidate_url, candidate)["score"] >= quality_threshold:
                    governed_candidates.append(candidate)
            rejected_for_governed_ingest = len(merged) - len(governed_candidates)
            if rejected_for_governed_ingest:
                logger.info(
                    "web_research: rejected %s source(s) below the governed ingest quality threshold",
                    rejected_for_governed_ingest,
                )
            merged = governed_candidates
        # A live search outage or a short live result set must not strand a corpus-backed
        # report below its configured source contract. The report may declare an already-
        # imported Index-Retriever corpus; use it through the normal service tool to
        # supplement live sources with public URLs and retrieved passages for model authorship.
        corpus_recovery: Optional[Dict[str, Any]] = None
        if self._default_vdb and (not merged or len(merged) < required_sources):
            live_source_count = len(merged)
            vdb_service = str(self._default_vdb.get("service") or "").strip()
            vdb_profile = str(self._default_vdb.get("profile") or "").strip()
            collections = self._default_vdb.get("collections")
            vdb_collection = ""
            if isinstance(collections, dict):
                vdb_collection = str(collections.get("library") or collections.get("content") or "").strip()
            if vdb_service and vdb_profile and vdb_collection:
                fallback_queries: List[str] = []
                for candidate in [*queries, *self._default_research_queries]:
                    candidate = str(candidate or "").strip()
                    if candidate and candidate not in fallback_queries:
                        fallback_queries.append(candidate)
                # The index ranks chunks, not source documents.  A small ``top_k`` can
                # therefore return many chunks from the same few doctrine PDFs and leave
                # a report one source short even though its imported corpus contains
                # enough distinct public sources.  Retrieve a bounded candidate set and
                # traverse the schedule-owned facets until we have a small validation
                # buffer.  This only configures normal retrieval; the model still selects
                # and authors the report citations from the returned source pack.
                corpus_candidate_depth = (
                    max(1, min(60, max(max_sources, required_sources * 4)))
                    if required_sources
                    else max(1, min(max_results, 12))
                )
                # Link validation runs after corpus retrieval.  Stopping at a
                # small pre-validation buffer can leave a strict report below
                # its governed source floor when several otherwise-authoritative
                # documents have moved or become temporarily unavailable.  In
                # that mode, collect the already-bounded source pool before
                # filtering it for live access; without link validation retain
                # the smaller retrieval target to avoid unnecessary calls.
                corpus_target = (
                    max_sources
                    if args.get("validate_links")
                    else min(
                        max_sources,
                        required_sources + min(5, max(1, required_sources // 3)),
                    )
                )
                corpus_recovery = {
                    "service": vdb_service,
                    "profile": vdb_profile,
                    "collection": vdb_collection,
                    "queries": fallback_queries,
                    "candidate_depth": corpus_candidate_depth,
                }
                for q in fallback_queries[:12]:
                    try:
                        raw = await self._dispatch_service(
                            vdb_service,
                            "search",
                            {
                                "profile": vdb_profile,
                                "collection": vdb_collection,
                                "query": q,
                                "top_k": corpus_candidate_depth,
                            },
                        )
                        self._record_service_invocation(
                            vdb_service,
                            "search",
                            {
                                "profile": vdb_profile,
                                "collection": vdb_collection,
                                "query": q,
                                "top_k": corpus_candidate_depth,
                            },
                            raw,
                        )
                        _raise_mcp_failure(raw, "index-retriever search")
                        payload = _mcp_payload(raw)
                        rows = payload.get("results") if isinstance(payload, dict) else []
                    except Exception as exc:
                        logger.warning("web_research: corpus fallback failed (%s): %s", q[:40], exc)
                        continue
                    if not isinstance(rows, list):
                        continue
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
                        url = _public_url(metadata.get("source_url") or row.get("source_url"))
                        if not url or url in seen:
                            continue
                        seen.add(url)
                        merged.append(
                            {
                                "title": str(metadata.get("title") or metadata.get("filename") or row.get("doc_id") or "Corpus source"),
                                "url": url,
                                "publishedDate": str(metadata.get("modified_at") or metadata.get("created_at") or ""),
                                "content": str(row.get("text") or ""),
                            }
                        )
                    if len(merged) >= corpus_target:
                        break
                if merged:
                    recovered = len(merged) - live_source_count
                    if live_source_count:
                        logger.info(
                            "web_research: supplemented %s live sources with %s corpus sources from %s",
                            live_source_count,
                            recovered,
                            vdb_collection,
                        )
                    else:
                        logger.info(
                            "web_research: live search returned no sources; recovered %s corpus sources from %s",
                            recovered,
                            vdb_collection,
                        )
        # A product may supply a bounded register of public primary-data families
        # for an outage in the shared search backend.  This is retrieval policy,
        # not report authorship: the model still chooses which governed evidence
        # supports its claims and writes every final source entry.  Do not fall
        # back to opaque strings or invented URLs; only typed, public endpoints
        # declared by the product are eligible.
        if (
            (not merged or len(merged) < required_sources)
            and isinstance(self._default_source_families, list)
        ):
            live_source_count = len(merged)
            for source in self._default_source_families:
                if not isinstance(source, dict):
                    continue
                url = _public_url(source.get("url") or source.get("source_url"))
                if not url or url in seen:
                    continue
                seen.add(url)
                merged.append(
                    {
                        "title": str(
                            source.get("title")
                            or source.get("description")
                            or source.get("id")
                            or urlsplit(url).netloc
                        ),
                        "url": url,
                        "publishedDate": str(source.get("publishedDate") or ""),
                        "content": str(source.get("content") or ""),
                    }
                )
                if len(merged) >= max_sources:
                    break
            if merged:
                if live_source_count:
                    logger.info(
                        "web_research: supplemented %s live sources with %s configured public source families",
                        live_source_count,
                        len(merged) - live_source_count,
                    )
                else:
                    logger.info(
                        "web_research: live search returned no sources; using %s configured public source families",
                        len(merged),
                    )
        if args.get("validate_links"):
            timeout = max(2, min(int(args.get("link_timeout") or 12), 30))
            # The final rendered-document gate can require citations to be
            # recipient-accessible, rather than merely extant.  Apply that
            # exact policy while building the governed source register so the
            # model never spends a full authoring pass on a 401/403/429 source
            # which publication must reject.  This is retrieval validation
            # only: it neither chooses a source nor alters report content.
            require_public_access = bool(args.get("require_public_access"))
            semaphore = asyncio.Semaphore(8)

            async def _validated(result: Dict[str, Any]) -> bool:
                url = _public_url(result.get("url"))
                if not url:
                    return False
                async with semaphore:
                    return await asyncio.to_thread(
                        _external_url_retrievable,
                        url,
                        timeout,
                        require_public_access=require_public_access,
                    )

            decisions = await asyncio.gather(*(_validated(result) for result in merged))
            rejected = len(merged) - sum(bool(value) for value in decisions)
            merged = [result for result, keep in zip(merged, decisions) if keep]
            logger.info("web_research: rejected %s non-retrievable source URLs", rejected)
            # Corpus retrieval ranks chunks, while the governed register requires
            # distinct, retrievable document URLs.  The first bounded pool can
            # therefore contain enough candidates before validation but still fall
            # below the source floor after moved or unavailable documents are
            # removed.  Re-query the same schedule-owned facets at a bounded deeper
            # depth and validate only previously unseen URLs.  This is still the
            # normal Index-Retriever flow; it does not introduce URLs or author
            # report content in code.
            if (
                required_sources
                and len(merged) < required_sources
                and corpus_recovery is not None
            ):
                recovery_depth = min(
                    180,
                    max(
                        int(corpus_recovery["candidate_depth"]) * 3,
                        required_sources * 12,
                    ),
                )
                recovered_after_validation = 0
                for q in corpus_recovery["queries"][:12]:
                    try:
                        recovery_args = {
                            "profile": corpus_recovery["profile"],
                            "collection": corpus_recovery["collection"],
                            "query": q,
                            "top_k": recovery_depth,
                        }
                        raw = await self._dispatch_service(
                            corpus_recovery["service"], "search", recovery_args
                        )
                        self._record_service_invocation(
                            corpus_recovery["service"], "search", recovery_args, raw
                        )
                        _raise_mcp_failure(raw, "index-retriever recovery search")
                        payload = _mcp_payload(raw)
                        rows = payload.get("results") if isinstance(payload, dict) else []
                    except Exception as exc:
                        logger.warning(
                            "web_research: validated corpus recovery failed (%s): %s",
                            q[:40],
                            exc,
                        )
                        continue
                    if not isinstance(rows, list):
                        continue
                    candidates: List[Dict[str, Any]] = []
                    for row in rows:
                        if not isinstance(row, dict):
                            continue
                        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
                        url = _public_url(metadata.get("source_url") or row.get("source_url"))
                        if not url or url in seen:
                            continue
                        seen.add(url)
                        candidates.append(
                            {
                                "title": str(
                                    metadata.get("title")
                                    or metadata.get("filename")
                                    or row.get("doc_id")
                                    or "Corpus source"
                                ),
                                "url": url,
                                "publishedDate": str(
                                    metadata.get("modified_at") or metadata.get("created_at") or ""
                                ),
                                "content": str(row.get("text") or ""),
                            }
                        )
                    if not candidates:
                        continue
                    decisions = await asyncio.gather(
                        *(_validated(candidate) for candidate in candidates)
                    )
                    accepted = [
                        candidate
                        for candidate, keep in zip(candidates, decisions)
                        if keep
                    ]
                    merged.extend(accepted)
                    recovered_after_validation += len(accepted)
                    if len(merged) >= required_sources:
                        break
                if recovered_after_validation:
                    logger.info(
                        "web_research: recovered %s additional retrievable corpus source(s) after validation",
                        recovered_after_validation,
                    )
        cap = max_sources
        picked = merged[:cap]
        # W28M-1636 R5: source TITLES that reach the report must be MODEL-AUTHORED and clean — search
        # providers return titles truncated with '…'/'...' and cluttered with currency/query text, and
        # the coordinator forbids deterministic REPAIR of citation labels. So the local generator
        # authors a clean, complete label for each retrieved source here (keeping its REAL URL); the
        # raw provider title is used only as a fallback when no generator is bound.
        _authored: Dict[int, str] = {}
        gen_lbl = self._generator_child_id()
        if gen_lbl is not None and picked:
            _rows = "\n".join(
                f"{i}. site={urlsplit(_public_url(r.get('url')) or '').netloc or 'source'} "
                f":: {str(r.get('title') or '')[:140]}"
                for i, r in enumerate(picked, 1)
            )
            _lp = (
                "Write a CLEAN, COMPLETE citation label for each numbered source below, one per line, "
                "each prefixed with its number and a period. Use the form 'Publisher/site - short clear "
                    "topic' (e.g. '3. World Bank - Individuals using the Internet' or "
                    "'7. Salary publisher - Senior software engineer salary'). Every label MUST be a "
                "whole human-readable phrase: NEVER end with '...' or '…', never leave a word clipped, "
                "and never include a URL, a currency figure, or query text. Output ONLY the numbered "
                "labels, nothing else.\n\n" + _rows
            )
            _label_currency_re = re.compile(
                r"(?:\b(?:USD|US\$|CLP|COP|ARS|BRL|MXN|PEN|UYU)\b|\$|R\$|"
                r"\b\d[\d.,]*\s*(?:pesos|reais|reales)\b)",
                re.I,
            )

            def _bad_label(lbl: Optional[str]) -> bool:
                return (
                    (not lbl)
                    or bool(re.search(r"…|\.\.\.", lbl))
                    or bool(_label_currency_re.search(lbl))
                    or len(lbl) < 6
                )

            async def _ask_labels(prompt: str) -> None:
                try:
                    _raw = await self._dispatch_subexpert(gen_lbl, prompt, {})
                    for _ln in clean_final_content(_raw if isinstance(_raw, str) else str(_raw)).splitlines():
                        _mm = re.match(r"\s*(\d+)[.)]\s*(.+)", _ln.strip())
                        if _mm and not _bad_label(_mm.group(2).strip()):
                            _authored[int(_mm.group(1))] = _mm.group(2).strip()
                except Exception as _exc:
                    logger.warning("web_research: source-label authoring failed: %s", _exc)

            await _ask_labels(_lp)
            # re-ask for any label the model left truncated/clipped/currency-bearing until every label is a complete
            # phrase (the coordinator forbids deterministically trimming a label — it must be authored).
            for _lr in range(4):
                _need = [i for i in range(1, len(picked) + 1) if _bad_label(_authored.get(i))]
                if not _need:
                    break
                _rows_need = "\n".join(
                    f"{i}. site={urlsplit(_public_url(picked[i - 1].get('url')) or '').netloc or 'source'} "
                    f":: {str(picked[i - 1].get('title') or '')[:140]}"
                    for i in _need
                )
                await _ask_labels(
                    "Your earlier label(s) for these sources were truncated or incomplete. Write a "
                    "WHOLE, COMPLETE citation label for EACH one below, one per line prefixed with its "
                    "number and a period, form 'Publisher/site - short clear topic'. The label MUST be a "
                    "finished phrase - NEVER end with '...' or '…', never clip a word, no URL, no "
                    "currency symbol, no currency code, no salary amount, and no query text. Output ONLY "
                    "the numbered labels.\n\n" + _rows_need
                )
            # Keep only sources with a clean, complete model-authored label; DROP the rest rather than
            # cite a truncated label (deterministic trimming is forbidden). Safe to renumber here — the
            # report has not been authored yet, so no inline [n] citation exists to disturb.
            _kept = [(picked[i - 1], _authored[i]) for i in range(1, len(picked) + 1)
                     if not _bad_label(_authored.get(i))]
            if _kept:
                picked = [p for p, _ in _kept]
                _authored = {j: lbl for j, (_, lbl) in enumerate(_kept, 1)}
        await self._persist_research_ingest(picked)
        grounding, sources = [], []
        for i, r in enumerate(picked, 1):
            raw_title = (str(r.get("title") or "Source")).strip()
            title = _authored.get(i) or raw_title
            url = _public_url(r.get("url"))  # drop localhost/private/relative — never cite a dead link
            date = (str(r.get("publishedDate") or "")).strip()[:10]
            snip = _clean_snippet(r.get("content"))[:560]
            model_authored_sources = bool(args.get("model_authored_sources_required"))
            grounding.append(
                f"[{i}] {title}"
                + (f" — URL: {url}" if model_authored_sources and url else "")
                + (f" — {date}" if date else "")
                + (f": {snip}" if snip else "")
            )
            sources.append(f"[{i}] [{title}]({url})" if url else f"[{i}] {title}")
        logger.info("web_research: %s sources from %s queries (%s model-authored labels)",
                    str(len(grounding)), str(min(len(queries), max_queries)), str(len(_authored)))
        if forbidden_rejected:
            logger.info("web_research: rejected %s source(s) by configured forbidden-content policy",
                        forbidden_rejected)
        if not grounding:
            return "No current sources were retrieved for this query."
        self._research_grounding = "\n".join(grounding)
        self._research_sources_md = "## Sources\n\n" + "\n".join(sources)
        if args.get("model_authored_sources_required"):
            return ("CURRENT SOURCE REGISTER — ground EVERY factual claim in these validated sources "
                    "and cite inline using each source's real bracketed number, e.g. [2] (copy the "
                    "actual digit shown; NEVER write the literal placeholder [n]). Author the final "
                    "'## Sources' section yourself from the URLs you actually cite; do NOT reproduce "
                    "any supplied Sources block verbatim.\n\n" + self._research_grounding)
        return ("CURRENT SOURCES — ground EVERY factual claim in these and cite inline using each "
                "source's real bracketed number, e.g. [2] (copy the actual digit shown below; NEVER "
                "write the literal placeholder [n]); include the specific names, dates and numbers "
                "they contain; reproduce the '## Sources' block verbatim as the final section of the "
                "document:\n\n" + self._research_grounding + "\n\n" + self._research_sources_md)

    @staticmethod
    def _research_source_quality(url: str, source: Dict[str, Any]) -> Dict[str, Any]:
        """Score a candidate for governed storage without selecting report citations.

        The model still chooses which of the retrieved sources it cites. This
        policy only decides whether a public candidate is suitable to preserve
        and index for the configured research workspace.
        """
        host = (urlsplit(url).hostname or "").lower()
        primary_suffixes = (
            "nato.int",
            "gov.uk",
            ".gov",
            ".mil",
            "coemed.org",
            "cimic-coe.org",
            "army.gr",
            # Official Allied defence publishers represented in the governed
            # doctrine corpus.  These are government or armed-forces domains,
            # not generic country-code domains, so their inclusion preserves
            # the official-source policy while allowing the corpus fallback to
            # meet a NATO source contract during a live-search outage.
            "gouv.fr",
            "gov.pl",
            "puolustusvoimat.fi",
            "fmn.dk",
            "forsvaret.dk",
        )
        public_open_data_suffixes = (
            "openstreetmap.org",
            "overpass-api.de",
            "wikidata.org",
            "wikipedia.org",
            "wikimedia.org",
            "earth-search.aws",
            "element84.com",
        )
        institutional_suffixes = (".int", ".europa.eu", ".edu")
        if host.endswith(primary_suffixes) or host.endswith(public_open_data_suffixes):
            authority = 100
        elif host.endswith(institutional_suffixes):
            authority = 78
        else:
            authority = 55
        relevance = 90 if str(source.get("content") or source.get("title") or "").strip() else 70
        freshness = 75 if str(source.get("publishedDate") or "").strip() else 60
        score = round((authority * 0.65) + (relevance * 0.25) + (freshness * 0.10), 1)
        return {
            "authority": authority,
            "relevance": relevance,
            "freshness": freshness,
            "score": score,
        }

    @staticmethod
    def _download_research_source(
        url: str,
        *,
        timeout_seconds: int,
        max_bytes: int,
    ) -> tuple[bytes, str, str]:
        """Retrieve one already-public, validated source within bounded limits."""
        status_code, resolved_url, payload, response_headers = _platform_http_get(
            url,
            headers={
                "User-Agent": "Cloud-Dog-Research-Ingest/1.0",
                "Accept": "application/pdf,text/html,text/plain,application/json,*/*",
            },
            timeout_seconds=timeout_seconds,
            max_bytes=max_bytes + 1,
        )
        if not 200 <= status_code < 400:
            raise RuntimeError(f"research source retrieval returned HTTP {status_code}")
        if not _public_url(resolved_url):
            raise RuntimeError("research source redirect did not resolve to a public URL")
        if len(payload) > max_bytes:
            raise RuntimeError(f"research source exceeds {max_bytes} byte retrieval limit")
        content_type = str(response_headers.get("content-type") or "").split(";", 1)[0].lower()
        return payload, content_type, resolved_url

    @staticmethod
    def _research_storage_filename(url: str, digest: str, content_type: str) -> str:
        """Create a content-addressed FileMCP filename without trusting URL path text."""
        suffix = (urlsplit(url).path.rsplit(".", 1)[-1].lower()
                  if "." in urlsplit(url).path.rsplit("/", 1)[-1] else "")
        allowed = {"pdf", "html", "htm", "txt", "json", "xml", "doc", "docx"}
        if suffix not in allowed:
            suffix = {
                "application/pdf": "pdf",
                "text/html": "html",
                "text/plain": "txt",
                "application/json": "json",
            }.get(content_type, "bin")
        return f"{digest[:24]}.{suffix}"

    async def _persist_research_ingest(self, candidates: List[Dict[str, Any]]) -> None:
        """Store and index accepted live-research sources through bound MCP services.

        This is bounded retrieval/storage/index plumbing. It does not change the
        candidate source register, choose citations, or author report content.
        """
        cfg = self._default_research_ingest
        if not cfg or not bool(cfg.get("download_permitted_sources_to_file_mcp")):
            return
        profile = str(cfg.get("profile") or self._default_profile or "").strip()
        storage_path = str(cfg.get("storage_path") or "downloaded/research").strip().strip("/")
        if not profile or not storage_path:
            raise RuntimeError("RESEARCH_INGEST_CONFIGURATION_INVALID: profile and storage_path are required")
        threshold = float(cfg.get("quality_threshold") or 80)
        max_sources = max(1, min(int(cfg.get("max_downloaded_sources") or 6), 12))
        minimum_accepted = max(1, min(int(cfg.get("minimum_accepted_sources") or 1), max_sources))
        max_bytes = max(1024, min(int(cfg.get("max_source_bytes") or 8_000_000), 20_000_000))
        timeout_seconds = max(5, min(int(cfg.get("download_timeout_seconds") or 30), 90))
        file_service = self._svc_for("b64_decode_to_file", "filemcpserver0")
        directory_service = self._svc_for("create_dir", "filemcpserver0")
        vdb = self._default_vdb
        collections = vdb.get("collections") if isinstance(vdb.get("collections"), dict) else {}
        index_service = str(vdb.get("service") or "indexretriever0").strip()
        collection = str(collections.get("content") or collections.get("library") or "").strip()
        ingest_enabled = bool(cfg.get("ingest_accepted_sources_to_vdb"))
        if ingest_enabled and (not index_service or not collection):
            raise RuntimeError("RESEARCH_INGEST_CONFIGURATION_INVALID: VDB profile and collection are required")

        directory_args = {"profile": profile, "path": storage_path, "parents": True}
        directory_result = await self._dispatch_service(directory_service, "create_dir", directory_args)
        self._record_service_invocation(directory_service, "create_dir", directory_args, directory_result)
        _raise_mcp_failure(directory_result, "research FileMCP create_dir")

        accepted = 0
        for candidate in candidates:
            url = _public_url(candidate.get("url"))
            if not url:
                continue
            quality = self._research_source_quality(url, candidate)
            record: Dict[str, Any] = {
                "url": url,
                "title": str(candidate.get("title") or "Source").strip(),
                "publisher": str(candidate.get("publisher") or urlsplit(url).hostname or "").strip(),
                "published_date": str(candidate.get("publishedDate") or "").strip()[:64],
                "accessed_at": _datetime.datetime.now(_datetime.timezone.utc).isoformat().replace("+00:00", "Z"),
                "quality": quality,
                "status": "rejected",
            }
            if quality["score"] < threshold:
                record["reason"] = "quality_below_threshold"
                self._research_ingest_records.append(record)
                continue
            if accepted >= max_sources:
                record["reason"] = "bounded_source_limit"
                self._research_ingest_records.append(record)
                continue
            try:
                payload, content_type, resolved_url = await asyncio.to_thread(
                    self._download_research_source,
                    url,
                    timeout_seconds=timeout_seconds,
                    max_bytes=max_bytes,
                )
                digest = hashlib.sha256(payload).hexdigest()
                path = f"{storage_path}/{self._research_storage_filename(resolved_url, digest, content_type)}"
                file_args = {
                    "profile": profile,
                    "path": path,
                    "data": base64.b64encode(payload).decode("ascii"),
                    "overwrite": True,
                }
                file_result = await self._dispatch_service(file_service, "b64_decode_to_file", file_args)
                self._record_service_invocation(file_service, "b64_decode_to_file", file_args, file_result)
                _raise_mcp_failure(file_result, "research FileMCP b64_decode_to_file")
                record.update({
                    "url": resolved_url,
                    "storage_path": path,
                    "sha256": digest,
                    "content_type": content_type or "application/octet-stream",
                    "source_type": "document" if content_type else "unknown",
                })
                if ingest_enabled:
                    snippet = str(candidate.get("content") or "").strip()
                    if content_type.startswith("text/") or content_type == "application/json":
                        snippet = payload.decode("utf-8", "replace")[:200_000]
                    ingest_args = {
                        "profile": str(vdb.get("profile") or profile),
                        "collection": collection,
                        "text": "\n\n".join(part for part in (
                            record["title"],
                            snippet,
                            f"SOURCE: {resolved_url}",
                        ) if part),
                        "source": resolved_url,
                        "idempotency_key": f"research-ingest-{digest[:32]}",
                        "metadata": {
                            "research_ingest": True,
                            "source_url": resolved_url,
                            "source_sha256": digest,
                            "storage_path": path,
                            "title": record["title"],
                            "quality_score": quality["score"],
                        },
                    }
                    ingest_result = await self._dispatch_service(
                        index_service, "ingest_text", ingest_args
                    )
                    self._record_service_invocation(
                        index_service, "ingest_text", ingest_args, ingest_result
                    )
                    _raise_mcp_failure(ingest_result, "research Index-Retriever ingest_text")
                    record["ingest"] = "completed"
                    ingest_summary = self._extract_invocation_summary(ingest_result)
                    if ingest_summary.get("job_id"):
                        record["vdb_job_id"] = ingest_summary["job_id"]
                record["status"] = "accepted"
                accepted += 1
            except Exception as exc:
                record["reason"] = f"retrieval_or_ingest_failed:{type(exc).__name__}"
            self._research_ingest_records.append(record)

        manifest_args = {
            "profile": profile,
            "path": f"{storage_path}/research-ingest-manifest.json",
            "content": json.dumps(
                {
                    "status": "completed" if accepted >= minimum_accepted else "insufficient_accepted_sources",
                    "accepted_sources": accepted,
                    "minimum_accepted_sources": minimum_accepted,
                    "records": self._research_ingest_records,
                },
                ensure_ascii=False,
                sort_keys=True,
            ),
            "overwrite": True,
        }
        manifest_result = await self._dispatch_service(file_service, "write_file", manifest_args)
        self._record_service_invocation(file_service, "write_file", manifest_args, manifest_result)
        _raise_mcp_failure(manifest_result, "research FileMCP manifest write")
        if accepted < minimum_accepted:
            raise RuntimeError(
                "RESEARCH_INGEST_INCOMPLETE: "
                f"{accepted} accepted source(s); {minimum_accepted} required"
            )

    async def _ingest_newsletters(self, spec: Dict[str, Any]) -> int:
        """Ingest the analyst newsletters from an IMAP mailbox into a vector collection so the
        report can ground on (and cite) them. Searches the mailbox (`mail_headlines`), extracts
        each message body (`mail_extract_message`), and indexes it (`ingest_text`) with the
        post URL as the source. Best-effort; returns the count indexed."""
        prof = str(spec.get("imap_profile") or "gmail_personal")
        query = str(spec.get("query") or "ukraine")
        limit = int(spec.get("max_messages") or 25)
        vprof = spec.get("vdb_profile")
        vcoll = spec.get("vdb_collection")
        if not (vprof and vcoll):
            return 0
        imap = self._svc_for("imap", "imapmcpserver0")
        idx = self._svc_for("index", "indexretriever0")
        # url -> citable analyst label for THIS run's ingests, so grounding can label every
        # retrieved chunk by its source even when the chunk lost the inline "[label]" prefix.
        self._newsletter_meta = getattr(self, "_newsletter_meta", {})
        try:
            hl = await self._dispatch_service(imap, "mail_headlines",
                                              {"profile_id": prof, "mode": "imap", "query": query, "limit": limit})
        except Exception as exc:
            logger.warning("newsletter ingest: mail_headlines failed: %s", exc)
            raise RuntimeError("newsletter ingest could not query the mailbox") from exc
        _raise_mcp_failure(hl, "mail_headlines")
        heads = _imap_headlines(hl)
        count = 0
        digest: List[Dict[str, Any]] = []  # for the saved "Ukraine file" digest on Drive
        for h in heads:
            uid = str(h.get("uid") or "").strip()
            if not uid:
                continue
            try:
                ex = await self._dispatch_service(imap, "mail_extract_message",
                                                  {"profile_id": prof, "uid": uid, "format": "markdown"})
            except Exception:
                continue
            body = _imap_body(ex)
            if not body or len(body) < 80:
                continue
            subject = str(h.get("headline") or h.get("subject") or "").strip()
            published_at = _newsletter_published_at(h.get("date") or h.get("received"))
            language = _newsletter_language(h, spec.get("default_language"))
            # Fail closed on identity/time.  Ingesting an untitled or undated record would
            # make the downstream daily/weekly reports unable to prove source freshness.
            if not subject or not published_at:
                logger.warning(
                    "newsletter ingest: skipped uid=%s because title/publication time is missing",
                    uid,
                )
                continue
            url = _public_url(_first_url(body))
            # name from the From header, else from the post URL (Substack subdomain), else generic.
            label = _newsletter_label(h.get("from")) or (_label_from_url(url) if url else "") or "Analyst newsletter"
            # Strip the Substack redirect/tracking wrappers and any non-public links before
            # indexing, so retrieval never surfaces a dead localhost/redirect URL to be copied.
            clean = re.sub(r"\[\s*https?://substack\.com/redirect/\S+\s*\]", " ", body)
            clean = re.sub(r"\s+", " ", clean).strip()
            text = "[%s — %s] %s" % (label, subject[:90], clean[:4000])
            source = url or ("newsletter://" + re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-"))
            import datetime as _dt
            import hashlib as _hashlib

            collected_at = _dt.datetime.now(_dt.timezone.utc).isoformat().replace("+00:00", "Z")
            content_hash = _hashlib.sha256(clean.encode("utf-8")).hexdigest()
            metadata = {
                "title": subject,
                "publisher": label,
                "source": source,
                "source_url": url,
                "published_at": published_at,
                "language": language,
                "language_method": "source_header" if (
                    h.get("language") or h.get("content_language") or h.get("content-language")
                ) else ("configured_default" if spec.get("default_language") else "undetermined"),
                "collected_at": collected_at,
                "content_hash": content_hash,
                "message_uid": uid,
                "record_type": "analyst_newsletter",
            }
            idempotency_key = _hashlib.sha256(
                (str(vprof) + "\0" + str(vcoll) + "\0" + uid + "\0" + content_hash).encode("utf-8")
            ).hexdigest()
            try:
                await self._dispatch_service(
                    idx,
                    "ingest_text",
                    {
                        "profile": vprof,
                        "collection": vcoll,
                        "text": text,
                        "source": source,
                        "metadata": metadata,
                        "idempotency_key": idempotency_key,
                    },
                )
                # Map BOTH the source string and (if present) the URL to the From-header label,
                # so grounding labels every retrieved chunk — including link-less Patreon ones.
                self._newsletter_meta[source] = label
                if url:
                    self._newsletter_meta[url] = label
                digest.append({"label": label, "subject": subject, "url": url,
                               "date": published_at,
                               "excerpt": re.sub(r"^#.*?\n", "", clean).strip()[:600]})
                count += 1
            except Exception:
                continue
        logger.info("newsletter ingest: indexed %s of %s messages from %s/%s",
                    str(count), str(len(heads)), prof, query)
        # Save the "Ukraine file": a readable Drive digest of the ingested newsletters (the VDB
        # holds the full searchable copy; this is the human-browsable companion).
        if digest and spec.get("digest_path"):
            try:
                await self._write_newsletter_digest(digest, spec)
            except Exception as exc:
                logger.warning("newsletter ingest: digest write failed: %s", exc)
        return count

    async def _write_newsletter_digest(self, digest: List[Dict[str, Any]], spec: Dict[str, Any]) -> None:
        """Write the ingested newsletters to a single Drive Markdown file (the operator's
        'Ukraine file') — each entry with analyst, subject, dated source link and an excerpt."""
        import datetime as _dt
        path = str(spec.get("digest_path"))
        title = str(spec.get("digest_title") or "Ukraine — Analyst Newsletter Digest")
        today = _dt.date.today().strftime("%d %B %Y")
        lines = ["# %s" % title, "",
                 "_Updated %s · %d newsletters · auto-ingested from the analyst mailboxes; "
                 "full searchable copy in the `%s` vector collection._" % (today, len(digest), spec.get("vdb_collection")),
                 ""]
        # de-dupe by URL/subject, newest first as returned by the mailbox
        seen = set()
        for d in digest:
            k = d.get("url") or d.get("subject")
            if k in seen:
                continue
            seen.add(k)
            head = "## %s — %s" % (d.get("label") or "Analyst", (d.get("subject") or "").strip() or "(untitled)")
            meta = " · ".join(x for x in [d.get("date") or "", ("[Read on the web](%s)" % d["url"]) if d.get("url") else ""] if x)
            lines += [head, ("*%s*" % meta) if meta else "", "", (d.get("excerpt") or "").strip(), ""]
        content = "\n".join(lines)
        await self._dispatch_service(self._svc_for("write_file", "filemcpserver0"), "write_file",
                                     {"profile": "google_drive", "path": path, "content": content, "overwrite": True})
        logger.info("newsletter digest: wrote %s entries to %s", str(len(seen)), path)

    async def _vdb_grounding(self, spec: Dict[str, Any], query: str) -> int:
        """Retrieve the most relevant newsletter passages from the vector collection and APPEND
        them to the research grounding + Sources block (continuing the citation numbering), so
        the report grounds on the named analysts and cites each with a link to their post."""
        vprof = spec.get("vdb_profile")
        vcoll = spec.get("vdb_collection")
        if not (vprof and vcoll):
            return 0
        idx = self._svc_for("index", "indexretriever0")
        try:
            res = await self._dispatch_service(idx, "search",
                                               {"profile": vprof, "collection": vcoll,
                                                "query": query, "top_k": int(spec.get("top_k") or 8)})
        except Exception as exc:
            logger.warning("vdb grounding: search failed: %s", exc)
            return 0
        rows = _vdb_results(res)
        if not rows:
            return 0
        meta = getattr(self, "_newsletter_meta", {}) or {}
        base = len(re.findall(r"(?m)^\[\d+\]", self._research_grounding or ""))
        add_g, add_s = [], []
        seen: set = set()
        n = base
        for m in rows:
            src = str(m.get("source_uri") or m.get("source") or "").strip()
            pub = _public_url(src)
            # One citation per analyst/source — keep the first (highest-scoring) chunk, drop
            # the duplicate chunks that otherwise filled the Sources block with repeats.
            key = pub or src or _bracket_label(str(m.get("text", "") or "")) or str(len(seen))
            if key in seen:
                continue
            seen.add(key)
            # Label by source first (reliable across chunks), then the chunk prefix, then the URL
            # subdomain, then the non-URL source slug — only then the generic fallback.
            label = meta.get(pub) or meta.get(src) or _bracket_label(str(m.get("text", "") or "")) \
                or (_label_from_url(pub) if pub else "") or _source_label(src) or "Analyst newsletter"
            snippet = _clean_snippet(re.sub(r"^\s*\[[^\]]*\]\s*", "", str(m.get("text", "") or "")))[:420]
            n += 1
            # Link text = analyst + the specific article title (from the post URL slug), so the
            # citation points to the actual page, e.g. "Phillips O'Brien — Weekend Update 191".
            _art = _article_title_from_url(pub)
            _linktext = ("%s — %s" % (label, _art)) if _art else label
            add_g.append("[%d] %s — %s" % (n, label, snippet))
            add_s.append("[%d] [%s](%s)" % (n, _linktext, pub) if pub else "[%d] %s" % (n, label))
        if not add_g:
            return 0
        self._research_grounding = (self._research_grounding or "") + "\n" + "\n".join(add_g)
        if not self._research_sources_md:
            self._research_sources_md = "## Sources\n\n"
        self._research_sources_md = self._research_sources_md.rstrip() + "\n" + "\n".join(add_s)
        logger.info("vdb grounding: added %s newsletter sources (from %s chunks)",
                    str(len(add_g)), str(len(rows)))
        return len(add_g)

    async def _previous_editions(self, series: str, base_url: str,
                                 exclude_subject: str = "", limit: int = 3) -> List[Dict[str, Any]]:
        """Build the 'Further Detail & Previous Reports' links from the notification message
        store — the report archive. Lists recent messages, keeps the ones in this report
        ``series`` (by subject), and links each to its public ``/messages/<id>`` permalink.
        Best-effort: returns [] on any failure so delivery is never blocked."""
        if not series:
            return []
        notif = self._svc_for("send_notification", "notificationagent0")
        try:
            res = await self._dispatch_service(notif, "list_messages", {"limit": 40})
        except Exception as exc:
            logger.warning("previous editions: list_messages failed: %s", exc)
            return []
        base = (base_url or str(get_config("research.messages_base_url", "") or "")).rstrip("/")
        key = series.lower()
        out: List[Dict[str, Any]] = []
        for m in _msg_items(res):
            subj = str(m.get("subject") or "").strip()
            if key not in subj.lower():
                continue
            if exclude_subject and subj == exclude_subject:
                continue
            ident = m.get("guid") or m.get("id") or m.get("message_id")
            if ident in (None, ""):
                continue
            note = str(m.get("created_at") or m.get("created") or "")[:10]
            out.append({"title": subj, "url": "%s/%s" % (base, ident), "note": note or None})
            if len(out) >= max(1, int(limit)):
                break
        logger.info("previous editions: %s prior '%s' editions linked", str(len(out)), series)
        return out

    async def _extract_data_points(self, topic: str, max_points: int = 7) -> List[Dict[str, Any]]:
        """Extract real QUANTITATIVE data points from the current web-search grounding (one LLM
        pass over the sources already retrieved by ``_web_research``). This lets a report chart
        genuine figures from current web sources for topics the SQL dataset does not cover
        (e.g. beneficial-ownership registers, sanctions tallies). Best-effort: returns
        ``[{"label","value"}]`` for charting, or ``[]`` when the sources carry no clean,
        comparable numbers (the caller then skips that chart)."""
        grounding = getattr(self, "_research_grounding", "") or ""
        if not grounding:
            return []
        prompt = (
            "From the SOURCES below, extract up to %d concrete QUANTITATIVE data points relevant to: %s.\n"
            "Use ONLY real figures actually stated in the sources (counts, amounts, percentages, indices, "
            "rankings). Keep each label short (<=5 words). Convert amounts to plain numbers (e.g. "
            "'EUR 2.3 billion' -> value 2.3 with label ending '(EUR bn)'). The points must be comparable "
            "on one axis (same kind of measure).\n"
            "Reply with ONLY a JSON array and nothing else: [{\"label\":\"...\",\"value\":<number>}]. "
            "If the sources contain no clear comparable figures, reply exactly [].\n\nSOURCES:\n%s"
            % (int(max_points), topic, grounding[:3800])
        )
        try:
            resp = await self._llm.generate(messages=[{"role": "user", "content": prompt}],
                                            temperature=0.1, max_tokens=600)
            text = _strip_think((resp.get("content") if isinstance(resp, dict) else str(resp)) or "")
            m = re.search(r"\[.*\]", text, re.DOTALL)
            data = json.loads(m.group(0)) if m else []
        except Exception as exc:
            logger.warning("document pipeline: web data extraction failed: %s", exc)
            return []
        out: List[Dict[str, Any]] = []
        for d in (data if isinstance(data, list) else [])[:max_points]:
            if isinstance(d, dict) and d.get("label") is not None and d.get("value") is not None:
                try:
                    out.append({"label": str(d["label"])[:48], "value": float(d["value"])})
                except (TypeError, ValueError):
                    continue
        return out

    async def _auto_section_visuals(self, doc: str, *, map_style: str = "satellite",
                                    max_images: int = 6, control: Optional[List[Dict[str, Any]]] = None,
                                    front_lines: Optional[List[Dict[str, Any]]] = None, topic: str = ""
                                    ) -> tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
        """Embellish a report: for each ``## section`` extract the notable places (→ a
        satellite/topo detail map) and concrete visual subjects (→ a licence-cleared
        Wikimedia Commons image), and return inline-CID images + figure placements +
        an attribution/credits Markdown block. ``control``/``front_lines`` (the theatre
        areas-of-control + line of contact) are overlaid on each map so a detail map shows the
        territorial situation, not just place markers. Fully content-driven, best-effort."""
        import asyncio
        from src.core.execution import media as _media
        sections = re.findall(r"(?m)^##\s+(.+?)\s*$\n(.*?)(?=^##\s+|\Z)", doc, re.DOTALL)
        inline: List[Dict[str, Any]] = []
        figures: List[Dict[str, Any]] = []
        credits: List[str] = []
        used_subjects: set = set()
        img_count = 0
        # Skip the lead/synthesis sections (executive summary, "in brief", assessment/outlook/
        # watch, sources) so figures distribute through the substantive detail sections instead
        # of piling up at the top; one map + at most one image per illustrated section.
        _skip = re.compile(r"(?i)\b(in brief|executive summary|^summary|overview|sources|credits|"
                           r"further detail|assessment|outlook|watch ?(items|list)?|conclusion|key takeaways)\b")
        # Fail-fast: Wikimedia Commons is best-effort and can be slow/unreachable. After a few
        # consecutive fetch failures/timeouts, stop attempting Commons images for the rest of the
        # document so a flaky provider cannot drag an async run to 30-40 minutes (short per-fetch
        # timeouts in media.py bound each attempt; this bounds the total).
        _commons_fails = 0
        _commons_giveup = False
        for si, (heading, body) in enumerate(sections):
            if _skip.search(heading) or len(body.strip()) < 140:
                continue
            spec = await self._extract_section_visuals(heading, body, topic)
            after = heading.strip()[:46]
            # --- detail map from the section's places (span-aware framing) ---
            places = [p for p in spec.get("places", []) if _valid_lonlat(p)]
            # A section about the front / territory must be FRAMED ON THE FRONT LINE, not on
            # whatever (often rear or mis-located) places the model named — otherwise the
            # "Frontline Changes" map ends up over a rear city with the front off-screen.
            _front_pts = [(float(c[0]), float(c[1])) for ln in (front_lines or [])
                          for c in (ln.get("coords") or []) if isinstance(c, (list, tuple)) and len(c) >= 2]
            _frontish = bool(re.search(r"(?i)front\s*line|frontline|territor|area[s]? of control|"
                                       r"advance|offensive|gains|incursion|salient|counter[- ]?attack",
                                       heading + " " + str(spec.get("map_title") or "")))
            if _frontish and _front_pts:
                def _near_front(p):
                    """Return true when a place is close enough to the front-line geometry."""
                    return min(abs(float(p["lon"]) - fx) + abs(float(p["lat"]) - fy) for fx, fy in _front_pts) < 1.3
                near = [p for p in places if _near_front(p)]
                frame_pts = ([(float(p["lon"]), float(p["lat"])) for p in near] + _front_pts) if near else _front_pts
                places = near  # markers: only the towns actually on this front sector
                xs = [x for x, _ in frame_pts]
                ys = [y for _, y in frame_pts]
                west, east, south, north = min(xs) - 0.5, max(xs) + 0.5, min(ys) - 0.4, max(ys) + 0.4
                _do_map = True
            elif places:
                xs, ys = [], []
                for p in places:
                    sp = float(p.get("span") or 0.7)
                    xs += [float(p["lon"]) - sp, float(p["lon"]) + sp]
                    ys += [float(p["lat"]) - sp * 0.72, float(p["lat"]) + sp * 0.72]
                west, east, south, north = min(xs), max(xs), min(ys), max(ys)
                _do_map = True
            else:
                _do_map = False
            if _do_map:
                # enforce a minimum frame so a single place still shows context, and a ceiling
                if east - west < 2.6:
                    c = (east + west) / 2
                    west, east = c - 1.3, c + 1.3
                if north - south < 1.8:
                    c = (north + south) / 2
                    south, north = c - 0.9, c + 0.9
                bbox = [west, south, east, north]
                if (east - west) <= 60 and (north - south) <= 40:  # allow multi-country regional maps
                    markers = [{"lon": float(p["lon"]), "lat": float(p["lat"]), "label": str(p.get("name") or "")[:24]} for p in places]
                    mtitle = str(spec.get("map_title") or heading)[:70]
                    b64 = await asyncio.to_thread(_media.render_location_map, bbox,
                                                  markers=markers, areas=control, lines=front_lines,
                                                  title=mtitle, style=map_style)
                    if b64:
                        cid = "automap%d" % si
                        inline.append({"content_id": cid, "content_type": "image/png",
                                       "data": b64, "filename": cid + ".png"})
                        _base = "OpenStreetMap" if map_style == "osm" else ("topographic" if map_style == "topo" else "satellite")
                        _capx = " — areas of control + line of contact shown" if control else ""
                        figures.append({"content_id": cid, "after_heading": after, "max_width": "560px",
                                        "caption": "Map — %s (%s%s)." % (mtitle, _base, _capx)})
            # --- one licence-cleared illustrative image from the section's subjects ---
            for subj in spec.get("images", [])[:1]:
                if img_count >= max_images or _commons_giveup:
                    break
                s = str(subj or "").strip()
                if not s or s.lower() in used_subjects:
                    continue
                # HARD reject generic categories — only embed for a specifically-named system/person.
                if not _is_specific_subject(s):
                    logger.info("auto visuals: dropped GENERIC subject %r (not a specific named system)", s)
                    continue
                img = await asyncio.to_thread(_media.fetch_commons_image, s)
                if not img:
                    _commons_fails += 1
                    if _commons_fails >= 3:
                        _commons_giveup = True
                        logger.warning("auto visuals: giving up on Commons images after %s consecutive "
                                       "failures/timeouts (best-effort; document still delivers)", _commons_fails)
                    continue
                _commons_fails = 0
                # Relevance gate: confirm the matched file actually depicts the subject before
                # embedding (drops e.g. an unrelated painting or a unit emblem that slipped the
                # type filter); logged so additions are auditable.
                if not await self._image_relevant(s, img.get("title", ""), topic):
                    logger.info("auto visuals: dropped IRRELEVANT image for %r — file %r", s, img.get("title"))
                    continue
                logger.info("auto visuals: image for %r -> %r (%s)", s, img.get("title"), img.get("licence"))
                used_subjects.add(s.lower())
                img_count += 1
                cid = "autoimg%d_%d" % (si, img_count)
                inline.append({"content_id": cid, "content_type": img.get("content_type", "image/jpeg"),
                               "data": img["data"], "filename": cid + ".jpg"})
                cap = "%s. Image: %s, %s (Wikimedia Commons)." % (s, img.get("author"), img.get("licence"))
                figures.append({"content_id": cid, "after_heading": after, "max_width": "400px", "caption": cap})
                credits.append("- **%s** — %s, %s. [Source](%s)" % (
                    s, img.get("author"), img.get("licence"), img.get("source_url")))
        # Fold image/map credits into the canonical Sources block so they always render with
        # a clickable link + author + licence (a standalone trailing section gets stripped by
        # the publish step's trailing-sources cleanup).
        if credits or figures:
            block = ["", "### Image & map credits", ""] + credits + [
                "- **Maps**: base imagery © Esri, Maxar, Earthstar Geographics / © OpenStreetMap contributors; overlays by Cloud-Dog AI."]
            if not self._research_sources_md:
                self._research_sources_md = "## Sources\n"
            self._research_sources_md = self._research_sources_md.rstrip() + "\n" + "\n".join(block)
        logger.info("auto visuals: %s figures across %s sections (%s images, %s maps)",
                    str(len(figures)), str(len(sections)), str(img_count), str(len(figures) - img_count))
        return inline, figures, ""

    async def _extract_section_visuals(self, heading: str, body: str, topic: str = "") -> Dict[str, Any]:
        """One LLM pass per section: the real places to map and concrete visual subjects to
        illustrate, for a report about ``topic``. Coords corrected against a small gazetteer."""
        if not self._llm:
            return {"places": [], "images": []}
        _t = (str(topic).strip() or "current affairs")[:120]
        prompt = (
            "You are selecting illustrations for ONE section of a report about: %s.\n"
            "SECTION TITLE: %s\nSECTION TEXT:\n%s\n\n"
            "Return ONLY this JSON (no prose):\n"
            "{\"map_title\":\"<=8 words or empty\",\n"
            " \"places\":[{\"name\":\"real place named in the text\",\"lat\":<deg>,\"lon\":<deg>,\"span\":<deg>}],\n"
            " \"images\":[\"a SPECIFIC, named, photographable thing mentioned in the text\"]}\n"
            "Rules: places = up to 4 real places the text names — settlements/sites OR the COUNTRIES /"
            " regions it actually discusses — each with accurate decimal lat/lon (a country's centre) and a"
            " ``span`` half-width in DEGREES so the map frames it: ~0.5 for a town, ~3-6 for a country, ~2-4"
            " for a sub-national region (omit any you are unsure of). If the section is about"
            " governance/policy in particular countries, map THOSE countries.\n"
            "images = up to 2 subjects, each a SPECIFIC NAMED thing a real photo would show and that is"
            " genuinely relevant to the topic above — e.g. a named equipment/vehicle/aircraft/system TYPE"
            " (use the exact model, e.g. 'HIMARS', 'Su-34', 'Bayraktar TB2'), a specific named PERSON"
            " (e.g. 'Volodymyr Zelenskyy'), a specific named PLACE / building / landmark, or a specific"
            " named INSTITUTION or report/index that has a recognisable visual.\n"
            "NEVER use as an image subject: a country or its people ('United States', 'Russians'), a bare"
            " alliance/organisation acronym, an abstract concept ('sanctions', 'diplomacy', 'corruption',"
            " 'governance', 'aid', 'reform'), an event, a date, a generic word ('tank', 'official',"
            " 'document'), or a generic CATEGORY with no specific name ('air-defence systems',"
            " 'anti-corruption agencies'). If the text names nothing specific, named and depictable that"
            " fits the topic, use \"images\":[]."
            % (_t, heading[:80], (body or "")[:2200])
        )
        try:
            resp = await self._llm.generate(messages=[{"role": "user", "content": prompt}],
                                            temperature=0.1, max_tokens=500)
            text = _strip_think((resp.get("content") if isinstance(resp, dict) else str(resp)) or "")
            obj = _first_json_object(text) or {}
        except Exception as exc:
            logger.warning("auto visuals: section extract failed (%s): %s", heading[:30], exc)
            return {"places": [], "images": []}
        places = []
        for p in (obj.get("places") or [])[:4]:
            if not isinstance(p, dict):
                continue
            name = str(p.get("name") or "").strip()
            gz = _UA_GAZETTEER.get(name.lower())
            if gz:
                places.append({"name": name, "lon": gz[0], "lat": gz[1], "span": gz[2]})
            elif _valid_lonlat(p):
                # honour the model's span (so a country frames wide, a town tight); clamp it.
                try:
                    sp = float(p.get("span") or 0.7)
                except (TypeError, ValueError):
                    sp = 0.7
                sp = min(max(sp, 0.3), 8.0)
                places.append({"name": name, "lat": float(p["lat"]), "lon": float(p["lon"]), "span": sp})
        images = [str(x).strip() for x in (obj.get("images") or [])[:2] if str(x or "").strip()]
        return {"map_title": str(obj.get("map_title") or "")[:70], "places": places, "images": images}

    async def _image_relevant(self, subject: str, title: str, topic: str = "") -> bool:
        """Strict relevance gate on a candidate Commons file: does it genuinely depict ``subject``
        AND fit a report about ``topic``? Requires an explicit YES (anything else is rejected).
        Fails OPEN (True) only when there is no LLM or on a technical error — the licence +
        off-topic-type filters have already run."""
        if not self._llm or not title:
            return True
        _t = (str(topic).strip() or "the report's subject")[:120]
        try:
            prompt = ("You are vetting an illustration for a report about: %s.\n"
                      "Wanted subject: %r.\nCandidate Wikimedia Commons file title: %r.\n"
                      "Answer YES only if the file CLEARLY FITS — it genuinely shows that subject AND is "
                      "appropriate and current for that report topic (the actual thing / place / person / "
                      "organisation involved, or the same model/type referred to). Answer NO if it is an "
                      "unrelated subject, a different country or historical era that does not fit the "
                      "topic, a generic or stock mismatch, or a logo / emblem / coat of arms / flag / map "
                      "/ painting / document. When unsure, answer NO.\n"
                      "Reply with ONLY one word: YES or NO." % (_t, str(subject)[:90], str(title)[:160]))
            resp = await self._llm.generate(messages=[{"role": "user", "content": prompt}],
                                            temperature=0.0, max_tokens=200)
            text = _strip_think((resp.get("content") if isinstance(resp, dict) else str(resp)) or "")
            return text.strip().upper().startswith("YES")  # require an explicit YES
        except Exception:
            return True

    async def _rewrite_salary_consistency_defects(
        self,
        content: str,
        quality_controls: Dict[str, Any],
        *,
        title: str,
    ) -> str:
        """Ask the configured generator to re-author salary inconsistencies before delivery.

        This is intentionally generic and data-driven: the profile supplies the entities,
        bounds and token format. The strategy never supplies hub-specific salary values and
        never rewrites report text deterministically; any remaining defect is blocked by the
        final quality gate.
        """
        salary_control = (
            quality_controls.get("salary_consistency")
            if isinstance(quality_controls, dict)
            else None
        )
        if not isinstance(salary_control, dict) or not salary_control.get("required"):
            return content
        gen_id = self._generator_child_id()
        if gen_id is None:
            return content

        def _combined_quality_issues(doc: str) -> List[str]:
            issues = list(_salary_consistency_defects(doc, quality_controls))
            issues.extend("content_defect: " + defect for defect in _report_content_defects(doc))
            return issues

        token_re = re.compile(
            r"(?<![A-Za-z])(?:US\$|USD\s*\$?|\$)\s*"
            r"(?:[0-9]{2,3}(?:,[0-9]{3})+|[0-9]{2,3}(?:\.[0-9])?\s*k)"
            r"\s*(?:/yr|per\s+year|annually|annual)?",
            re.I,
        )

        def _salary_context(doc: str) -> str:
            lines: List[str] = []
            last_heading = ""
            for line_no, line in enumerate(str(doc or "").splitlines(), start=1):
                if re.match(r"^\s{0,3}#{1,6}\s+", line):
                    last_heading = re.sub(r"\s+", " ", line.strip())
                if token_re.search(line):
                    prefix = f"line {line_no}"
                    if last_heading:
                        prefix += f" under {last_heading}"
                    lines.append(f"{prefix}: {line.strip()}")
                if len(lines) >= 80:
                    break
            return "\n".join(lines) if lines else "(no visible salary-bearing lines)"

        entities_for_sections = [
            str(entity.get("name") or "").strip()
            for entity in salary_control.get("entities", [])
            if isinstance(entity, dict) and str(entity.get("name") or "").strip()
        ]

        def _entity_mentions(text: str) -> List[str]:
            return [
                entity
                for entity in entities_for_sections
                if re.search(r"\b" + re.escape(entity) + r"\b", text or "", re.I)
            ]

        def _markdown_blocks(doc: str) -> List[tuple[int, int, str, str]]:
            heading_matches = list(re.finditer(r"(?m)^(#{2,6})\s+(.+?)\s*$", doc))
            if not heading_matches:
                return [(0, len(doc), "Document", doc)]
            sections: List[tuple[int, int, str, str]] = []
            entity_sections: set[tuple[int, int]] = set()
            if heading_matches[0].start() > 0:
                sections.append((0, heading_matches[0].start(), "Document preface", doc[:heading_matches[0].start()]))
            for idx, match in enumerate(heading_matches):
                start = match.start()
                level = len(match.group(1))
                heading = re.sub(r"\s+", " ", match.group(2)).strip() or "Section"
                end = len(doc)
                has_nested_heading = False
                for later in heading_matches[idx + 1:]:
                    later_level = len(later.group(1))
                    if later_level > level:
                        has_nested_heading = True
                    if later_level <= level:
                        end = later.start()
                        break
                heading_entities = _entity_mentions(heading)
                # Preserve hub/entity context for nested salary subheadings. A
                # subfragment such as "Annual USD salary" lacks the entity name and
                # gives the model too little context to repair consistently.
                include_whole_section = (
                    len(heading_entities) == 1
                    or (level <= 3 and not has_nested_heading)
                )
                if not include_whole_section:
                    continue
                block = doc[start:end]
                sections.append((start, end, heading, block))
                if len(heading_entities) == 1:
                    entity_sections.add((start, end))
            blocks: List[tuple[int, int, str, str]] = list(sections)
            seen_spans = {(start, end) for start, end, _, _ in blocks}
            for section_start, section_end, heading, block in sections:
                if (section_start, section_end) in entity_sections:
                    continue
                groups: List[tuple[int, int, str]] = []
                pos = 0
                for match in re.finditer(r"\n\s*\n", block):
                    if match.start() > pos:
                        groups.append((section_start + pos, section_start + match.start(), block[pos:match.start()]))
                    pos = match.end()
                if pos < len(block):
                    groups.append((section_start + pos, section_end, block[pos:]))
                if (
                    len(groups) >= 2
                    and re.match(r"^\s{0,3}#{2,6}\s+.+\s*$", groups[0][2].strip())
                    and groups[1][0] > groups[0][1]
                ):
                    first = (groups[0][0], groups[1][1], block[groups[0][0] - section_start:groups[1][1] - section_start])
                    groups = [first] + groups[2:]
                for frag_start, frag_end, fragment in groups:
                    if not fragment.strip() or (frag_start, frag_end) in seen_spans:
                        continue
                    seen_spans.add((frag_start, frag_end))
                    blocks.append((frag_start, frag_end, f"{heading} fragment", fragment))
            return blocks

        def _normalised_salary_token(raw: str) -> str | None:
            match = re.search(r"([0-9]{2,3}(?:,[0-9]{3})+|[0-9]{2,3}(?:\.[0-9])?\s*k)", raw, re.I)
            if not match:
                return None
            value_text = match.group(1).strip().lower().replace(" ", "")
            try:
                if value_text.endswith("k"):
                    value = int(round(float(value_text[:-1]) * 1000))
                else:
                    value = int(value_text.replace(",", ""))
            except ValueError:
                return None
            return f"US${value:,.0f}/yr"

        def _block_quality_issues(block: str) -> List[str]:
            issues = list(_report_content_defects(block))
            issues.extend(
                issue
                for issue in _salary_consistency_defects(block, quality_controls)
                if " has no annual USD salary occurrence" not in issue
            )
            return issues

        def _canonical_table_salaries(doc: str) -> Dict[str, str]:
            entities = list(entities_for_sections)
            if not entities:
                return {}
            canonical: Dict[str, str] = {}
            for line in str(doc or "").splitlines():
                stripped = line.strip()
                if not (
                    stripped.startswith("|")
                    and stripped.endswith("|")
                    and stripped.count("|") >= 3
                    and not re.fullmatch(r"\|[\s:\-|]+\|", stripped)
                ):
                    continue
                line_tokens = [
                    token
                    for token in (_normalised_salary_token(m.group(0)) for m in token_re.finditer(stripped))
                    if token
                ]
                if len(line_tokens) != 1:
                    continue
                for entity in entities:
                    if entity not in canonical and re.search(r"\b" + re.escape(entity) + r"\b", stripped, re.I):
                        canonical[entity] = line_tokens[0]
                        break
                if len(canonical) == len(entities):
                    break
            return canonical

        def _valid_canonical_salary_plan(plan: Dict[str, Any]) -> Dict[str, str]:
            valid: Dict[str, str] = {}
            for entity in entities_for_sections:
                raw_value = plan.get(entity)
                if raw_value is None:
                    continue
                token = _normalised_salary_token(str(raw_value))
                if not token:
                    continue
                match = re.search(r"([0-9]{2,3}(?:,[0-9]{3})+)", token)
                if not match:
                    continue
                try:
                    value = int(match.group(1).replace(",", ""))
                except ValueError:
                    continue
                if salary_control.get("min_usd") is not None:
                    try:
                        if value < int(salary_control["min_usd"]):
                            continue
                    except (TypeError, ValueError):
                        pass
                if salary_control.get("max_usd") is not None:
                    try:
                        if value > int(salary_control["max_usd"]):
                            continue
                    except (TypeError, ValueError):
                        pass
                valid[entity] = token
            return valid

        def _salary_plan_needed(issues: List[str], table_plan: Dict[str, str]) -> bool:
            if len(table_plan) < len(entities_for_sections):
                return True
            return any(
                marker in issue
                for issue in issues
                for marker in (
                    "multiple salary values",
                    "not canonical annual USD token format",
                    "outside configured annual USD range",
                )
            )

        async def _model_canonical_salary_plan(doc: str, issues: List[str]) -> Dict[str, str]:
            if not entities_for_sections:
                return {}
            controls_for_prompt = {
                key: salary_control.get(key)
                for key in (
                    "required_token_format",
                    "min_usd",
                    "max_usd",
                    "reject_unscoped_salary_values",
                    "reject_ambiguous_multi_entity_salary",
                )
                if key in salary_control
            }
            prompt = (
                f'The report "{title}" failed a generic salary consistency gate before delivery.\n'
                "Choose ONE canonical annual US-dollar salary token for each configured entity. "
                "This is a correction plan for a model-authored report, not final prose. "
                "Use only configured entities. Choose plausible annual values within the configured "
                "bounds and in the exact token format US$<amount>/yr with comma grouping. "
                "Prefer values already present in the report when they are plausible and compliant; "
                "ignore local-currency, monthly, range, source-title, benchmark and malformed values.\n\n"
                "Configured entities:\n"
                f"{json.dumps(entities_for_sections, ensure_ascii=True)}\n\n"
                "Controls:\n"
                f"{json.dumps(controls_for_prompt, ensure_ascii=True, sort_keys=True)}\n\n"
                "Current salary-bearing lines:\n"
                f"{_salary_context(doc)}\n\n"
                "Current quality defects:\n- "
                + "\n- ".join(issues[:60])
                + "\n\n"
                "Return ONLY a JSON object mapping every configured entity name to its chosen token."
            )
            try:
                raw = await self._dispatch_subexpert(
                    gen_id,
                    prompt,
                    {"temperature": 0.0, "max_tokens": max(900, 80 * len(entities_for_sections))},
                )
            except Exception as exc:
                logger.warning("salary/content repair salary-plan generation failed: %s", exc)
                return {}
            text = clean_final_content(raw if isinstance(raw, str) else str(raw)).strip()
            obj = _first_json_object(text) or {}
            if isinstance(obj.get("salaries"), dict):
                obj = obj["salaries"]
            elif isinstance(obj.get("canonical_salaries"), dict):
                obj = obj["canonical_salaries"]
            if not isinstance(obj, dict):
                return {}
            plan = _valid_canonical_salary_plan(obj)
            if plan:
                logger.info(
                    "salary/content repair: generator supplied canonical salary plan for %s of %s configured entities",
                    len(plan),
                    len(entities_for_sections),
                )
            return plan

        current = content
        current_issues = _combined_quality_issues(current)
        if not current_issues:
            return current
        try:
            max_attempts = int(salary_control.get("repair_attempts") or 3)
        except Exception:
            max_attempts = 3
        max_attempts = max(1, min(14, max_attempts))

        table_re = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|){2,}\s*$", re.M)
        original_table_count = len(table_re.findall(current))
        seen: set[str] = set()
        controls_json = json.dumps(salary_control, ensure_ascii=True, sort_keys=True)
        table_salary_plan = _canonical_table_salaries(current)
        model_salary_plan: Dict[str, str] = {}
        if _salary_plan_needed(current_issues, table_salary_plan):
            model_salary_plan = await _model_canonical_salary_plan(current, current_issues)
        attempts_used = 0
        while attempts_used < max_attempts:
            if not current_issues:
                break
            progress = False
            salary_context = _salary_context(current)
            canonical_salaries = _canonical_table_salaries(current)
            if model_salary_plan:
                canonical_salaries.update(model_salary_plan)
            canonical_context = json.dumps(canonical_salaries, ensure_ascii=True, sort_keys=True) if canonical_salaries else "{}"
            blocks = []
            for start, end, heading, block in _markdown_blocks(current):
                block_issues = _block_quality_issues(block)
                block_content_defects = [issue for issue in block_issues if not issue.startswith("salary_consistency:")]
                block_salary_defects = [issue for issue in block_issues if issue.startswith("salary_consistency:")]
                noncanonical_hits = 0
                for entity_name, canonical in canonical_salaries.items():
                    if not re.search(r"\b" + re.escape(entity_name) + r"\b", block, re.I):
                        continue
                    for match in token_re.finditer(block):
                        token = _normalised_salary_token(match.group(0))
                        if token and token != canonical:
                            noncanonical_hits += 1
                has_salary = bool(re.search(r"(?<![A-Za-z])(?:US\$|USD\s*\$?|\$)\s*[0-9]", block, re.I))
                entity_mentions = sum(
                    1
                    for entity in salary_control.get("entities", []) if isinstance(entity, dict)
                    if str(entity.get("name") or "").strip()
                    and re.search(r"\b" + re.escape(str(entity.get("name")).strip()) + r"\b", block, re.I)
                )
                if block_issues or has_salary or entity_mentions:
                    defect_score = len(block_content_defects) + len(block_salary_defects) + noncanonical_hits
                    blocks.append(
                        (
                            start,
                            end,
                            heading,
                            block,
                            defect_score,
                            len(block_content_defects),
                            len(block_salary_defects),
                            noncanonical_hits,
                            has_salary,
                            entity_mentions,
                            block_issues,
                        )
                    )
            blocks.sort(key=lambda item: (-int(bool(item[5])), -item[5], -item[4], -item[6], -item[7], -int(item[8]), -item[9], len(item[3])))
            if not blocks:
                break
            for start, end, heading, block, _, _, _, _, _, _, block_issues in blocks:
                if attempts_used >= max_attempts:
                    break
                attempts_used += 1
                block_issue_text = "\n- ".join(block_issues) if block_issues else "(no isolated block defects; reduce the listed full-report defects visible in this fragment)"
                prompt = (
                    f'The report "{title}" failed a generic publication quality gate.\n'
                    "Return the SAME Markdown block or fragment with ONLY the listed salary/citation defects "
                    "corrected. Preserve every heading level, section order, non-salary claim, "
                    "table, citation number, link target, figure marker and recommendation unless "
                    "a listed defect forces a minimal edit inside this block or fragment.\n\n"
                    "Profile controls (data supplied by the run, not fixed code values):\n"
                    f"{controls_json}\n\n"
                    "Canonical annual salary tokens extracted from the current report table:\n"
                    f"{canonical_context}\n\n"
                    "Required correction behavior:\n"
                    "- The ranking table is the canonical salary table when it is present.\n"
                    "- If a canonical salary plan is supplied above, update the ranking table "
                    "salary column and every entity salary line to that plan.\n"
                    "- Use exactly one canonical annual US-dollar salary token per configured entity.\n"
                    "- Every visible salary token for the same entity must match byte-for-byte.\n"
                    "- Under each entity subsection, keep one line named Annual USD salary: followed "
                    "by that entity's canonical token.\n"
                    "- Outside the ranking table and each entity's Annual USD salary line, remove "
                    "salary numbers and write 'the annual salary above' or 'salary cost'.\n"
                    "- Remove local-currency, monthly, range, alternate-conversion, national-benchmark "
                    "and source-title pay figures from prose and labels; keep citation links.\n"
                    "- Delete '[n/a]' and empty citation brackets; keep the underlying figure or claim.\n"
                    "- Do not invent, add, remove or substitute configured entities.\n\n"
                    "Current full-report salary-bearing lines, for consistency only:\n"
                    f"{salary_context}\n\n"
                    "Defects visible in this block or fragment:\n- "
                    f"{block_issue_text}\n\n"
                    "Current full-report defects to reduce:\n- " + "\n- ".join(current_issues) + "\n\n"
                    f"BLOCK OR FRAGMENT TO CORRECT ({heading}):\n{block}\n\n"
                    "Output ONLY the corrected Markdown block or fragment."
                )
                try:
                    raw = await self._dispatch_subexpert(
                        gen_id,
                        prompt,
                        {
                            "temperature": 0.1,
                            "max_tokens": max(900, min(3600, (len(block) // 3) + 700)),
                        },
                    )
                except Exception as exc:
                    logger.warning(
                        "salary/content repair attempt %s failed for block %r: %s",
                        attempts_used,
                        heading,
                        exc,
                    )
                    continue
                fixed_block = clean_final_content(raw if isinstance(raw, str) else str(raw)).strip()
                if not fixed_block:
                    continue
                candidate = current[:start] + fixed_block.rstrip() + "\n\n" + current[end:].lstrip("\n")
                candidate_key = re.sub(r"\s+", " ", candidate).strip()
                if candidate_key in seen:
                    logger.warning(
                        "publish_document: repeated salary/content repair output for block %r",
                        heading,
                    )
                    continue
                seen.add(candidate_key)
                candidate_issues = _combined_quality_issues(candidate)
                if len(table_re.findall(candidate)) >= original_table_count and (
                    len(candidate_issues) < len(current_issues)
                ):
                    current = candidate
                    current_issues = candidate_issues
                    progress = True
                    logger.info(
                        "publish_document: salary/content repair reduced defects to %s",
                        len(current_issues),
                    )
                    break
            if not progress:
                logger.warning(
                    "publish_document: stopping non-improving salary/content repair "
                    "after %s attempt(s)",
                    attempts_used,
                )
                break
        return current

    async def _publish_document(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic delivery tail collapsed into ONE reliable tool call so the
        agent cannot drift/terminate before delivering: quality-check -> render to
        HTML -> write the Markdown to storage -> email the FULL HTML document
        (content_style:html, format_mode:passthrough). Returns a small result."""
        content = args.get("content") or args.get("document") or ""
        if not isinstance(content, str):
            content = json.dumps(content, default=str)
        # An agentic report is an immutable model-authored artifact.  The
        # runtime may validate, render, store and deliver it, but it must never
        # even apply the generic final-content cleaner: that would make code a
        # post-generation editor.  AgentLLMAdapter already removes private
        # reasoning before accepting a Markdown completion.  Legacy products
        # retain their established boundary cleaner.
        if not self._agentic_document_required:
            content = clean_final_content(content)
        logger.info(f"publish_document: START ({len(content)} chars content)")  # W28M-1633 delivery-tail trace
        # Guarantee a real, clickable '## Sources' section: small models often hallucinate
        # generic/placeholder URLs (example.com, ...). Replace any trailing Sources block with
        # the actual links captured by web_research so the document always carries real links;
        # if research returned nothing, at least strip the hallucinated placeholders.
        # The run specification owns its quality contract. A ReAct model may
        # intentionally keep a delivery call small, so omitted tool arguments
        # inherit the configured contract rather than reopening repair paths.
        quality_controls = (
            args.get("quality_controls")
            if isinstance(args.get("quality_controls"), dict)
            else self._default_quality_controls
        )
        model_authored_sources = _model_authored_sources_required(quality_controls)
        repair_allowed = _deterministic_content_repair_allowed(quality_controls)
        sources_md = args.get("sources") or self._research_sources_md
        if sources_md and not model_authored_sources:
            if not repair_allowed:
                raise RuntimeError(
                    "MODEL_AUTHORED_SOURCES_REQUIRED: refusing deterministic Sources injection"
                )
            content = _merge_canonical_sources(content, sources_md)
        elif re.search(r"example\.(com|org|net)|//(www\.)?example\b|placeholder", content, re.IGNORECASE):
            if not repair_allowed:
                raise RuntimeError(
                    "MODEL_AUTHORED_CONTENT_REQUIRED: refusing deterministic placeholder repair"
                )
            content = _strip_trailing_sources(content)
        # Reasoning models habitually open with stale "As of <past-year>" framing even when the
        # cited sources are current. Deterministically refresh the document's OWN temporal framing
        # to the run date so the brief reads as current (factual year references are untouched).
        if repair_allowed:
            content = _freshen_as_of(content, args.get("current_year"))
        # Standalone emphasis markers are a common small-model tail artifact.
        # They render as literal ``***`` in the email/PDF rather than useful
        # content, so remove them before the quality gate and delivery.
        if repair_allowed:
            content = re.sub(r"(?m)^[ \t]*\*{3,}[ \t]*$", "", content)
        # Fall back to the run's configured delivery spec when the model omits these from the
        # tool call — guarantees the document is emailed to the recipients and written to the
        # path even if the agent drifts (the cause of docs landing on Drive but not in inboxes).
        title = str(args.get("title") or self._default_title or "Research Document")
        if not re.search(r"20\d{2}", title):  # date-stamp the email subject too
            import datetime as _dt
            _t = _dt.date.today()
            title = "%s — %d %s %d" % (title, _t.day, _t.strftime("%B"), _t.year)
        destinations = args.get("destinations") or self._default_destinations or []
        working_path = args.get("working_path") or self._default_working_path
        profile = args.get("profile") or self._default_profile or "google_drive"
        _validate_direct_recipient_uniqueness(destinations, quality_controls)

        # Visual and archive-link evidence is part of the output gate, so collect it before
        # rendering or any storage/delivery side effect occurs.
        inline_images = args.get("inline_images") or []
        figures = args.get("figures") or []
        inline_images, figures = _dedupe_visual_payloads(
            [image for image in inline_images if isinstance(image, dict)],
            [figure for figure in figures if isinstance(figure, dict)],
        )
        previous_reports = args.get("previous_reports") or []
        if repair_allowed:
            content = _repair_required_front_matter(content, quality_controls)
            content = _repair_single_table_deficit(
                content, quality_controls, inline_images
            )
            content = await self._rewrite_salary_consistency_defects(
                content,
                quality_controls,
                title=title,
            )

        logger.info("publish_document: before render_markdown")  # W28M-1633 delivery-tail trace
        # W28M-1636: pass the spec's optional `brand` block through so the markdown renderer can
        # apply the Transparent Borders visual brand. Absent/empty -> byte-identical legacy output.
        html = self._render_markdown(
            {"content": content, "brand": args.get("brand") or self._default_brand}
        )
        logger.info(f"publish_document: markdown rendered ({len(html)} html chars)")  # W28M-1633 delivery-tail trace

        # Additive visuals: inject inline-CID figures (maps/charts) at their headings and append
        # a "Further Detail & Previous Reports" links section. All optional — absent => unchanged.
        if figures or previous_reports:
            from src.core.execution import visuals as _visuals
            if previous_reports:
                prev_html = _visuals.previous_reports_html(previous_reports)
                if prev_html:
                    html = _visuals.inject_before_sources(html, prev_html)
            if figures:
                logger.info(f"publish_document: injecting {len(figures)} figures")  # W28M-1633 delivery-tail trace
                html = _visuals.inject_figures(html, figures)

        logger.info("publish_document: before quality_gate")  # W28M-1650 pre-side-effect gate trace
        qg = self._quality_gate({
            "content": content, "html_content": html, "current_year": args.get("current_year"),
            "min_words": args.get("min_words", 600), "min_sections": args.get("min_sections", 1),
            "inline_images": inline_images, "figures": figures,
            "previous_reports": previous_reports, "quality_controls": quality_controls,
            "quality_self_assessment": args.get("quality_self_assessment")})
        block_on_failure = quality_controls.get(
            "block_delivery_on_failure", bool(quality_controls)
        )
        if block_on_failure and not qg["pass"]:
            logger.error("publish_document: %s", qg["marker"])
            raise RuntimeError(qg["marker"] + " " + "; ".join(qg["issues"]))

        deferred_artifacts = [
            artifact for artifact in (args.get("pre_publish_artifacts") or [])
            if isinstance(artifact, dict)
        ]
        persisted_artifacts: List[Dict[str, str]] = []
        for artifact in deferred_artifacts:
            path = str(artifact.get("path") or "").strip()
            artifact_profile = str(artifact.get("profile") or profile).strip()
            artifact_content = artifact.get("content")
            label = str(artifact.get("label") or "model-authored artifact").strip()
            if not path or not isinstance(artifact_content, str):
                raise RuntimeError(
                    "MODEL_AUTHORED_ARTIFACT_INVALID: accepted artifact needs a path and exact text content"
                )
            write_service = self._svc_for("write_file", "filemcpserver0")
            write_args = {
                "profile": artifact_profile,
                "path": path,
                "content": artifact_content,
                "overwrite": True,
            }
            persisted = await self._dispatch_service(write_service, "write_file", write_args)
            self._record_service_invocation(write_service, "write_file", write_args, persisted)
            write_error = self._file_mcp_result_error(persisted)
            if write_error:
                raise RuntimeError(f"MODEL_AUTHORED_ARTIFACT_PERSIST_FAILED: {label}: {write_error[:300]}")
            read_service = self._svc_for("read_file", "filemcpserver0")
            read_args = {"profile": artifact_profile, "path": path}
            reloaded = await self._dispatch_service(read_service, "read_file", read_args)
            self._record_service_invocation(read_service, "read_file", read_args, reloaded)
            if self._file_text(reloaded) != artifact_content:
                raise RuntimeError(
                    f"MODEL_AUTHORED_ARTIFACT_INTEGRITY_FAILED: {label} FileMCP reload differed"
                )
            await self._mirror_file_mcp_artifact(
                source_profile=artifact_profile,
                source_path=path,
                content=artifact_content,
            )
            persisted_artifacts.append({"label": label, "path": path})

        logger.info(f"publish_document: visuals injected; before write_file (working_path={bool(working_path)})")  # W28M-1633
        written = None
        if working_path:
            write_args = {"profile": profile, "path": working_path, "content": content, "overwrite": True}
            write_service = self._svc_for("write_file", "filemcpserver0")
            try:
                written = await self._dispatch_service(write_service, "write_file", write_args)
                self._record_service_invocation(write_service, "write_file", write_args, written)
                write_error = self._file_mcp_result_error(written)
                if write_error:
                    raise RuntimeError(write_error)
                # A configured mirror is a cross-workspace storage contract:
                # read the primary value and the mirror before delivery.  Leave
                # products without that contract on their established write-only
                # path; this lane never enables a mirror without the readback.
                if self._file_mcp_mirrors_for(
                    source_profile=profile, source_path=working_path
                ):
                    read_service = self._svc_for("read_file", "filemcpserver0")
                    read_args = {"profile": profile, "path": working_path}
                    reloaded = await self._dispatch_service(read_service, "read_file", read_args)
                    self._record_service_invocation(read_service, "read_file", read_args, reloaded)
                    if self._file_text(reloaded) != content:
                        raise RuntimeError("FileMCP final-artifact readback differed from model-authored content")
                    await self._mirror_file_mcp_artifact(
                        source_profile=profile,
                        source_path=working_path,
                        content=content,
                    )
            except Exception as exc:
                written = {"error": str(exc)[:200]}
        if quality_controls.get("storage_required"):
            if not working_path:
                raise RuntimeError("FILEMCP_STORAGE_REQUIRED: working_path is required before delivery")
            if not written or (isinstance(written, dict) and written.get("error")):
                detail = (
                    str(written.get("error"))[:200]
                    if isinstance(written, dict) and written.get("error")
                    else "write_file failed before delivery"
                )
                raise RuntimeError(f"FILEMCP_STORAGE_REQUIRED: {detail}")

        # default each destination to full-HTML passthrough so the inbox shows the
        # whole document, not an LLM summary/link.
        dests = []
        for d in destinations:
            if isinstance(d, dict):
                d = dict(d)
                d.setdefault("preferences", {"content_style": "html", "format_mode": "passthrough"})
                dests.append(d)
        # Idempotency must collapse an exact retry while allowing a genuinely regenerated
        # same-day edition to be delivered. A title/day-only key silently reuses the first
        # message after a quality fix, leaving the stale body in the archive. Scope the
        # default key to the rendered payload hash: identical retry => same key; changed
        # report or figures => fresh message.
        import datetime as _dt_idem
        import hashlib as _hashlib_idem
        _idem_payload = json.dumps(
            {"html": html, "inline_images": inline_images},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        _idem_digest = _hashlib_idem.sha256(_idem_payload.encode("utf-8")).hexdigest()
        _idem_default = "%s|%s|%s" % (
            title,
            _dt_idem.date.today().isoformat(),
            _idem_digest,
        )
        notif_args: Dict[str, Any] = {
            "destinations": dests, "subject": title,
            "content": [{"type": "html", "body": html}],
            "idempotency_key": str(args.get("idempotency_key") or _idem_default)}
        # Forward inline CID images so embedded <img src="cid:..."> figures resolve in the
        # inbox (the notification-agent now supports a top-level inline_images field).
        if inline_images:
            notif_args["inline_images"] = inline_images
        logger.info(f"publish_document: write_file done; before send_notification ({len(dests)} dests, {len(inline_images)} inline_images)")  # W28M-1633 delivery-tail trace
        notification_service = self._svc_for("send_notification", "notificationagent0")
        sent = await self._dispatch_service(notification_service, "send_notification", notif_args)
        self._record_service_invocation(notification_service, "send_notification", notif_args, sent)
        logger.info("publish_document: send_notification returned")  # W28M-1633 delivery-tail trace
        # Unwrap the MCP result envelope so the delivered message_id/status surface (the raw
        # dispatch result is a content/SSE envelope, not a flat dict) — this is what lets a
        # chat-launched report return its /messages/<id> web-view link.
        _sent = _mcp_payload(sent)
        return {"delivered": not (isinstance(_sent, dict) and _sent.get("error")),
                "quality": qg, "written": bool(written) and not (isinstance(written, dict) and written.get("error")),
                "figures": len(inline_images),
                "persisted_model_artifacts": persisted_artifacts,
                "notification": _sent if not isinstance(_sent, dict) else {k: _sent.get(k) for k in ("message_id", "status", "id") if k in _sent}}

    @staticmethod
    def _quality_gate(args: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic output quality check. Returns {pass, issues, metrics} so the
        agent can revise before delivery. Catches the common defects: stale dates,
        thin/summary content, missing sections, missing grounding, wrong language and
        missing client-ready visuals. Strict controls are opt-in and data-driven."""
        content = args.get("content") or ""
        if not isinstance(content, str):
            content = json.dumps(content, default=str)
        html_content = args.get("html_content") or args.get("rendered_html") or ""
        if not isinstance(html_content, str):
            html_content = json.dumps(html_content, default=str)
        controls = args.get("quality_controls") if isinstance(args.get("quality_controls"), dict) else {}
        import html as _html
        html_visible_text = _html.unescape(re.sub(r"<[^>]+>", " ", html_content))
        combined_visible_text = re.sub(
            r"\s+",
            " ",
            "\n".join(part for part in (content, html_content, html_visible_text) if part),
        ).strip()
        current_year = int(args.get("current_year") or 0)
        min_words = int(args.get("min_words") or 300)
        min_sections = int(args.get("min_sections") or 1)
        issues: List[str] = []
        words = len(re.findall(r"\w+", content))
        sections = content.count("\n## ") + (1 if content.lstrip().startswith("## ") else 0)
        years = [int(y) for y in re.findall(r"\b(20[12][0-9])\b", content)]
        table_count = len(re.findall(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|){2,}\s*$", content, re.MULTILINE))
        has_table = table_count > 0
        raw_links = _markdown_link_urls(content) + _bare_url_urls(content)
        links = list(dict.fromkeys(link.rstrip(".,;:") for link in raw_links))
        external_links = [
            link for link in links
            if not re.search(r"(?i)://(?:localhost|127\.0\.0\.1|[^/]*\.cloud-dog\.net)(?:[/:]|$)", link)
            and not re.search(r"(?i)://(?:www\.)?example\.(?:com|org|net)(?:[/:]|$)", link)
        ]
        required_classification = str(controls.get("required_classification") or "").strip()
        required_classification_present = (
            bool(required_classification)
            and required_classification in combined_visible_text
        )
        required_reporting_period = str(controls.get("required_reporting_period") or "").strip()
        required_reporting_period_present = (
            bool(required_reporting_period)
            and required_reporting_period in combined_visible_text
        )
        as_at_reporting_period_required = bool(
            controls.get("as_at_reporting_period_required")
            or required_reporting_period.lower().startswith("as at")
        )
        as_of_framing_hits = (
            _as_of_temporal_framing_hits(_strip_trailing_sources(content))
            if as_at_reporting_period_required else []
        )
        allowed_external_source_urls_raw = (
            controls.get("allowed_external_source_urls")
            or controls.get("governed_external_source_urls")
            or controls.get("governed_source_urls")
            or []
        )
        if isinstance(allowed_external_source_urls_raw, dict):
            allowed_external_source_urls_raw = list(allowed_external_source_urls_raw.values())
        elif isinstance(allowed_external_source_urls_raw, str):
            allowed_external_source_urls_raw = [
                item.strip()
                for item in re.split(r"[\n,]", allowed_external_source_urls_raw)
                if item.strip()
            ]
        allowed_external_source_urls = sorted({
            _public_url(url).rstrip("/")
            for url in allowed_external_source_urls_raw
            if _public_url(url)
        })
        external_links_restricted_to_allowed_sources = bool(
            controls.get("external_links_restricted_to_allowed_sources")
            or controls.get("source_urls_restricted_to_governed_register")
        )
        undeclared_external_source_urls: List[str] = []
        if external_links_restricted_to_allowed_sources:
            allowed_url_set = set(allowed_external_source_urls)
            undeclared_external_source_urls = [
                link for link in external_links
                if _public_url(link).rstrip("/") not in allowed_url_set
            ]
        # Research-input validation is not sufficient: the document model can add or
        # alter URLs while composing the final report.  Revalidate every URL in the
        # final document immediately before any write/delivery side effect.  Strict
        # production profiles already declare ``block_delivery_on_failure``; make
        # that declaration fail closed on dead/restricted final links as well.
        live_link_validation = bool(
            controls.get(
                "live_external_links_required",
                controls.get("block_delivery_on_failure", False),
            )
        )
        live_link_timeout = max(
            2,
            min(
                int(
                    controls.get("external_link_timeout")
                    or controls.get("link_timeout")
                    or 12
                ),
                30,
            ),
        )
        failed_live_links = 0
        failed_live_link_urls: List[str] = []
        if live_link_validation and external_links:
            public_access_required = bool(
                controls.get("external_links_publicly_accessible_required")
            )
            live_results = (
                [
                    _external_url_retrievable(
                        link,
                        live_link_timeout,
                        require_public_access=True,
                    )
                    for link in external_links
                ]
                if public_access_required
                else [
                    _external_url_retrievable(link, live_link_timeout)
                    for link in external_links
                ]
            )
            failed_live_link_urls = [
                link for link, result in zip(external_links, live_results) if not result
            ]
            failed_live_links = len(failed_live_link_urls)
        inline_images = [image for image in (args.get("inline_images") or []) if isinstance(image, dict)]
        inline_content_ids = [
            str(image.get("content_id") or image.get("cid") or "").strip().strip("<>")
            for image in inline_images
        ]
        blank_content_ids = sum(not content_id for content_id in inline_content_ids)
        duplicate_content_ids = sorted({
            content_id for content_id in inline_content_ids
            if content_id and inline_content_ids.count(content_id) > 1
        })
        figure_ids = {str(figure.get("content_id") or "") for figure in (args.get("figures") or []) if isinstance(figure, dict)}
        previous_reports = [item for item in (args.get("previous_reports") or []) if isinstance(item, dict) and item.get("url")]
        unresolved_placeholders = sorted(set(re.findall(
            r"(?i)\{\{(?:run\.[a-z0-9_.:-]+|schedule_run_id|schedule_id)\}\}|"
            r"\{(?:run_date|current_date|report_date|date)\}|"
            r"\$(?:RUN_DATE|CURRENT_DATE|REPORT_DATE)\b",
            content,
        )))
        sources_match = re.search(
            r"(?ims)^##\s+(?:numbered\s+)?(?:sources|references)(?:\s+(?:and|&)\s+methodology)?\s*$",
            content,
        )
        sources_tail = content[sources_match.end():] if sources_match else ""
        numbered_sources = re.findall(r"(?m)^\s*(?:\[\d+\]|\d+[.)])\s+.*https?://", sources_tail)
        source_family_metrics = _configured_required_source_family_metrics(
            sources_tail, controls
        )
        reporting_period_declaration = re.search(
            r"(?im)^\s*(?:[*_`]+\s*)?reporting period\s*:\s*([^\n]+)",
            content,
        )
        reporting_period_value = (
            reporting_period_declaration.group(1).strip()
            if reporting_period_declaration
            else ""
        )
        concrete_source_cutoff_present = bool(
            re.search(r"(?i)\bsource\s+cut-?off\b", reporting_period_value)
            and re.search(
                r"\b20\d{2}(?:-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?Z?)?|\d{4}T\d{6}Z)\b",
                reporting_period_value,
            )
        )
        # Input-scoped products can name their exact section framework.  Counting headings
        # alone is not enough: a model can return sixteen arbitrary headings while omitting a
        # decision-critical one.  This is validation only; it never inserts or rewrites prose.
        required_section_titles = [
            str(title).strip()
            for title in (controls.get("required_section_titles") or [])
            if str(title).strip()
        ]
        heading_titles = [
            re.sub(r"\s+", " ", title).strip()
            for title in re.findall(r"(?m)^##\s+([^\n#]+?)\s*$", content)
        ]
        if required_section_titles:
            normalized_required_titles = [
                re.sub(r"\s+", " ", title).strip()
                for title in required_section_titles
            ]
            missing_section_titles = [
                title for title in normalized_required_titles if title not in heading_titles
            ]
            duplicate_section_titles = [
                title for title in normalized_required_titles if heading_titles.count(title) != 1
            ]
            ordered_titles = [title for title in heading_titles if title in normalized_required_titles]
            if missing_section_titles:
                issues.append(
                    "required_sections: missing exact heading(s): "
                    + "; ".join(missing_section_titles)
                )
            if duplicate_section_titles:
                issues.append(
                    "required_sections: heading must appear exactly once: "
                    + "; ".join(sorted(set(duplicate_section_titles)))
                )
            if not missing_section_titles and ordered_titles != normalized_required_titles:
                issues.append("required_sections: exact headings are not in the configured order")
        # A section-level product framework can set an upper word bound for a
        # reader-critical section such as a concise BLUF.  This is a
        # validation-only control: a failed agentic draft is returned to the
        # model for complete re-authoring; runtime code never trims or rewrites
        # prose.  Keys are exact H2 titles so the mechanism is reusable across
        # products without embedding a product name or content rule here.
        section_maximum_words = (
            controls.get("section_maximum_words")
            if isinstance(controls.get("section_maximum_words"), dict)
            else {}
        )
        section_word_counts: Dict[str, int] = {}
        for title, maximum in section_maximum_words.items():
            normalized_title = re.sub(r"\s+", " ", str(title)).strip()
            try:
                maximum_words = max(1, int(maximum))
            except (TypeError, ValueError):
                continue
            heading_match = re.search(
                r"(?ms)^##\s+" + re.escape(normalized_title) + r"\s*$\n?(.*?)(?=^##\s+|\Z)",
                content,
            )
            if not heading_match:
                continue
            actual_words = len(re.findall(r"\w+", heading_match.group(1)))
            section_word_counts[normalized_title] = actual_words
            if actual_words > maximum_words:
                issues.append(
                    "section_words: "
                    f"{normalized_title!r} has {actual_words} words; maximum is {maximum_words}"
                )
        repetition_metrics = _configured_repetition_metrics(content, controls)
        if repetition_metrics["duplicate_paragraphs"]:
            issues.append(
                "repetitive_prose: "
                f"{len(repetition_metrics['duplicate_paragraphs'])} repeated substantive paragraph(s) "
                "exceed the configured occurrence limit"
            )
        if repetition_metrics["repeated_ngrams"]:
            issues.append(
                "repetitive_prose: "
                f"{len(repetition_metrics['repeated_ngrams'])} repeated substantive phrase(s) "
                "exceed the configured occurrence limit"
            )
        section_quality_metrics = _configured_section_quality_metrics(
            content, controls, repetition_metrics
        )
        for failure in section_quality_metrics["failures"]:
            issues.append("section_quality: " + failure)
        model_quality_assessment = _model_authored_quality_assessment_metrics(
            args.get("quality_self_assessment"), controls
        )
        for failure in model_quality_assessment["failures"]:
            issues.append("quality_self_assessment: " + failure)
        # A numbered source register has to resolve the markers used in the narrative.  Treat
        # this as an optional strict product contract so ordinary documents remain unchanged.
        narrative_content = content[:sources_match.start()] if sources_match else content
        topic_coverage_metrics = _configured_required_topic_coverage_metrics(
            narrative_content, controls
        )
        inline_citation_numbers = {
            int(number) for number in re.findall(r"\[(\d+)\]", narrative_content)
        }
        source_citation_numbers = {
            int(number) for number in re.findall(
                r"(?m)^\s*\[(\d+)\]\s+.*https?://", sources_tail
            )
        }
        min_citation_markers = int(controls.get("minimum_citation_markers") or 0)
        if min_citation_markers and len(inline_citation_numbers) < min_citation_markers:
            issues.append(
                "citation_markers: "
                f"{len(inline_citation_numbers)} of {min_citation_markers} distinct inline markers required"
            )
        unresolved_citation_numbers = sorted(inline_citation_numbers - source_citation_numbers)
        if controls.get("citation_markers_resolve_required") and unresolved_citation_numbers:
            issues.append(
                "citation_markers: unresolved inline marker(s): "
                + ", ".join(f"[{number}]" for number in unresolved_citation_numbers)
            )
        unused_source_citation_numbers = sorted(source_citation_numbers - inline_citation_numbers)
        if controls.get("citation_markers_resolve_required") and unused_source_citation_numbers:
            issues.append(
                "citation_markers: listed source marker(s) not cited in the narrative: "
                + ", ".join(f"[{number}]" for number in unused_source_citation_numbers)
            )
        if controls.get("numeric_claim_citations_required"):
            numeric_blocks_without_citations = []
            for block in re.split(r"\n\s*\n", narrative_content):
                stripped_block = _narrative_text_from_markdown_block(block)
                if not stripped_block or stripped_block.startswith("|"):
                    continue
                # The reporting period is runtime metadata supplied by the
                # scheduler, not an externally sourced factual claim. It is
                # deliberately required as a standalone declaration and has
                # no citation marker to resolve.
                metadata_block = re.sub(r"[*_`]", "", stripped_block).strip()
                if re.match(r"(?i)^reporting period\s*:", metadata_block):
                    continue
                if _is_reporting_window_table_leadin(stripped_block):
                    continue
                if _is_relative_window_only_narrative(stripped_block):
                    continue
                if _block_has_citable_numeric_claim(stripped_block) and not re.search(r"\[\d+\]", stripped_block):
                    numeric_blocks_without_citations.append(stripped_block)
            if numeric_blocks_without_citations:
                issues.append(
                    "citation_markers: "
                    f"{len(numeric_blocks_without_citations)} numeric narrative block(s) lack an inline [n] citation"
                )
        # figures = concrete numbers that are NOT bare years (percentages, counts, money, etc.)
        figures = [n for n in re.findall(r"\d[\d,.]*%?", content) if not re.fullmatch(r"20[12][0-9]", n)]
        require_links = bool(args.get("require_links", True))
        min_figures = int(args.get("min_figures") or 3)
        if words < min_words:
            issues.append(f"too_thin: {words} words (< {min_words}); reads as a summary, not a full document")
        if sections < min_sections:
            issues.append(f"missing_sections: {sections} of {min_sections} expected")
        if require_links and not external_links:
            issues.append("no_links: the document has no source links — add a '## Sources' section of real links and cite [n]")
        if len(figures) < min_figures:
            issues.append(f"no_depth: only {len(figures)} concrete figures/numbers — add specific named facts, dates and statistics")
        if current_year:
            if current_year not in years:
                issues.append(f"not_current: the document never references the current year {current_year}")
            # an explicit "as of <past year>" framing is the specific defect the operator flagged
            for m in re.finditer(r"as of\s+(?:early|mid|late|the start of|end of)?\s*(20[12][0-9])", content, re.I):
                if int(m.group(1)) < current_year:
                    issues.append(f"stale_as_of: '{m.group(0)}' — must be reframed to {current_year}")
                    break
        min_external_links = int(controls.get("minimum_external_links") or 0)
        min_tables = int(controls.get("minimum_tables") or 0)
        min_images = int(controls.get("minimum_images") or 0)
        if required_classification and not required_classification_present:
            issues.append(
                "required_classification: exact required classification/framing line is missing"
            )
        if required_reporting_period and not required_reporting_period_present:
            issues.append(
                "reporting_period: exact required reporting period is missing"
            )
        if re.search(r"\{\{[^{}]+\}\}", required_reporting_period):
            issues.append(
                "reporting_period: configured reporting period contains an unresolved runtime token"
            )
        if controls.get("concrete_source_cutoff_required") and not concrete_source_cutoff_present:
            issues.append(
                "reporting_period: concrete dated source cut-off is missing from the reporting-period declaration"
            )
        if as_of_framing_hits:
            issues.append(
                "reporting_period: forbidden 'As of' temporal framing; use configured 'As at' wording"
            )
        if len(external_links) < min_external_links:
            issues.append(f"external_links: {len(external_links)} of {min_external_links} required direct external links")
        if external_links_restricted_to_allowed_sources and not allowed_external_source_urls:
            issues.append("external_links: governed source URL allowlist is empty")
        if undeclared_external_source_urls:
            issues.append(
                "external_links: final document URL(s) outside the governed source register: "
                + "; ".join(sorted(set(undeclared_external_source_urls)))
            )
        if failed_live_links:
            issues.append(
                "external_links: "
                f"{failed_live_links} final document link(s) failed live retrieval: "
                + "; ".join(failed_live_link_urls)
            )
        if table_count < min_tables:
            issues.append(f"tables: {table_count} of {min_tables} required structured tables")
        if len(inline_images) < min_images:
            issues.append(f"images: {len(inline_images)} of {min_images} required meaningful images")
        if blank_content_ids:
            issues.append(f"inline_images: {blank_content_ids} image(s) have no content ID")
        if duplicate_content_ids:
            issues.append(
                "inline_images: duplicate content IDs: " + ", ".join(duplicate_content_ids)
            )
        required_visual_classes = _configured_required_visual_classes(controls)
        figures_by_id = {
            str(figure.get("content_id") or "").strip(): figure
            for figure in (args.get("figures") or [])
            if isinstance(figure, dict) and str(figure.get("content_id") or "").strip()
        }
        images_by_id = {
            str(image.get("content_id") or image.get("cid") or "").strip().strip("<>"): image
            for image in inline_images
            if str(image.get("content_id") or image.get("cid") or "").strip().strip("<>")
        }
        rendered_visual_classes: Dict[str, int] = {}
        missing_visual_classes: List[str] = []
        for visual_class in required_visual_classes:
            matching_ids = []
            for content_id, figure in figures_by_id.items():
                image = images_by_id.get(content_id, {})
                observed_class = str(
                    figure.get("quality_class") or image.get("quality_class") or ""
                ).strip()
                source_urls = figure.get("source_urls") or image.get("source_urls") or []
                rendered_payload = bool(image) and bool(
                    image.get("data")
                    or image.get("content")
                    or image.get("bytes")
                    or image.get("base64")
                )
                rendered_in_html = bool(re.search(
                    r"(?i)<img[^>]+src=[\"']cid:" + re.escape(content_id) + r"(?:[\"'])",
                    html_content,
                ))
                rendered = rendered_payload and (
                    rendered_in_html if html_content else True
                )
                source_backed = isinstance(source_urls, list) and any(
                    isinstance(url, str) and url.startswith("https://") for url in source_urls
                )
                public_source_count = len([
                    url for url in source_urls
                    if isinstance(url, str) and url.startswith("https://")
                ]) if isinstance(source_urls, list) else 0
                required_metadata_present = all(
                    (
                        figure.get(field)
                        if figure.get(field) not in (None, "", [], {})
                        else image.get(field)
                    )
                    not in (None, "", [], {})
                    for field in visual_class["required_metadata_fields"]
                )
                if observed_class == visual_class["id"] and rendered and (
                    not visual_class["source_backed"] or source_backed
                ) and public_source_count >= visual_class["minimum_source_urls"] and required_metadata_present:
                    matching_ids.append(content_id)
            rendered_visual_classes[visual_class["id"]] = len(matching_ids)
            if len(matching_ids) < visual_class["minimum"]:
                suffix = " source-backed rendered" if visual_class["source_backed"] else " rendered"
                if visual_class["minimum_source_urls"]:
                    suffix += f" with >= {visual_class['minimum_source_urls']} source URLs"
                if visual_class["required_metadata_fields"]:
                    suffix += " and metadata " + ",".join(visual_class["required_metadata_fields"])
                missing_visual_classes.append(
                    f"{visual_class['id']} ({len(matching_ids)} of {visual_class['minimum']}{suffix})"
                )
        if missing_visual_classes:
            issues.append(
                "visual_classes: required visual class deficit: " + "; ".join(missing_visual_classes)
            )
        if controls.get("unresolved_placeholders_forbidden") and unresolved_placeholders:
            issues.append(
                "unresolved_placeholders: " + ", ".join(unresolved_placeholders)
            )
        forbidden_scan_content = content
        if html_content:
            forbidden_scan_content = content + "\n\n" + html_content
        forbidden_content_hits = []
        seen_forbidden_hits: set[tuple[str, str]] = set()
        for hit in _configured_forbidden_content_hits(forbidden_scan_content, controls):
            key = (str(hit.get("category") or ""), str(hit.get("term") or ""))
            if key in seen_forbidden_hits:
                continue
            seen_forbidden_hits.add(key)
            forbidden_content_hits.append(hit)
        for hit in forbidden_content_hits:
            issues.append(
                "forbidden_content: "
                f"{hit['category']} matched configured term {hit['term']!r}"
            )
        if controls.get("numbered_sources_required"):
            if not sources_match or len(numbered_sources) < min_external_links:
                issues.append(
                    f"numbered_sources: {len(numbered_sources)} numbered linked entries; "
                    f"at least {min_external_links} required in one final Sources section"
                )
            if re.search(r"\[[nN](?:\s*,\s*[nN])*\]", content):
                issues.append("numbered_sources: literal [n] citation placeholder remains")
        if source_family_metrics["failures"]:
            issues.append(
                "source_families: required final source-register family deficit: "
                + "; ".join(source_family_metrics["failures"])
            )
        if topic_coverage_metrics["failures"]:
            issues.append(
                "topic_coverage: required cited current-window topic deficit: "
                + "; ".join(topic_coverage_metrics["failures"])
            )
        if controls.get("executive_summary_required") and not re.search(
            r"(?im)^##\s+(?:executive summary|key judgements|in brief)(?:\s*(?:[-—:]|\()[^\n]*)?\s*$",
            content,
        ):
            issues.append("executive_summary: required section is missing")
        if controls.get("reporting_period_required") and not re.search(r"(?i)\breporting period\s*:", content):
            issues.append("reporting_period: required reporting-period declaration is missing")
        if controls.get("relationship_diagram_required") and "actor_relationships" not in figure_ids:
            issues.append("relationship_diagram: required rendered relationship diagram is missing")
        maximum_previous = controls.get("maximum_previous_report_links")
        if maximum_previous is not None and len(previous_reports) > int(maximum_previous):
            issues.append(f"previous_reports: {len(previous_reports)} exceeds maximum {int(maximum_previous)}")
        if str(controls.get("expected_language") or "").lower() == "en":
            alpha_tokens = re.findall(r"[A-Za-z]+", re.sub(r"https?://\S+", " ", content.lower()))
            english_markers = {"the", "and", "of", "to", "in", "for", "with", "that", "this", "from", "as", "by", "is", "are", "was", "were"}
            if len(alpha_tokens) >= 40 and len(english_markers.intersection(alpha_tokens)) < 5:
                issues.append("language: output does not satisfy the configured English-language gate")
        # W28M-1636 R4: fail-closed BLUF <-> ranking consistency. If the document carries a rank+hub
        # table and its bottom-line recommendation names hubs other than the ranking's top-2, the
        # report contradicts itself — block delivery (block_delivery_on_failure profiles). No-op when
        # there is no ranking table, so non-placement reports are unaffected.
        _bluf_ok, _bluf_ranking, _bluf_named = _bluf_ranking_status(content)
        if not _bluf_ok:
            issues.append(
                "bluf_ranking: bottom-line recommendation names "
                f"{[_bare_city(x) for x in _bluf_named]} but the ranking top-2 is "
                f"{[_bare_city(_bluf_ranking[0]), _bare_city(_bluf_ranking[1])]}"
            )
        # W28M-1636 R5: reject (fail-closed) any content defect the local agent must not emit —
        # [n/a]/empty citations, ellipsis-truncated labels, printed row SHA-256 digests, local-currency
        # salary figures, false "SQL not executed/pending" claims, invented SQL tables. The gate NEVER
        # repairs these; a defective report is blocked and the model re-authors the offending section.
        for _d in _report_content_defects(content, controls):
            issues.append("content_defect: " + _d)
        for _d in _salary_consistency_defects(content, controls):
            issues.append(_d)
        marker = f"QUALITY_GATE: {'PASS' if not issues else 'FAIL'} failures={len(issues)}"
        return {
            "pass": not issues,
            "issues": issues,
            "marker": marker,
            "metrics": {"words": words, "sections": sections, "years": sorted(set(years)),
                        "has_table": has_table, "tables": table_count,
                        "links": len(links), "external_links": len(external_links),
                        "live_external_links_checked": live_link_validation,
                        "failed_live_external_links": failed_live_links,
                        "failed_live_external_link_urls": failed_live_link_urls,
                        "required_classification": required_classification,
                        "required_classification_present": required_classification_present,
                        "required_reporting_period": required_reporting_period,
                        "required_reporting_period_present": required_reporting_period_present,
                        "reporting_period_declaration": reporting_period_value,
                        "concrete_source_cutoff_present": concrete_source_cutoff_present,
                        "as_at_reporting_period_required": as_at_reporting_period_required,
                        "as_of_framing_hits": as_of_framing_hits,
                        "allowed_external_source_urls": allowed_external_source_urls,
                        "undeclared_external_source_urls": undeclared_external_source_urls,
                        "forbidden_content_hits": forbidden_content_hits,
                        "forbidden_content_checked_html": bool(html_content),
                        "numbered_sources": len(numbered_sources), "images": len(inline_images),
                        "unique_image_content_ids": len(set(filter(None, inline_content_ids))),
                        "unresolved_placeholders": unresolved_placeholders,
                        "relationship_diagram": "actor_relationships" in figure_ids,
                        "previous_reports": len(previous_reports), "figures": len(figures),
                        "current_year": current_year,
                        "required_section_titles": required_section_titles,
                        "section_word_counts": section_word_counts,
                        "section_quality": section_quality_metrics,
                        "model_authored_quality_assessment": model_quality_assessment,
                        "repetition": repetition_metrics,
                        "required_visual_classes": required_visual_classes,
                        "rendered_visual_classes": rendered_visual_classes,
                        "inline_citation_markers": sorted(inline_citation_numbers),
                        "source_citation_markers": sorted(source_citation_numbers),
                        "unused_source_citation_markers": unused_source_citation_numbers,
                        "required_source_families": source_family_metrics,
                        "required_topic_coverage": topic_coverage_metrics},
        }

    @staticmethod
    def _render_markdown(args: Dict[str, Any]) -> str:
        """Render Markdown -> inline-styled HTML email body (tables, links, headings,
        lists, rules). Inline styles because Gmail/Outlook strip <style> blocks."""
        md = args.get("content") or args.get("markdown") or ""
        if not isinstance(md, str):
            md = json.dumps(md, default=str)
        # W28M-1636 R5 (coordinator agentic-boundary ruling): deterministic code MUST NOT author or
        # repair report/citation/provenance CONTENT. The earlier render-time strips ([n/a], fabricated
        # SHA/hash, ellipsis de-truncation, BLUF name-swap) are REMOVED. The local agent must author
        # clean content; any residual defect is caught FAIL-CLOSED by the quality gate (which rejects,
        # never transforms) so a defective report is never delivered. Only presentation styling
        # (table layout, headings, brand) is applied below — that renders content, it does not alter it.
        import html as _html
        S_TABLE = "border-collapse:collapse;margin:1.1em 0;width:100%;font-size:14px;font-family:Arial,Helvetica,sans-serif"
        S_TH = "border:1px solid #c9ced6;padding:6px 11px;text-align:left;vertical-align:top;background:#eef2f7;font-family:Arial,Helvetica,sans-serif"
        S_TD = "border:1px solid #c9ced6;padding:6px 11px;text-align:left;vertical-align:top"
        S_H = {1: "font-family:Arial,Helvetica,sans-serif;color:#10243f;margin:0 0 .3em",
               2: "font-family:Arial,Helvetica,sans-serif;color:#1a2330;border-bottom:1px solid #e3e7ee;padding-bottom:3px;margin:1.6em 0 .5em",
               3: "font-family:Arial,Helvetica,sans-serif;color:#2a3340;margin:1.2em 0 .4em",
               4: "font-family:Arial,Helvetica,sans-serif;color:#3a4350;margin:1.0em 0 .3em"}
        S_HR = "border:0;border-top:1px solid #d0d5dd;margin:1.8em 0"
        S_A = "color:#15569c"
        S_P = "margin:.7em 0"
        # --- OPTIONAL brand-styling hook (W28M-1636) -------------------------------------
        # When the report spec carries a NON-EMPTY `brand` block (e.g. the Transparent
        # Borders visual brand: palette / fonts / wordmark / tagline), override the hardcoded
        # inline styles above and prepend a brand header band. Fully BACKWARD-COMPATIBLE:
        # with no `brand` (or an empty one) every style constant, the body font and the
        # rendered output are byte-identical to the legacy path. Guard everything on `brand`.
        _brand_raw = args.get("brand")
        brand = _brand_raw if (isinstance(_brand_raw, dict) and _brand_raw) else None
        _body_font_css = "Georgia,serif"
        _brand_header = ""
        if brand:
            def _font_chain(fd: Any, fallback: str) -> str:
                """Build a CSS font-family chain from a brand font descriptor (family + fallbacks)."""
                if isinstance(fd, dict):
                    fam = str(fd.get("family") or "").strip()
                    fbs = [str(x).strip() for x in (fd.get("weasyprint_fallbacks") or []) if str(x).strip()]
                    chain = [f for f in ([fam] + fbs) if f]
                    if chain:
                        return ", ".join(chain)
                return fallback

            def _pal(name: str, default: str) -> str:
                """Resolve a palette colour hex by key ({name:{hex:..}} or {name:'#..'}), else default."""
                v = (brand.get("palette") or {}).get(name)
                if isinstance(v, dict):
                    v = v.get("hex")
                v = str(v).strip() if v else ""
                return v or default

            _fonts = brand.get("fonts") if isinstance(brand.get("fonts"), dict) else {}
            body_font = _font_chain(_fonts.get("body"), "Arial,Helvetica,sans-serif")
            display_font = _font_chain(_fonts.get("display"), body_font)
            dark_purple = str(brand.get("primary_dark") or "").strip() or _pal("dark_purple", "#150029")
            accent = str(brand.get("primary_accent") or "").strip() or _pal("aero_blue", "#1EC2DE")
            tint = _pal("ivory_white", "#F5F8E9")
            border_grey = _pal("border_grey", "#d7d2de")
            _body_font_css = body_font
            S_TABLE = f"border-collapse:collapse;margin:1.1em 0;width:100%;font-size:14px;font-family:{body_font}"
            S_TH = (f"border:1px solid {border_grey};padding:6px 11px;text-align:left;vertical-align:top;"
                    f"background:{tint};color:{dark_purple};font-family:{body_font};"
                    "-webkit-print-color-adjust:exact;print-color-adjust:exact")
            S_TD = f"border:1px solid {border_grey};padding:6px 11px;text-align:left;vertical-align:top"
            S_H = {1: f"font-family:{display_font};color:{dark_purple};margin:0 0 .3em",
                   2: (f"font-family:{display_font};color:{dark_purple};border-bottom:2px solid {accent};"
                       "padding-bottom:3px;margin:1.6em 0 .5em"),
                   3: f"font-family:{body_font};color:{dark_purple};margin:1.2em 0 .4em",
                   4: f"font-family:{body_font};color:{dark_purple};margin:1.0em 0 .3em"}
            S_A = f"color:{accent}"
            # Brand header band: wordmark (display font) over tagline (body font) on the dark fill.
            _wm = brand.get("wordmark")
            _wm_parts = None
            _wm_text = ""
            if isinstance(_wm, dict):
                _wm_parts = _wm.get("parts")
                _wm_text = str(_wm.get("text") or "")
            elif isinstance(_wm, str):
                _wm_text = _wm
            _wm_text = _wm_text or "Transparent Borders"
            if not _wm_parts:
                _sp = _wm_text.split()
                if len(_sp) >= 2:
                    _wm_parts = [_sp[0], " ".join(_sp[1:])]
            if _wm_parts and len(_wm_parts) >= 2:
                _thin = _html.escape(str(_wm_parts[0]), quote=True)
                _bold = _html.escape(" ".join(str(p) for p in _wm_parts[1:]), quote=True)
                _wordmark_html = (f'<span style="font-weight:300">{_thin}</span>'
                                  f'<span style="font-weight:800"> {_bold}</span>')
            else:
                _wordmark_html = f'<span style="font-weight:800">{_html.escape(_wm_text, quote=True)}</span>'
            _tagline = str(brand.get("tagline") or "").strip()
            _tagline_html = ""
            if _tagline:
                _tagline_html = (f'<div style="font-family:{body_font};font-size:13px;color:#e8e2f0;'
                                 f'margin-top:6px;letter-spacing:.02em">{_html.escape(_tagline, quote=True)}</div>')
            _brand_header = (
                f'<div style="background:{dark_purple};color:#ffffff;padding:22px 26px;margin:0 0 1.4em;'
                f'border-radius:0 0 6px 6px;-webkit-print-color-adjust:exact;print-color-adjust:exact">'
                f'<div style="font-family:{display_font};font-size:34px;line-height:1.05;'
                f'letter-spacing:.03em;color:#ffffff">{_wordmark_html}</div>'
                f'{_tagline_html}</div>\n'
            )

        def inline(t: str) -> str:
            """Render inline markdown links and emphasis as escaped HTML."""
            t = _html.escape(t, quote=False)
            t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", rf'<a href="\2" style="{S_A}">\1</a>', t)
            t = re.sub(r'(?<![">\w])(https?://[^\s<)\]]+)', rf'<a href="\1" style="{S_A}">\1</a>', t)
            t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
            t = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", t)
            return t

        out: List[str] = []
        toc: List[tuple] = []  # (level, slug, text) for h2/h3 -> Table of Contents
        _seen_slugs: dict = {}
        def _slug(t: str) -> str:
            """Create a stable, unique anchor slug for a heading."""
            base = re.sub(r"[^a-z0-9]+", "-", _html.unescape(t).lower()).strip("-")[:60] or "section"
            if base in _seen_slugs:
                _seen_slugs[base] += 1
                base = f"{base}-{_seen_slugs[base]}"
            else:
                _seen_slugs[base] = 0
            return base
        lines = md.split("\n")
        i, n = 0, len(lines)
        while i < n:
            ln = lines[i]
            mh = re.match(r"(#{1,4})\s+(.*)", ln)
            if mh:
                lvl = len(mh.group(1))
                _htext = mh.group(2)
                _anchor = ""
                # Anchor + collect h2/h3 for the Table of Contents (skip the Sources/References tail).
                if lvl in (2, 3) and not re.match(r"\s*(sources|references)\b", _htext, re.IGNORECASE):
                    _sl = _slug(_htext)
                    _anchor = f' id="{_sl}"'
                    toc.append((lvl, _sl, _htext))
                out.append(f"<h{lvl}{_anchor} style=\"{S_H.get(lvl, S_H[4])}\">{inline(_htext)}</h{lvl}>")
                i += 1
                continue
            if re.match(r"\s*\|.*\|\s*$", ln) and i + 1 < n and re.match(r"\s*\|?[\s:-]+\|[\s:|-]*$", lines[i + 1]):
                header = [c.strip() for c in ln.strip().strip("|").split("|")]
                i += 2
                rows = []
                while i < n and re.match(r"\s*\|.*\|\s*$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")])
                    i += 1
                # W28M-1636 R4 (acceptance A10, zero layout defect): a wide table — e.g. the 12-column
                # team-placement ranking — overflows the A4 page and clips its rightmost columns under
                # the default auto layout. For many-column tables, force table-layout:fixed with a
                # scaled-down font/padding and word wrapping so every column fits within the page width.
                _ncol = max(len(header), max((len(r) for r in rows), default=0))
                if _ncol >= 9:
                    _fs, _pad = "9px", "3px 4px"
                elif _ncol >= 7:
                    _fs, _pad = "11px", "4px 7px"
                else:
                    _fs, _pad = "", ""
                if _fs:
                    _wrap = f";font-size:{_fs};word-break:break-word;overflow-wrap:anywhere"
                    _t_style = re.sub(r"font-size:[^;]+", f"font-size:{_fs}", S_TABLE) + ";table-layout:fixed"
                    _th_style = re.sub(r"padding:[^;]+", f"padding:{_pad}", S_TH) + _wrap
                    _td_style = re.sub(r"padding:[^;]+", f"padding:{_pad}", S_TD) + _wrap
                else:
                    _t_style, _th_style, _td_style = S_TABLE, S_TH, S_TD
                th = "".join(f'<th style="{_th_style}">{inline(c)}</th>' for c in header)
                trs = "".join("<tr>" + "".join(f'<td style="{_td_style}">{inline(c)}</td>' for c in r) + "</tr>" for r in rows)
                out.append(f'<table style="{_t_style}"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>')
                continue
            if re.match(r"\s*[-*]\s+", ln):
                items = []
                while i < n and re.match(r"\s*[-*]\s+", lines[i]):
                    item_text = re.sub(r"^\s*[-*]\s+", "", lines[i])
                    items.append(f'<li style="{S_P}">{inline(item_text)}</li>')
                    i += 1
                out.append("<ul>" + "".join(items) + "</ul>")
                continue
            if re.match(r"\s*---+\s*$", ln):
                out.append(f'<hr style="{S_HR}">')
                i += 1
                continue
            if ln.strip():
                out.append(f'<p style="{S_P}">{inline(ln)}</p>')
            i += 1
        inner = "\n".join(out)
        # Table of Contents intentionally NOT rendered. For a 16-section country brief the TOC was
        # too long and its in-email anchor links do not navigate reliably across mail clients
        # ("the TOC doesn't work — too big — remove it"). Heading `id` anchors are still emitted
        # (harmless, enable deep-linking) but no TOC block is inserted. `toc` is retained above only
        # so the anchor slugs stay unique.
        _ = toc  # (kept for anchor-slug uniqueness; no TOC block emitted)
        return ("<!doctype html><html lang='en'><head><meta charset='utf-8'></head>"
                f"<body style=\"font-family:{_body_font_css};max-width:900px;margin:1.5em auto;"
                "line-height:1.55;color:#1a1a1a;padding:0 14px\">\n" + _brand_header + inner + "\n</body></html>")

    def _maybe_spill(self, raw: Any) -> Any:
        """Replace oversized tool output with an artifact reference."""
        text = raw if isinstance(raw, str) else json.dumps(raw, default=str)
        if len(text) > self._spill:
            ref = self._store.put(raw)
            preview = text[:200].replace("\n", " ")
            return {"ref": ref, "chars": len(text), "preview": preview}
        return raw


# --------------------------------------------------------------------------- #
# Tool / sub-expert descriptor assembly (DATA: expert.tools_json + bindings)
# --------------------------------------------------------------------------- #
def build_tool_descriptors(db: Any, expert: Any) -> List[Dict[str, Any]]:
    """Derive the action space from the expert's bound tools and sub-experts.

    Always includes the generic presentation/quality builtins (render_markdown,
    quality_gate) so any agent can render for email and self-check output quality."""
    descriptors: List[Dict[str, Any]] = [
        {"name": "web_research", "kind": "builtin",
         "description": "Search the web for CURRENT facts and return a citable source pack "
                        "(numbered grounding snippets with dates + figures, plus a ready-made "
                        "'## Sources' block of real links). args: {query, max_results}. Pass the "
                        "result to the Document Generator so the report has current detail, "
                        "numbers and links — and reproduce its '## Sources' block at the end."},
        {"name": "quality_gate", "kind": "builtin",
         "description": "Check a document for quality before delivery. args: {content (or art:N ref), "
                        "current_year, min_words, min_sections}. Returns {pass, issues, metrics}. "
                        "If pass is false, fix the issues (regenerate weak/stale sections) and re-check."},
        {"name": "render_markdown", "kind": "builtin",
         "description": "Render a Markdown document (content or art:N ref) to an inline-styled HTML email "
                        "body. Returns the HTML (as art:N). Use before send_notification so the full "
                        "document renders in the inbox."},
        {"name": "compose_report", "kind": "builtin",
         "description": "Build a LONG, deep, multi-page report by generating EVERY section in full, one "
                        "at a time (each ~target_words of evidence-rich prose with figures and tables). "
                        "args: {sections:[{title,brief,target_words}], title, target, target_words}. "
                        "Returns the assembled document (as art:N). USE THIS to produce the full report "
                        "after web_research, then pass its art:N to publish_document — it is what gives the "
                        "document real depth (a single generation is too shallow)."},
        {"name": "publish_document", "kind": "builtin",
         "description": "Quality-check, render to HTML, save, and EMAIL the full document in ONE step. "
                        "args: {content (the document, or art:N ref), title, current_year, min_sections, "
                        "working_path, destinations}. Returns {delivered, quality, written}. This is the "
                        "ONLY delivery step — call it once after the document is generated."},
    ]

    raw = getattr(expert, "tools_json", None)
    items: List[Any] = []
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, list):
                items = parsed
        except Exception:
            items = []
    for item in items:
        service = tool = desc = None
        if isinstance(item, str) and "." in item:
            service, tool = item.split(".", 1)
        elif isinstance(item, dict) and item.get("sub_expert_id") is not None:
            try:
                child_id = int(item["sub_expert_id"])
            except (TypeError, ValueError):
                continue
            descriptors.append(
                {
                    "name": str(item.get("name") or f"expert_{child_id}"),
                    "description": str(item.get("description") or "Delegate a sub-task to this expert.")[:200],
                    "kind": "subexpert",
                    "child_id": child_id,
                }
            )
            continue
        elif isinstance(item, dict) and item.get("service") and item.get("tool"):
            service, tool = item["service"], item["tool"]
            desc = item.get("description")
        if service and tool:
            descriptor = {
                "name": f"{service}.{tool}",
                "description": desc or f"Call {tool} on {service}.",
                "kind": "service",
                "service": service,
                "tool": tool,
            }
            if isinstance(item, dict):
                for key in (
                    "default_profile",
                    "default_collection",
                    "default_channel",
                    "collection_template",
                    "arguments",
                ):
                    if key in item:
                        descriptor[key] = item[key]
            descriptors.append(descriptor)

    try:
        from src.database.models import SubExpertBinding, ExpertConfig

        bindings = (
            db.query(SubExpertBinding)
            .filter(SubExpertBinding.parent_expert_id == int(expert.id), SubExpertBinding.enabled.is_(True))
            .all()
        )
        for b in bindings:
            child = db.query(ExpertConfig).filter(ExpertConfig.id == b.child_expert_id).first()
            if not child:
                continue
            descriptors.append(
                {
                    "name": (getattr(child, "title", None) or f"expert_{child.id}").strip(),
                    "description": (b.delegation_prompt or getattr(child, "description", None) or "Delegate a sub-task to this expert.")[:200],
                    "kind": "subexpert",
                    "child_id": int(child.id),
                }
            )
    except Exception as exc:
        logger.debug("sub-expert descriptor enumeration skipped: %s", exc)

    return descriptors


def _report_word_count(text: Any) -> int:
    """Count prose words for report-depth gates."""
    return len(re.findall(r"\b[\w'-]+\b", str(text or "")))


def _looks_like_thin_report_placeholder(text: str) -> bool:
    """Detect agent stop messages that describe report generation instead of returning it."""
    lowered = str(text or "").lower()
    return any(
        phrase in lowered
        for phrase in (
            "compose_report has been initiated",
            "report generation will continue",
            "next step is to ensure",
            "cannot be completed due to a missing",
            "no document-generator sub-expert",
            "missing dependency",
        )
    )


def _normalise_report_sections(params: Dict[str, Any], min_words: int) -> List[Dict[str, Any]]:
    """Build a section list for explicit long-report recovery."""
    raw = params.get("report_sections") or params.get("sections") or []
    sections: List[Dict[str, Any]] = []
    if isinstance(raw, list):
        for i, item in enumerate(raw, 1):
            if isinstance(item, dict):
                title = str(item.get("title") or f"Section {i}").strip()
                brief = str(item.get("brief") or "").strip()
                target_words = item.get("target_words")
            else:
                title = str(item or f"Section {i}").strip()
                brief = ""
                target_words = None
            if title:
                sections.append({"title": title, "brief": brief, "target_words": target_words})
    if not sections:
        sections = [
            {
                "title": "BLUF and Priority Judgements",
                "brief": "Summarise the bottom-line intelligence judgements and confidence levels.",
            },
            {
                "title": "Retrieved Evidence and Theatre Assessment",
                "brief": "Analyse the retrieved corpus passages and cite source_id/chunk_id evidence inline.",
            },
            {
                "title": "Risks, Indicators, and Collection Gaps",
                "brief": "Set out risks, observable indicators, and gaps for further collection.",
            },
        ]
    default_target = _as_int(params.get("target_words"), max(650, (max(min_words, 1) // max(len(sections), 1)) + 150))
    for section in sections:
        section["target_words"] = _as_int(section.get("target_words"), default_target)
    return sections


async def _recover_thin_report_if_requested(
    *,
    content: str,
    tool_adapter: AgentToolAdapter,
    params: Dict[str, Any],
    input_text: str,
) -> tuple[str, Optional[Dict[str, Any]]]:
    """For explicit long-report runs, replace thin RLM placeholders with a composed report."""
    min_words = _as_int(params.get("min_words"), 0)
    if min_words <= 0:
        return content, None
    original_words = _report_word_count(content)
    if original_words >= min_words and not _looks_like_thin_report_placeholder(content):
        return content, None
    retrieved = any(
        inv.get("service_name") == "indexretriever0"
        and inv.get("tool_name") in {"search", "retrieve"}
        and inv.get("status") == "ok"
        and _as_int(inv.get("result_count"), 0) > 0
        for inv in tool_adapter.invocations
    )
    if not retrieved:
        return content, {
            "attempted": False,
            "reason": "no_successful_indexretriever_result",
            "original_words": original_words,
            "min_words": min_words,
        }

    import datetime as _dt

    today = _dt.date.today()
    sections = _normalise_report_sections(params, min_words)
    doc = await tool_adapter._compose_report(
        {
            "title": params.get("report_title") or params.get("title") or "Cloud-Dog Intelligence Brief",
            "target": params.get("target") or params.get("type") or input_text,
            "target_words": _as_int(params.get("target_words"), 850),
            "sections": sections,
            "current_year": today.year,
            "current_date": today.isoformat(),
            "recency_days": params.get("recency_days"),
        }
    )
    if isinstance(doc, dict) and doc.get("error"):
        return content, {
            "attempted": True,
            "error": str(doc.get("error")),
            "original_words": original_words,
            "min_words": min_words,
        }
    return str(doc), {
        "attempted": True,
        "recovered": True,
        "original_words": original_words,
        "recovered_words": _report_word_count(doc),
        "min_words": min_words,
        "sections": len(sections),
    }


# --------------------------------------------------------------------------- #
# Strategy runner (selects + runs a cloud_dog_agent loop)
# --------------------------------------------------------------------------- #
async def run_agent_strategy(
    *,
    strategy: str,
    db: Any,
    executor: Any,
    expert: Any,
    system_prompt: str,
    input_text: str,
    params: Dict[str, Any],
    auth_context: Optional[Dict[str, Any]],
    llm_cfg: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Run ``strategy`` via the cloud_dog_agent package. Returns ``{"content": str}``
    so the caller's existing post-processing works unchanged. ``llm_cfg`` carries the
    orchestrating expert's per-agent LLM config (temperature/max_tokens/num_ctx/think)."""
    strategy = (strategy or "").strip().lower()
    if strategy not in _SUPPORTED:
        raise ValueError(f"agent_strategy '{strategy}' not supported by this service; supported: {sorted(_SUPPORTED)}")

    descriptors = build_tool_descriptors(db, expert)
    store = _ArtifactStore()
    # PS-96 plumbing: the ref-spill threshold is per-run configurable. A small default (600)
    # keeps the document pipeline's large sections out of the LLM context; agents that must
    # SEE and chain moderate tool results (e.g. the geospatial assessment agent reading
    # discovered features) raise it via params.spill_threshold so results stay visible inline
    # instead of being spilled to art:N refs the small model then has to juggle blind.
    _spill = _as_int(params.get("spill_threshold"), _SPILL_THRESHOLD)

    auth = auth_context or {}

    # W28M-1636 R5 (coordinator finding 3): capture a raw per-call service log for the run so the
    # document pipeline's genuine Geo/Chart/File/Notification/Search actions appear in the job's
    # tool trace (previously services_invoked was empty for the document strategy).
    _svc_call_log: List[Dict[str, Any]] = []

    def _release_db_transaction() -> None:
        """End any local transaction before a long remote/model wait.

        SQLite permits only one writer. Holding the execution session open while
        a model generates can block the durable MCP lease heartbeat, making a
        live report look abandoned to Scheduler. This checkpoints local
        audit/configuration state only; it never changes model-authored content.
        """
        transaction_state = getattr(db, "in_transaction", None)
        if callable(transaction_state) and not transaction_state():
            return
        commit = getattr(db, "commit", None)
        if not callable(commit):
            return
        try:
            commit()
        except Exception:
            rollback = getattr(db, "rollback", None)
            if callable(rollback):
                rollback()
            raise

    async def _dispatch_service(service_name: str, tool_name: str, args: Dict[str, Any]) -> Any:
        """Invoke a registered service tool by service name and unwrap its payload."""
        from src.core.service.composition import ServiceCompositionManager
        from src.core.service.manager import ServiceManager

        # Search rows created by older releases may still hold a literal API key.
        # Reconcile the exact bound alias through the canonical managed-service
        # helper before research. It stores only a Vault/config-key reference.
        if (
            tool_name == "search"
            and service_name in {"searchmcp0", "search-mcp"}
            and callable(getattr(db, "query", None))
        ):
            svc = ServiceCompositionManager(db).ensure_search_mcp_service(
                service_name_override=service_name
            )
        else:
            svc = ServiceManager(db).get_service(name=service_name)
        if not svc:
            return {"error": f"service '{service_name}' not found"}
        res = await executor.service_manager.invoke_tool(
            service_id=int(svc.id), tool_name=tool_name, arguments=args, auth_context=auth
        )
        # unwrap the composition envelope to the tool's own result, tolerating
        # SSE-framed responses ("data: {...}") from streaming MCP servers (searchmcp).
        inner = res.get("result", res) if isinstance(res, dict) else res
        inner = _unwrap_sse(inner)
        _svc_call_log.append({
            "service": service_name, "tool": tool_name,
            "ok": not (isinstance(inner, dict) and inner.get("error")),
        })
        _release_db_transaction()
        return inner

    def _make_http_get(service_name: str) -> Callable[[str], Any]:
        """Build an async REST GET bound to ``service_name`` for fetching non-MCP assets
        (e.g. the chart service's PNG bytes at ``GET <base>/api/assets/{id}``).

        The base URL is the service's registered ``endpoint_url`` with any trailing ``/mcp``
        suffix removed; the credential is resolved by the SAME composition-layer auth logic
        used for MCP calls (Vault-backed X-API-Key / Bearer) so no secret is duplicated here.
        """
        async def _get(path: str) -> Any:
            """Fetch a REST asset from the service using composition-layer credentials."""
            from src.core.service.manager import ServiceManager

            svc = ServiceManager(db).get_service(name=service_name)
            if not svc:
                return {"error": f"service '{service_name}' not found"}
            base = str(svc.endpoint_url or "").rstrip("/")
            if base.endswith("/mcp"):
                base = base[: -len("/mcp")]
            url = base + (path if path.startswith("/") else "/" + path)
            headers = executor.service_manager._auth_headers(svc, auth_context=auth)
            resp = await executor.service_manager.client.get(url, headers=headers, timeout=90.0)
            _svc_call_log.append({
                "service": service_name, "tool": "GET " + (path.split("?")[0]),
                "ok": 200 <= int(getattr(resp, "status_code", 0)) < 400,
            })
            try:
                return resp.json()
            except Exception:
                return resp.text

        return _get

    async def _dispatch_subexpert(child_id: int, text: str, args: Dict[str, Any]) -> Any:
        """Execute a bound sub-expert with optional per-call generation overrides."""
        # Only override the sub-expert's own per-agent LLM config when the caller
        # explicitly set a value; otherwise the child expert's stored llm_params
        # (num_ctx / num_predict / temperature) govern — so a generator expert keeps
        # its large context + output budget instead of being clamped here.
        sub_params: Dict[str, Any] = {"persist_session": False}
        if args.get("max_tokens") is not None:
            sub_params["max_tokens"] = int(args["max_tokens"])
        if args.get("temperature") is not None:
            sub_params["temperature"] = float(args["temperature"])
        timeout_override = (
            args.get("timeout")
            if args.get("timeout") is not None
            else args.get("llm_timeout")
            if args.get("llm_timeout") is not None
            else params.get("subexpert_timeout")
            if params.get("subexpert_timeout") is not None
            else params.get("subexpert_timeout_seconds")
            if params.get("subexpert_timeout_seconds") is not None
            else params.get("llm_timeout")
            if params.get("llm_timeout") is not None
            else params.get("timeout")
        )
        if timeout_override is not None:
            sub_params["timeout"] = int(timeout_override)
        _release_db_transaction()
        result = await executor.execute(
            expert_id=int(child_id), input_text=text, parameters=sub_params, auth_context=auth
        )
        if isinstance(result, dict):
            return result.get("output_text", "")
        return str(result)

    # Capture the run's delivery spec (destinations / working_path / title) from the input so
    # publish_document can fall back to it when the model omits those args.
    _defaults: Dict[str, Any] = {}
    _nl_prompt = None  # set when the document run was driven by a free-text (chat) prompt
    try:
        _spec = json.loads(input_text) if isinstance(input_text, str) else (input_text or {})
        if isinstance(_spec, str) or _spec is None:
            raise ValueError("not a spec")
        if isinstance(_spec, dict):
            # Runtime schedule variables must resolve before both the ReAct model
            # and the configuration-owned visual tools see the report spec.  The
            # Scheduler intentionally stores its template unchanged; doing this
            # here keeps the selected country coherent across all consumers.
            _spec = _interp_round_robin_tokens(_spec, _datetime.date.today())
            _spec = _interp_run_date(_spec, _datetime.date.today())
            input_text = json.dumps(_spec, ensure_ascii=False)
            _defaults = {"destinations": _spec.get("destinations"),
                         "working_path": _spec.get("working_path"),
                         "profile": _spec.get("profile"),
                         "selected_scenario_id": _spec.get("selected_scenario_id"),
                         "rotation_registry": _spec.get("rotation_registry"),
                         "rotation_selection_rule": _spec.get("rotation_selection_rule"),
                         # Retain the workspace object as part of the execution
                         # defaults.  AgentToolAdapter resolves FileMCP profile
                         # precedence from this product-scoped configuration.
                         "file_mcp_workspace": _spec.get("file_mcp_workspace"),
                         "title": _spec.get("title"),
                         "sections": _spec.get("sections"),
                         "target": _spec.get("target"),
                         "template_family": _spec.get("template_family"),
                         "recency_days": _spec.get("recency_days"),
                         "theme_rotation": _spec.get("theme_rotation"),
                         "country_rotation": _spec.get("country_rotation"),
                         "newsletter_sources": _spec.get("newsletter_sources"),
                         "ingest_only": _spec.get("ingest_only"),
                         "research": _spec.get("research"),
                         "research_ingest": _spec.get("research_ingest"),
                         "research_queries": _spec.get("research_queries"),
                         "grounding": _spec.get("grounding"),
                         "source_families": _spec.get("source_families"),
                         "reporting_period": _spec.get("reporting_period"),
                         "introduction": _spec.get("introduction"),
                         "quality_required_date": _spec.get("quality_required_date"),
                         "quality_controls": _spec.get("quality_controls"),
                         "agentic_document_required": _spec.get("agentic_document_required"),
                         "runtime_guide_bundle": _spec.get("runtime_guide_bundle"),
                         "quality_guide": _spec.get("quality_guide"),
                         "vdb": _spec.get("vdb"),
                         "visuals": _spec.get("visuals"),
                         "auto_visuals": _spec.get("auto_visuals"),
                         "report_series": _spec.get("report_series"),
                         "messages_base_url": _spec.get("messages_base_url"),
                         "previous_reports": _spec.get("previous_reports"),
                         "brand": _spec.get("brand")}
    except Exception:
        # Free-text (natural-language) prompt — e.g. a chat-client message like "Run the
        # Transparent Borders country report for Hungary". Treat the whole message as the
        # research TARGET; a generic research template is applied below when no sections are
        # otherwise resolved, so any chat prompt yields a full, structured report.
        _nl_prompt = (input_text or "").strip() if isinstance(input_text, str) else ""
        # Default delivery for a chat-launched free-text report so it is always delivered and
        # returns a real web-view link (the chat-client forwards no destinations of its own).
        # Default recipient is config/env-driven (CLOUD_DOG__EXPERT__RESEARCH__DEFAULT_TO);
        # public default is empty so no internal address ships in the image.
        _default_to = str(get_config("research.default_to", "") or "")
        _defaults = {"target": _nl_prompt, "auto_visuals": {"map_style": "osm", "max_images": 2},
                     "recency_days": 30,
                     "destinations": [{"channel": "email_default", "address": _default_to,
                                       "preferences": {"content_style": "html", "format_mode": "passthrough"}}]}
    tool_adapter = AgentToolAdapter(descriptors, _dispatch_service, _dispatch_subexpert, store,
                                    spill_threshold=_spill,
                                    defaults=_defaults, llm=getattr(executor, "llm_manager", None),
                                    request_input=input_text, request_params=params)

    # W28M-1638: an input-scoped, model-authored document run.  No product name
    # is hard-coded here: a compatible runtime guide bundle and the report spec
    # carry the scope, style, section framework, source policy and destinations.
    # An agentic product may explicitly select ReACT. Its model-authored
    # boundary must remain in force and never re-expose compose_report.
    _agentic_document = bool(_defaults.get("agentic_document_required"))
    _agentic_strict_completion = False
    _agentic_completion_max_attempts = 1
    _agentic_chunked_authoring = False
    _agentic_chunk_target_words = 1800
    _agentic_chunk_max_sections = 3
    _agentic_table_plan: Dict[str, int] = {}
    _agentic_forbidden_discipline = ""
    if _agentic_document:
        strategy = AgentStrategy.REACT.value
        # ``compose_report`` is the legacy code-driven, section-by-section document
        # pipeline.  A model-authored report must never be able to select that
        # deterministic body path merely because it is normally advertised as a
        # builtin.  Retain research, quality, rendering and delivery tools: those
        # configure, validate, persist and deliver the model's own content.
        descriptors = [
            descriptor for descriptor in descriptors
            if descriptor.get("name") != "compose_report"
        ]
        guide_context = await tool_adapter.load_runtime_guide_bundle()
        section_titles = [
            str(section.get("title") or "").strip()
            for section in (_defaults.get("sections") or [])
            if isinstance(section, dict) and str(section.get("title") or "").strip()
        ]
        quality_controls = tool_adapter._default_quality_controls
        _agentic_forbidden_discipline = _forbidden_content_generation_discipline(quality_controls)
        target_words = _as_int(params.get("target_words"), 850)
        minimum_report_words = int(
            quality_controls.get("agentic_minimum_report_words")
            or max(600, target_words * max(1, len(section_titles)) // 2)
        )
        # A single local-model completion cannot safely carry a multi-thousand
        # word report plus a governed evidence register inside its context
        # window.  For a large configured product, have the model author bounded
        # section chunks and persist each exact chunk through FileMCP.  This is
        # generic configuration/orchestration: code neither writes nor repairs a
        # report word.  A smaller strict report retains the one-completion path.
        _agentic_chunked_authoring = bool(
            quality_controls.get("model_authored_chunked_authoring", minimum_report_words >= 4000)
        )
        _agentic_chunk_target_words = max(
            900,
            min(
                2400,
                _as_int(quality_controls.get("model_authored_chunk_target_words"), 1800),
            ),
        )
        # Limit the number of exact H2 headings assigned to one bounded model
        # turn.  This is generic model-turn scheduling, not report assembly:
        # the model still authors every byte, but cannot silently omit later
        # headings after spending its turn on an earlier section.
        _agentic_chunk_max_sections = max(
            1,
            min(
                3,
                _as_int(quality_controls.get("model_authored_chunk_max_sections"), 3),
            ),
        )
        minimum_external_links = int(quality_controls.get("minimum_external_links") or 0)
        minimum_citation_markers = int(quality_controls.get("minimum_citation_markers") or 0)
        minimum_tables = int(quality_controls.get("minimum_tables") or 0)
        configured_table_plan = quality_controls.get("model_authored_table_plan")
        if configured_table_plan is not None:
            if not isinstance(configured_table_plan, dict):
                raise ValueError("model_authored_table_plan must map exact section titles to table counts")
            for configured_title, configured_count in configured_table_plan.items():
                title = re.sub(r"\s+", " ", str(configured_title)).strip()
                try:
                    count = int(configured_count)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        "model_authored_table_plan values must be positive integers"
                    ) from exc
                if not title or count < 1:
                    raise ValueError(
                        "model_authored_table_plan needs non-empty section titles and positive counts"
                    )
                if title not in section_titles:
                    raise ValueError(
                        "model_authored_table_plan names a section absent from the report contract: "
                        + title
                    )
                if re.search(r"(?i)source|methodology", title):
                    raise ValueError(
                        "model_authored_table_plan cannot assign tables to the source or methodology tail"
                    )
                _agentic_table_plan[title] = count
            if sum(_agentic_table_plan.values()) < minimum_tables:
                raise ValueError(
                    "model_authored_table_plan does not satisfy the configured minimum_tables"
                )
        # A governed report contract can demand a model-owned retry checkpoint.
        # The checkpoint only validates a draft and returns its deficits to the
        # model for a complete replacement; it never edits, appends to, or
        # otherwise repairs report prose in code.
        _agentic_strict_completion = bool(
            minimum_external_links
            or minimum_citation_markers
            or minimum_tables
            or quality_controls.get("numbered_sources_required")
        )
        _agentic_completion_max_attempts = max(
            1,
            min(
                3,
                _as_int(
                    quality_controls.get("agentic_completion_attempts"),
                    3 if _agentic_strict_completion else 1,
                ),
            ),
        )
        # A strict agentic report must receive a usable evidence register before
        # it starts drafting.  Merely advertising web_research as an optional
        # ReAct tool allowed a model to write a plausible but uncited summary
        # without ever retrieving its governed source set.  This is tool
        # configuration/retrieval only: the model still chooses the sources it
        # cites and authors every word of the report, its source entries, and
        # its analysis.  We deliberately run it only when the input contract
        # actually requires citations/URLs, so ordinary agentic conversations
        # retain their existing free-form tool selection.
        preflight_source_register = ""
        source_count = 0
        # The strict preflight has already performed live retrieval.  Keep an
        # exact marker-to-URL allowlist from that *current run* so the final
        # model-authored Sources section cannot silently replace a retrieved
        # URL with a plausible-looking historical URL.  This is a validation
        # boundary, not source selection or prose repair: the model continues
        # to choose which validated sources to cite and authors every source
        # line itself.
        governed_source_urls: Dict[int, str] = {}
        research_request: Dict[str, Any] = {}
        source_register_refreshes: List[Dict[str, Any]] = []
        caller_source_register, caller_governed_source_urls = _caller_governed_source_register(_defaults)
        if caller_governed_source_urls and bool(quality_controls.get("model_authored_sources_required")):
            preflight_source_register = caller_source_register
            source_count = len(caller_governed_source_urls)
            governed_source_urls = dict(caller_governed_source_urls)
            quality_controls["allowed_external_source_urls"] = sorted(
                set(governed_source_urls.values())
            )
            quality_controls["external_links_restricted_to_allowed_sources"] = True

        async def _refresh_governed_source_register(*, reason: str) -> str:
            """Refresh the strict run's live-validated citation namespace.

            A final rendered-document link check can legitimately fail after an
            earlier source preflight.  A retry must not ask the model to
            re-author against that stale source set.  This helper only invokes
            the normal research tool and rebuilds the validator's URL
            allowlist; the model still selects sources and authors the report.
            """
            nonlocal preflight_source_register, source_count, governed_source_urls
            if not research_request:
                raise RuntimeError(
                    "AGENTIC_DOCUMENT_RESEARCH_INCOMPLETE: no configured source request is available "
                    "for a live-link retry"
                )
            try:
                refreshed_register = await tool_adapter._web_research(dict(research_request))
            except Exception as exc:
                raise RuntimeError(
                    "AGENTIC_DOCUMENT_RESEARCH_INCOMPLETE: configured evidence refresh failed: "
                    + str(exc)
                ) from exc

            refreshed_count = len(
                re.findall(r"(?m)^\[\d+\]", tool_adapter._research_grounding or "")
            )
            refreshed_urls: Dict[int, str] = {}
            for marker_text, source_url in re.findall(
                r"(?m)^\[(\d+)\].*?\s—\sURL:\s(https?://\S+)",
                tool_adapter._research_grounding or "",
            ):
                refreshed_urls[int(marker_text)] = source_url.rstrip(".,;:")
            required_sources = max(minimum_external_links, minimum_citation_markers)
            if refreshed_count < required_sources:
                raise RuntimeError(
                    "AGENTIC_DOCUMENT_RESEARCH_INCOMPLETE: "
                    f"{refreshed_count} governed sources available; {required_sources} required"
                )
            if bool(quality_controls.get("model_authored_sources_required")) and (
                len(refreshed_urls) < required_sources
            ):
                raise RuntimeError(
                    "AGENTIC_DOCUMENT_RESEARCH_INCOMPLETE: live-validated source URL allowlist "
                    f"contains {len(refreshed_urls)} of {required_sources} required source(s)"
                )
            preflight_source_register = str(refreshed_register or "")
            source_count = refreshed_count
            governed_source_urls = {
                **dict(caller_governed_source_urls),
                **refreshed_urls,
            }
            if bool(quality_controls.get("model_authored_sources_required")):
                quality_controls["allowed_external_source_urls"] = sorted(
                    set(governed_source_urls.values())
                )
                quality_controls["external_links_restricted_to_allowed_sources"] = True
            source_register_refreshes.append(
                {
                    "reason": reason,
                    "source_count": source_count,
                    "governed_url_count": len(governed_source_urls),
                }
            )
            return preflight_source_register

        if minimum_external_links or minimum_citation_markers:
            required_sources = max(minimum_external_links, minimum_citation_markers)
            research_cfg = _defaults.get("research") if isinstance(_defaults.get("research"), dict) else {}
            specified_queries = [
                str(query).strip()
                for query in (_defaults.get("research_queries") or [])
                if str(query or "").strip()
            ]
            target_topic = str(_defaults.get("target") or _defaults.get("title") or "report subject").strip()
            target_name = target_topic.split(":", 1)[0].strip() or target_topic
            generated_facets = [
                f"{target_name} {title}"
                for title in section_titles
                if not re.search(r"(?i)source|methodology|summary|bluf", title)
            ]
            primary_query = (
                specified_queries[0]
                if specified_queries
                else f"{target_name} current governance integrity media border economic external alignment"
            )
            extra_queries = (specified_queries[1:] + generated_facets)[:8]
            # Search backends can return only one or two distinct public URLs for
            # a broad query.  Ask every bounded, section-derived facet before
            # failing a strict source contract; this is retrieval configuration,
            # not source selection or report authorship.
            preflight_query_count = min(12, 1 + len(extra_queries))
            research_request = {
                "query": primary_query,
                "extra_queries": extra_queries,
                "max_results": max(
                    int(research_cfg.get("max_results") or 0),
                    minimum_external_links,
                    8,
                ),
                "max_queries": max(
                    int(research_cfg.get("max_queries") or 0),
                    5,
                    preflight_query_count,
                ),
                "max_sources": max(
                    int(research_cfg.get("max_sources") or 0),
                    minimum_external_links + 3,
                    18,
                ),
                "engines": research_cfg.get("engines") or [],
                # A strict document source register must be live-validated before
                # authoring.  Product contracts use ``external_link_validation``;
                # older profiles use ``live_external_links_required`` or the
                # fail-closed delivery switch.  Treat all three as an explicit
                # request so a stale corpus URL cannot reach the model and fail
                # only after a long report has been authored.
                "validate_links": bool(
                    quality_controls.get("external_link_validation")
                    or quality_controls.get("live_external_links_required")
                    or quality_controls.get("block_delivery_on_failure")
                ),
                # Keep source-register validation aligned with the final
                # rendered citation policy.  A strict public-access delivery
                # gate must not seed the model with sources it will later
                # reject as recipient-inaccessible.
                "require_public_access": bool(
                    quality_controls.get("external_links_publicly_accessible_required")
                ),
                "link_timeout": int(research_cfg.get("link_timeout") or 12),
                "model_authored_sources_required": bool(
                    quality_controls.get("model_authored_sources_required")
                ),
                "forbidden_content": quality_controls.get("forbidden_content"),
            }
            if (
                bool(quality_controls.get("model_authored_sources_required"))
                and len(governed_source_urls) >= required_sources
            ):
                source_register_refreshes.append(
                    {
                        "reason": "caller_governed_register",
                        "source_count": source_count,
                        "governed_url_count": len(governed_source_urls),
                    }
                )
            else:
                await _refresh_governed_source_register(reason="initial_preflight")
        # Strict runs already have a governed source register.  Leaving the
        # optional research tool advertised let the ReAct controller ignore the
        # preflight and spend an authoring turn retrieving a smaller, duplicate
        # set instead of writing the report.  This is tool configuration only;
        # the model continues to select and cite the final sources itself.
        if _agentic_strict_completion:
            descriptors = [
                descriptor for descriptor in descriptors
                if descriptor.get("name") != "web_research"
            ]
        authored_sections = [
            section for section in (_defaults.get("sections") or [])
            if isinstance(section, dict)
            and str(section.get("title") or "").strip()
            and not re.search(r"(?i)source|methodology", str(section.get("title") or ""))
        ]
        section_word_maxima: Dict[str, int] = {}
        configured_section_maximum_words = quality_controls.get("section_maximum_words")
        if isinstance(configured_section_maximum_words, dict):
            for configured_title, configured_maximum in configured_section_maximum_words.items():
                title = re.sub(r"\s+", " ", str(configured_title)).strip()
                try:
                    maximum = max(1, int(configured_maximum))
                except (TypeError, ValueError):
                    continue
                if title:
                    section_word_maxima[title] = maximum
        bounded_floor_total = sum(
            min(
                section_word_maxima[title],
                max(1, _as_int(section.get("target_words"), 1)),
            )
            for section in authored_sections
            for title in [re.sub(r"\s+", " ", str(section.get("title") or "")).strip()]
            if title in section_word_maxima
        )
        unbounded_section_count = sum(
            1
            for section in authored_sections
            if re.sub(r"\s+", " ", str(section.get("title") or "")).strip()
            not in section_word_maxima
        )
        unbounded_section_floor = (
            max(
                1,
                (max(0, minimum_report_words - bounded_floor_total)
                 + max(1, unbounded_section_count) - 1) // max(1, unbounded_section_count),
            )
            if unbounded_section_count else 1
        )
        section_word_floors: Dict[str, int] = {}
        for section in authored_sections:
            title = re.sub(r"\s+", " ", str(section.get("title") or "")).strip()
            target_words = max(1, _as_int(section.get("target_words"), 1))
            maximum = section_word_maxima.get(title)
            section_word_floors[title] = (
                min(maximum, target_words)
                if maximum is not None
                else max(unbounded_section_floor, target_words)
            )
        section_quality_contract = (
            quality_controls.get("section_quality")
            if isinstance(quality_controls.get("section_quality"), dict)
            else {}
        )
        section_quality_overrides = (
            section_quality_contract.get("section_overrides")
            if isinstance(section_quality_contract.get("section_overrides"), dict)
            else {}
        )
        default_section_minimum = max(
            1, _as_int(section_quality_contract.get("minimum_words"), 1)
        )
        section_quality_word_minima: Dict[str, int] = {}
        configured_sections = {
            re.sub(r"\s+", " ", str(section.get("title") or "")).strip(): section
            for section in (_defaults.get("sections") or [])
            if isinstance(section, dict) and str(section.get("title") or "").strip()
        }
        for title in section_titles:
            section = configured_sections.get(title, {})
            override = (
                section_quality_overrides.get(title)
                if isinstance(section_quality_overrides.get(title), dict)
                else {}
            )
            quality_minimum = max(
                1, _as_int(override.get("minimum_words"), default_section_minimum)
            )
            if section_quality_contract.get("required"):
                section_quality_word_minima[title] = quality_minimum
            configured_target = max(1, _as_int(section.get("target_words"), 1))
            required_floor = max(
                section_word_floors.get(title, 1),
                configured_target,
                quality_minimum,
            )
            maximum = section_word_maxima.get(title)
            section_word_floors[title] = (
                min(maximum, required_floor)
                if maximum is not None
                else required_floor
            )
        section_word_floor_contract = "; ".join(
            f"{title}: at least {section_word_floors[title]} substantive words"
            + (
                f" and no more than {section_word_maxima[title]} words"
                if title in section_word_maxima else ""
            )
            for title in section_titles
            if title in section_word_floors
        )
        source_access_requirement = (
            "publicly accessible (2xx/3xx)"
            if quality_controls.get("external_links_publicly_accessible_required")
            else "live"
        )
        source_contract = (
            f"Use at least {minimum_external_links} distinct, {source_access_requirement} external source URLs and "
            f"at least {minimum_citation_markers} distinct numbered inline citation markers. "
            if minimum_external_links or minimum_citation_markers else ""
        )
        required_front_matter: List[str] = []
        outer_required_classification = str(
            quality_controls.get("required_classification")
            or _defaults.get("introduction")
            or ""
        ).strip()
        outer_required_reporting_period = str(
            quality_controls.get("required_reporting_period")
            or _defaults.get("reporting_period")
            or ""
        ).strip()
        if outer_required_reporting_period:
            outer_required_reporting_period = outer_required_reporting_period.replace(
                "{run_date}", _datetime.date.today().isoformat()
            )
        if outer_required_classification:
            required_front_matter.append(
                f"the exact standalone classification/framing line `{outer_required_classification}`"
            )
        if outer_required_reporting_period:
            required_front_matter.append(
                f"the exact standalone declaration `Reporting period: {outer_required_reporting_period}`"
            )
        front_matter_contract = (
            "Required front matter before substantive analysis: include "
            + " and ".join(required_front_matter)
            + ". "
            + (
                "Use the configured `As at` wording; do not write any `As of` phrase. "
                if outer_required_reporting_period.lower().startswith("as at")
                or quality_controls.get("as_at_reporting_period_required")
                else ""
            )
            if required_front_matter else ""
        )
        source_register_contract = (
            "The governed source register is the complete allowed citation namespace for this "
            f"run: use only its existing markers [1] through [{source_count}], reuse those markers "
            "where necessary, and create a final source entry for every marker you use. Never invent "
            "a marker outside that register. "
            if source_count else ""
        )
        selected_scenario_id = str(_defaults.get("selected_scenario_id") or "").strip()
        selected_scenario = next(
            (
                item for item in (_defaults.get("rotation_registry") or [])
                if isinstance(item, dict) and str(item.get("id") or "").strip() == selected_scenario_id
            ),
            None,
        )
        scenario_contract = (
            "This scheduler run selected exactly this product scenario; assess it and no other "
            "geography/type: " + json.dumps(selected_scenario, ensure_ascii=False, sort_keys=True) + ". "
            + str(_defaults.get("rotation_selection_rule") or "") + " "
            if isinstance(selected_scenario, dict) else ""
        )
        section_guidance_rows = [
            "%s: %s" % (str(section.get("title") or "").strip(), str(section.get("brief") or "").strip())
            for section in (_defaults.get("sections") or [])
            if isinstance(section, dict)
            and str(section.get("title") or "").strip()
            and str(section.get("brief") or "").strip()
        ]
        section_guidance = (
            "\n\nProduct section guidance (the report model must author this analysis itself):\n- "
            + "\n- ".join(section_guidance_rows)
            if section_guidance_rows else ""
        )
        table_contract = (
            f"Include at least {minimum_tables} decision-useful Markdown comparator table(s); "
            if minimum_tables else ""
        )
        vdb_contract = ""
        vdb = _defaults.get("vdb") if isinstance(_defaults.get("vdb"), dict) else {}
        if vdb:
            collections = vdb.get("collections") if isinstance(vdb.get("collections"), dict) else {}
            vdb_collection = str(collections.get("library") or collections.get("content") or "").strip()
            if vdb_collection:
                vdb_contract = (
                    "The configured `web_research` tool will fall back to the approved "
                    f"{vdb_collection} corpus when live search is unavailable; treat that returned "
                    "source register as evidence and do not keep retrying an empty live search. "
                )
        completion_checkpoint_instruction = ""
        if _agentic_strict_completion:
            completion_checkpoint_instruction = (
                "\n\n## Non-negotiable model completion checkpoint\n"
                "Do not return a summary, outline, plan, partial draft, or tool action. Your next "
                "answer must be one complete replacement report beginning with `FINAL_REPORT`. Before "
                "you answer, silently verify every required H2, the configured total word floor, at "
                "least one comparator table, distinct numbered inline citations, and one final numbered "
                "Sources and Methodology section whose direct URLs resolve every marker you used. The "
                "runtime will validate this draft before any persistence or delivery. If it fails, only "
                "you—not code—will be asked to author another complete report."
            )
        system_prompt = (
            system_prompt
            + "\n\n## Model-authored document delivery contract\n"
            + "This is an agentic document run. You are the sole author of the report prose, "
            + "analysis, source selection, citations, recommendations, visual rationale, and "
            + "section-level quality self-assessment. A governed candidate source register is already "
            + "loaded below. Select the sources you actually cite from it; do not skip it, invent URLs, "
            + "or spend an iteration re-running `web_research`. "
            + source_register_contract
            + scenario_contract
            + vdb_contract
            + (_agentic_forbidden_discipline + " " if _agentic_forbidden_discipline else "")
            + "After evidence is available, return the complete reader-ready Markdown report by writing "
            + "`FINAL_REPORT` on its own line followed by the report, not a summary or a plan. "
            + "The report must be at least "
            + f"{minimum_report_words} words. Every factual/numeric claim needs a resolving inline "
            + "citation in the form [n]; write the final Sources and Methodology yourself from the "
            + "sources actually used, with each matching [n] source entry containing its direct URL. "
            + front_matter_contract
            + source_contract
            + table_contract
            + "Use each required section title once and exactly as a Markdown H2 (`## Title`) in "
            + "the stated order; use H3 for any subheadings. Meet these section-specific word contracts "
            + "before writing the final source register: "
            + section_word_floor_contract
            + ". Before returning `FINAL_REPORT`, conduct "
            + "your own silent completion check for word count, all headings, citations, Sources and "
            + "Methodology, substantive analysis, and no placeholders. Do not call `compose_report`, "
            + "and do not call delivery tools: "
            + "the runtime will validate, persist, render, and deliver exactly your final Markdown. "
            + "Do not invent evidence, claim unavailable sources without retrying research, or leave "
            + "placeholder/hollow sections.\n\nRequired report sections, in this order:\n- "
            + "\n- ".join(section_titles)
            + "\n\nApproved runtime guide bundle (must be followed and reflected in your self-assessment):\n"
            + guide_context
            + section_guidance
            + ("\n\nGoverned candidate source register (select and cite only sources you actually use):\n"
               + preflight_source_register if preflight_source_register else "")
            + completion_checkpoint_instruction
        )

    # --- Deterministic document pipeline -----------------------------------------------------
    # The "document" strategy does NOT rely on the (drift-prone) model to orchestrate: it runs
    # the three builtins in a fixed order — web_research -> compose_report (EVERY section, in
    # full) -> publish_document — driven entirely by the input template. This is what reliably
    # reaches the depth of the original template-driven reports (a react loop may skip the deep
    # section-by-section step). Still 100% template/data-driven; no per-demo code.
    if strategy == "document":
        import datetime as _dt
        _today = _dt.date.today()
        _year = _today.year
        _defaults = _interp_run_date(_defaults, _today)
        tool_adapter._default_destinations = _defaults.get("destinations") or []
        tool_adapter._default_working_path = _defaults.get("working_path")
        tool_adapter._default_title = _defaults.get("title")
        tool_adapter._default_sections = _defaults.get("sections") or []
        tool_adapter._default_target = _defaults.get("target")
        _target = str(_defaults.get("target") or "")
        _tw = _as_int(params.get("target_words"), 1000)
        # Template-driven: fetch the LATEST index-retriever template for the named family and use
        # its sections; fall back to any sections supplied in the input spec.
        _sections = _defaults.get("sections") or []
        _template_id = None
        _family = _defaults.get("template_family")
        if _family:
            tpl = await tool_adapter._fetch_template(str(_family))
            if tpl and tpl.get("sections"):
                _sections = tpl["sections"]
                tool_adapter._default_sections = _sections
                _template_id = tpl.get("template_id")
                logger.info("document pipeline: using template %s (%s) — %s sections",
                            _template_id, tpl.get("name"), len(_sections))
            else:
                logger.warning("document pipeline: no template for family %r; using spec sections", _family)
        # Theme rotation (per-theme templates): when the spec carries a `theme_rotation`, pick
        # TODAY's per-theme template (its own tailored section structure) + zone deterministically
        # by day-of-year. Each theme is pre-built with sections suited to it and is enhanced by
        # editing the config — no per-demo code.
        _theme_label = None
        _zone_map = None
        _theme_charts = []
        if _defaults.get("theme_rotation"):
            _sel = _select_rotated_theme(_defaults["theme_rotation"], _dt.date.today().timetuple().tm_yday)
            if _sel:
                _zone_map = _sel.get("zone_map")
                _theme_charts = _sel.get("charts") or []
                if _sel.get("target"):
                    _target = _sel["target"]
                if _sel.get("sections"):
                    _sections = _sel["sections"]
                    tool_adapter._default_sections = _sections
                if _sel.get("title"):
                    _defaults["title"] = _sel["title"]
                    tool_adapter._default_title = _sel["title"]
                _theme_label = _sel.get("name")
                logger.info("document pipeline: theme rotation -> %s (zone %s), %s sections",
                            _theme_label, _sel.get("zone"), str(len(_sections)))
        # Country rotation: the TB country report rotates through countries ('next at random' =
        # next in the deterministic daily cycle) rather than always Hungary. Pick today's country
        # and specialise the title + section briefs to it ({country} placeholders); the visuals are
        # specialised below once the spec is assembled.
        _country = None
        _country_bbox = None
        if _defaults.get("country_rotation"):
            _sel_c = _select_rotated_country(_defaults["country_rotation"], _dt.date.today().timetuple().tm_yday)
            if _sel_c:
                _country = _sel_c["name"]
                _country_bbox = _sel_c.get("bbox")
                if tool_adapter._default_title:
                    tool_adapter._default_title = tool_adapter._default_title.replace("{country}", _country)
                    _defaults["title"] = tool_adapter._default_title
                if _target:
                    _target = _interp_country(_target, _country)
                if _sections:
                    _sections = [_interp_country(s, _country) for s in _sections]
                    tool_adapter._default_sections = _sections
                logger.info("document pipeline: country rotation -> %s", _country)
        # Country-report detection: a chat/NL request such as "TB country report for Peru" or
        # "Transparent Borders country risk brief — Ecuador" must get the CANONICAL 16-section
        # country structure (the same one the scheduled deep country brief uses, ~13.6k target
        # words) parameterised to the named country — NOT the shallow generic template. This is
        # what makes a chat-launched country report a full document rather than a ~2.4k summary.
        if not _sections and _nl_prompt:
            import re as _re_c
            _nl_low = _nl_prompt.lower()
            _is_country = (
                ("country report" in _nl_low or "country risk" in _nl_low or "country brief" in _nl_low
                 or "country profile" in _nl_low)
                and ("transparent border" in _nl_low or "tb " in _nl_low or _nl_low.strip().startswith("tb")
                     or "country report" in _nl_low or "country risk" in _nl_low or "country brief" in _nl_low)
            )
            if _is_country:
                # Extract the country name: prefer "for/on/about/of/—/: <Country>", else the
                # capitalised run adjacent to the word "country", else the cleaned prompt tail.
                _cn = None
                _stop = {"transparent borders", "transparent", "borders", "tb"}
                # A country is a Title-Case run of 1-3 words (allows an optional leading article).
                _tc = r"[A-Z][A-Za-z’'.-]+(?:\s+[A-Z][A-Za-z’'.-]+){0,2}"
                for _pat in (rf"(?:for|on|about|of|regarding|:|—|-)\s+(?:the\s+)?({_tc})",
                             rf"\b({_tc})\s+country\b"):
                    _m = _re_c.search(_pat, _nl_prompt)
                    if _m:
                        _cand = _m.group(1).strip(" .-—")
                        # drop trailing trigger words captured by a greedy match
                        _cand = _re_c.sub(r"\s+(country|report|risk|brief|profile|assessment).*$", "", _cand, flags=_re_c.I).strip()
                        if _cand and len(_cand) <= 40 and _cand.lower() not in _stop:
                            _cn = _cand
                            break
                if _cn:
                    _country = _cn  # feeds the visuals specialisation below (map focus, chart title)
                    _c_title = f"{_cn} — Transparent Borders Country Risk Brief"
                    tool_adapter._default_title = _c_title
                    _defaults["title"] = _c_title
                    _target = f"{_cn}: comprehensive transparency, governance and border-integrity risk assessment"
                    _c_briefs = [
                        ("Executive Summary", "Concise overview of the country's transparency, governance and border-integrity risk posture: headline rating, the three to five key drivers, and what has changed most recently."),
                        ("Country Context and Political Landscape", "Government structure, ruling coalition, recent elections, and the political dynamics that shape governance and transparency."),
                        ("Governance and Rule of Law", "Independence of the judiciary, separation of powers, checks and balances, constitutional changes, and rule-of-law trajectory; cite specific institutions and rulings."),
                        ("Corruption and Anti-Corruption Framework", "Corruption Perceptions Index trend with numbers, notable cases, public procurement integrity, and the effectiveness of anti-corruption bodies; a comparator table where useful."),
                        ("Media Freedom and Civil Society", "Media ownership concentration, press-freedom rankings with figures, treatment of NGOs and civil society, and information integrity."),
                        ("Transparency and Open Government", "Access to information, fiscal transparency, beneficial-ownership registers, and open-data commitments; quantify where possible."),
                        ("Border Integrity and Migration Management", "Border control posture, migration and asylum policy, smuggling/trafficking risk, and any regional visa/free-movement developments."),
                        ("Economic and Fiscal Risk", "Macroeconomic indicators (GDP growth, inflation, debt with numbers) and the link between fiscal pressures and governance risk."),
                        ("International Relations and Conditionality", "Relations with regional blocs and lenders, any funding conditionality, disputes or proceedings, and the trajectory of external relations."),
                        ("Foreign Policy and External Alignment", "Relations with neighbouring states and major powers, and how external alignment affects transparency and border policy."),
                        ("Key Developments (last 12 months)", "A dated, specific run-down of the most significant governance, corruption and border-integrity developments over the past year; include dates and names."),
                        ("Comparative Benchmarking", "How the country compares with regional peers on the main transparency/governance indices, in a comparator table with figures."),
                        ("Risks, Gaps and Red Flags", "The principal forward-looking risks and structural weaknesses, prioritised."),
                        ("Outlook (12 months)", "A grounded 12-month outlook with scenarios and the signals that would distinguish them."),
                        ("Recommendations", "Three to five prioritised, actionable recommendations for stakeholders."),
                        ("Methodology and Evidence Basis", "Explain in flowing prose how this assessment was made — the approach, the categories of evidence consulted (indices, official bodies, reporting) and their recency, comparative benchmarking, and limitations. Do NOT include any URLs, any numbered/bulleted citation list, and do NOT create a 'Sources', 'References' or 'Data Collection and Sources' sub-heading — the single consolidated Sources list follows at the very end of the document."),
                    ]
                    # 16 sections is the canonical country structure. For an ON-DEMAND (chat/API)
                    # run the whole document must generate + publish inside the synchronous request
                    # window (the api_kit request-timeout middleware, 900s on this service; long ops
                    # are otherwise meant to use jobs). At ~59s/section for 850 words, 16 sections
                    # overran 900s (published nothing). 600 words/section keeps all 16 topics and
                    # yields a deep ~9.6k-word brief that completes well within the window. The
                    # scheduled deep brief is unaffected (it supplies its own 850-word sections and
                    # never reaches this free-text branch).
                    _sections = [
                        {"title": _t, "brief": f"For {_cn}: {_b}", "target_words": 600}
                        for (_t, _b) in _c_briefs
                    ]
                    tool_adapter._default_sections = _sections
                    logger.info("document pipeline: country-report structure applied for %s (%s sections, ~%s target words)",
                                _cn, len(_sections), sum(s["target_words"] for s in _sections))
        # Free-text / chat-driven run with no template: apply a generic research structure so ANY
        # natural-language prompt yields a full, well-structured report (Exec Summary + TOC come for
        # free downstream). This is what lets a chat-client message launch a real report.
        if not _sections and (_nl_prompt or not _defaults.get("template_family")):
            _topic = _nl_prompt or _target or "the requested topic"
            if not tool_adapter._default_title:
                _ttl = _topic if len(_topic) <= 90 else _topic[:87] + "…"
                tool_adapter._default_title = _ttl
                _defaults["title"] = _ttl
            if not _target:
                _target = _topic
            _sections = [
                {"title": "Executive Summary", "brief": f"A substantive 8-12 sentence executive summary of {_topic}: the situation, the most important findings, the competing interpretations, and the bottom-line assessment with a stated confidence level. No preamble.", "target_words": 320},
                {"title": "Background & Historical Context", "brief": f"The essential background and history needed to understand {_topic} — how the current situation arose, key events on a dated timeline, and the structural factors at play. Cite named sources with dates for every claim.", "target_words": 520},
                {"title": "Current Situation", "brief": f"A detailed, up-to-date account of the present state of {_topic}: what is happening now, who the principal actors are, the most recent developments (with dates), and the facts on the ground. Ground every statement in a named, dated source.", "target_words": 560},
                {"title": "Key Findings", "brief": f"The most important, specific, evidence-backed findings about {_topic}. Use concrete facts, figures, named sources and at least one comparison table. Each finding must be a distinct, sourced claim — no generic filler.", "target_words": 620},
                {"title": "Detailed Analysis", "brief": f"Deep multi-angle analysis of {_topic}: the underlying drivers, cause-and-effect chains, comparisons with peers/precedents, and competing interpretations presented fairly where sources disagree. Reason explicitly from the evidence.", "target_words": 640},
                {"title": "Stakeholders & Dynamics", "brief": f"The key stakeholders in {_topic} — their positions, interests, incentives and leverage — and how they interact. Name organisations and individuals with sources; a stakeholder table where it aids clarity.", "target_words": 480},
                {"title": "Data & Indicators", "brief": f"The quantitative picture of {_topic}: the relevant metrics, indices, trends and figures, with the numbers and their sources and dates. Present a table of the key indicators and interpret what the data shows.", "target_words": 480},
                {"title": "Risks & Scenarios", "brief": f"Forward-looking risks and uncertainties for {_topic}, and 2-3 plausible scenarios (e.g. base / upside / downside) with the signposts that would indicate each. Reason through likelihoods.", "target_words": 520},
                {"title": "Outlook", "brief": f"The considered forward outlook for {_topic} over the near and medium term, synthesising the analysis above into a clear directional assessment with reasoning and a confidence level.", "target_words": 400},
                {"title": "Recommendations & Watch-Points", "brief": f"Actionable, prioritised recommendations or watch-points relating to {_topic}, each tied to a specific finding above and to the indicator that would trigger action.", "target_words": 380},
            ]
            tool_adapter._default_sections = _sections
            logger.info(
                "document pipeline: generic research template applied for free-text prompt (%s sections)",
                len(_sections),
            )
        _recency = _defaults.get("recency_days")
        # Recency-scoped query for change/period briefs so the grounding is genuinely about the
        # window, not a year of background (the cause of stale "this week" event dates).
        if _recency:
            _mon = _today.strftime("%B %Y")
            _q = f"{_target} latest developments in the past {int(_recency)} days {_mon}"
            _maxr = 10
        else:
            _q = f"{_target} latest developments analysis {_year}"
            _maxr = 8
        # Newsletter ingest (the Ukraine tracker upgrade): pull the analyst newsletters from the
        # configured IMAP mailbox into the vector collection so the report can ground on + cite
        # them. ``ingest_only`` returns straight after (used by the daily ingest schedule).
        _news = _defaults.get("newsletter_sources")
        if isinstance(_news, dict) and _news.get("ingest"):
            try:
                _n = await tool_adapter._ingest_newsletters(_news)
                # indexing is async — give the embeddings a moment before we retrieve below.
                if _n:
                    import asyncio as _aio
                    await _aio.sleep(int(_news.get("index_settle_seconds") or 25))
            except Exception as exc:
                logger.warning("document pipeline: newsletter ingest failed: %s", exc)
                if _defaults.get("ingest_only"):
                    raise RuntimeError("ingest-only run failed during newsletter ingestion") from exc
            if _defaults.get("ingest_only"):
                return {"content": f"Newsletter ingest complete for query '{_news.get('query')}'.",
                        "agent_trace": {"strategy": "document", "ingest_only": True}}
        try:
            # Prefer the schedule's explicit, domain-specific live research queries. Facets
            # derived from section titles remain an additive fallback for older schedules.
            _facets = []
            for _s in (_sections or [])[:4]:
                _st = str(_s.get("title") if isinstance(_s, dict) else "").strip()
                if _st and not re.search(r"(?i)source|brief|summary|in brief", _st):
                    _facets.append(("%s %s" % (_target, _st))[:120])
            _specified_queries = [str(q).strip() for q in (_defaults.get("research_queries") or [])
                                  if str(q or "").strip()]
            _research_cfg = _defaults.get("research") if isinstance(_defaults.get("research"), dict) else {}
            if _specified_queries:
                _q = _specified_queries[0]
                _extra_queries = _specified_queries[1:] + _facets
            else:
                _extra_queries = _facets
            await tool_adapter._web_research({
                "query": _q,
                "max_results": int(_research_cfg.get("max_results") or _maxr),
                "max_queries": int(_research_cfg.get("max_queries") or 5),
                "max_sources": int(_research_cfg.get("max_sources") or 18),
                "engines": _research_cfg.get("engines") or [],
                "extra_queries": _extra_queries,
                "validate_links": bool(_research_cfg.get("validate_links")),
                "link_timeout": int(_research_cfg.get("link_timeout") or 12),
                "model_authored_sources_required": bool(
                    (_defaults.get("quality_controls") or {}).get("model_authored_sources_required")
                    if isinstance(_defaults.get("quality_controls"), dict)
                    else False
                ),
                "forbidden_content": (
                    (_defaults.get("quality_controls") or {}).get("forbidden_content")
                    if isinstance(_defaults.get("quality_controls"), dict)
                    else None
                ),
            })
        except Exception as exc:  # research is best-effort grounding
            logger.warning("document pipeline: web_research failed: %s", exc)
        # Fold the newsletter passages into the grounding (cited with links) alongside web search.
        if isinstance(_news, dict):
            try:
                await tool_adapter._vdb_grounding(_news, _q)
            except Exception as exc:
                logger.warning("document pipeline: vdb grounding failed: %s", exc)
        doc = await tool_adapter._compose_report(
            {"target_words": _tw, "current_year": _year,
             "current_date": _today.isoformat(), "recency_days": _recency})
        if isinstance(doc, dict) and doc.get("error"):
            return {"content": "document pipeline failed at compose_report: " + str(doc.get("error")),
                    "agent_trace": {"strategy": "document", "error": True}}
        # Deterministic client-facing front matter. The schedule owns this wording so the
        # model cannot omit branding, reporting window, cut-off or evidence limitations.
        _run_date = f"{_today.day} {_today.strftime('%B %Y')}"

        def _expand_front_matter(value: Any) -> str:
            """Expand schedule-owned current-date tokens for client-facing front matter."""

            return (
                str(value)
                .replace("{run_date}", _run_date)
                .replace("{current_date}", _today.isoformat())
                .strip()
            )

        _front_matter: List[str] = []
        if _defaults.get("reporting_period"):
            _front_matter.append(
                "Reporting period: "
                + _expand_front_matter(_defaults["reporting_period"])
            )
        if _defaults.get("introduction"):
            _front_matter.append(_expand_front_matter(_defaults["introduction"]))
        if _front_matter:
            _front = "\n\n".join(_front_matter)
            _title_match = re.match(r"^(#\s+[^\n]+\n)", str(doc))
            if _title_match:
                doc = str(doc)[:_title_match.end()] + "\n" + _front + "\n" + str(doc)[_title_match.end():].lstrip("\n")
            else:
                doc = _front + "\n\n" + str(doc)
        # Additive visuals: render real-backdrop maps + varied charts as inline CID figures.
        # Best-effort — any render failure is skipped so the report still delivers (the depth
        # fix in compose_report/publish_document is untouched when no `visuals` spec is given).
        _inline_images: List[Dict[str, Any]] = []
        _figures: List[Dict[str, Any]] = []
        _visuals_spec = _defaults.get("visuals")
        # Merge the rotated theme's per-zone geopolitical map into the visuals so the themed
        # researcher always carries a map of the current zone (placed first).
        if _zone_map:
            _visuals_spec = dict(_visuals_spec) if isinstance(_visuals_spec, dict) else {}
            _visuals_spec["maps"] = [_zone_map] + list(_visuals_spec.get("maps") or [])
        # Merge the rotated theme's own data charts (real sql-agent chart where the dataset covers
        # the theme; web-extracted chart where it does not) into the visuals.
        if _theme_charts:
            _visuals_spec = dict(_visuals_spec) if isinstance(_visuals_spec, dict) else {}
            _visuals_spec["charts"] = list(_theme_charts) + list(_visuals_spec.get("charts") or [])
        # Web-extracted-data charts: for any chart carrying ``web_extract``, pull real figures from
        # the current web sources (already retrieved for grounding) and fill the chart's rows — so
        # the report can chart genuine current data even where the SQL dataset has none. A chart
        # whose extraction yields nothing is dropped (best-effort).
        if isinstance(_visuals_spec, dict) and _visuals_spec.get("charts"):
            _kept = []
            for _c in _visuals_spec["charts"]:
                if isinstance(_c, dict) and _c.get("web_extract"):
                    _we = _c.get("web_extract") or {}
                    _topic = str(_we.get("topic") or _target or _defaults.get("title") or "")
                    _pts = await tool_adapter._extract_data_points(_topic, int(_we.get("max_points") or 7))
                    if not _pts:
                        logger.info("document pipeline: web_extract chart %r found no figures; skipping", _c.get("id"))
                        continue
                    _c = dict(_c)
                    _c["rows"], _c["x"], _c["y"] = _pts, "label", "value"
                    _c.setdefault("chart_type", "hbar")
                _kept.append(_c)
            _visuals_spec["charts"] = _kept
        # Specialise the rotating country report's visuals to the selected country: interpolate
        # {country} across map/chart titles, captions and SQL questions, and stamp the country's
        # precomputed geopolitical bbox on any map flagged ``rotate_bbox``.
        if _country and isinstance(_visuals_spec, dict):
            _visuals_spec = _interp_country(_visuals_spec, _country)
            if _country_bbox:
                for _m in _visuals_spec.get("maps") or []:
                    if isinstance(_m, dict) and _m.get("rotate_bbox"):
                        _m["bbox"] = _country_bbox
        if isinstance(_visuals_spec, dict):
            from src.core.execution import visuals as _visuals_mod
            try:
                _inline_images, _figures = await _visuals_mod.render_visuals(
                    _visuals_spec, _dispatch_service,
                    http_get=_make_http_get("chartmcpserver0"))
            except Exception as exc:
                logger.warning("document pipeline: render_visuals failed: %s", exc)
                _inline_images, _figures = [], []
            # Fail-closed visual contract (opt-in via visuals.require_all_rendered): every
            # declared map + chart MUST have produced a figure. render_visuals skips a failed
            # map/chart best-effort so the report still sends, but a report whose contract is
            # "one detailed map + N data charts" must not silently ship missing them (W28M-1635:
            # message 6790 shipped 7 context maps and 0 data charts and passed the gate).
            if _visuals_spec.get("require_all_rendered"):
                _declared = (len([m for m in (_visuals_spec.get("maps") or []) if isinstance(m, dict)])
                             + len([c for c in (_visuals_spec.get("charts") or []) if isinstance(c, dict)]))
                if len(_figures) < _declared:
                    raise RuntimeError(
                        "VISUAL_CONTRACT: FAIL declared=%d rendered=%d - a declared map or chart "
                        "failed to render; failing closed rather than delivering an incomplete report"
                        % (_declared, len(_figures)))
        # Content-driven embellishment (opt-in via spec.auto_visuals): for each section, add a
        # satellite/topo detail map of the places it names and a licence-cleared Wikimedia Commons
        # image of a concrete subject it mentions — appended to the spec-declared visuals, with a
        # credits block carrying each image's author, licence and source link.
        _av = _defaults.get("auto_visuals")
        if isinstance(_av, dict) and _av.get("enabled"):
            try:
                # Reuse the theatre map's areas-of-control + line of contact so the per-section
                # detail maps show the territorial situation (front line), not just place markers.
                _theatre = next((m for m in (_visuals_spec.get("maps") or [])
                                 if isinstance(m, dict)), {}) if isinstance(_visuals_spec, dict) else {}
                _ctrl = [a for a in (_theatre.get("control") or []) if isinstance(a, dict) and a.get("coords")]
                _flines = [
                    line
                    for line in (_theatre.get("lines") or [])
                    if isinstance(line, dict) and line.get("coords")
                ]
                _ai, _af, _credits_md = await tool_adapter._auto_section_visuals(
                    doc, map_style=str(_av.get("map_style") or "satellite"),
                    max_images=int(_av.get("max_images") or 6),
                    control=_ctrl or None, front_lines=_flines or None,
                    topic=str(_defaults.get("title") or _target or ""))
                _inline_images = list(_inline_images) + _ai
                _figures = list(_figures) + _af
                if _credits_md:
                    doc = doc + "\n\n" + _credits_md
            except Exception as exc:
                logger.warning("document pipeline: auto section visuals failed: %s", exc)
        # Previous-reports links: the static spec list (e.g. the deep monthly assessment) MERGED
        # with prior editions of this series auto-discovered from the notification message archive
        # (each linked to its /messages/<id> permalink), so the brief points to recent 7-day
        # editions as well as any curated links. De-duplicated by URL, static entries first.
        _prev = list(_defaults.get("previous_reports") or [])
        _series = _defaults.get("report_series")
        if _series:
            try:
                _auto = await tool_adapter._previous_editions(
                    str(_series), str(_defaults.get("messages_base_url") or ""),
                    exclude_subject=str(_defaults.get("title") or ""), limit=3)
                _have = {str(r.get("url")) for r in _prev if isinstance(r, dict)}
                _prev = _prev + [r for r in _auto if str(r.get("url")) not in _have]
            except Exception as exc:
                logger.warning("document pipeline: previous editions failed: %s", exc)
        # An on-demand / chat-launched report (free-text prompt) must ALWAYS deliver as a fresh
        # message — the publisher's default idempotency key is the title, which would otherwise
        # dedup a re-run of "the Peru country report" onto the previous edition. Give the on-demand
        # path a per-run unique key; the scheduled/template path keeps title-based idempotency so a
        # daily brief stays idempotent.
        _pub_args = {"content": doc, "current_year": _year,
                     "min_sections": len(_sections), "min_words": int(_tw) * max(1, len(_sections)) // 2,
                     "inline_images": _inline_images, "figures": _figures,
                     "previous_reports": _prev,
                     "quality_controls": _defaults.get("quality_controls") or {},
                     "brand": _defaults.get("brand")}
        # A durable MCP wait=false job supplies a stable delivery key.  If its
        # in-process worker is replaced, the resumed run cannot create a second
        # notification for the same accepted scheduler job.
        if params.get("delivery_idempotency_key"):
            _pub_args["idempotency_key"] = str(params["delivery_idempotency_key"])
        elif _nl_prompt:
            import datetime as _dtk
            _pub_args["idempotency_key"] = "%s|%s" % (
                _defaults.get("title") or "report", _dtk.datetime.now().isoformat(timespec="seconds"))
        published = await tool_adapter._publish_document(_pub_args)
        words = len(str(doc).split())
        return {"content": (f"Generated and delivered '{_defaults.get('title')}' — "
                            f"{len(_sections)} sections, ~{words} words, {len(_inline_images)} figures"
                            + (f" (template {_template_id})" if _template_id else "") + f". {published}"),
                "services_invoked": list(_svc_call_log),
                "agent_trace": {"strategy": "document", "sections": len(_sections),
                                "figures": len(_inline_images), "words": words,
                                "template_id": _template_id,
                                "tool_calls": [f"{c['service']}::{c['tool']}" for c in _svc_call_log]}}

    cfg = llm_cfg or {}
    max_iter = _as_int(params.get("max_iterations"), int(get_config("agent.max_iterations") or 12))
    max_wall = _as_int(params.get("max_wall_time_seconds"), int(get_config("agent.max_wall_time_seconds") or 600))
    memory_scope = str(params.get("memory_scope") or "none")
    # Orchestrator LLM config from the orchestrating expert (per-agent), call-params override.
    temperature = _as_float(params.get("temperature"), _as_float(cfg.get("temperature"), 0.3))
    max_tokens = _as_int(params.get("max_tokens"), _as_int(cfg.get("max_tokens"), 2000))
    num_ctx = params.get("num_ctx") or cfg.get("num_ctx")
    think = bool(params.get("think") if params.get("think") is not None else cfg.get("think"))

    llm_adapter = AgentLLMAdapter(
        executor.llm_manager, system_prompt, descriptors, temperature=temperature,
        max_tokens=max_tokens, num_ctx=(int(num_ctx) if num_ctx else None), think=think,
        allow_markdown_final=_agentic_document,
        before_generate=_release_db_transaction,
    )
    # FileMCP chunks are evidence artifacts, so their paths must be immutable
    # across separate deliveries of the same report title.  Keep the identity
    # fixed for all retries within this execution while giving every execution a
    # new namespace.
    model_authoring_run_id = uuid.uuid4().hex[:16] if _agentic_chunked_authoring else ""
    deferred_model_artifacts: List[Dict[str, str]] = []
    citation_selection_records: List[Dict[str, Any]] = []
    if (
        _agentic_chunked_authoring
        and tool_adapter._default_quality_controls.get("immutable_run_artifact_required")
    ):
        # The final report must have the same immutable identity as its staged
        # model-authored chunks.  This prevents later daily runs from replacing
        # the exact FileMCP artifact whose hash was delivered by email/PDF.
        # It is a configured storage-name operation only; report content stays
        # entirely model-authored and is still read back byte-for-byte.
        tool_adapter._default_working_path = _run_scoped_artifact_path(
            tool_adapter._default_working_path,
            model_authoring_run_id,
        )

    async def _author_large_agentic_document_chunks(
        *,
        authoring_attempt: int,
        deficit_ledger: str = "",
    ) -> tuple[str, List[Dict[str, Any]]]:
        """Have the model author an exact section chunk sequence for deferred persistence.

        This is intentionally an orchestration/storage primitive, not a report
        builder.  The LLM returns every byte of every chunk; the runtime writes
        each byte in request-scoped memory, validates the complete candidate, then
        persists and reloads the accepted immutable artifacts immediately before
        normal delivery. A rejected candidate has no FileMCP write side effect.
        No code path invents, patches, normalises, or repairs prose, citations,
        sources, recommendations, or visual rationale.
        """
        nonlocal deferred_model_artifacts
        deferred_model_artifacts = []
        sections = [
            section for section in (tool_adapter._default_sections or [])
            if isinstance(section, dict) and str(section.get("title") or "").strip()
        ]
        if not sections:
            raise RuntimeError("MODEL_AUTHORED_CHUNKS_REQUIRED: configured report sections are missing")
        unexpected_cjk_forbidden = bool(
            tool_adapter._default_quality_controls.get("unexpected_cjk_forbidden")
        )
        section_maximum_words: Dict[str, int] = {}
        configured_section_maximum_words = tool_adapter._default_quality_controls.get(
            "section_maximum_words"
        )
        if isinstance(configured_section_maximum_words, dict):
            for configured_title, configured_maximum in configured_section_maximum_words.items():
                title = re.sub(r"\s+", " ", str(configured_title)).strip()
                try:
                    maximum = max(1, int(configured_maximum))
                except (TypeError, ValueError):
                    continue
                if title:
                    section_maximum_words[title] = maximum

        def _is_source_section(section: Dict[str, Any]) -> bool:
            return bool(re.search(r"(?i)source|methodology", str(section.get("title") or "")))

        def _is_standalone_decision_section(section: Dict[str, Any]) -> bool:
            """Keep a decision/recommendation section in its own model turn.

            Recommendations are the reader's discrete decision surface.  When
            a long-report word floor groups them with outlook and risk sections,
            a model can spend its bounded turn on the preceding analysis and
            omit the final required heading.  This is model-turn scheduling
            only: the model remains the sole author of the recommendation and
            every other report word.
            """
            return bool(
                re.search(r"(?i)\brecommendations?\b", str(section.get("title") or ""))
            )

        def _is_bounded_section(section: Dict[str, Any]) -> bool:
            """Give a capped reader-critical section its own model completion.

            This is model-turn scheduling only. It prevents an otherwise valid
            concise section from being crowded by a neighbouring long analysis,
            while the model remains the sole author of every report word.
            """
            title = re.sub(r"\s+", " ", str(section.get("title") or "")).strip()
            return title in section_maximum_words

        def _is_table_planned_section(section: Dict[str, Any]) -> bool:
            """Give every explicitly planned table its own model completion.

            A table is a distinct reader-facing contract, not supporting prose
            for a neighbouring H2. Keeping the planned section isolated gives
            the model one bounded response to satisfy both the exact heading
            and the table grammar without dropping a later heading in a larger
            group. The runtime still only schedules and validates the turn;
            the model authors the table and all report text.
            """
            title = re.sub(r"\s+", " ", str(section.get("title") or "")).strip()
            return bool(_agentic_table_plan.get(title))

        non_source_sections = [section for section in sections if not _is_source_section(section)]
        source_sections = [section for section in sections if _is_source_section(section)]
        if not non_source_sections:
            raise RuntimeError("MODEL_AUTHORED_CHUNKS_REQUIRED: no narrative report sections configured")
        groups: List[List[Dict[str, Any]]] = []
        current: List[Dict[str, Any]] = []
        current_words = 0
        for section in non_source_sections:
            if (
                _is_standalone_decision_section(section)
                or _is_bounded_section(section)
                or _is_table_planned_section(section)
            ):
                if current:
                    groups.append(current)
                    current, current_words = [], 0
                groups.append([section])
                continue
            title = re.sub(r"\s+", " ", str(section.get("title") or "")).strip()
            section_words = section_word_floors.get(
                title,
                max(1, _as_int(section.get("target_words"), 1)),
            )
            if current and (
                len(current) >= _agentic_chunk_max_sections
                or current_words + section_words > _agentic_chunk_target_words
            ):
                groups.append(current)
                current, current_words = [], 0
            current.append(section)
            current_words += section_words
        if current:
            groups.append(current)
        # Keep the reader-facing Sources/Methodology tail in one final model
        # completion so it can resolve the exact citation markers actually used
        # by prior model-authored narrative chunks.
        if source_sections:
            groups.append(source_sections)

        working_path = str(tool_adapter._default_working_path or "").strip()
        profile = str(tool_adapter._default_profile or "google_drive").strip()
        identity = hashlib.sha256(
            (model_authoring_run_id + "|" + str(authoring_attempt)).encode("utf-8")
        ).hexdigest()[:16]
        used_markers: set[int] = set()
        chunks: List[str] = []
        chunk_records: List[Dict[str, Any]] = []
        narrative_group_count = len(groups) - (1 if source_sections else 0)
        reporting_period = str(_defaults.get("reporting_period") or "").strip()
        if reporting_period:
            reporting_period = reporting_period.replace(
                "{run_date}", _datetime.date.today().isoformat()
            )
        required_classification = str(
            tool_adapter._default_quality_controls.get("required_classification")
            or _defaults.get("introduction")
            or ""
        ).strip()
        required_reporting_period = str(
            tool_adapter._default_quality_controls.get("required_reporting_period")
            or reporting_period
            or ""
        ).strip()
        if required_reporting_period:
            required_reporting_period = required_reporting_period.replace(
                "{run_date}", _datetime.date.today().isoformat()
            )
        as_at_reporting_period_required = bool(
            tool_adapter._default_quality_controls.get("as_at_reporting_period_required")
            or required_reporting_period.lower().startswith("as at")
        )
        def _chunk_contract_issues(
            text: str,
            *,
            source_tail: bool,
            first_narrative_chunk: bool,
            existing_markers: set[int],
            required_new_markers: int,
            required_selected_markers: set[int],
            allowed_chunk_markers: Optional[set[int]],
            required_tables: int,
            maximum_words: int,
            required_heading_titles: List[str],
        ) -> List[str]:
            """Reject incomplete model chunks before final report assembly.

            A rejection is returned to the model as a request for a full
            replacement chunk. This runtime only validates; it never writes,
            patches, or synthesises report text, citations, or source lines.
            """
            issues: List[str] = []
            if unexpected_cjk_forbidden:
                cjk_match = re.search(r"[\u3400-\u4DBF\u4E00-\u9FFF\uF900-\uFAFF]", text)
                if cjk_match:
                    start = max(0, cjk_match.start() - 25)
                    snippet = re.sub(
                        r"\s+", " ", text[start:cjk_match.end() + 25]
                    ).strip()[:80]
                    issues.append(
                        f"unexpected CJK glyph '{cjk_match.group(0)}' near: '{snippet}' — "
                        "re-author the affected English prose"
                    )
            forbidden_hits = _configured_forbidden_content_hits(
                text,
                tool_adapter._default_quality_controls,
            )
            if forbidden_hits:
                categories = sorted({str(hit.get("category") or "forbidden") for hit in forbidden_hits})
                issues.append(
                    "configured forbidden-content policy hit in model-authored chunk "
                    f"category/categories: {', '.join(categories)}; re-author with neutral "
                    "economic-geography and public-infrastructure wording, and do not quote, "
                    "enumerate, or paraphrase caller policy controls"
                )
            actual_h2_titles = [
                title.strip()
                for title in re.findall(r"(?m)^##\s+(.+?)\s*$", text)
            ]
            missing_h2_titles = [
                title for title in required_heading_titles
                if actual_h2_titles.count(title) == 0
            ]
            duplicate_h2_titles = [
                title for title in required_heading_titles
                if actual_h2_titles.count(title) > 1
            ]
            unexpected_h2_titles = [
                title for title in actual_h2_titles
                if title not in required_heading_titles
            ]
            if missing_h2_titles:
                issues.append(
                    "chunk is missing exact required H2 heading(s): "
                    + ", ".join(missing_h2_titles)
                )
            if duplicate_h2_titles:
                issues.append(
                    "chunk repeats required H2 heading(s): "
                    + ", ".join(duplicate_h2_titles)
                )
            if unexpected_h2_titles:
                issues.append(
                    "chunk contains unrequested H2 heading(s): "
                    + ", ".join(sorted(set(unexpected_h2_titles)))
                )
            for title in required_heading_titles:
                section_word_minimum = section_quality_word_minima.get(title)
                section_word_limit = section_maximum_words.get(title)
                section_match = re.search(
                    r"(?ms)^##\s+" + re.escape(title) + r"\s*$\n?(.*?)(?=^##\s+|\Z)",
                    text,
                )
                if not section_match:
                    continue
                actual_words = len(re.findall(r"\w+", section_match.group(1)))
                if (
                    section_word_minimum is not None
                    and actual_words < section_word_minimum
                ):
                    issues.append(
                        "section_words: "
                        f"{title!r} has {actual_words} words; minimum is {section_word_minimum}"
                    )
                if section_word_limit is not None and actual_words > section_word_limit:
                    issues.append(
                        "section_words: "
                        f"{title!r} has {actual_words} words; maximum is {section_word_limit}"
                    )
            if source_tail:
                source_entries = {
                    int(marker): url.rstrip(".,;:")
                    for marker, url in re.findall(
                        r"(?m)^\s*\[(\d+)\]\s+.*?(https?://\S+)", text
                    )
                }
                source_markers = set(source_entries)
                missing = sorted(existing_markers - source_markers)
                unexpected = sorted(source_markers - existing_markers)
                if missing:
                    issues.append(
                        "source register is missing required marker(s): "
                        + ", ".join(f"[{marker}]" for marker in missing)
                    )
                if unexpected:
                    issues.append(
                        "source register contains marker(s) unused by the narrative: "
                        + ", ".join(f"[{marker}]" for marker in unexpected)
                    )
                if len(source_markers) < minimum_external_links:
                    issues.append(
                        f"source register has {len(source_markers)} direct URL marker(s); "
                        f"{minimum_external_links} required"
                    )
                if governed_source_urls:
                    mismatched_urls = [
                        f"[{marker}] uses {source_entries.get(marker) or '<missing URL>'}; "
                        f"current-run live-verified URL is {governed_source_urls[marker]}"
                        for marker in sorted(existing_markers)
                        if marker in governed_source_urls
                        and source_entries.get(marker) != governed_source_urls[marker]
                    ]
                    if mismatched_urls:
                        issues.append(
                            "source register URL(s) do not match the current-run live-verified allowlist: "
                            + " | ".join(mismatched_urls)
                        )
                    allowed_urls = set(governed_source_urls.values())
                    all_tail_urls = [
                        url.rstrip(".,;:")
                        for url in re.findall(r"https?://\S+", text)
                    ]
                    unallowlisted_urls = [url for url in all_tail_urls if url not in allowed_urls]
                    if unallowlisted_urls:
                        issues.append(
                            "source register contains URL(s) outside the current-run live-verified allowlist: "
                            + ", ".join(sorted(set(unallowlisted_urls)))
                        )
                return issues

            repetition_contract = (
                tool_adapter._default_quality_controls.get("repetition")
                if isinstance(
                    tool_adapter._default_quality_controls.get("repetition"),
                    dict,
                )
                else {}
            )
            if repetition_contract.get("required"):
                assembled_candidate = "\n\n".join([*chunks, text])
                repetition = _configured_repetition_metrics(
                    assembled_candidate,
                    tool_adapter._default_quality_controls,
                )
                current_titles = set(required_heading_titles)
                duplicate_paragraphs = [
                    item
                    for item in repetition["duplicate_paragraphs"]
                    if current_titles.intersection(item["sections"])
                ]
                repeated_ngrams = [
                    item
                    for item in repetition["repeated_ngrams"]
                    if current_titles.intersection(item["sections"])
                ]
                affected_titles = sorted({
                    title
                    for item in [*duplicate_paragraphs, *repeated_ngrams]
                    for title in item["sections"]
                    if title in current_titles
                })
                affected = ", ".join(affected_titles) or ", ".join(required_heading_titles)
                if duplicate_paragraphs:
                    issues.append(
                        "repetitive_prose: current chunk contains "
                        f"{len(duplicate_paragraphs)} repeated substantive paragraph(s) "
                        "within itself or accepted earlier chunks; affected current section(s): "
                        + affected
                    )
                if repeated_ngrams:
                    collision_examples = " | ".join(
                        str(item.get("phrase") or "")
                        for item in repeated_ngrams[:5]
                        if str(item.get("phrase") or "")
                    )
                    issues.append(
                        "repetitive_prose: current chunk contains "
                        f"{len(repeated_ngrams)} repeated "
                        f"{repetition['ngram_words']}-word phrase(s) within itself or accepted "
                        "earlier chunks; affected current section(s): "
                        + affected
                        + (
                            "; exact normalized collision(s): " + collision_examples
                            if collision_examples
                            else ""
                        )
                    )

            if first_narrative_chunk:
                if required_classification and required_classification not in text:
                    issues.append(
                        "required classification/framing line is missing from the first model-authored chunk"
                    )
                if required_reporting_period and required_reporting_period not in text:
                    issues.append(
                        "required reporting period is missing from the first model-authored chunk"
                    )
            if as_at_reporting_period_required and _as_of_temporal_framing_hits(text):
                issues.append(
                    "forbidden 'As of' temporal framing appears under an 'As at' reporting-period contract"
                )
            markers = {int(marker) for marker in re.findall(r"\[(\d+)\]", text)}
            # Every model-authored narrative checkpoint must retain at least
            # one resolving citation.  Intermediate chunks may reuse a
            # previously selected source, but an uncited chunk is never an
            # acceptable way to defer the document-level distinct-marker
            # floor to the final narrative checkpoint.
            if not markers:
                issues.append(
                    "chunk contains no resolving inline citation marker; every narrative chunk "
                    "must cite its factual analysis"
                )
            # A narrative chunk must never be allowed to introduce a citation
            # marker which the current-run research preflight did not govern.
            # Otherwise an invented marker can satisfy the incremental-count
            # check and only become visible at the final Sources checkpoint,
            # after every later chunk has already been authored.  This is a
            # validation boundary: the model receives a full replacement
            # request; runtime code neither substitutes a source nor repairs
            # any report prose.
            unavailable_markers = sorted(
                marker for marker in markers if marker < 1 or marker > source_count
            )
            if unavailable_markers:
                issues.append(
                    "chunk uses citation marker(s) outside the governed current-run source register "
                    + f"[1] through [{source_count}]: "
                    + ", ".join(f"[{marker}]" for marker in unavailable_markers)
                )
            new_markers = (markers & set(range(1, source_count + 1))) - existing_markers
            missing_selected_markers = sorted(required_selected_markers - markers)
            if missing_selected_markers:
                issues.append(
                    "chunk omits model-selected mandatory citation marker(s): "
                    + ", ".join(f"[{marker}]" for marker in missing_selected_markers)
                )
            unselected_markers = sorted(
                markers - allowed_chunk_markers
                if allowed_chunk_markers is not None
                else set()
            )
            if unselected_markers:
                issues.append(
                    "chunk uses citation marker(s) outside the model-selected per-chunk "
                    "allowlist: "
                    + ", ".join(f"[{marker}]" for marker in unselected_markers)
                )
            word_count = len(re.findall(r"\w+", text))
            if word_count > maximum_words:
                issues.append(
                    f"chunk contains {word_count} words; the configured maximum is "
                    f"{maximum_words}"
                )
            if required_tables:
                table_count = len(
                    re.findall(
                        r"^\s*\|?(?:\s*:?-{3,}:?\s*\|){2,}\s*$",
                        text,
                        re.MULTILINE,
                    )
                )
                if table_count < required_tables:
                    issues.append(
                        f"tables: {table_count} of {required_tables} required structured tables "
                        "in this model-authored chunk"
                    )
            if len(new_markers) < required_new_markers:
                issues.append(
                    f"chunk introduces {len(new_markers)} new citation marker(s); "
                    f"{required_new_markers} required"
                )
            uncited_numeric_blocks: List[str] = []
            for block in re.split(r"\n\s*\n", text):
                stripped = _narrative_text_from_markdown_block(block)
                if not stripped or stripped.startswith("|"):
                    continue
                metadata_block = re.sub(r"[*_`]", "", stripped).strip()
                if re.match(r"(?i)^reporting period\s*:", metadata_block):
                    continue
                if _is_reporting_window_table_leadin(stripped):
                    continue
                if _is_relative_window_only_narrative(stripped):
                    continue
                if _block_has_citable_numeric_claim(stripped) and not re.search(r"\[\d+\]", stripped):
                    uncited_numeric_blocks.append(re.sub(r"\s+", " ", stripped)[:180])
            if uncited_numeric_blocks:
                issues.append(
                    f"{len(uncited_numeric_blocks)} numeric narrative block(s) lack an inline [n] citation: "
                    + " | ".join(repr(block) for block in uncited_numeric_blocks[:4])
                )
            return issues

        for index, group in enumerate(groups, 1):
            titles = [str(section.get("title") or "").strip() for section in group]
            source_tail = bool(source_sections and index == len(groups))
            planned_tables = sum(_agentic_table_plan.get(title, 0) for title in titles)
            group_floor = sum(
                section_word_floors.get(
                    re.sub(r"\s+", " ", str(section.get("title") or "")).strip(),
                    max(1, _as_int(section.get("target_words"), 1)),
                )
                for section in group
            )
            chunk_word_ceiling = max(
                group_floor,
                _as_int(
                    tool_adapter._default_quality_controls.get(
                        "model_authored_chunk_max_words"
                    ),
                    _agentic_chunk_target_words * 2,
                ),
            )
            # This is a model-generation configuration, not a content repair:
            # constrain each response to the small, declared section group so a
            # long-context model cannot emit an entire report for one chunk. The
            # lower bound accommodates compact source/provenance tails, while the
            # upper bound leaves the model enough space to meet each group floor.
            bounded_group_titles = [
                title for title in titles if title in section_maximum_words
            ]
            if bounded_group_titles:
                bounded_group_budget = sum(
                    section_word_floors.get(title, section_maximum_words[title])
                    for title in bounded_group_titles
                )
                # Bound the model response itself for a capped section. This
                # is a generation parameter, not a post-generation truncation:
                # the model must author a complete concise replacement inside
                # the declared envelope.
                chunk_generation_max_tokens = min(
                    max_tokens,
                    max(300, min(1600, (bounded_group_budget * 14 + 9) // 10)),
                )
            else:
                chunk_generation_max_tokens = min(
                    max_tokens,
                    max(1800, min(3000, (group_floor * 17 + 9) // 10)),
                )
            if source_tail and used_markers:
                # A source/provenance tail has an output floor determined by
                # the exact, model-selected citation register rather than its
                # prose word target.  Give the model enough bounded response
                # capacity to emit one complete URL line for each marker; do
                # not truncate, split, or synthesize a tail in runtime code.
                source_tail_response_budget = 384 + sum(
                    max(
                        120,
                        (len(governed_source_urls.get(marker, "")) + 182) // 3,
                    )
                    for marker in used_markers
                )
                chunk_generation_max_tokens = min(
                    max_tokens,
                    max(
                        chunk_generation_max_tokens,
                        min(6000, source_tail_response_budget),
                    ),
                )
            heading_contract = (
                "EXACT HEADING ALLOWLIST: your raw Markdown output must contain exactly "
                f"{len(titles)} H2 heading line(s), in this exact order: "
                + "; ".join(f"## {title}" for title in titles)
                + ". These are the ONLY permitted Markdown heading lines in this chunk. "
                "Do not repeat them, do not introduce any other #/##/### heading, and express "
                "all supporting labels as ordinary prose or list text."
            )
            table_contract = ""
            if planned_tables:
                table_contract = (
                    "MODEL-OWNED TABLE REQUIREMENT: this chunk owns "
                    f"{planned_tables} of the report's required structured table(s). Author at least "
                    f"{planned_tables} complete reader-ready Markdown comparator table(s) in the named "
                    "section(s), each with a header row, separator row and evidence-bearing cells. "
                    "The tables must be meaningful rather than placeholders. TABLE-ADJACENT "
                    "NUMERIC-CITATION RULE: every narrative paragraph that introduces, explains, "
                    "or concludes a planned table and contains any digit, percentage, date, count, "
                    "or ranking must include a resolving inline [n] citation in that same paragraph. "
                    "When no governed source supports the number, write the paragraph qualitatively "
                    "without digits.\n"
                )
            elif minimum_tables and any(
                re.search(r"(?i)comparative|comparator|benchmark", title)
                for title in titles
            ):
                table_contract = (
                    "MODEL-OWNED TABLE REQUIREMENT: this chunk contains the configured comparison "
                    "section. Author at least one complete reader-ready Markdown comparator table in "
                    "that section, with a header row, separator row and evidence-bearing cells. The "
                    "table must be meaningful rather than a placeholder.\n"
                )
            citation_selection_contract: Dict[str, Any] = {}
            citation_selection_required = False
            if source_tail:
                marker_text = ", ".join(f"[{marker}]" for marker in sorted(used_markers)) or "(none)"
                source_tail_url_allowlist = "\n".join(
                    f"[{marker}] {governed_source_urls[marker]}"
                    for marker in sorted(used_markers)
                    if marker in governed_source_urls
                )
                chunk_instruction = (
                    "MODEL-OWNED CHUNK PROTOCOL. Author ONLY the final required H2 section(s) listed "
                    "below. Begin exactly `FINAL_REPORT_CHUNK` on its own line, then return raw Markdown. "
                    "Do not include a title, preamble, earlier section, tool action, or explanation. "
                    "For every cited narrative marker listed below, write exactly one model-authored final "
                    "numbered source line in the form `[n] source title — https://direct-url`. The list is "
                    "exhaustive: before returning, count the lines and confirm that every listed marker has "
                    "one line, with no omitted marker, range shorthand, substitute marker, or unused marker. "
                    "The source allowlist is a lookup only, not a request to list every researched source: "
                    "omit every marker that is not in the narrative citation marker list. "
                    "Use only the governed source register. The Methodology prose, provenance and limitations "
                    "are also model-authored. "
                    f"Write at least {group_floor} substantive words across this source and methodology "
                    "chunk, including concise provenance, relevance and limitation context for the cited "
                    "sources; preserve every exact marker-to-URL mapping.\n\n"
                    f"Required final H2 section(s): {', '.join('## ' + title for title in titles)}\n"
                    f"Narrative citation markers that must resolve exactly: {marker_text}\n"
                    + (
                        "EXCLUSIVE CURRENT-RUN LIVE-VERIFIED SOURCE URL ALLOWLIST: for each [n] "
                        "line, copy the matching URL below byte-for-byte. Do not substitute a familiar, "
                        "archived, redirected, guessed, or previously failed URL. No other external URL "
                        "may appear in this chunk.\n"
                        + source_tail_url_allowlist
                        + "\n"
                        if source_tail_url_allowlist else ""
                    )
                    + heading_contract
                    + "\n"
                    + (f"Previous validation deficits to avoid: {deficit_ledger}\n" if deficit_ledger else "")
                )
            else:
                configured_citation_selection = (
                    tool_adapter._default_quality_controls.get(
                        "model_authored_citation_selection"
                    )
                )
                citation_selection_contract = (
                    configured_citation_selection
                    if isinstance(configured_citation_selection, dict)
                    else {}
                )
                citation_selection_required = bool(
                    citation_selection_contract.get("required")
                )
                remaining_groups = max(1, narrative_group_count - index + 1)
                still_needed = max(0, minimum_citation_markers - len(used_markers))
                new_markers_needed = (
                    max(1, (still_needed + remaining_groups - 1) // remaining_groups)
                    if still_needed else 0
                )
                unused_governed_markers = [
                    marker for marker in range(1, source_count + 1)
                    if marker not in used_markers
                ]
                unused_governed_source_rows = _source_register_rows_for_markers(
                    preflight_source_register,
                    unused_governed_markers,
                )
                available_marker_contract = (
                    "A separate model-owned citation-selection checkpoint will provide the exact "
                    "active marker-to-source binding for this chunk. That selected set is the closed "
                    "per-chunk citation allowlist.\n"
                    if citation_selection_required and new_markers_needed else
                    "AVAILABLE UNUSED GOVERNED MARKERS: "
                    + ", ".join(f"[{marker}]" for marker in unused_governed_markers)
                    + ". Select and introduce at least "
                    + str(new_markers_needed)
                    + " of these exact unused markers in distinct, evidence-supported claims in this "
                    "narrative chunk. This proportional hand-off prevents the document-level citation "
                    "minimum from accumulating at the final narrative checkpoint. "
                    + (
                        "EXACT UNUSED GOVERNED SOURCE LOOKUP:\n"
                        + unused_governed_source_rows
                        + "\nUse these exact rows to select evidence-supported claims; do not infer "
                        "a source from its marker number alone. "
                        if unused_governed_source_rows else ""
                    )
                    if new_markers_needed and unused_governed_markers else ""
                )
                citation_contract = (
                    "HARD CITATION COVERAGE: preserve resolving citations for every factual or numeric "
                    f"claim. The complete document must finish with at least {minimum_citation_markers} "
                    f"distinct inline citation markers and still needs {still_needed}. Introduce at least "
                    f"{new_markers_needed} new resolving marker(s) in this chunk before returning it; "
                    "each new marker must support a distinct claim."
                    if new_markers_needed else
                    "CITATION COVERAGE: preserve resolving citations for every factual or numeric "
                    "claim. The document-level distinct-marker minimum is already represented by "
                    "accepted earlier chunks; reuse the correct governed evidence for this chunk."
                )
                paragraph_citation_contract = ""
                if (
                    quality_controls.get("citation_markers_resolve_required")
                    or quality_controls.get("numeric_claim_citations_required")
                ):
                    paragraph_citation_contract = (
                        "PARAGRAPH CITATION FORMAT: every non-heading narrative paragraph and bullet "
                        "must contain at least one resolving inline [n] marker from the governed source "
                        "register. This includes the first body paragraph, BLUF sentences, map/context "
                        "descriptions, confidence prose, and any block that repeats the reporting date. "
                        "Do not return an uncited introductory or transition paragraph.\n"
                    )
                marker_introduction_instruction = (
                    "Use every marker chosen by the separate model-owned citation-selection "
                    "checkpoint on a directly supported claim in this chunk. "
                    if citation_selection_required and new_markers_needed else
                    f"Choose and introduce at least {new_markers_needed} distinct resolving citation "
                    "marker(s) selected from this literal currently-unused governed set: "
                    + ", ".join(f"[{marker}]" for marker in unused_governed_markers)
                    + ". Place each selected marker on a claim that its registered source directly "
                    "supports; self-count the selected unused markers before returning. "
                    if new_markers_needed else
                    "Use an unused governed marker only where it directly supports a distinct claim; "
                    "reuse an existing allowed marker where it is the correct evidence. "
                )
                section_word_ceiling_contract = ""
                bounded_titles = [
                    title for title in titles if title in section_maximum_words
                ]
                if bounded_titles:
                    section_word_ceiling_contract = (
                        "SECTION WORD CEILINGS: "
                        + "; ".join(
                            f"{title} must contain no more than "
                            f"{section_maximum_words[title]} substantive words"
                            for title in bounded_titles
                        )
                        + ". Use these safety budgets while drafting: "
                        + "; ".join(
                            f"{title} no more than "
                            f"{max(section_word_floors.get(title, 1), section_maximum_words[title] - max(40, section_maximum_words[title] // 5))} "
                            "substantive words"
                            for title in bounded_titles
                        )
                        + ". Count each bounded H2 section yourself before returning; runtime will "
                        "reject rather than trim or rewrite any over-limit prose.\n\n"
                    )
                chunk_requirements: List[str] = []
                if index == 1 and required_classification:
                    chunk_requirements.append(
                        "Start the first narrative chunk with this exact standalone classification/framing line: "
                        f"`{required_classification}`."
                    )
                if index == 1 and reporting_period:
                    chunk_requirements.append(
                        "Include this exact standalone declaration in the Executive Summary: "
                        f"`Reporting period: {reporting_period}`."
                    )
                    chunk_requirements.append(
                        "FIRST-CHUNK CITATION FLOOR: the first non-heading narrative paragraph after "
                        "front matter must include a resolving [n] marker. Do not begin with an uncited "
                        "`As at` sentence or any uncited date-bearing summary."
                    )
                if as_at_reporting_period_required:
                    chunk_requirements.append(
                        "TEMPORAL-FRAMING SELF-CHECK: use the configured `As at` reporting-period wording exactly. "
                        "Before returning, scan every paragraph opening and reporting-period label: none may begin "
                        "with `As of`; use `As at` or rephrase the sentence."
                    )
                if planned_tables:
                    chunk_requirements.append(
                        f"Include at least {planned_tables} decision-useful Markdown comparator table(s) "
                        "in this chunk; use a header row and Markdown separator row for each table."
                    )
                    chunk_requirements.append(
                        "For planned-table introductions, explanations and conclusions, cite every "
                        "numeric narrative block with an inline [n] marker in that same block; remove "
                        "digits rather than returning an unsupported numeric statement."
                    )
                elif minimum_tables and any(
                    re.search(r"(?i)comparative|comparator|benchmark", title)
                    for title in titles
                ):
                    chunk_requirements.append(
                        f"Include at least {minimum_tables} decision-useful Markdown comparator table(s) "
                        "in this chunk; use a header row and Markdown separator row for each table."
                    )
                chunk_requirements.append(
                    "STRICT NUMERIC BLOCK SELF-AUDIT: before returning, inspect every non-heading "
                    "narrative Markdown block for every digit. Each paragraph, bullet, or table-adjacent "
                    "explanatory block containing a year, date, range, number, percentage, quantity, "
                    "statistic, forecast, figure/chart label, reporting-period date, or numbered-list item "
                    "must include a resolving inline [n] citation in that same Markdown block. There are "
                    "no exceptions. If a numeric block cannot be supported by the governed source register, "
                    "rewrite that block without digits rather than returning an uncited numeric claim."
                )
                chunk_requirements.append(
                    "SECTION-CLOSING PARAGRAPH RULE: the final paragraph of this chunk, and any "
                    "paragraph beginning 'In summary', 'Overall', 'In conclusion' or 'Taken "
                    "together', must contain NO digits at all — no years, counts, percentages, "
                    "ranks or scores. State direction and standing in words only; every figure "
                    "belongs in an earlier evidence sentence that carries its inline [n] marker, "
                    "or in a table. Before returning, re-read your final paragraph and rewrite it "
                    "without numerals if it contains any digit."
                )
                if any(re.search(r"\boutlook\b", title, flags=re.IGNORECASE) for title in titles):
                    chunk_requirements.append(
                        "OUTLOOK-SPECIFIC NUMERIC CONCLUSION RULE: do not write `next 12 months` or "
                        "any digit-based timeframe in an outlook conclusion unless that same paragraph "
                        "contains a resolving [n] citation. When the governed source register does not "
                        "support the timeframe, write `the outlook period` instead. Complete a final "
                        "model self-audit for `12` and `next 12 months` before returning this chunk."
                    )
                script_integrity_contract = (
                    "SCRIPT INTEGRITY: author reader-facing prose in English using Latin characters and "
                    "ordinary punctuation only. Before returning, scan the complete chunk and remove any "
                    "Chinese, Japanese, Korean, or other unexpected CJK glyph; runtime will reject rather "
                    "than repair a contaminated model completion.\n"
                    if unexpected_cjk_forbidden else ""
                )
                section_depth_shapes: Dict[str, tuple[int, int, int]] = {}
                if not source_tail:
                    for title in titles:
                        required_words = section_word_floors.get(title)
                        if required_words is None:
                            continue
                        safety_target = required_words + max(80, required_words // 4)
                        paragraph_count = max(3, (safety_target + 89) // 90)
                        paragraph_floor = max(70, (safety_target + paragraph_count - 1) // paragraph_count)
                        section_depth_shapes[title] = (
                            paragraph_count,
                            paragraph_floor,
                            paragraph_floor + 25,
                        )
                section_depth_shape_contract = ""
                if section_depth_shapes:
                    section_depth_shape_contract = (
                        "SECTION DEPTH SHAPE: use blank-line-separated narrative paragraphs so the "
                        "required depth is concrete rather than aspirational. After each H2, author "
                        "exactly this model-owned paragraph shape: "
                        + "; ".join(
                            f"{title}: {paragraph_count} substantive paragraphs of "
                            f"{paragraph_floor}-{paragraph_ceiling} words each"
                            for title, (
                                paragraph_count,
                                paragraph_floor,
                                paragraph_ceiling,
                            ) in section_depth_shapes.items()
                        )
                        + ". A table, heading, classification line, reporting-period declaration, "
                        "caption or list label does not count as one of these narrative paragraphs. "
                        "Every paragraph must add distinct source-grounded analysis and carry a "
                        "resolving inline [n] marker. Self-count paragraphs and words before returning; "
                        "runtime will reject rather than expand or repair shallow prose.\n\n"
                    )
                chunk_instruction = (
                    "MODEL-OWNED CHUNK PROTOCOL. Author ONLY the exact required H2 section(s) listed "
                    "below for one larger report. Begin exactly `FINAL_REPORT_CHUNK` on its own line, then "
                    "return raw reader-ready Markdown. Do not include a title, preamble, Sources/Methodology, "
                    "a tool action, an outline, or an explanation. Use the governed source register; every "
                    "factual or numeric claim must carry a resolving inline [n] marker. "
                    + marker_introduction_instruction
                    + (
                        "The separate evidence-selection checkpoint supplies the complete exclusive "
                        "marker namespace for this chunk below. Marker labels are opaque source IDs: "
                        "copy each selected token literally and never renumber it by list position. "
                        if citation_selection_required and new_markers_needed else
                        f"The exclusive marker range is [1] through [{source_count}]. Never invent, "
                        "increment, or cite a marker outside that range; reuse an allowed marker or "
                        "re-author an unsupported claim without a factual assertion. "
                    )
                    + (
                        "PERMITTED INLINE CITATION TOKENS FOR THIS CHUNK are assigned by the separate "
                        "model-owned selection checkpoint below. Use only that exact selected set. "
                        if citation_selection_required and new_markers_needed else
                        "PERMITTED INLINE CITATION TOKENS FOR THIS CHUNK: "
                        + ", ".join(f"[{marker}]" for marker in range(1, source_count + 1))
                        + ". These are a closed lookup set, not a sequential footnote counter: after the last "
                        "permitted token, reuse a supporting token from this list. Never continue with a new "
                        "number. "
                    )
                    + f"Write at least {group_floor} substantive words across this chunk, with each H2 exactly once.\n\n"
                    f"Do not exceed {chunk_word_ceiling} words in this chunk; concise, decision-useful "
                    "analysis is required rather than exhaustive repetition.\n\n"
                    + section_word_ceiling_contract
                    + section_depth_shape_contract
                    + script_integrity_contract
                    + "Required H2 section(s), in this exact order:\n- "
                    + "\n- ".join(titles)
                    + "\n"
                    + heading_contract
                    + "\n"
                    + table_contract
                    + paragraph_citation_contract
                    + citation_contract
                    + "\n"
                    + (
                        "Earlier chunks already used other citation markers. Their marker IDs are "
                        "intentionally omitted because they are prohibited in this chunk.\n"
                        if citation_selection_required and new_markers_needed and used_markers else
                        f"Earlier chunks already used citation marker(s): "
                        f"{', '.join(f'[{m}]' for m in sorted(used_markers)) or '(none)'}.\n"
                    )
                    + available_marker_contract
                    + "Non-negotiable requirements for this chunk:\n- "
                    + "\n- ".join(chunk_requirements)
                    + "\n"
                    + (f"Previous validation deficits to avoid: {deficit_ledger}\n" if deficit_ledger else "")
            )
            selected_new_markers: set[int] = set()
            selected_source_rows = ""
            if (
                not source_tail
                and new_markers_needed
                and citation_selection_required
            ):
                if not unused_governed_source_rows:
                    raise RuntimeError(
                        "MODEL_AUTHORED_CITATION_SELECTION_FAILED: no exact governed source "
                        f"rows are available for chunk {index}"
                    )
                selection_adapter = AgentLLMAdapter(
                    executor.llm_manager,
                    (
                        "You are the model-owned evidence-selection checkpoint for a "
                        "source-grounded report. Select evidence only from the exact rows "
                        "provided by the user and obey the completion format."
                    ),
                    [],
                    temperature=0.0,
                    max_tokens=256,
                    num_ctx=(int(num_ctx) if num_ctx else None),
                    think=False,
                    allow_markdown_final=True,
                    markdown_completion_marker="FINAL_CITATION_SELECTION",
                    marked_final_payload_description=(
                        "only the exact requested bracketed citation marker tokens"
                    ),
                    before_generate=_release_db_transaction,
                )
                selection_attempts = max(
                    1,
                    min(
                        5,
                        _as_int(citation_selection_contract.get("max_attempts"), 3),
                    ),
                )
                rejected_selection = ""
                selection_error = ""
                selected_markers: List[int] = []
                for selection_attempt in range(1, selection_attempts + 1):
                    selection_prompt = _build_model_authored_citation_selection_prompt(
                        titles=titles,
                        required_count=new_markers_needed,
                        source_rows=unused_governed_source_rows,
                        rejected=rejected_selection,
                        last_error=selection_error,
                    )
                    parsed_selection = await selection_adapter.call(
                        [{"role": "user", "content": selection_prompt}]
                    )
                    rejected_selection = _final_text(
                        parsed_selection.get("final_answer"),
                        store,
                    )
                    selected_markers, selection_failures = (
                        _validate_model_authored_citation_selection(
                            rejected_selection,
                            allowed_markers=unused_governed_markers,
                            required_count=new_markers_needed,
                        )
                    )
                    citation_selection_records.append(
                        {
                            "authoring_attempt": authoring_attempt,
                            "chunk_index": index,
                            "section_titles": titles,
                            "selection_attempt": selection_attempt,
                            "required_count": new_markers_needed,
                            "selected_markers": selected_markers,
                            "failures": selection_failures,
                            "model_authored": True,
                        }
                    )
                    if not selection_failures:
                        break
                    selection_error = "; ".join(selection_failures)
                else:
                    raise RuntimeError(
                        "MODEL_AUTHORED_CITATION_SELECTION_FAILED: model did not select "
                        f"the governed evidence for chunk {index} after "
                        f"{selection_attempts} attempt(s): {selection_error}"
                    )
                selected_new_markers = set(selected_markers)
                selected_source_rows = _source_register_rows_for_markers(
                    preflight_source_register,
                    selected_markers,
                )
                if len(selected_source_rows.splitlines()) != len(selected_new_markers):
                    raise RuntimeError(
                        "MODEL_AUTHORED_CITATION_SELECTION_FAILED: selected marker-to-source "
                        f"readback is incomplete for chunk {index}"
                    )
                chunk_instruction += (
                    "\nFINAL MODEL-AUTHORED EVIDENCE BINDING FOR THIS CHUNK: the separate "
                    "model selection checkpoint chose "
                    + ", ".join(f"[{marker}]" for marker in selected_markers)
                    + ". Include every one of these exact markers on claims directly supported "
                    "by its row below. These are the ONLY permitted inline citation markers in "
                    "this chunk. Do not use an earlier-chunk marker or any other bracketed source "
                    "number. Marker labels are opaque IDs: copy the selected tokens byte-for-byte "
                    "and do not replace them with positional ordinals. This binding is "
                    "mandatory and supersedes the document-wide source register for this chunk.\n"
                    + selected_source_rows
                    + "\n"
                )
            active_chunk_system_prompt = system_prompt
            if selected_new_markers:
                selected_namespace_contract = (
                    "For this chunk, the selected governed source rows below are the complete "
                    "allowed citation namespace. Their bracketed marker labels are opaque source "
                    "IDs and must be copied literally; never renumber them by row position. "
                )
                if source_register_contract:
                    active_chunk_system_prompt = active_chunk_system_prompt.replace(
                        source_register_contract,
                        selected_namespace_contract,
                        1,
                    )
                if preflight_source_register:
                    active_chunk_system_prompt = active_chunk_system_prompt.replace(
                        preflight_source_register,
                        selected_source_rows,
                        1,
                    )
                active_chunk_system_prompt += (
                    "\n\nACTIVE MODEL-SELECTED CITATION BOUNDARY FOR THIS CHUNK\n"
                    "Use only these exact inline citation marker tokens in the chunk: "
                    + ", ".join(
                        f"[{marker}]" for marker in sorted(selected_new_markers)
                    )
                    + ". Include every token at least once on a claim directly supported by its "
                    "exact governed row. Any other bracketed source marker makes the whole chunk "
                    "invalid. These labels are opaque IDs: do not renumber them by selected-row "
                    "position. Exact governed rows:\n"
                    + selected_source_rows
                )
                active_chunk_system_prompt = _selected_citation_prompt_boundary(
                    active_chunk_system_prompt,
                    selected_new_markers,
                )
            def _new_chunk_adapter(
                prompt: str,
                *,
                attempt_temperature: float,
            ) -> AgentLLMAdapter:
                return AgentLLMAdapter(
                    executor.llm_manager,
                    prompt,
                    [],
                    temperature=attempt_temperature,
                    max_tokens=chunk_generation_max_tokens,
                    num_ctx=(int(num_ctx) if num_ctx else None),
                    think=think,
                    allow_markdown_final=True,
                    markdown_completion_marker="FINAL_REPORT_CHUNK",
                    before_generate=_release_db_transaction,
                )

            chunk_adapter = _new_chunk_adapter(
                active_chunk_system_prompt,
                attempt_temperature=temperature,
            )
            model_chunk = ""
            rejected_chunk_issues: List[str] = []
            rejected_chunk_text = ""
            chunk_authoring_attempts = max(
                1,
                min(
                    6,
                    _as_int(
                        tool_adapter._default_quality_controls.get(
                            "model_authored_chunk_retry_attempts"
                        ),
                        4,
                    ),
                ),
            )
            if planned_tables:
                # A table section has two exact output contracts (its H2 and
                # structured table) plus citation-bearing surrounding prose.
                # Keep retries model-owned and bounded, but allow two extra
                # complete reauthorings before a valid table section fails.
                chunk_authoring_attempts = max(chunk_authoring_attempts, 6)
            # A model can mistake inline source markers for a sequential
            # footnote counter late in a long report.  Give that validation
            # failure one additional complete, model-owned re-authoring turn;
            # no citation, source, or report text is synthesized by runtime
            # code.
            if source_count:
                chunk_authoring_attempts = max(chunk_authoring_attempts, 5)
            if quality_controls.get("numeric_claim_citations_required"):
                # Numeric-citation correction requires a complete model-authored
                # replacement. Keep that bounded, but provide enough independent
                # attempts for a long narrative chunk to satisfy its per-block
                # literal citation contract without runtime content repair.
                chunk_authoring_attempts = max(chunk_authoring_attempts, 8)
            for chunk_attempt in range(1, chunk_authoring_attempts + 1):
                numeric_citation_deficit = any(
                    "numeric narrative block(s) lack an inline" in issue
                    for issue in rejected_chunk_issues
                )
                numeric_only_deficit = (
                    numeric_citation_deficit
                    and all(
                        "numeric narrative block(s) lack an inline" in issue
                        for issue in rejected_chunk_issues
                    )
                )
                distinct_citation_deficit = any(
                    (
                        issue.startswith("chunk introduces ")
                        and "new citation marker(s)" in issue
                    )
                    or issue.startswith(
                        "chunk omits model-selected mandatory citation marker(s)"
                    )
                    or issue.startswith(
                        "chunk uses citation marker(s) outside the model-selected "
                        "per-chunk allowlist"
                    )
                    for issue in rejected_chunk_issues
                )
                structural_chunk_deficit = any(
                    "required H2 heading(s)" in issue
                    or "unrequested H2 heading(s)" in issue
                    for issue in rejected_chunk_issues
                )
                section_depth_deficit = any(
                    issue.startswith("section_words:") and "minimum is" in issue
                    for issue in rejected_chunk_issues
                )
                section_ceiling_deficit = any(
                    issue.startswith("section_words:") and "maximum is" in issue
                    for issue in rejected_chunk_issues
                )
                repetition_chunk_deficit = any(
                    issue.startswith("repetitive_prose:")
                    for issue in rejected_chunk_issues
                )
                retry_instruction = ""
                if rejected_chunk_issues:
                    overlength_retry_target = max(
                        1,
                        chunk_word_ceiling - min(600, max(200, chunk_word_ceiling // 6)),
                    )
                    retry_instruction = (
                        "\nMODEL-OWNED CHUNK VALIDATION REAUTHORING: the previous chunk was rejected "
                        "before assembly. Re-author the complete chunk, not a patch, and correct every "
                        f"item in this deficit ledger. This is replacement attempt {chunk_attempt} "
                        f"of {chunk_authoring_attempts}; discard every earlier rejected completion "
                        "and produce an independently authored replacement:\n- "
                        + "\n- ".join(rejected_chunk_issues)
                        + "\n"
                        + "ABSOLUTE RESPONSE BUDGET: before returning, self-count this one response. "
                        + f"It must contain fewer than {chunk_word_ceiling} words; do not return a whole "
                        + "report, Sources section, or any H2 outside the exact section list for this "
                        + "checkpoint. If material remains, reserve it for a later model-authored "
                        + "checkpoint rather than exceeding this response budget. Runtime code will not "
                        + "truncate, split, or repair an overlong response.\n"
                        + (
                            "OVERLENGTH RETRY RULE: the prior response exceeded the absolute limit. "
                            f"Re-author the complete chunk at no more than {overlength_retry_target} "
                            "words by your own count, leaving this safety buffer below the configured "
                            "maximum. Preserve only the most decision-useful cited analysis; do not "
                            "return any draft until your model self-count is within that lower target.\n"
                            if any(issue.startswith("chunk contains ") for issue in rejected_chunk_issues)
                            else ""
                        )
                        + (
                            "SECTION-CEILING RETRY RULE: the prior response exceeded a configured H2 "
                            "ceiling. Re-author the complete chunk with every bounded section at these "
                            "safety budgets: "
                            + "; ".join(
                                f"{title} no more than "
                                f"{max(section_word_floors.get(title, 1), section_maximum_words[title] - max(40, section_maximum_words[title] // 5))} words"
                                for title in titles
                                if title in section_maximum_words
                            )
                            + ". Keep only the most decision-useful cited analysis in that section. "
                            "Runtime will not trim, move, or repair any excess words.\n"
                            if section_ceiling_deficit
                            else ""
                        )
                        + (
                            "SECTION-DEPTH RETRY RULE: the prior response left one or more required "
                            "H2 sections below their configured substantive depth. Re-author the "
                            "complete chunk and make each deficient section reach these model-owned "
                            "safety targets: "
                            + "; ".join(
                                f"{title} at least "
                                f"{section_word_floors[title] + max(40, section_word_floors[title] // 8)} words"
                                for title in titles
                                if title in section_word_floors
                            )
                            + ". Add source-grounded doctrine analysis, implications, concrete facts "
                            "and a cited assessment; do not pad with repetition. Self-count each H2 "
                            "body independently before returning. Use the declared SECTION DEPTH SHAPE "
                            "for every deficient H2 and do not return a draft until both its paragraph "
                            "count and word floor pass. Runtime will reject rather than expand or repair "
                            "an underlength section.\n"
                            if section_depth_deficit
                            else ""
                        )
                        + (
                            "HEADING-INVENTORY RETRY RULE: discard prose for every H2 outside this "
                            "checkpoint. Re-author the complete chunk with exactly these H2 headings, "
                            "once each and in this order:\n- "
                            + "\n- ".join(titles)
                            + "\nDo not emit, continue, or summarize any other report section.\n"
                            if structural_chunk_deficit
                            else ""
                        )
                        + (
                            "SCRIPT-INTEGRITY RETRY RULE: the prior response contained an unexpected CJK "
                            "glyph. Re-author the complete chunk in English using Latin characters and ordinary "
                            "punctuation only. Before returning, scan every character in the response; do not "
                            "reuse the contaminated token or wording.\n"
                            if any("unexpected CJK glyph" in issue for issue in rejected_chunk_issues)
                            else ""
                        )
                        + (
                            "CALLER-POLICY RETRY RULE: the prior response breached a configured fail-closed "
                            "forbidden-content category. Re-author the complete chunk with neutral "
                            "economic-geography and public-infrastructure wording only. Do not quote, "
                            "enumerate, name, or paraphrase the caller policy controls; silently self-audit "
                            "the full replacement before returning it. Runtime will reject, not repair, "
                            "another policy-breaching chunk.\n"
                            if any("configured forbidden-content policy hit" in issue for issue in rejected_chunk_issues)
                            else ""
                        )
                        + "NUMERIC-CLAIM RETRY RULE: if the deficit ledger identifies an uncited numeric "
                        + "narrative block, every sentence or bullet containing a number, date, percentage, "
                        + "ranking, comparison, time interval, forecast, or wording such as `next 12 months` "
                        + "must carry a resolving inline [n] marker in that same block. Do not repeat the "
                        + "rejected wording without its evidence marker; either cite supported evidence or "
                        + "re-author the claim without a numeric assertion. If the rejected wording includes "
                        + "`next 12 months`, it must not recur unless that exact paragraph has [n]; otherwise "
                        + "replace it with the literal phrase `the outlook period`. Before emitting, perform "
                        + "a final model self-audit for the literal tokens `12` and `next 12 months`.\n"
                        + (
                            "NUMERIC-DEFICIT FULL-PARAGRAPH CITATION RULE: the prior draft contained "
                            "at least one uncited numeric block. In the complete replacement, end every "
                            "non-heading narrative paragraph and bullet with a resolving inline [n] marker, "
                            "including qualitative synthesis and conclusion paragraphs. Do not leave a "
                            "summary uncited merely because its number, date, or comparison appears later "
                            "in the same paragraph. If no governed source supports a paragraph, omit that "
                            "paragraph rather than returning it without a marker.\n"
                            if any("numeric narrative block(s) lack an inline" in issue for issue in rejected_chunk_issues)
                            else ""
                        )
                        + (
                            "LITERAL CITATION-FORMAT PRECHECK: before returning the full replacement, "
                            "inspect every blank-line-separated, non-heading narrative paragraph and "
                            "bullet yourself. Each must literally contain a governed marker in the form "
                            "`[<source number>]`; a citation only in a neighbouring paragraph does not "
                            "count. For every rejected numeric block named in the ledger, either retain "
                            "its factual meaning with a resolving marker in that exact block or omit it. "
                            "Do not return until this literal per-block check passes.\n"
                            if any("numeric narrative block(s) lack an inline" in issue for issue in rejected_chunk_issues)
                            else ""
                        )
                        + (
                            "CLOSED-CITATION-SET RETRY RULE: the previous draft used an ungoverned "
                            "citation number. Re-author the complete chunk using only these literal "
                            "tokens: "
                            + ", ".join(f"[{marker}]" for marker in range(1, source_count + 1))
                            + ". Source markers are labels for the current-run register, not a sequence "
                            "to extend. Reuse a supporting allowed marker; do not continue numbering after "
                            f"[{source_count}]. Before returning, scan every bracketed number and replace "
                            "the entire unsupported claim with a sourced claim or omit it. Runtime will not "
                            "renumber, substitute, or repair a marker.\n"
                            if any(
                                "outside the governed current-run source register" in issue
                                for issue in rejected_chunk_issues
                            )
                            else ""
                        )
                        + (
                            "TABLE-ADJACENT NUMERIC-CITATION RETRY RULE: this planned-table chunk "
                            "was rejected for a numeric narrative block. Re-author the complete chunk. "
                            "Every table introduction, explanation and conclusion that contains a digit, "
                            "percentage, date, count, or ranking must include an inline [n] citation in "
                            "that same paragraph. If a governed marker cannot support the statement, "
                            "make the paragraph qualitative with no digits. Do not repeat an uncited "
                            "phrase such as a percentage target, a year, or a country ranking.\n"
                            if planned_tables
                            and any("numeric narrative block(s) lack an inline" in issue for issue in rejected_chunk_issues)
                            else ""
                        )
                        + (
                            "SOURCE-REGISTER RETRY RULE: emit a one-to-one source register for the exact "
                            "narrative marker list only. Do not add a source line merely because its marker "
                            "appears in the original research register or URL allowlist. Before returning, "
                            "compare the bracketed marker on every source line against the mandatory narrative "
                            "marker list and omit every non-matching line.\n"
                            if source_tail else ""
                        )
                        + (
                            "FRONT-MATTER RETRY RULE: the prior first chunk omitted required run front matter. "
                            "Re-author the complete chunk with the exact classification/framing line and exact "
                            "reporting-period declaration before the Executive Summary body.\n"
                            if any(
                                "required classification" in issue
                                or "required reporting period" in issue
                                for issue in rejected_chunk_issues
                            )
                            else ""
                        )
                        + (
                            "TEMPORAL-FRAMING RETRY RULE: the prior chunk used prohibited `As of` temporal "
                            "framing. Re-author the complete chunk. Before returning, inspect every paragraph "
                            "opening and every reporting-period label; replace each temporal `As of` framing with "
                            "the configured `As at` wording or a neutral rephrasing.\n"
                            if any("As of" in issue for issue in rejected_chunk_issues)
                            else ""
                        )
                    )
                refreshed_source_register_instruction = (
                    "\nCURRENT-RUN REFRESHED GOVERNED SOURCE REGISTER: this register supersedes "
                    "all earlier source URL and marker mappings in the system prompt. Use only these "
                    "current, live-validated sources for this complete replacement chunk.\n"
                    + preflight_source_register
                    + "\n"
                    if len(source_register_refreshes) > 1 and preflight_source_register
                    else ""
                )
                prior_chunk_anti_repetition_register = (
                    "\nANTI-REPETITION BOUNDARY: accepted earlier sections exist, but their prose "
                    "is deliberately withheld because showing it can anchor a replacement model "
                    "completion. Author distinct analysis for the current H2 section(s). Runtime "
                    "compares the candidate against all accepted chunks and, on rejection, reports "
                    "a bounded list of exact normalized collisions. Runtime will reject rather than "
                    "rewrite repetitive prose. Prior prose and heading identities are not included "
                    "in this model turn.\n"
                    if chunks and not source_tail
                    else ""
                )
                completion_deficit_instruction = ""
                if deficit_ledger:
                    focused_rules: List[str] = []
                    if "repetitive_prose:" in deficit_ledger:
                        focused_rules.append(
                            "The prior assembled report repeated substantive prose. Re-author this "
                            "section with distinct analysis and no paragraph or 12-word sequence "
                            "copied from the accepted earlier-chunk register."
                        )
                    if re.search(
                        r"section_quality:\s+Sources.*words=\d+<\d+",
                        deficit_ledger,
                    ):
                        focused_rules.append(
                            "The prior Sources section was below its configured depth. Author every "
                            "required source entry with concise provenance and relevance context "
                            "while preserving the exact governed marker-to-URL mapping."
                        )
                    if "final document link(s) failed live retrieval" in deficit_ledger:
                        focused_rules.append(
                            "The prior report used dead source URLs. Use the refreshed governed "
                            "marker-to-URL mapping exactly: do not shorten, wrap, infer, reconstruct, "
                            "or reuse any URL from the rejected report."
                        )
                    if focused_rules:
                        completion_deficit_instruction = (
                            "\nASSEMBLED-REPORT DEFICIT REAUTHORING RULES:\n- "
                            + "\n- ".join(focused_rules)
                            + "\n"
                        )
                model_messages = [{
                    "role": "user",
                    "content": (
                        f"Document title: {tool_adapter._default_title or tool_adapter._default_target or 'Report'}\n"
                        + chunk_instruction
                        + retry_instruction
                        + refreshed_source_register_instruction
                        + prior_chunk_anti_repetition_register
                        + completion_deficit_instruction
                    ),
                }]
                if (
                    numeric_only_deficit
                    and not structural_chunk_deficit
                    and not section_depth_deficit
                    and not section_ceiling_deficit
                ):
                    # Keep the fail-closed validator and require a complete model replacement.
                    # Represent the rejected completion as the model's preceding assistant
                    # turn only for a numeric-only deficit. Structurally invalid output is
                    # deliberately excluded because it anchors the next turn to wrong H2s.
                    numeric_deficits = "\n".join(
                        "- " + issue
                        for issue in rejected_chunk_issues
                        if "numeric narrative block(s) lack an inline" in issue
                    )
                    allowed_marker_values = (
                        sorted(selected_new_markers)
                        if selected_new_markers
                        else range(1, source_count + 1)
                    )
                    allowed_markers = ", ".join(
                        f"[{marker}]" for marker in allowed_marker_values
                    )
                    model_messages.append({
                        "role": "assistant",
                        "content": (
                            "FINAL_REPORT_CHUNK\n"
                            + rejected_chunk_text.removeprefix("FINAL_REPORT_CHUNK").lstrip()
                        ),
                    })
                    model_messages.append({
                        "role": "user",
                        "content": (
                            "CORRECTION REQUIRED: your preceding model-authored chunk was rejected before "
                            "assembly and was never delivered. Return a complete replacement "
                            "FINAL_REPORT_CHUNK, not a patch or commentary. Before emitting it, inspect every "
                            "blank-line-separated "
                            "narrative block, including every table introduction, explanation, and conclusion. "
                            "A block with any digit, percentage, date, count, ranking, comparison, or numeric "
                            "target must contain a resolving governed [n] marker in that same block. Every "
                            "non-heading narrative paragraph and bullet must end with one of these literal "
                            "permitted marker tokens: "
                            + allowed_markers
                            + ". Do not repeat any rejected numeric wording without its marker; instead cite "
                            "the supporting governed source or re-author that block without the numeric "
                            "assertion. FINAL BLOCKING NUMERIC-CITATION CHECK FAILED:\n"
                            + numeric_deficits
                            + "\nReturn no commentary, patch, or draft fragment. Runtime will reject rather "
                            "than edit the response."
                        ),
                    })
                elif (
                    repetition_chunk_deficit
                    and not structural_chunk_deficit
                    and not section_depth_deficit
                    and not section_ceiling_deficit
                ):
                    model_messages.append({
                        "role": "user",
                        "content": (
                            "CORRECTION REQUIRED: your preceding model-authored chunk was rejected "
                            "before assembly and was never persisted or delivered. Return a complete "
                            "replacement FINAL_REPORT_CHUNK, not a patch or commentary. The rejected "
                            "draft is deliberately not repeated in this correction because it must not "
                            "anchor the replacement. This is repetition replacement attempt "
                            f"{chunk_attempt} of {chunk_authoring_attempts}. Before drafting, assign a "
                            "distinct analytical purpose to every required narrative paragraph and "
                            "table-adjacent narrative block, then ensure no two blocks restate the same "
                            "thesis. Remove every "
                            "substantive paragraph and phrase that repeats within the rejected chunk "
                            "or from the accepted earlier-chunk anti-repetition register. Each paragraph "
                            "in the replacement must contribute distinct source-grounded analysis for "
                            "its exact H2 section. Preserve the required citation binding, headings, "
                            "depth, and tables, but do not copy a repeated sentence merely to retain "
                            "length. The fail-closed repetition deficits are:\n- "
                            + "\n- ".join(
                                issue
                                for issue in rejected_chunk_issues
                                if issue.startswith("repetitive_prose:")
                            )
                            + "\nRuntime will reject rather than delete, paraphrase, or otherwise "
                            "repair repeated report prose."
                        ),
                    })
                elif (
                    distinct_citation_deficit
                    and not structural_chunk_deficit
                    and not section_depth_deficit
                    and not section_ceiling_deficit
                ):
                    # A late narrative chunk can legitimately reuse most of the
                    # document's evidence while still owing the remaining
                    # document-level distinct-marker floor. Smaller models can
                    # preserve the stale citation set when the rejected draft
                    # is represented as an assistant turn. Keep the gate
                    # unchanged and require a clean complete replacement from
                    # an explicit unused governed set. Runtime neither inserts
                    # a citation nor changes report prose.
                    unused_markers = [
                        marker
                        for marker in range(1, source_count + 1)
                        if marker not in used_markers
                    ]
                    active_markers = (
                        sorted(selected_new_markers)
                        if selected_new_markers
                        else unused_markers
                    )
                    unused_source_rows = _source_register_rows_for_markers(
                        preflight_source_register,
                        active_markers,
                    )
                    model_messages.append({
                        "role": "user",
                        "content": (
                            "CORRECTION REQUIRED: your preceding model-authored chunk was rejected "
                            "before assembly and was never delivered. Return a complete replacement "
                            "FINAL_REPORT_CHUNK, not a patch or commentary. The document-level distinct "
                            "citation floor is still unmet. Introduce at least "
                            f"{new_markers_needed} distinct, resolving citation marker(s) selected from "
                            "this literal unused governed set: "
                            + ", ".join(f"[{marker}]" for marker in active_markers)
                            + ". Place each selected marker on an evidence-supported claim in this "
                            "replacement chunk. This active set is the entire per-chunk citation "
                            "allowlist: do not reuse an earlier marker or any marker outside it. "
                            "Do not invent a marker, source, URL, claim, or "
                            "report prose outside the normal model-authored response. Before returning, "
                            "self-count the distinct markers from the unused set that actually appear in "
                            "the complete replacement. Runtime will reject rather than insert or repair "
                            "citations."
                            + (
                                "\nMODEL-SELECTED MANDATORY CITATIONS: the separate model-owned "
                                "selection checkpoint chose "
                                + ", ".join(
                                    f"[{marker}]"
                                    for marker in sorted(selected_new_markers)
                                )
                                + ". Include every selected marker in the complete replacement "
                                "on a claim directly supported by its governed source row. Treat "
                                "those marker labels as opaque IDs: copy them literally and do not "
                                "renumber them by row position."
                                if selected_new_markers else ""
                            )
                            + (
                                "\nEXACT UNUSED GOVERNED SOURCE LOOKUP:\n"
                                + unused_source_rows
                                + "\nUse these exact governed rows to choose claims and markers. Do not "
                                "infer a source from marker order, and do not cite a row that does not "
                                "directly support the claim."
                                if unused_source_rows else ""
                            )
                            + (
                                " CLOSED-CITATION-SET RETRY RULE: the preceding draft also used an "
                                "ungoverned citation number. Use only these literal permitted tokens: "
                                + ", ".join(
                                    f"[{marker}]"
                                    for marker in range(1, source_count + 1)
                                )
                                + ". Do not extend the sequence or retain the unsupported claim; "
                                "runtime will not renumber, substitute, or repair a marker. "
                                "The complete rejected-source deficit is: "
                                + " | ".join(
                                    issue
                                    for issue in rejected_chunk_issues
                                    if "outside the governed current-run source register"
                                    in issue
                                )
                                if any(
                                    "outside the governed current-run source register"
                                    in issue
                                    for issue in rejected_chunk_issues
                                )
                                else ""
                            )
                        ),
                    })
                if selected_new_markers:
                    model_messages = [
                        {
                            **message,
                            "content": _selected_citation_prompt_boundary(
                                str(message.get("content") or ""),
                                selected_new_markers,
                            ),
                        }
                        for message in model_messages
                    ]
                attempt_chunk_adapter = chunk_adapter
                if repetition_chunk_deficit:
                    active_repetition_contract = (
                        tool_adapter._default_quality_controls.get("repetition")
                        if isinstance(
                            tool_adapter._default_quality_controls.get("repetition"),
                            dict,
                        )
                        else {}
                    )
                    repetition_ngram_words = max(
                        3,
                        _as_int(
                            active_repetition_contract.get("ngram_words")
                            or active_repetition_contract.get("minimum_phrase_words"),
                            12,
                        ),
                    )
                    collision_phrases: List[str] = []
                    for issue in rejected_chunk_issues:
                        if "exact normalized collision(s):" not in issue:
                            continue
                        _, _, collision_tail = issue.partition(
                            "exact normalized collision(s):"
                        )
                        collision_phrases.extend(
                            phrase.strip()
                            for phrase in collision_tail.split("|")
                            if phrase.strip()
                        )
                    collision_phrases = list(dict.fromkeys(collision_phrases))[:5]
                    repetition_system_boundary = (
                        "\n\nFAIL-CLOSED REPETITION REAUTHORING BOUNDARY\n"
                        f"This is independent replacement attempt {chunk_attempt} of "
                        f"{chunk_authoring_attempts}. The earlier completion was rejected and "
                        "must not be reconstructed. Author every paragraph with a distinct "
                        "analytical purpose. Paraphrase governed evidence in original reader-ready "
                        f"analysis; do not copy any sequence of {repetition_ngram_words} or more "
                        "consecutive prose words from a source-register row. Citation marker tokens "
                        "and exact official publication titles remain governed and may be copied. "
                        "The following normalized token sequences are forbidden anywhere in this replacement "
                        "chunk, even if one appears in a source row:\n- "
                        + ("\n- ".join(collision_phrases) if collision_phrases else "(none reported)")
                        + "\nBefore returning FINAL_REPORT_CHUNK, scan the complete replacement "
                        "against this boundary. Runtime will reject rather than delete, paraphrase, "
                        "or repair repeated prose."
                    )
                    attempt_chunk_adapter = _new_chunk_adapter(
                        active_chunk_system_prompt + repetition_system_boundary,
                        attempt_temperature=min(
                            1.0,
                            max(float(temperature), 0.4) + (0.1 * (chunk_attempt - 1)),
                        ),
                    )
                parsed = await attempt_chunk_adapter.call(
                    model_messages
                )
                if parsed.get("tool_call") or parsed.get("final_answer") is None:
                    raise RuntimeError(
                        "MODEL_AUTHORED_CHUNK_INCOMPLETE: model did not return a FINAL_REPORT_CHUNK "
                        f"for chunk {index}"
                    )
                candidate_chunk = _final_text(parsed.get("final_answer"), store)
                if not candidate_chunk.strip():
                    raise RuntimeError(
                        f"MODEL_AUTHORED_CHUNK_INCOMPLETE: model returned an empty chunk {index}"
                    )
                rejected_chunk_issues = _chunk_contract_issues(
                    candidate_chunk,
                    source_tail=source_tail,
                    first_narrative_chunk=(not source_tail and index == 1),
                    existing_markers=used_markers,
                    required_new_markers=(
                        0 if source_tail else new_markers_needed
                    ),
                    required_selected_markers=(
                        set() if source_tail else selected_new_markers
                    ),
                    allowed_chunk_markers=(
                        None
                        if source_tail or not selected_new_markers
                        else selected_new_markers
                    ),
                    required_tables=planned_tables,
                    maximum_words=chunk_word_ceiling,
                    required_heading_titles=titles,
                )
                if not rejected_chunk_issues:
                    model_chunk = candidate_chunk
                    break
                rejected_chunk_text = candidate_chunk
                if chunk_attempt == chunk_authoring_attempts:
                    raise RuntimeError(
                        "MODEL_AUTHORED_CHUNK_CHECKPOINT_FAILED: model did not satisfy the "
                        f"chunk completion contract for chunk {index} after {chunk_attempt} attempt(s): "
                        + "; ".join(rejected_chunk_issues)
                    )

            # Keep the immutable model completion request-scoped until the full
            # assembled candidate passes the terminal quality gate. Persisting a
            # weak/repetitive/two-map draft would violate the zero-side-effect
            # rejection contract even though it was never delivered.
            reloaded_chunk = model_chunk
            staging_path = ""
            if working_path:
                staging_path = f"{working_path}.model-authored-{identity}-part-{index:02d}.md"
                deferred_model_artifacts.append({
                    "label": f"model-authored chunk {index}",
                    "profile": profile,
                    "path": staging_path,
                    "content": model_chunk,
                })

            chunks.append(reloaded_chunk)
            if not source_tail:
                used_markers.update(int(marker) for marker in re.findall(r"\[(\d+)\]", reloaded_chunk))
            chunk_records.append(
                {
                    "index": index,
                    "section_titles": titles,
                    "words": len(re.findall(r"\w+", reloaded_chunk)),
                    "sha256": hashlib.sha256(reloaded_chunk.encode("utf-8")).hexdigest(),
                    "filemcp_staging_path": staging_path or None,
                    "persistence": "deferred_until_quality_gate",
                    "model_authored": True,
                    "authoring_attempts": chunk_attempt,
                    "model_selected_citation_markers": sorted(selected_new_markers),
                }
            )

        # This is immutable artifact assembly only: each element was emitted by
        # the model and FileMCP-reloaded unchanged above.  Validation below is
        # fail-closed and publication writes this exact aggregate; it never
        # inserts, rewrites, or repairs report content.
        return "\n\n".join(chunks), chunk_records

    if strategy == AgentStrategy.REACT.value:
        model_chunk_records: List[Dict[str, Any]] = []
        if _agentic_document and _agentic_chunked_authoring:
            content, model_chunk_records = await _author_large_agentic_document_chunks(authoring_attempt=1)
            trace = None
        else:
            config = ReActConfig(
                max_iterations=max_iter,
                max_wall_time_seconds=max_wall,
                memory_scope=memory_scope,
                tools_available=descriptors,
            )
            trace = await ReActLoop(config, llm_adapter, tool_adapter).run(input_text)
            content = _final_text(trace.final_answer, store)
        publication: Optional[Dict[str, Any]] = None
        if _agentic_document:
            if trace is not None and trace.terminated_by != "answer":
                raise RuntimeError(
                    "AGENTIC_DOCUMENT_INCOMPLETE: ReAct terminated by %s after %s iterations without a model final_answer"
                    % (trace.terminated_by or "unknown", trace.iterations_used)
                )
            today = _datetime.date.today()
            section_count = len(tool_adapter._default_sections)
            target_words = _as_int(params.get("target_words"), 850)
            min_words = int(
                tool_adapter._default_quality_controls.get("agentic_minimum_report_words")
                or max(600, target_words * max(1, section_count) // 2)
            )
            model_visual_plan_evidence: Dict[str, Any] = {}

            async def _author_model_authored_visual_plan(
                configured_visuals: Dict[str, Any],
            ) -> Dict[str, Any]:
                """Ask the document model for the product's visual plan, or use config visuals.

                A model-authored visual plan is a separate immutable artefact.  The
                model chooses the candidate overlays, chart values, captions and
                rationale from its own completed, cited document.  Runtime code only
                validates the declared schema, preserves it through FileMCP and gives
                it to normal GeoMCP/ChartMCP rendering.
                """
                contract = configured_visuals.get("model_authored_plan")
                if not isinstance(contract, dict) or not contract.get("required"):
                    return configured_visuals

                # A rejected plan must be re-authored by the report model; runtime
                # code never completes a missing visual or changes the model's
                # candidate selection.  Product contracts may permit up to five
                # complete re-authoring attempts for an exact-kind deficit.
                # A visual plan is a separate model-authored artefact with a
                # comparatively strict renderer contract.  Give the model the
                # full governed re-authoring budget even if an older schedule
                # payload carries a smaller value: this is a retry of the same
                # model-owned plan, never a runtime repair or a fallback visual.
                # Seven complete re-authorings: one invalid bbox or missing
                # required kind on a small local model must not consume the
                # whole budget before a compliant plan lands (W28M-1640B).
                attempts = 7
                minimum_maps = max(0, _as_int(contract.get("minimum_maps"), 0))
                required_kind_inventory = "; ".join(
                    "kind %r: at least %d" % (str(kind), int(minimum))
                    for kind, minimum in sorted(
                        (contract.get("minimum_map_kinds") or {}).items(),
                        key=lambda item: str(item[0]),
                    )
                )
                visual_classes = contract.get("required_visual_classes") or []
                if isinstance(visual_classes, dict):
                    visual_classes = [
                        dict({"id": key}, **(value if isinstance(value, dict) else {}))
                        for key, value in visual_classes.items()
                    ]
                required_class_inventory = "; ".join(
                    "quality_class %r: at least %d %s(s)"
                    % (
                        str(requirement.get("id") or requirement.get("visual_class")).strip(),
                        max(1, _as_int(requirement.get("minimum"), 1)),
                        str(requirement.get("kind") or "visual").strip().lower(),
                    )
                    for requirement in visual_classes
                    if isinstance(requirement, dict)
                    and str(requirement.get("id") or requirement.get("visual_class") or "").strip()
                )
                inventory_instruction = (
                    "VISUAL-PLAN INVENTORY (preflight this before you answer): emit at least %d map object(s)"
                    % minimum_maps
                    + (
                        "; exact literal map-kind inventory: " + required_kind_inventory
                        if required_kind_inventory else ""
                    )
                    + (
                        "; exact required quality_class inventory: " + required_class_inventory
                        + ". A visual only counts when its JSON `quality_class` string is exactly the stated value; "
                        "do not rename, combine, or omit required classes"
                        if required_class_inventory else ""
                    )
                    + ". A map only counts when its JSON `kind` string is exactly the stated value; "
                    "do not rename, combine, or omit required kinds.\n\n"
                )
                last_error = "model did not return a visual plan"
                rejected_plan = ""
                for attempt in range(1, attempts + 1):
                    adapter = AgentLLMAdapter(
                        getattr(executor, "llm_manager", None),
                        "You are the visual-planning model for a cited, public-data research report. "
                        "You author visual rationale and data only; never emit report prose, a source "
                        "section, hidden reasoning, an outline, or a tool call.",
                        [],
                        temperature=0.1,
                        max_tokens=6000,
                        num_ctx=24576,
                        allow_markdown_final=True,
                        markdown_completion_marker="FINAL_VISUAL_PLAN",
                    )
                    retry_instruction = (
                        "\nMODEL-OWNED VISUAL-PLAN REAUTHORING: the previous complete visual plan was "
                        "rejected before rendering. Re-author the entire JSON object, not a patch, and correct "
                        "this exact validation deficit: " + last_error + ". "
                        "If you select a radar chart, its `categories` MUST be a JSON array and its `series` "
                        "MUST be a JSON object; otherwise select a supported bar, grouped_bar, hbar or line "
                        "chart and include model-authored `rows`. Do not return commentary, a partial plan, "
                        "or the rejected JSON verbatim.\n"
                        + (
                            "--- rejected model-authored visual plan ---\n"
                            + rejected_plan
                            + "\n--- end rejected visual plan ---\n"
                            if rejected_plan
                            else ""
                        )
                        if attempt > 1
                        else ""
                    )
                    prompt = (
                        "Create one complete machine-readable visual plan for the exact completed report below. "
                        "Return exactly FINAL_VISUAL_PLAN on its own line followed by one JSON object. "
                        "Do not use markdown fences. The JSON must contain only maps and charts arrays. "
                        + inventory_instruction
                        +
                        "Every candidate, coordinate, rank, score, metric, map overlay, caption and chart value "
                        "must be selected and authored by you from the cited report and its governed public source "
                        "register; do not invent values or use placeholder data. Captions must state the decision "
                        "purpose and include the report's resolving [n] marker(s). Use the report's candidate names "
                        "consistently. Each map must have id, kind, quality_class, title, caption, after, bbox, basemap, map_date, attribution "
                        "and source_urls. Each chart must have id, kind, quality_class, title, caption, after, chart_type and source_urls. "
                        + (
                            "Every map must also supply these contract fields: "
                            + ", ".join(
                                str(field).strip()
                                for field in (contract.get("required_map_fields") or [])
                                if str(field).strip()
                            )
                            + ". "
                            if contract.get("required_map_fields") else ""
                        )
                        + (
                            "Do not include these forbidden map fields: "
                            + ", ".join(
                                str(field).strip()
                                for field in (contract.get("forbidden_map_fields") or [])
                                if str(field).strip()
                            )
                            + ". "
                            if contract.get("forbidden_map_fields") else ""
                        )
                        + "For every bar, hbar, grouped_bar or line chart, `x` and `y` each MUST be one "
                        "non-empty JSON string naming a field (never arrays), and `rows` MUST be a non-empty JSON "
                        "array of objects where every object has scalar values for those named fields and the `y` "
                        "value is numeric. Radar charts must include scalar `categories` and an aligned `series` "
                        "object of numeric arrays. Charts are optional unless the product contract requires them; "
                        "omit a chart rather than returning a malformed chart.\n\n"
                        + "Map field shapes are strict: `legend`, `markers`, `lines`, `control`, `highlight` and "
                        "`neighbours` must be JSON arrays when present; `legend` is never a boolean. When the "
                        "contract requires `legend`, provide a non-empty array of model-authored objects such as "
                        "`{\"label\": \"reported activity\", \"colour\": [r, g, b]}`. A map `bbox` MUST be "
                        "a four-item JSON numeric array in exact `[west_longitude, south_latitude, "
                        "east_longitude, north_latitude]` order (not strings and not latitude/longitude pairs), "
                        "where west < east and south < north. If the product contract includes "
                        "`minimum_overlay_entries_by_kind`, every map of that exact `kind` must include each "
                        "named array with at least its required count. Those coordinates, labels, routes and "
                        "event distinctions are your cited, model-authored evidence marks; an orientation-only "
                        "basemap cannot satisfy an axis, movement or strike visual.\n\n"
                        + "PRODUCT VISUAL CONTRACT:\n"
                        + json.dumps(contract, ensure_ascii=False, sort_keys=True)
                        + retry_instruction
                        + "\n\nCOMPLETED MODEL-AUTHORED REPORT:\n"
                        + content
                    )
                    raw_plan: Any = None
                    try:
                        response = await adapter.call([{"role": "user", "content": prompt}])
                        if response.get("tool_call") or response.get("final_answer") is None:
                            raise ValueError("model returned no FINAL_VISUAL_PLAN")
                        raw_plan = response.get("final_answer")
                        if not isinstance(raw_plan, str):
                            raise ValueError("model returned a non-text visual plan")
                        plan = _parse_model_authored_visual_plan(raw_plan, contract)
                    except Exception as exc:
                        last_error = str(exc)[:500]
                        if isinstance(raw_plan, str):
                            rejected_plan = raw_plan
                        continue

                    working_path = str(tool_adapter._default_working_path or "").strip()
                    profile = str(tool_adapter._default_profile or "google_drive").strip()
                    plan_path = ""
                    if working_path:
                        plan_path = working_path + ".model-authored-visual-plan.json"
                        deferred_model_artifacts[:] = [
                            artifact for artifact in deferred_model_artifacts
                            if artifact.get("label") != "model-authored visual plan"
                        ]
                        deferred_model_artifacts.append({
                            "label": "model-authored visual plan",
                            "profile": profile,
                            "path": plan_path,
                            "content": raw_plan,
                        })
                    model_visual_plan_evidence.update(
                        {
                            "model_authored": True,
                            "attempt": attempt,
                            "sha256": hashlib.sha256(raw_plan.encode("utf-8")).hexdigest(),
                            "filemcp_path": plan_path or None,
                            "persistence": "deferred_until_quality_gate",
                            "maps": len(plan["maps"]),
                            "charts": len(plan["charts"]),
                        }
                    )
                    return plan
                raise RuntimeError(
                    "MODEL_AUTHORED_VISUAL_PLAN_FAILED: " + last_error
                )

            async def _render_configured_agentic_visuals() -> tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
                """Render configured visuals before the agentic pre-delivery checkpoint.

                Visual selection is product configuration and rendering is a normal
                tool call.  It must precede validation so a valid model-authored
                report is measured against the actual map/chart payloads that will
                be delivered with it, rather than an empty placeholder list.
                """
                images: List[Dict[str, Any]] = []
                rendered_figures: List[Dict[str, Any]] = []
                visuals_spec = _defaults.get("visuals")
                if not isinstance(visuals_spec, dict):
                    return images, rendered_figures
                visuals_spec = dict(visuals_spec)
                visuals_spec = await _author_model_authored_visual_plan(visuals_spec)
                selected_country = (
                    _country_from_visual_focus(
                        _defaults.get("country_rotation"), visuals_spec
                    )
                    or _select_rotated_country(
                        _defaults.get("country_rotation"),
                        today.timetuple().tm_yday,
                    )
                )
                if selected_country:
                    visuals_spec = _interp_country(visuals_spec, str(selected_country["name"]))
                    country_bbox = selected_country.get("bbox")
                    if country_bbox:
                        for map_spec in visuals_spec.get("maps") or []:
                            if isinstance(map_spec, dict) and map_spec.get("rotate_bbox"):
                                map_spec["bbox"] = list(country_bbox)
                from src.core.execution import visuals as _visuals_mod
                try:
                    images, rendered_figures = await _visuals_mod.render_visuals(
                        visuals_spec,
                        _dispatch_service,
                        http_get=_make_http_get("chartmcpserver0"),
                    )
                except Exception as exc:
                    logger.warning("agentic document: render_visuals failed: %s", exc)
                    images, rendered_figures = [], []
                if visuals_spec.get("require_all_rendered"):
                    declared_visuals = (
                        len([item for item in (visuals_spec.get("maps") or []) if isinstance(item, dict)])
                        + len([item for item in (visuals_spec.get("charts") or []) if isinstance(item, dict)])
                    )
                    if len(rendered_figures) < declared_visuals:
                        raise RuntimeError(
                            "VISUAL_CONTRACT: FAIL declared=%d rendered=%d - a declared map or chart "
                            "failed to render; failing closed rather than delivering an incomplete report"
                            % (declared_visuals, len(rendered_figures))
                        )
                return images, rendered_figures

            async def _author_model_authored_quality_assessment() -> Dict[str, Any]:
                """Ask the report model to score the completed candidate before persistence."""
                contract = tool_adapter._default_quality_controls.get(
                    "model_authored_quality_assessment"
                )
                if not isinstance(contract, dict) or not contract.get("required"):
                    return {}
                attempts = max(1, min(int(contract.get("max_attempts") or 3), 5))
                required_titles = list(tool_adapter._default_quality_controls.get("required_section_titles") or [])
                minimum_score = float(contract.get("minimum_score") or 0)
                last_error = "model did not return a quality self-assessment"
                rejected = ""
                for assessment_attempt in range(1, attempts + 1):
                    adapter = AgentLLMAdapter(
                        getattr(executor, "llm_manager", None),
                        "You are the quality-assessment model for a source-grounded research report. "
                        "Assess the completed candidate honestly; do not write or repair report prose, do not "
                        "call a tool, and do not emit hidden reasoning.",
                        [],
                        temperature=0.0,
                        max_tokens=4000,
                        num_ctx=24576,
                        allow_markdown_final=True,
                        markdown_completion_marker="FINAL_QUALITY_SELF_ASSESSMENT",
                        marked_final_payload_description=(
                            "one complete JSON quality-assessment object whose `sections` value is an array"
                        ),
                        allow_bare_json_final=True,
                    )
                    prompt = _build_model_authored_quality_assessment_prompt(
                        content=content,
                        contract=contract,
                        required_titles=required_titles,
                        minimum_score=minimum_score,
                        rejected=rejected,
                        last_error=last_error,
                    )
                    raw: Any = None
                    try:
                        response = await adapter.call([{"role": "user", "content": prompt}])
                        if response.get("tool_call") or response.get("final_answer") is None:
                            raise ValueError("model returned no FINAL_QUALITY_SELF_ASSESSMENT")
                        raw = response.get("final_answer")
                        if not isinstance(raw, str):
                            raise ValueError("model returned a non-text quality self-assessment")
                        parsed = _parse_model_authored_quality_assessment(
                            raw,
                            {"required_section_titles": required_titles},
                        )
                        return {
                            **parsed,
                            "model_authored": True,
                            "attempt": assessment_attempt,
                            "sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
                            "raw": raw,
                        }
                    except Exception as exc:
                        last_error = str(exc)[:500]
                        if isinstance(raw, str):
                            rejected = raw
                raise RuntimeError("MODEL_AUTHORED_QUALITY_ASSESSMENT_FAILED: " + last_error)

            # Render first: the completion gate validates the same concrete visual
            # payload that publication will attach.  It never changes model prose.
            inline_images, figures = await _render_configured_agentic_visuals()
            completion_checkpoints: List[Dict[str, Any]] = []
            quality_self_assessment: Dict[str, Any] = {}
            if _agentic_strict_completion:
                # This is a model-owned checkpoint/retry boundary.  The gate is
                # deliberately validation-only. It uses the same live-link
                # controls as publication, so a dead model-authored source is
                # returned to the model as a deficit before the terminal
                # write/delivery boundary. A failed draft is never modified in
                # code: the model gets the deficit ledger and must return a
                # complete replacement.
                for attempt in range(1, _agentic_completion_max_attempts + 1):
                    # Re-snapshot the controls on every attempt: a live-link
                    # failure refreshes the governed source register and swaps
                    # allowed_external_source_urls on the adapter's controls, so
                    # a pre-loop snapshot would validate a refreshed-register
                    # re-author against the stale allowlist and fail every
                    # remaining attempt as "outside the governed register".
                    checkpoint_controls = dict(tool_adapter._default_quality_controls)
                    quality_self_assessment = await _author_model_authored_quality_assessment()
                    checkpoint = tool_adapter._quality_gate(
                        {
                            "content": content,
                            "current_year": today.year,
                            "min_sections": section_count,
                            "min_words": min_words,
                            "quality_controls": checkpoint_controls,
                            "require_links": True,
                            "inline_images": inline_images,
                            "figures": figures,
                            "quality_self_assessment": quality_self_assessment,
                        }
                    )
                    checkpoint_metrics = checkpoint.get("metrics") or {}
                    completion_checkpoints.append(
                        {
                            "attempt": attempt,
                            "pass": bool(checkpoint.get("pass")),
                            "issues": list(checkpoint.get("issues") or []),
                            "metrics": {
                                key: checkpoint_metrics.get(key)
                                for key in (
                                    "words",
                                    "sections",
                                    "tables",
                                    "external_links",
                                    "numbered_sources",
                                    "inline_citation_markers",
                                    "source_citation_markers",
                                    "section_quality",
                                    "model_authored_quality_assessment",
                                    "repetition",
                                    "required_visual_classes",
                                    "rendered_visual_classes",
                                )
                            },
                        }
                    )
                    if checkpoint.get("pass"):
                        break
                    if attempt >= _agentic_completion_max_attempts:
                        raise RuntimeError(
                            "AGENTIC_DOCUMENT_CHECKPOINT_FAILED: model-authored report did not pass "
                            "the configured completion contract after "
                            f"{attempt} attempt(s): "
                            + "; ".join(str(issue) for issue in (checkpoint.get("issues") or []))
                        )
                    deficit_ledger = "\n- ".join(
                        str(issue) for issue in (checkpoint.get("issues") or [])
                    )
                    live_link_failure = any(
                        "final document link(s) failed live retrieval" in str(issue)
                        for issue in (checkpoint.get("issues") or [])
                    )
                    if live_link_failure:
                        await _refresh_governed_source_register(
                            reason=f"completion_checkpoint_{attempt}_failed_live_link_validation"
                        )
                    if _agentic_chunked_authoring:
                        content, model_chunk_records = await _author_large_agentic_document_chunks(
                            authoring_attempt=attempt + 1,
                            deficit_ledger=deficit_ledger,
                        )
                    else:
                        retry = await llm_adapter.call(
                            [
                                {"role": "user", "content": input_text},
                                {
                                    "role": "user",
                                    "content": (
                                        "MODEL-OWNED COMPLETION CHECKPOINT: your previous draft was "
                                        "validated before persistence and delivery, and it failed. Do not "
                                        "explain the failure, patch fragments, or call a tool. Re-author a "
                                        "complete replacement report from the governed source register and "
                                        "runtime guides already in the system prompt. Return exactly "
                                        "`FINAL_REPORT` followed by the entire reader-ready Markdown report. "
                                        "Every required section, factual/numeric claim, comparator table, "
                                        "inline citation and final numbered Sources/Methodology entry must be "
                                        "model-authored in this replacement. Meet the full configured word floor "
                                        f"of {min_words} words before the source register; do not compress sections "
                                        "into a summary. Use only citation markers already present in the governed "
                                        f"register ([1] through [{source_count}]) and give every marker you use a "
                                        "matching final direct-URL source entry.\n\n"
                                        "Validation deficit ledger:\n- " + deficit_ledger
                                        + (
                                            "\n\nCURRENT-RUN REFRESHED GOVERNED SOURCE REGISTER: this "
                                            "register supersedes all earlier source URL and marker mappings "
                                            "in the system prompt. Use only these current, live-validated "
                                            "sources for this complete replacement report.\n"
                                            + preflight_source_register
                                            if live_link_failure and preflight_source_register
                                            else ""
                                        )
                                    ),
                                },
                            ]
                        )
                        if retry.get("tool_call") or retry.get("final_answer") is None:
                            raise RuntimeError(
                                "AGENTIC_DOCUMENT_CHECKPOINT_INCOMPLETE: the model did not return a "
                                "complete replacement FINAL_REPORT"
                            )
                        content = _final_text(retry.get("final_answer"), store)
                    inline_images, figures = await _render_configured_agentic_visuals()
            publication = await tool_adapter._publish_document(
                {
                    "content": content,
                    "current_year": today.year,
                    "min_sections": section_count,
                    "min_words": min_words,
                    "quality_controls": tool_adapter._default_quality_controls,
                    "brand": tool_adapter._default_brand,
                    "inline_images": inline_images,
                    "figures": figures,
                    "quality_self_assessment": quality_self_assessment,
                    "pre_publish_artifacts": deferred_model_artifacts,
                }
            )
            if not publication.get("written") or not publication.get("delivered"):
                raise RuntimeError("AGENTIC_DOCUMENT_DELIVERY_REQUIRED: publication did not persist and deliver")
        return {
            "content": content,
            "services_invoked": list(tool_adapter.invocations),
            "agent_trace": {
                "strategy": "react-model-authored-chunks" if _agentic_chunked_authoring else "react",
                "iterations_used": len(model_chunk_records) if trace is None else trace.iterations_used,
                "terminated_by": "answer" if trace is None else trace.terminated_by,
                "wall_time_seconds": None if trace is None else round(trace.wall_time_seconds, 2),
                "tool_calls": ["filemcpserver0::write_file", "filemcpserver0::read_file"]
                if trace is None else [o.tool_name for o in trace.observations],
                "model_authoring_run_id": model_authoring_run_id or None,
                "run_artifact_path": tool_adapter._default_working_path if _agentic_document else None,
                "model_authored_chunks": model_chunk_records,
                "runtime_guide_bundle": tool_adapter.runtime_guide_bundle_evidence if _agentic_document else None,
                "file_mcp_mirrors": list(tool_adapter._file_mcp_mirror_evidence) if _agentic_document else [],
                "publication": publication,
                "declared_visuals": len(figures) if _agentic_document else None,
                "model_authored_visual_plan": model_visual_plan_evidence if _agentic_document else {},
                "model_authored_quality_assessment": quality_self_assessment if _agentic_document else {},
                "model_authored_citation_selections": citation_selection_records
                if _agentic_document else [],
                "completion_checkpoints": completion_checkpoints if _agentic_document else [],
                "source_register_refreshes": source_register_refreshes if _agentic_document else [],
                "research_ingest": list(tool_adapter._research_ingest_records) if _agentic_document else [],
            },
        }

    if strategy == AgentStrategy.RLM.value:
        has_bound_tools = any(d.get("kind") in {"service", "subexpert"} for d in descriptors)
        if has_bound_tools:
            config = ReActConfig(
                max_iterations=max_iter,
                max_wall_time_seconds=max_wall,
                memory_scope=memory_scope,
                tools_available=descriptors,
            )
            trace = await ReActLoop(config, llm_adapter, tool_adapter).run(input_text)
            content = _final_text(trace.final_answer, store)
            content, report_recovery = await _recover_thin_report_if_requested(
                content=content,
                tool_adapter=tool_adapter,
                params=params,
                input_text=input_text,
            )
            warnings = [
                "cloud_dog_agent RLMRunner has no tool executor; bound tools were routed through the service tool adapter explicitly"
            ]
            if report_recovery:
                warnings.append("thin report final answer was recovered through compose_report")
            return {
                "content": content,
                "services_invoked": list(tool_adapter.invocations),
                "agent_trace": {
                    "strategy": "rlm",
                    "routing": "tool_enabled_react_adapter",
                    "warnings": warnings,
                    "report_recovery": report_recovery,
                    "iterations_used": trace.iterations_used,
                    "terminated_by": trace.terminated_by,
                    "tool_calls": [o.tool_name for o in trace.observations],
                },
            }
        config = RLMConfig(max_iterations=max_iter, max_wall_time_seconds=max_wall, memory_scope=memory_scope)
        trace = await RLMRunner(config, llm_adapter).run(input_text)
        return {"content": _final_text(getattr(trace, "final_result", ""), store),
                "services_invoked": [],
                "agent_trace": {"strategy": "rlm", "routing": "native_rlm"}}

    # reflexion: wraps a ReAct inner run
    config = ReflexionConfig(max_iterations=max_iter, max_wall_time_seconds=max_wall, memory_scope=memory_scope)
    react_cfg = ReActConfig(max_iterations=max_iter, max_wall_time_seconds=max_wall, tools_available=descriptors)
    inner = ReActLoop(react_cfg, llm_adapter, tool_adapter)
    trace = await ReflexionWrapper(config, llm_adapter, inner.run).run(input_text)
    return {"content": _final_text(getattr(trace, "final_answer", ""), store),
            "services_invoked": list(tool_adapter.invocations),
            "agent_trace": {"strategy": "reflexion"}}


def _final_text(final_answer: Any, store: _ArtifactStore) -> str:
    """Resolve a final answer that may itself be (or reference) a spilled artifact."""
    if isinstance(final_answer, str):
        if final_answer.startswith(_REF_PREFIX):
            resolved = store.get(final_answer)
            if resolved is not None:
                value = resolved if isinstance(resolved, str) else json.dumps(resolved, default=str)
                return clean_final_content(value)
        return clean_final_content(final_answer)
    if final_answer is None:
        return ""
    return clean_final_content(json.dumps(final_answer, default=str))


def _as_int(value: Any, default: int) -> int:
    """Coerce ``value`` to int, returning ``default`` when conversion fails."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    """Coerce ``value`` to float, returning ``default`` when conversion fails."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _as_bool(value: Any, default: bool) -> bool:
    """Coerce ``value`` to bool, returning ``default`` when value is absent."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
