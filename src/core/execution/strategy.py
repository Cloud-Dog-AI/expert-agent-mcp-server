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
"""

from __future__ import annotations

import json
import re
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


# --------------------------------------------------------------------------- #
# Artifact store (request-scoped; NOT an agent memory store — pure tool I/O)
# --------------------------------------------------------------------------- #
class _ArtifactStore:
    """Holds large tool results for the lifetime of a single execution.

    This is transient per-call plumbing for tool outputs, not a durable or
    cross-session agent memory store (which PS-96 §14.1 reserves for
    ``cloud_dog_cache.agent_memory``)."""

    def __init__(self) -> None:
        self._items: Dict[str, Any] = {}
        self._n = 0

    def put(self, value: Any) -> str:
        self._n += 1
        ref = f"{_REF_PREFIX}{self._n}"
        self._items[ref] = value
        return ref

    def get(self, ref: str) -> Any:
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
    ) -> None:
        self._llm = llm_manager
        self._system = system_prompt or ""
        self._tools = tools or []
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._num_ctx = num_ctx
        self._think = think

    def _protocol_block(self) -> str:
        lines = [
            "",
            "## Operating protocol (ReAct)",
            "Respond with ONE JSON object and nothing else. Either call a tool:",
            '  {"reasoning": "<brief>", "tool_call": {"name": "<tool>", "arguments": {<small>}}}',
            "or finish:",
            '  {"reasoning": "<brief>", "final_answer": "<short summary>"}',
            "",
            "Available tools:",
        ]
        if self._tools:
            for t in self._tools:
                lines.append(f"  - {t.get('name')}: {t.get('description', '')}")
        else:
            lines.append("  (none)")
        lines += [
            "",
            "Rules: keep tool arguments SMALL. Never paste large content (document "
            'sections, file bodies) into arguments — pass a "ref" token (e.g. "art:3") '
            "returned by a previous tool instead. Output ONLY the JSON object.",
        ]
        return "\n".join(lines)

    async def call(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
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
        last_text = ""
        for attempt in range(3):
            msgs = list(base)
            if attempt:
                msgs.append({
                    "role": "user",
                    "content": (
                        "Your previous reply was not a single valid JSON action object. "
                        "Reply NOW with ONLY one JSON object and nothing else: either "
                        '{"reasoning":"...","tool_call":{"name":"<tool>","arguments":{...}}} '
                        'or {"reasoning":"...","final_answer":"..."}. No prose, no markdown fences.'
                    ),
                })
            extra: Dict[str, Any] = {}
            if self._num_ctx:
                extra["num_ctx"] = int(self._num_ctx)
            if self._think:
                extra["think"] = True
            response = await self._llm.generate(
                messages=msgs, temperature=self._temperature, max_tokens=self._max_tokens, **extra
            )
            raw = (response.get("content") if isinstance(response, dict) else str(response)) or ""
            text = _strip_think(raw)  # qwen3 reasoning must not reach the JSON parser
            last_text = text
            parsed = self._parse(text)
            if parsed.get("tool_call") or parsed.get("final_answer") is not None:
                return parsed
        # Could not coax a structured action; surface the last text as the answer
        # so the loop terminates cleanly rather than spinning.
        return {"reasoning": "", "tool_call": None, "final_answer": last_text.strip() or None}

    @staticmethod
    def _parse(text: str) -> Dict[str, Any]:
        """Extract the ReAct envelope from model text. Robust to fences/prose."""
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
            return {"reasoning": reasoning, "tool_call": None, "final_answer": None}
        # No parseable envelope (prose drift): signal "no action" so the caller
        # can retry for a structured reply rather than ending the loop on prose.
        return {"reasoning": "", "tool_call": None, "final_answer": None}


def _strip_think(text: Any) -> str:
    """Strip qwen3 ``<think>...</think>`` chain-of-thought (and an unclosed leading
    think block when the token budget truncated the close tag) from model output."""
    s = str(text or "")
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.DOTALL)
    s = re.sub(r"<think>.*$", "", s, flags=re.DOTALL)
    return s.strip()


# Heading regex for a TOP-LEVEL (#/##, never ###) "Sources"/"References" section heading.
_TOP_SOURCES_RE = re.compile(r"\n#{1,2}[ \t]+(?:Sources|References)\b", re.IGNORECASE)


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
        return str(value).replace("{zone}", zone)
    sections = [dict(s, brief=fz(s.get("brief", ""))) for s in (th.get("sections") or []) if isinstance(s, dict)]
    # Per-theme charts (so each rotated theme carries its OWN data chart: a real sql-agent chart
    # where the dataset covers the theme, or a web-extracted chart where it does not). {zone} is
    # interpolated through every string of each chart spec (titles, SQL questions, web topics).
    def fz_deep(o: Any) -> Any:
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
    return text[:matches[-1].start()].rstrip()


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
        return stamp if int(m.group(1)) < cy else m.group(0)
    s = re.sub(r"\bAs of\s+(?!the\s+\d)(?:[\w*\-,]+\s+){0,5}?(20\d{2})\b", repl, s)

    # 3) Put the run date in the TITLE (H1) if it carries no date of its own.
    def _title_date(m: "re.Match") -> str:
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
    ) -> None:
        self._store = store
        self._dispatch_service = dispatch_service
        self._dispatch_subexpert = dispatch_subexpert
        self._spill = spill_threshold
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
        self._default_title = _d.get("title")
        self._default_sections = _d.get("sections") or []
        self._default_target = _d.get("target")
        self._default_template_family = _d.get("template_family")
        self._registry: Dict[str, Dict[str, Any]] = {}
        for t in tools or []:
            name = str(t.get("name") or "")
            if not name:
                continue
            self._registry[name] = t
            self._registry.setdefault(name.split(".")[-1], t)  # short alias

    # Always-available presentation/quality/delivery utilities (generic; NOT
    # task-specific and NOT agent loops/memory — deterministic transforms + the
    # bound file/notify services).
    _BUILTINS = {"render_markdown", "quality_gate", "publish_document", "web_research", "compose_report"}

    async def execute(self, tool_name: str, arguments: Dict[str, Any]) -> Any:
        short = str(tool_name).split(".")[-1]
        args = self._store.resolve(arguments or {})
        if short in self._BUILTINS:
            try:
                if short == "render_markdown":
                    return self._maybe_spill(self._render_markdown(args))
                if short == "compose_report":
                    return self._maybe_spill(await self._compose_report(args))
                if short == "publish_document":
                    return await self._publish_document(args)
                if short == "web_research":
                    return self._maybe_spill(await self._web_research(args))
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
                    text += "\n\nCURRENT SOURCES (ground every claim in these, cite [n]):\n" + self._research_grounding
                raw = await self._dispatch_subexpert(spec["child_id"], text, args)
            else:
                raw = await self._dispatch_service(spec["service"], spec["tool"], args)
        except Exception as exc:  # surface as an observation, do not crash the loop
            logger.warning("tool '%s' failed: %s", tool_name, exc)
            return {"error": str(exc)[:300]}
        return self._maybe_spill(raw)

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
                            nxt = json.loads(blk["text"]); break
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
        if gen_id is None:
            return {"error": "no document-generator sub-expert is bound to this expert"}
        default_words = int(args.get("target_words") or 850)
        grounding = self._research_grounding or "(no external sources retrieved — rely on well-established, verifiable facts)"

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
            "supported by one of the CURRENT SOURCES below and cited inline as [n]. Do NOT state any event or date "
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
            prompt = (
                f"You are writing ONE section of a long, detailed professional report titled "
                f"\"{title}\"" + (f" about {target}" if target else "") + ".\n\n"
                f"Write the FULL \"{stitle}\" section: about {words} words of substantive, specific, "
                "well-evidenced UK-English prose — concrete facts, figures, named entities, dates and "
                "examples; use short paragraphs, ### sub-headings where helpful, and a Markdown table "
                "where it adds value. Write the complete section body — NOT a summary, NOT placeholders.\n\n"
                f"Section brief: {brief}\n\n"
                + _discipline +
                "\n\nCURRENT SOURCES (the ONLY admissible basis for facts and dates):\n"
                + grounding +
                f"\n\nOutput ONLY this section, beginning with the heading \"## {stitle}\"."
            )
            try:
                raw = await self._dispatch_subexpert(gen_id, prompt, {})
            except Exception as exc:
                raw = f"## {stitle}\n\n_(section generation failed: {str(exc)[:120]})_"
            body = _strip_think(raw if isinstance(raw, str) else str(raw)).strip()
            # Force a single canonical "## <title>" heading per section: strip whatever heading
            # level/text the generator opened with (it often emits ### or repeats the title) and
            # demote any other top-level (#/##) headings it produced to ### so the section count
            # and outline are correct — each compose_report section is exactly one ## section.
            body = re.sub(r"^\s*#{1,6}\s+.*(?:\n|$)", "", body, count=1)
            body = re.sub(r"^(#{1,2})(\s+)", r"###\2", body, flags=re.M)  # demote stray #/## to ###
            parts.append(f"## {stitle}\n\n" + body.strip())

        doc = f"# {title}\n\n" + "\n\n".join(parts)
        if self._research_sources_md and not _TOP_SOURCES_RE.search(doc):
            doc += "\n\n" + self._research_sources_md
        doc = _freshen_as_of(doc, args.get("current_year"))
        return doc

    def _svc_for(self, tool_suffix: str, default_service: str) -> str:
        """Resolve the bound service name that exposes ``tool_suffix`` (e.g. write_file,
        send_notification), falling back to the platform default."""
        for name, spec in self._registry.items():
            if spec.get("kind") == "service" and str(spec.get("tool")) == tool_suffix:
                return str(spec.get("service"))
        return default_service

    async def _web_research(self, args: Dict[str, Any]) -> str:
        """Search the web (bound search service) and return a CITABLE source pack: numbered
        grounding snippets (title, date, content) plus a ready-made '## Sources' Markdown
        block of real links. This is what gives the document current facts, figures and
        links instead of vague generalities."""
        query = str(args.get("query") or "")
        max_results = int(args.get("max_results") or 6)
        raw = await self._dispatch_service(self._svc_for("search", "searchmcp0"), "search",
                                           {"query": query, "max_results": max_results})
        results = _search_results(raw)
        grounding, sources = [], []
        for i, r in enumerate([x for x in results if isinstance(x, dict)][:max_results], 1):
            title = (str(r.get("title") or "Source")).strip()
            url = (str(r.get("url") or "")).strip()
            date = (str(r.get("publishedDate") or "")).strip()[:10]
            snip = re.sub(r"\s+", " ", str(r.get("content") or "")).strip()[:500]
            grounding.append(f"[{i}] {title}" + (f" — {date}" if date else "") + (f": {snip}" if snip else ""))
            sources.append(f"[{i}] [{title}]({url})" if url else f"[{i}] {title}")
        if not grounding:
            return "No current sources were retrieved for this query."
        self._research_grounding = "\n".join(grounding)
        self._research_sources_md = "## Sources\n\n" + "\n".join(sources)
        return ("CURRENT SOURCES — ground EVERY factual claim in these and cite inline as [n]; "
                "include the specific names, dates and numbers they contain; reproduce the "
                "'## Sources' block verbatim as the final section of the document:\n\n"
                + self._research_grounding + "\n\n" + self._research_sources_md)

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

    async def _publish_document(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic delivery tail collapsed into ONE reliable tool call so the
        agent cannot drift/terminate before delivering: quality-check -> render to
        HTML -> write the Markdown to storage -> email the FULL HTML document
        (content_style:html, format_mode:passthrough). Returns a small result."""
        content = args.get("content") or args.get("document") or ""
        if not isinstance(content, str):
            content = json.dumps(content, default=str)
        # Guarantee a real, clickable '## Sources' section: small models often hallucinate
        # generic/placeholder URLs (example.com, ...). Replace any trailing Sources block with
        # the actual links captured by web_research so the document always carries real links;
        # if research returned nothing, at least strip the hallucinated placeholders.
        sources_md = args.get("sources") or self._research_sources_md
        if sources_md:
            content = _strip_trailing_sources(content)
            content = content + "\n\n" + str(sources_md)
        elif re.search(r"example\.(com|org|net)|//(www\.)?example\b|placeholder", content, re.IGNORECASE):
            content = _strip_trailing_sources(content)
        # Reasoning models habitually open with stale "As of <past-year>" framing even when the
        # cited sources are current. Deterministically refresh the document's OWN temporal framing
        # to the run date so the brief reads as current (factual year references are untouched).
        content = _freshen_as_of(content, args.get("current_year"))
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
        profile = args.get("profile") or "google_drive"

        qg = self._quality_gate({
            "content": content, "current_year": args.get("current_year"),
            "min_words": args.get("min_words", 600), "min_sections": args.get("min_sections", 1)})
        html = self._render_markdown({"content": content})

        # Additive visuals: inject inline-CID figures (maps/charts) at their headings and append
        # a "Further Detail & Previous Reports" links section. All optional — absent => unchanged.
        inline_images = args.get("inline_images") or []
        figures = args.get("figures") or []
        previous_reports = args.get("previous_reports") or []
        if figures or previous_reports:
            from src.core.execution import visuals as _visuals
            if previous_reports:
                prev_html = _visuals.previous_reports_html(previous_reports)
                if prev_html:
                    html = _visuals.inject_before_sources(html, prev_html)
            if figures:
                html = _visuals.inject_figures(html, figures)

        written = None
        if working_path:
            try:
                written = await self._dispatch_service(
                    self._svc_for("write_file", "filemcpserver0"), "write_file",
                    {"profile": profile, "path": working_path, "content": content, "overwrite": True})
            except Exception as exc:
                written = {"error": str(exc)[:200]}

        # default each destination to full-HTML passthrough so the inbox shows the
        # whole document, not an LLM summary/link.
        dests = []
        for d in destinations:
            if isinstance(d, dict):
                d = dict(d)
                d.setdefault("preferences", {"content_style": "html", "format_mode": "passthrough"})
                dests.append(d)
        notif_args: Dict[str, Any] = {
            "destinations": dests, "subject": title,
            "content": [{"type": "html", "body": html}],
            "idempotency_key": str(args.get("idempotency_key") or title)}
        # Forward inline CID images so embedded <img src="cid:..."> figures resolve in the
        # inbox (the notification-agent now supports a top-level inline_images field).
        if inline_images:
            notif_args["inline_images"] = inline_images
        sent = await self._dispatch_service(
            self._svc_for("send_notification", "notificationagent0"), "send_notification",
            notif_args)
        return {"delivered": not (isinstance(sent, dict) and sent.get("error")),
                "quality": qg, "written": bool(written) and not (isinstance(written, dict) and written.get("error")),
                "figures": len(inline_images),
                "notification": sent if not isinstance(sent, dict) else {k: sent.get(k) for k in ("message_id", "status", "id") if k in sent}}

    @staticmethod
    def _quality_gate(args: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic output quality check. Returns {pass, issues, metrics} so the
        agent can revise before delivery. Catches the common defects: stale dates,
        thin/summary content, missing sections, and missing grounding."""
        content = args.get("content") or ""
        if not isinstance(content, str):
            content = json.dumps(content, default=str)
        current_year = int(args.get("current_year") or 0)
        min_words = int(args.get("min_words") or 300)
        min_sections = int(args.get("min_sections") or 1)
        issues: List[str] = []
        words = len(re.findall(r"\w+", content))
        sections = content.count("\n## ") + (1 if content.lstrip().startswith("## ") else 0)
        years = [int(y) for y in re.findall(r"\b(20[12][0-9])\b", content)]
        has_table = "|---" in content or bool(re.search(r"\n\|.*\|", content))
        links = re.findall(r"\]\((https?://[^)\s]+)\)", content) + re.findall(r"(?<![\(\w])(https?://[^\s)\]]+)", content)
        # figures = concrete numbers that are NOT bare years (percentages, counts, money, etc.)
        figures = [n for n in re.findall(r"\d[\d,.]*%?", content) if not re.fullmatch(r"20[12][0-9]", n)]
        require_links = bool(args.get("require_links", True))
        min_figures = int(args.get("min_figures") or 3)
        if words < min_words:
            issues.append(f"too_thin: {words} words (< {min_words}); reads as a summary, not a full document")
        if sections < min_sections:
            issues.append(f"missing_sections: {sections} of {min_sections} expected")
        if require_links and not links:
            issues.append("no_links: the document has no source links — add a '## Sources' section of real links and cite [n]")
        if len(figures) < min_figures:
            issues.append(f"no_depth: only {len(figures)} concrete figures/numbers — add specific named facts, dates and statistics")
        if current_year:
            stale = [y for y in years if y < current_year - 0]
            if current_year not in years:
                issues.append(f"not_current: the document never references the current year {current_year}")
            # an explicit "as of <past year>" framing is the specific defect the operator flagged
            for m in re.finditer(r"as of\s+(?:early|mid|late|the start of|end of)?\s*(20[12][0-9])", content, re.I):
                if int(m.group(1)) < current_year:
                    issues.append(f"stale_as_of: '{m.group(0)}' — must be reframed to {current_year}")
                    break
        return {
            "pass": not issues,
            "issues": issues,
            "metrics": {"words": words, "sections": sections, "years": sorted(set(years)),
                        "has_table": has_table, "links": len(links), "figures": len(figures),
                        "current_year": current_year},
        }

    @staticmethod
    def _render_markdown(args: Dict[str, Any]) -> str:
        """Render Markdown -> inline-styled HTML email body (tables, links, headings,
        lists, rules). Inline styles because Gmail/Outlook strip <style> blocks."""
        md = args.get("content") or args.get("markdown") or ""
        if not isinstance(md, str):
            md = json.dumps(md, default=str)
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

        def inline(t: str) -> str:
            t = _html.escape(t, quote=False)
            t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", rf'<a href="\2" style="{S_A}">\1</a>', t)
            t = re.sub(r'(?<![">\w])(https?://[^\s<)\]]+)', rf'<a href="\1" style="{S_A}">\1</a>', t)
            t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
            t = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", t)
            return t

        out: List[str] = []
        lines = md.split("\n")
        i, n = 0, len(lines)
        while i < n:
            ln = lines[i]
            mh = re.match(r"(#{1,4})\s+(.*)", ln)
            if mh:
                lvl = len(mh.group(1))
                out.append(f"<h{lvl} style=\"{S_H.get(lvl, S_H[4])}\">{inline(mh.group(2))}</h{lvl}>")
                i += 1; continue
            if re.match(r"\s*\|.*\|\s*$", ln) and i + 1 < n and re.match(r"\s*\|?[\s:-]+\|[\s:|-]*$", lines[i + 1]):
                header = [c.strip() for c in ln.strip().strip("|").split("|")]
                i += 2
                rows = []
                while i < n and re.match(r"\s*\|.*\|\s*$", lines[i]):
                    rows.append([c.strip() for c in lines[i].strip().strip("|").split("|")]); i += 1
                th = "".join(f'<th style="{S_TH}">{inline(c)}</th>' for c in header)
                trs = "".join("<tr>" + "".join(f'<td style="{S_TD}">{inline(c)}</td>' for c in r) + "</tr>" for r in rows)
                out.append(f'<table style="{S_TABLE}"><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>')
                continue
            if re.match(r"\s*[-*]\s+", ln):
                items = []
                while i < n and re.match(r"\s*[-*]\s+", lines[i]):
                    items.append(f"<li style=\"{S_P}\">{inline(re.sub(r'^\s*[-*]\s+', '', lines[i]))}</li>"); i += 1
                out.append("<ul>" + "".join(items) + "</ul>"); continue
            if re.match(r"\s*---+\s*$", ln):
                out.append(f'<hr style="{S_HR}">'); i += 1; continue
            if ln.strip():
                out.append(f'<p style="{S_P}">{inline(ln)}</p>')
            i += 1
        inner = "\n".join(out)
        return ("<!doctype html><html><head><meta charset='utf-8'></head>"
                "<body style=\"font-family:Georgia,serif;max-width:900px;margin:1.5em auto;"
                "line-height:1.55;color:#1a1a1a;padding:0 14px\">\n" + inner + "\n</body></html>")

    def _maybe_spill(self, raw: Any) -> Any:
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
        elif isinstance(item, dict) and item.get("service") and item.get("tool"):
            service, tool = item["service"], item["tool"]
            desc = item.get("description")
        if service and tool:
            descriptors.append(
                {
                    "name": f"{service}.{tool}",
                    "description": desc or f"Call {tool} on {service}.",
                    "kind": "service",
                    "service": service,
                    "tool": tool,
                }
            )

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

    auth = auth_context or {}

    async def _dispatch_service(service_name: str, tool_name: str, args: Dict[str, Any]) -> Any:
        from src.core.service.manager import ServiceManager

        svc = ServiceManager(db).get_service(name=service_name)
        if not svc:
            return {"error": f"service '{service_name}' not found"}
        res = await executor.service_manager.invoke_tool(
            service_id=int(svc.id), tool_name=tool_name, arguments=args, auth_context=auth
        )
        # unwrap the composition envelope to the tool's own result, tolerating
        # SSE-framed responses ("data: {...}") from streaming MCP servers (searchmcp).
        inner = res.get("result", res) if isinstance(res, dict) else res
        return _unwrap_sse(inner)

    def _make_http_get(service_name: str) -> Callable[[str], Any]:
        """Build an async REST GET bound to ``service_name`` for fetching non-MCP assets
        (e.g. the chart service's PNG bytes at ``GET <base>/api/assets/{id}``).

        The base URL is the service's registered ``endpoint_url`` with any trailing ``/mcp``
        suffix removed; the credential is resolved by the SAME composition-layer auth logic
        used for MCP calls (Vault-backed X-API-Key / Bearer) so no secret is duplicated here.
        """
        async def _get(path: str) -> Any:
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
            try:
                return resp.json()
            except Exception:
                return resp.text

        return _get

    async def _dispatch_subexpert(child_id: int, text: str, args: Dict[str, Any]) -> Any:
        # Only override the sub-expert's own per-agent LLM config when the caller
        # explicitly set a value; otherwise the child expert's stored llm_params
        # (num_ctx / num_predict / temperature) govern — so a generator expert keeps
        # its large context + output budget instead of being clamped here.
        sub_params: Dict[str, Any] = {"persist_session": False}
        if args.get("max_tokens") is not None:
            sub_params["max_tokens"] = int(args["max_tokens"])
        if args.get("temperature") is not None:
            sub_params["temperature"] = float(args["temperature"])
        result = await executor.execute(
            expert_id=int(child_id), input_text=text, parameters=sub_params, auth_context=auth
        )
        if isinstance(result, dict):
            return result.get("output_text", "")
        return str(result)

    # Capture the run's delivery spec (destinations / working_path / title) from the input so
    # publish_document can fall back to it when the model omits those args.
    _defaults: Dict[str, Any] = {}
    try:
        _spec = json.loads(input_text) if isinstance(input_text, str) else (input_text or {})
        if isinstance(_spec, dict):
            _defaults = {"destinations": _spec.get("destinations"),
                         "working_path": _spec.get("working_path"),
                         "title": _spec.get("title"),
                         "sections": _spec.get("sections"),
                         "target": _spec.get("target"),
                         "template_family": _spec.get("template_family"),
                         "recency_days": _spec.get("recency_days"),
                         "theme_rotation": _spec.get("theme_rotation"),
                         "country_rotation": _spec.get("country_rotation"),
                         "visuals": _spec.get("visuals"),
                         "previous_reports": _spec.get("previous_reports")}
    except Exception:
        _defaults = {}
    tool_adapter = AgentToolAdapter(descriptors, _dispatch_service, _dispatch_subexpert, store, defaults=_defaults)

    # --- Deterministic document pipeline -----------------------------------------------------
    # The "document" strategy does NOT rely on the (drift-prone) model to orchestrate: it runs
    # the three builtins in a fixed order — web_research -> compose_report (EVERY section, in
    # full) -> publish_document — driven entirely by the input template. This is what reliably
    # reaches the depth of the original template-driven reports (a react loop may skip the deep
    # section-by-section step). Still 100% template/data-driven; no per-demo code.
    if strategy == "document":
        import datetime as _dt
        _year = _dt.date.today().year
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
                logger.info("document pipeline: using template %s (%s) — %d sections",
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
        import datetime as _ddt
        _today = _ddt.date.today()
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
        try:
            await tool_adapter._web_research({"query": _q, "max_results": _maxr})
        except Exception as exc:  # research is best-effort grounding
            logger.warning("document pipeline: web_research failed: %s", exc)
        doc = await tool_adapter._compose_report(
            {"target_words": _tw, "current_year": _year,
             "current_date": _today.isoformat(), "recency_days": _recency})
        if isinstance(doc, dict) and doc.get("error"):
            return {"content": "document pipeline failed at compose_report: " + str(doc.get("error")),
                    "agent_trace": {"strategy": "document", "error": True}}
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
        published = await tool_adapter._publish_document(
            {"content": doc, "current_year": _year,
             "min_sections": len(_sections), "min_words": int(_tw) * max(1, len(_sections)) // 2,
             "inline_images": _inline_images, "figures": _figures,
             "previous_reports": _defaults.get("previous_reports") or []})
        words = len(str(doc).split())
        return {"content": (f"Generated and delivered '{_defaults.get('title')}' — "
                            f"{len(_sections)} sections, ~{words} words, {len(_inline_images)} figures"
                            + (f" (template {_template_id})" if _template_id else "") + f". {published}"),
                "agent_trace": {"strategy": "document", "sections": len(_sections),
                                "figures": len(_inline_images),
                                "words": words, "template_id": _template_id}}

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
    )

    if strategy == AgentStrategy.REACT.value:
        config = ReActConfig(
            max_iterations=max_iter,
            max_wall_time_seconds=max_wall,
            memory_scope=memory_scope,
            tools_available=descriptors,
        )
        trace = await ReActLoop(config, llm_adapter, tool_adapter).run(input_text)
        content = _final_text(trace.final_answer, store)
        return {
            "content": content,
            "agent_trace": {
                "strategy": "react",
                "iterations_used": trace.iterations_used,
                "terminated_by": trace.terminated_by,
                "wall_time_seconds": round(trace.wall_time_seconds, 2),
                "tool_calls": [o.tool_name for o in trace.observations],
            },
        }

    if strategy == AgentStrategy.RLM.value:
        config = RLMConfig(max_iterations=max_iter, max_wall_time_seconds=max_wall, memory_scope=memory_scope)
        trace = await RLMRunner(config, llm_adapter).run(input_text)
        return {"content": _final_text(getattr(trace, "final_answer", ""), store),
                "agent_trace": {"strategy": "rlm"}}

    # reflexion: wraps a ReAct inner run
    config = ReflexionConfig(max_iterations=max_iter, max_wall_time_seconds=max_wall, memory_scope=memory_scope)
    react_cfg = ReActConfig(max_iterations=max_iter, max_wall_time_seconds=max_wall, tools_available=descriptors)
    inner = ReActLoop(react_cfg, llm_adapter, tool_adapter)
    trace = await ReflexionWrapper(config, llm_adapter, inner.run).run(input_text)
    return {"content": _final_text(getattr(trace, "final_answer", ""), store),
            "agent_trace": {"strategy": "reflexion"}}


def _final_text(final_answer: Any, store: _ArtifactStore) -> str:
    """Resolve a final answer that may itself be (or reference) a spilled artifact."""
    if isinstance(final_answer, str):
        if final_answer.startswith(_REF_PREFIX):
            resolved = store.get(final_answer)
            if resolved is not None:
                return resolved if isinstance(resolved, str) else json.dumps(resolved, default=str)
        return final_answer
    if final_answer is None:
        return ""
    return json.dumps(final_answer, default=str)


def _as_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
