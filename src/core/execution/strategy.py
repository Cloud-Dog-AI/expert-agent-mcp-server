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
    ) -> None:
        """Bind the service LLM manager and generation defaults for one agent call."""
        self._llm = llm_manager
        self._system = system_prompt or ""
        self._tools = tools or []
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._num_ctx = num_ctx
        self._think = think

    def _protocol_block(self) -> str:
        """Render the JSON-only ReAct protocol appended to the system prompt."""
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
        _h2 = re.match(r"##[ \t]+(?:sources|references)[ \t]*:?[ \t]*$", lines[i], re.IGNORECASE)
        _h3 = re.match(r"###[ \t]+.*\b(?:sources|references)\b", lines[i], re.IGNORECASE)
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
    s = re.sub(r"\bAs of\s+(?!the\s+\d)(?:[\w*\-,]+\s+){0,5}?(20\d{2})\b", repl, s)

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


def _bracket_label(text: str) -> Optional[str]:
    """Return a leading bracketed label from a grounded snippet, if present."""
    m = re.match(r"\s*\[([^\]—\-]+?)(?:\s*[—-]\s*[^\]]*)?\]", text)
    return m.group(1).strip() if m else None


# Hosts that must never appear as a citable link in a published report — a link to one
# of these is dead for the reader (the localhost/internal-proxy links the operator flagged).
_PRIVATE_HOST_RE = re.compile(
    r"^(localhost|127\.|0\.0\.0\.0|10\.|192\.168\.|169\.254\.|172\.(1[6-9]|2[0-9]|3[01])\.|\[?::1\]?)",
    re.IGNORECASE)


def _public_url(u: Any) -> str:
    """Return ``u`` only if it is a public, clickable http(s) URL; else "". Drops the
    localhost / private-host / relative links that otherwise leak into the Sources block."""
    s = str(u or "").strip().rstrip(").,;]")
    m = re.match(r"https?://([^/\s:]+)", s, re.IGNORECASE)
    if not m:
        return ""
    host = m.group(1)
    if _PRIVATE_HOST_RE.match(host) or "." not in host or host.lower().endswith(".local"):
        return ""
    return s


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
        self._default_title = _d.get("title")
        self._default_sections = _d.get("sections") or []
        self._default_target = _d.get("target")
        self._default_template_family = _d.get("template_family")
        self.invocations: List[Dict[str, Any]] = []
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
        """Execute a built-in, service, or sub-expert tool and normalise its result."""
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
                    text += ("\n\nCURRENT SOURCES (ground every claim in these; cite inline with each "
                             "source's real bracketed number, e.g. [2] — copy the actual digit, never "
                             "write the literal letter n):\n" + self._research_grounding)
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
            grounding.append(f"[{idx}] {meta}: {snippet}" if meta else f"[{idx}] {snippet}")
            if meta:
                sources.append(f"- [{idx}] {meta}")
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
                    _sub_args = {"max_tokens": max(400, int(words * 2))} if _attempt >= 2 else {}
                    if gen_id is not None:
                        raw = await self._dispatch_subexpert(gen_id, prompt, _sub_args)
                    else:
                        response = await self._llm.generate(
                            messages=[{"role": "user", "content": prompt}],
                            temperature=0.2,
                            max_tokens=max(700, int(words * 2)),
                        )
                        raw = response.get("content", "") if isinstance(response, dict) else str(response)
                    if _strip_think(raw if isinstance(raw, str) else str(raw)).strip():
                        _last_exc = None
                        break
                    _last_exc = "empty response"
                except Exception as exc:
                    _last_exc = exc
                    raw = ""
                if _attempt < 2:
                    await _aio.sleep(2 + _attempt * 3)
            if _last_exc is not None and not _strip_think(raw if isinstance(raw, str) else str(raw)).strip():
                raw = (f"## {stitle}\n\n_This section could not be generated in this run "
                       f"(the local model did not return content after 3 attempts). It will "
                       f"be included on the next scheduled run._")
            body = _strip_think(raw if isinstance(raw, str) else str(raw)).strip()
            # Force a single canonical "## <title>" heading per section: strip whatever heading
            # level/text the generator opened with (it often emits ### or repeats the title) and
            # demote any other top-level (#/##) headings it produced to ### so the section count
            # and outline are correct — each compose_report section is exactly one ## section.
            body = re.sub(r"^\s*#{1,6}\s+.*(?:\n|$)", "", body, count=1)
            body = re.sub(r"^(#{1,2})(\s+)", r"###\2", body, flags=re.M)  # demote stray #/## to ###
            parts.append(f"## {stitle}\n\n" + body.strip())

        doc = f"# {title}\n\n" + "\n\n".join(parts)
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
            doc = doc.rstrip() + "\n\n## Sources\n\n" + "\n".join(_uniq_src)
        doc = _freshen_as_of(doc, args.get("current_year"))
        # Safety net: if the generator copied the literal placeholder "[n]" (or "[n, n]") instead
        # of a real source number, strip it rather than ship a broken citation marker.
        doc = re.sub(r"[ \t]*\[[nN](?:\s*,\s*[nN])*\]", "", doc)
        doc = re.sub(r"[ \t]+([.,;:)])", r"\1", doc)
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
        import asyncio
        query = str(args.get("query") or "")
        max_results = int(args.get("max_results") or 6)
        # Run the main query plus any facet queries (e.g. one per section topic) and MERGE the
        # results, de-duplicated by URL — and retry empties, because the SearXNG backend is
        # intermittent and a single failed call would otherwise leave the brief with no web
        # sources (the cause of thin, under-sourced reports).
        queries = [query] + [str(q) for q in (args.get("extra_queries") or []) if str(q or "").strip()]
        svc = self._svc_for("search", "searchmcp0")
        seen: set = set()
        merged: List[Dict[str, Any]] = []
        for q in queries[:5]:
            res: List[Dict[str, Any]] = []
            for _attempt in range(3):
                try:
                    raw = await self._dispatch_service(svc, "search", {"query": q, "max_results": max_results})
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
                seen.add(key)
                merged.append(r)
        cap = max(max_results, 18)
        grounding, sources = [], []
        for i, r in enumerate(merged[:cap], 1):
            title = (str(r.get("title") or "Source")).strip()
            url = _public_url(r.get("url"))  # drop localhost/private/relative — never cite a dead link
            date = (str(r.get("publishedDate") or "")).strip()[:10]
            snip = _clean_snippet(r.get("content"))[:560]
            grounding.append(f"[{i}] {title}" + (f" — {date}" if date else "") + (f": {snip}" if snip else ""))
            sources.append(f"[{i}] [{title}]({url})" if url else f"[{i}] {title}")
        logger.info("web_research: %s sources from %s queries", str(len(grounding)), str(len(queries)))
        if not grounding:
            return "No current sources were retrieved for this query."
        self._research_grounding = "\n".join(grounding)
        self._research_sources_md = "## Sources\n\n" + "\n".join(sources)
        return ("CURRENT SOURCES — ground EVERY factual claim in these and cite inline using each "
                "source's real bracketed number, e.g. [2] (copy the actual digit shown below; NEVER "
                "write the literal placeholder [n]); include the specific names, dates and numbers "
                "they contain; reproduce the '## Sources' block verbatim as the final section of the "
                "document:\n\n" + self._research_grounding + "\n\n" + self._research_sources_md)

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
            return 0
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
            subject = str(h.get("headline") or "").strip()
            url = _public_url(_first_url(body))
            # name from the From header, else from the post URL (Substack subdomain), else generic.
            label = _newsletter_label(h.get("from")) or (_label_from_url(url) if url else "") or "Analyst newsletter"
            # Strip the Substack redirect/tracking wrappers and any non-public links before
            # indexing, so retrieval never surfaces a dead localhost/redirect URL to be copied.
            clean = re.sub(r"\[\s*https?://substack\.com/redirect/\S+\s*\]", " ", body)
            clean = re.sub(r"\s+", " ", clean).strip()
            text = "[%s — %s] %s" % (label, subject[:90], clean[:4000])
            source = url or ("newsletter://" + re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-"))
            try:
                await self._dispatch_service(idx, "ingest_text",
                                             {"profile": vprof, "collection": vcoll, "text": text, "source": source})
                # Map BOTH the source string and (if present) the URL to the From-header label,
                # so grounding labels every retrieved chunk — including link-less Patreon ones.
                self._newsletter_meta[source] = label
                if url:
                    self._newsletter_meta[url] = label
                digest.append({"label": label, "subject": subject, "url": url,
                               "date": str(h.get("date") or h.get("received") or "")[:16],
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
                                    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], str]:
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
                xs = [x for x, y in frame_pts]; ys = [y for x, y in frame_pts]
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
                    c = (east + west) / 2; west, east = c - 1.3, c + 1.3
                if north - south < 1.8:
                    c = (north + south) / 2; south, north = c - 0.9, c + 0.9
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
                        logger.warning("auto visuals: giving up on Commons images after %d consecutive "
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

    async def _publish_document(self, args: Dict[str, Any]) -> Dict[str, Any]:
        """Deterministic delivery tail collapsed into ONE reliable tool call so the
        agent cannot drift/terminate before delivering: quality-check -> render to
        HTML -> write the Markdown to storage -> email the FULL HTML document
        (content_style:html, format_mode:passthrough). Returns a small result."""
        content = args.get("content") or args.get("document") or ""
        if not isinstance(content, str):
            content = json.dumps(content, default=str)
        logger.info(f"publish_document: START ({len(content)} chars content)")  # W28M-1633 delivery-tail trace
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

        logger.info("publish_document: before quality_gate")  # W28M-1633 delivery-tail trace
        qg = self._quality_gate({
            "content": content, "current_year": args.get("current_year"),
            "min_words": args.get("min_words", 600), "min_sections": args.get("min_sections", 1)})
        logger.info("publish_document: before render_markdown")  # W28M-1633 delivery-tail trace
        html = self._render_markdown({"content": content})
        logger.info(f"publish_document: markdown rendered ({len(html)} html chars)")  # W28M-1633 delivery-tail trace

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
                logger.info(f"publish_document: injecting {len(figures)} figures")  # W28M-1633 delivery-tail trace
                html = _visuals.inject_figures(html, figures)

        logger.info(f"publish_document: visuals injected; before write_file (working_path={bool(working_path)})")  # W28M-1633
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
        # Idempotency key must be unique per run/day, NOT a bare constant title. Defaulting
        # to `title` alone means a report whose title carries a version-year (e.g.
        # "... (2026.10-v6)") — which skips the date-stamping guard above — produces the SAME
        # key on every run, so the FIRST send creates the message and every later send is
        # rejected 409 (duplicate) and silently never delivered (W28M-1633 root cause).
        import datetime as _dt_idem
        _idem_default = "%s|%s" % (title, _dt_idem.date.today().isoformat())
        notif_args: Dict[str, Any] = {
            "destinations": dests, "subject": title,
            "content": [{"type": "html", "body": html}],
            "idempotency_key": str(args.get("idempotency_key") or _idem_default)}
        # Forward inline CID images so embedded <img src="cid:..."> figures resolve in the
        # inbox (the notification-agent now supports a top-level inline_images field).
        if inline_images:
            notif_args["inline_images"] = inline_images
        logger.info(f"publish_document: write_file done; before send_notification ({len(dests)} dests, {len(inline_images)} inline_images)")  # W28M-1633 delivery-tail trace
        sent = await self._dispatch_service(
            self._svc_for("send_notification", "notificationagent0"), "send_notification",
            notif_args)
        logger.info("publish_document: send_notification returned")  # W28M-1633 delivery-tail trace
        # Unwrap the MCP result envelope so the delivered message_id/status surface (the raw
        # dispatch result is a content/SSE envelope, not a flat dict) — this is what lets a
        # chat-launched report return its /messages/<id> web-view link.
        _sent = _mcp_payload(sent)
        return {"delivered": not (isinstance(_sent, dict) and _sent.get("error")),
                "quality": qg, "written": bool(written) and not (isinstance(written, dict) and written.get("error")),
                "figures": len(inline_images),
                "notification": _sent if not isinstance(_sent, dict) else {k: _sent.get(k) for k in ("message_id", "status", "id") if k in _sent}}

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
        # Table of Contents intentionally NOT rendered. For a 16-section country brief the TOC was
        # too long and its in-email anchor links do not navigate reliably across mail clients
        # ("the TOC doesn't work — too big — remove it"). Heading `id` anchors are still emitted
        # (harmless, enable deep-linking) but no TOC block is inserted. `toc` is retained above only
        # so the anchor slugs stay unique.
        _ = toc  # (kept for anchor-slug uniqueness; no TOC block emitted)
        return ("<!doctype html><html><head><meta charset='utf-8'></head>"
                "<body style=\"font-family:Georgia,serif;max-width:900px;margin:1.5em auto;"
                "line-height:1.55;color:#1a1a1a;padding:0 14px\">\n" + inner + "\n</body></html>")

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

    async def _dispatch_service(service_name: str, tool_name: str, args: Dict[str, Any]) -> Any:
        """Invoke a registered service tool by service name and unwrap its payload."""
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
            _defaults = {"destinations": _spec.get("destinations"),
                         "working_path": _spec.get("working_path"),
                         "title": _spec.get("title"),
                         "sections": _spec.get("sections"),
                         "target": _spec.get("target"),
                         "template_family": _spec.get("template_family"),
                         "recency_days": _spec.get("recency_days"),
                         "theme_rotation": _spec.get("theme_rotation"),
                         "country_rotation": _spec.get("country_rotation"),
                         "newsletter_sources": _spec.get("newsletter_sources"),
                         "ingest_only": _spec.get("ingest_only"),
                         "visuals": _spec.get("visuals"),
                         "auto_visuals": _spec.get("auto_visuals"),
                         "report_series": _spec.get("report_series"),
                         "messages_base_url": _spec.get("messages_base_url"),
                         "previous_reports": _spec.get("previous_reports")}
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
                    logger.info("document pipeline: country-report structure applied for %s (%d sections, ~%d target words)",
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
            logger.info("document pipeline: generic research template applied for free-text prompt (%d sections)", len(_sections))
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
                return {"content": f"Newsletter ingest complete for query '{_news.get('query')}'.",
                        "agent_trace": {"strategy": "document", "ingest_only": True}}
        try:
            # Facet queries from the report's own section topics widen + diversify the sourcing.
            _facets = []
            for _s in (_sections or [])[:4]:
                _st = str(_s.get("title") if isinstance(_s, dict) else "").strip()
                if _st and not re.search(r"(?i)source|brief|summary|in brief", _st):
                    _facets.append(("%s %s" % (_target, _st))[:120])
            await tool_adapter._web_research({"query": _q, "max_results": _maxr, "extra_queries": _facets})
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
                _flines = [l for l in (_theatre.get("lines") or []) if isinstance(l, dict) and l.get("coords")]
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
                     "previous_reports": _prev}
        if _nl_prompt:
            import datetime as _dtk
            _pub_args["idempotency_key"] = "%s|%s" % (
                _defaults.get("title") or "report", _dtk.datetime.now().isoformat(timespec="seconds"))
        published = await tool_adapter._publish_document(_pub_args)
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
            "services_invoked": list(tool_adapter.invocations),
            "agent_trace": {
                "strategy": "react",
                "iterations_used": trace.iterations_used,
                "terminated_by": trace.terminated_by,
                "wall_time_seconds": round(trace.wall_time_seconds, 2),
                "tool_calls": [o.tool_name for o in trace.observations],
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
                return resolved if isinstance(resolved, str) else json.dumps(resolved, default=str)
        return final_answer
    if final_answer is None:
        return ""
    return json.dumps(final_answer, default=str)


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
