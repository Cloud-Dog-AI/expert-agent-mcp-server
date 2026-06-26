# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""W28M-1606 — Layered scheduled validated demo capability.

LAYERS the dynamic web-research source pool (W28M-1605/research_cycle) ONTO the
full-depth W28M-1604 document-generation quality bar, as ONE scheduler-callable
MCP tool ``run_research_document``:

    deterministic per-day target -> web research (search/crawl/ingest/rank/prune
    fresh source pool) -> read assured W28M-1604 template -> section-by-section
    generation GROUNDED in the fresh sources (>=0.9x example depth, comparator
    tables, [TAG] citations) -> correction (experts 26->27) -> Drive md+html ->
    Slack+email -> git-mcp audit -> per-run status record.

Built ALONGSIDE ``run_research_cycle`` (additive; the brief tool is untouched).
Full-depth qwen3 generation is minutes long, so the scheduler path runs ASYNC: the
tool returns ``{accepted, run_id, status_path}`` immediately and a background task
runs the pipeline and records the completed result to Drive + git audit + the
notification. A synchronous mode (``async_mode=False``) is provided for trial/chat
parity. Composes ``ResearchCycleAgent`` (source pool + delivery helpers) and the
proven W28M-1605 correction pattern; modifies no existing tool.
"""

from __future__ import annotations

import asyncio
import datetime
import hashlib
import json
import re
import time
from typing import Any, Dict, List, Optional

from src.config.loader import get_config
from src.utils.logger import get_logger
from src.core.agentic.research_cycle import ResearchCycleAgent, _now

logger = get_logger(__name__)

GENERATOR_EXPERT = 30      # DEMO-Document-Generator (qwen3:14b)
PLAIN_ENGLISH_EXPERT = 26  # DEMO-Plain-English-Rewrite
HUMANISE_EXPERT = 27       # DEMO-Humanise-Text
_DRIVE_OUT = "/CloudDog-Demos/transparent-borders-report-generation/output"
_DEFAULT_TEMPLATE = f"{_DRIVE_OUT}/templates/transparent-borders-country-template-v1.json"
_DEFAULT_EXAMPLE_WORDS = 7285   # W28M-1604 poland exemplar depth baseline

# Per-demo configuration AND templates are DATA, read from Drive at runtime — NOT hard-coded
# here. Edit /CloudDog-Demos/_config/research-demos.json (and the per-family template JSONs) to
# add/change demos; the service stays generic.
DEMOS_CONFIG_PATH = "/CloudDog-Demos/_config/research-demos.json"
_DEMOS_CACHE: Dict[str, Any] = {}


async def load_demos(agent: Any, auth_context: Dict[str, Any]) -> Dict[str, Any]:
    """Read the per-demo config (template_path/targets/queries/collection/drive_out/delivery)
    from Drive DATA. Cached for the process lifetime; the demo definitions live in data, not code."""
    if not _DEMOS_CACHE:
        try:
            res = await agent._svc(agent._file_id, "read_file",
                                   {"profile": get_config("research.storage_profile") or "google_drive",
                                    "path": DEMOS_CONFIG_PATH}, auth_context)
            struct = agent._mcp_struct(res)
            txt = struct.get("value") if isinstance(struct, dict) and isinstance(struct.get("value"), str) \
                else agent._mcp_text(res)
            _DEMOS_CACHE.update((json.loads(txt) or {}).get("demos", {}))
        except Exception as exc:
            logger.error("failed to load demo config %s: %s", DEMOS_CONFIG_PATH, exc)
    return dict(_DEMOS_CACHE)


# Async run registry — keeps a reference to background tasks so they are not GC'd
# and exposes the last result per run id for status polling.
_RUNS: Dict[str, Dict[str, Any]] = {}
_TASKS: set = set()


def _utc_date() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


_ACRONYMS = {"nato", "eu", "un", "uk", "us", "usa", "g20", "g7", "oecd", "imf", "who", "ai"}


def _human_dt(run_ts: str) -> str:
    """'20260625T071308Z' -> '25 June 2026, 07:13 UTC'."""
    try:
        t = time.strptime(run_ts, "%Y%m%dT%H%M%SZ")
        day = str(int(time.strftime("%d", t)))  # no leading zero
        return f"{day} {time.strftime('%B %Y, %H:%M', t)} UTC"
    except Exception:
        return run_ts


def _nice_name(s: str) -> str:
    """'poland-ukraine-corridor' -> 'Poland-Ukraine Corridor'; 'nato-interoperability' -> 'NATO Interoperability'."""
    out = []
    for word in re.split(r"[-_\s]+", str(s or "").strip()):
        if not word:
            continue
        out.append(word.upper() if word.lower() in _ACRONYMS else word[:1].upper() + word[1:])
    return " ".join(out) or str(s)


def _family_title(family: str) -> str:
    """'transparent-borders-country' -> 'Transparent Borders Country Report'."""
    base = _nice_name(family)
    return base if base.lower().endswith("report") else base + " Report"


def deterministic_target(topic: str, targets: List[str], date_str: Optional[str] = None) -> Dict[str, Any]:
    """Pick a NEW target every day with full coverage and no silent skip, while being
    stable for a given day (deterministic). A fixed pseudo-random order (seeded by
    topic, so it looks randomised, not alphabetical) is rotated by the date ordinal:
    consecutive days advance through the whole set before repeating."""
    date_str = date_str or _utc_date()
    order = sorted(targets, key=lambda t: hashlib.sha256(f"{topic}|{t}".encode()).hexdigest())
    try:
        ordinal = datetime.date.fromisoformat(date_str).toordinal()
    except Exception:
        ordinal = int(hashlib.sha256(date_str.encode()).hexdigest(), 16)
    idx = ordinal % len(order)
    return {"target": order[idx], "index": idx, "of": len(order), "date": date_str,
            "rotation": order, "method": "date-ordinal-rotation", "ordinal": ordinal}


class ResearchDocumentAgent(ResearchCycleAgent):
    """Layered: research source pool + full-depth W28M-1604 grounded generation."""

    PLAIN_ENGLISH_NAME = "Plain English Rewrite"
    HUMANISE_NAME = "Humanise Text"

    def __init__(self, db: Any) -> None:
        super().__init__(db)
        self._pe_id = PLAIN_ENGLISH_EXPERT
        self._hu_id = HUMANISE_EXPERT
        self._gsources: List[Dict[str, str]] = []  # this run's fresh sources -> global [S#] + links

    def _resolve_doc_ids(self) -> None:
        self._resolve_ids()  # index/file/notify/git + generator (expert 30)
        self._pe_id = self._expert_id(self.PLAIN_ENGLISH_NAME, PLAIN_ENGLISH_EXPERT)
        self._hu_id = self._expert_id(self.HUMANISE_NAME, HUMANISE_EXPERT)

    # -------------------------------------------------- W28M-1604 correction (26->27)
    @staticmethod
    def _protect_nums(text: str):
        nums: List[str] = []

        def repl(m):
            nums.append(m.group(0))
            return "⟦%d⟧" % (len(nums) - 1)

        return re.sub(r"\d[\d,\.%]*", repl, text), nums

    @staticmethod
    def _restore_nums(text: str, nums: List[str]) -> str:
        for i, n in enumerate(nums):
            text = text.replace("⟦%d⟧" % i, n)
        return text

    async def _correct_section(self, md: str, auth_context: Dict[str, Any]) -> str:
        """Prose-only PE(26)->Humanise(27), preserving headings/tables/lists and
        every numeric token (revert on number drop)."""
        out, buf = [], []

        async def flush():
            text = "\n".join(buf)
            buf.clear()
            if not text.strip():
                out.append(text)
                return
            prot, nums = self._protect_nums(text)
            pe = await self._execute(self._pe_id,
                "Improve the clarity and plain-English readability of the following report prose WITHOUT "
                "shortening it or removing any detail, figure, table row, or analysis. Keep approximately the "
                "same length and every ⟦n⟧ token EXACTLY (drop none). Return only the improved prose.\n\n" + prot,
                auth_context, max_tokens=1600)
            hu = await self._execute(self._hu_id,
                "Refine the following prose for a natural, consistent professional voice WITHOUT shortening it; "
                "preserve all detail, length and every ⟦n⟧ token EXACTLY. Return only the prose.\n\n" + pe,
                auth_context, max_tokens=1600)
            if hu and all(("⟦%d⟧" % i) in hu for i in range(len(nums))):
                out.append(self._restore_nums(hu, nums))
            else:
                out.append(text)  # number-fidelity guard

        for ln in md.split("\n"):
            st = ln.strip()
            if st.startswith("#") or st.startswith("|") or re.match(r"^[-*]\s", st) or "|" in st:
                if buf:
                    await flush()
                out.append(ln)
            else:
                buf.append(ln)
        if buf:
            await flush()
        return "\n".join(out)

    @staticmethod
    def _md_to_html(md: str) -> str:
        """Render Markdown -> HTML with real tables, hyperlinks, headings, lists, and rules."""
        import html as _html

        # INLINE styles on every element: email clients (Gmail/Outlook) strip <head>/<style>
        # blocks, so a <style>-only sheet renders tables as borderless, unformatted text in the
        # inbox. The <style> block is kept for the Drive HTML view; the inline styles guarantee
        # the report renders with real table borders/spacing/links inside the delivered email.
        S_TABLE = ("border-collapse:collapse;margin:1.1em 0;width:100%;font-size:14px;"
                   "font-family:Arial,Helvetica,sans-serif")
        S_TH = ("border:1px solid #c9ced6;padding:6px 11px;text-align:left;vertical-align:top;"
                "background:#eef2f7;font-family:Arial,Helvetica,sans-serif")
        S_TD = "border:1px solid #c9ced6;padding:6px 11px;text-align:left;vertical-align:top"
        S_H = {2: "font-family:Arial,Helvetica,sans-serif;color:#1a2330;border-bottom:1px solid #e3e7ee;"
                  "padding-bottom:3px;margin:1.6em 0 0.5em",
               3: "font-family:Arial,Helvetica,sans-serif;color:#2a3340;margin:1.2em 0 0.4em",
               4: "font-family:Arial,Helvetica,sans-serif;color:#3a4350;margin:1.0em 0 0.3em"}
        S_HR = "border:0;border-top:1px solid #d0d5dd;margin:1.8em 0"
        S_A = "color:#15569c"
        S_P = "margin:0.7em 0"

        def inline(t: str) -> str:
            t = _html.escape(t, quote=False)
            t = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", rf'<a href="\2" style="{S_A}">\1</a>', t)
            t = re.sub(r'(?<![">\w])(https?://[^\s<)\]]+)', rf'<a href="\1" style="{S_A}">\1</a>', t)
            t = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", t)
            t = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"<em>\1</em>", t)
            return t

        CSS = ("<style>body{font-family:Georgia,serif;max-width:900px;margin:2em auto;line-height:1.55;color:#1a1a1a}"
               "h1,h2,h3,th{font-family:'Helvetica Neue',Arial,sans-serif}"
               "table{border-collapse:collapse;margin:1.2em 0;width:100%;font-size:0.95em}"
               "th,td{border:1px solid #c9ced6;padding:6px 11px;text-align:left;vertical-align:top}"
               "th{background:#eef2f7}.subtitle{color:#555}a{color:#15569c}"
               "hr{border:0;border-top:1px solid #d0d5dd;margin:2em 0}"
               "footer,em{color:#555}</style>")
        lines = md.splitlines()
        out: List[str] = [CSS]
        i, n, ul = 0, len(lines), False

        def close_ul():
            nonlocal ul
            if ul:
                out.append("</ul>"); ul = False

        def cells(row: str):
            return [c.strip() for c in row.strip().strip("|").split("|")]

        while i < n:
            s = lines[i].rstrip()
            # Markdown table: a header row followed by a |---|---| separator row
            if s.strip().startswith("|") and i + 1 < n and "-" in lines[i + 1] \
                    and re.match(r"^\s*\|?[\s:|\-]+\|?\s*$", lines[i + 1]):
                close_ul()
                header = cells(s)
                out.append(f'<table style="{S_TABLE}"><thead><tr>'
                           + "".join(f'<th style="{S_TH}">{inline(c)}</th>' for c in header)
                           + "</tr></thead><tbody>")
                i += 2
                while i < n and lines[i].strip().startswith("|"):
                    out.append("<tr>" + "".join(f'<td style="{S_TD}">{inline(c)}</td>'
                                                 for c in cells(lines[i])) + "</tr>")
                    i += 1
                out.append("</tbody></table>")
                continue
            m = re.match(r"^(#{1,4})\s+(.*)$", s)
            if m:
                close_ul()
                lvl = min(max(2, len(m.group(1))), 4)   # body headings: ## -> h2, ### -> h3 (title is the page h1)
                out.append(f'<h{lvl} style="{S_H[lvl]}">{inline(m.group(2).strip())}</h{lvl}>'); i += 1; continue
            if s.strip() in ("---", "***", "___"):
                close_ul(); out.append(f'<hr style="{S_HR}">'); i += 1; continue
            if re.match(r"^\s*[-*]\s+", s):
                if not ul:
                    out.append('<ul style="margin:0.6em 0 0.6em 1.3em">'); ul = True
                out.append("<li>" + inline(re.sub(r"^\s*[-*]\s+", "", s)) + "</li>"); i += 1; continue
            close_ul()
            if s.strip():
                out.append(f'<p style="{S_P}">' + inline(s.strip()) + "</p>")
            i += 1
        close_ul()
        return "\n".join(out)

    # -------------------------------------------------- template + grounding
    async def _read_template(self, path: str, auth_context: Dict[str, Any]) -> Dict[str, Any]:
        res = await self._svc(self._file_id, "read_file",
                              {"profile": get_config("research.storage_profile") or "google_drive",
                               "path": path}, auth_context)
        struct = self._mcp_struct(res)
        txt = struct.get("value") if isinstance(struct, dict) and isinstance(struct.get("value"), str) \
            else self._mcp_text(res)
        return json.loads(txt) if txt else {}

    def _gnum(self, uri: str) -> Optional[int]:
        """Global [S#] number for a source_uri (1-based), or None if not a this-run source."""
        for i, g in enumerate(self._gsources):
            if g["url"] == uri:
                return i + 1
        return None

    async def _ground(self, profile: str, collection: str, query: str, auth_context: Dict[str, Any]) -> str:
        """Retrieve section-relevant facts, each labelled with its GLOBAL [S#] (consistent
        across the whole document) so citations map to the real source list / links."""
        sr = await self._svc(self._index_id, "search",
                             {"profile": profile, "collection": collection, "query": query, "top_k": 5},
                             auth_context)
        hits = self._mcp_struct(sr).get("results") or []
        lines = []
        for h in hits:
            sn = self._gnum(h.get("source_uri") or "")
            if sn:
                lines.append(f"[S{sn}] {(h.get('text') or '')[:600]}")
        return "\n".join(lines)

    async def _gen_section(self, spec: Dict[str, Any], family: str, target: str,
                           profile: str, collection: str, auth_context: Dict[str, Any]) -> str:
        title = spec.get("title", "Section")
        facts = await self._ground(profile, collection, f"{target} {title}", auth_context)
        n_src = len(self._gsources)
        src_list = "\n".join(f"[S{i+1}] {g['title']} ({g['host']})" for i, g in enumerate(self._gsources))
        nice_target = _nice_name(target)
        tw = int(spec.get("target_words", 400) or 400)
        lo, hi = max(520, int(tw * 1.4)), max(680, int(tw * 1.7))
        # sections whose subject is comparative/quantitative MUST contain a real table.
        sig = (title + " " + " ".join(spec.get("required_elements") or [])).lower()
        needs_table = any(kw in sig for kw in ("compar", "metric", "scorecard", "chart", "profile",
                                               "benchmark", "indicator", "statistic", "table", "rate", "rank"))
        table_rule = (
            "You MUST include at least one well-formed Markdown table in this section: a header row, a "
            "`|---|---|` separator row, and at least 3 data rows with real values. "
            if needs_table else
            "Include a Markdown comparator table with real rows where the data lends itself to comparison. ")
        if n_src:
            cite_rule = (f"Ground factual claims in the SOURCE FACTS and cite the relevant source inline as "
                         f"[S1]..[S{n_src}], using ONLY the numbers in the SOURCE LIST below ({n_src} sources). "
                         f"Never cite a number that is not in the list. State general/established context without "
                         f"a citation rather than inventing one. Use Markdown comparator tables with real rows where "
                         f"the required elements call for comparison, and proper Markdown links where helpful.")
        else:
            cite_rule = ("Write from established public context; do NOT use any [S] citation markers (no fresh "
                         "sources were retrieved). Still include Markdown comparator tables with real rows.")
        gp = (f"You are writing the '{title}' section of an in-depth, professional report on {nice_target}.\n"
              f"This must be a SUBSTANTIVE, analytical section of {lo}-{hi} words: multiple full paragraphs, "
              f"specific figures, named institutions/laws/dates, and genuine comparative analysis. Be thorough and "
              f"detailed; do not be brief or generic.\n"
              f"Purpose: {spec.get('purpose','')}\n"
              f"Cover each required element in depth: {', '.join(spec.get('required_elements') or [])}\n"
              f"Style: formal analytical UK English, policy register.\n"
              f"{table_rule}\n{cite_rule}\n"
              f"Begin with '## {title}'. Return ONLY this section's Markdown — no preamble, no notes, no "
              f"word-count remarks.\n\n"
              f"SOURCE LIST ({n_src}):\n{src_list or '(none)'}\n\n"
              f"SECTION-RELEVANT SOURCE FACTS:\n{facts or '(none retrieved for this section)'}\n")
        draft = await self._execute(self._gen_id, gp, auth_context, max_tokens=2400, temperature=0.35)
        if not draft.strip():
            raise RuntimeError(f"generator returned empty section '{title}'")
        corrected = await self._correct_section(draft, auth_context)
        if not re.search(r"^##\s", corrected, re.M):
            corrected = f"## {title}\n\n{corrected}"
        return corrected.strip()

    # -------------------------------------------------- full pipeline (sync core)
    async def run_document(self, topic: str, *, target: Optional[str] = None, deliver: bool = True,
                           slack_endpoint: Optional[str] = None, date_str: Optional[str] = None,
                           refresh_sources: bool = True, actor: str = "research-document") -> Dict[str, Any]:
        self._resolve_doc_ids()
        run_ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        auth_context = {"actor": actor, "role": "system",
                        "correlation_id": f"research-document-{topic}-{run_ts}"}
        # demo definitions are DATA (Drive config), not hard-coded
        demos = await load_demos(self, auth_context)
        if topic not in demos:
            return {"status": "failed", "error": f"unknown topic '{topic}'; known={list(demos)}"}
        dt = demos[topic]
        rc = dt.get("delivery", {})                    # delivery channels/group/extra_recipients (data)
        profile = dt.get("profile", "default")
        collection = dt.get("collection", f"demo-research-{topic}")
        pick = deterministic_target(topic, dt["targets"], date_str)
        target = target or pick["target"]
        summary: Dict[str, Any] = {"status": "ok", "topic": topic, "target": target,
                                   "target_pick": pick, "run_ts": run_ts, "layered": True}

        # 1) refresh the dynamic web-research source pool for this target (reuses research_cycle)
        if refresh_sources:
            try:
                await self._svc(self._index_id, "admin_collection_create",
                                {"profile": profile, "collection": collection}, auth_context)
                if dt.get("queries"):
                    qs = [q.format(t=target) for q in dt["queries"]]
                else:
                    qs = [f"{target} border migration policy latest", f"{target} {dt['label']} news",
                          f"{target} country profile statistics report"]
                cands = await self._research({"queries": qs})
                ingested = 0
                self._gsources = []  # reset per run
                # crawl more candidates for the document path — grounding needs breadth so [S]
                # citations reference real sources (the brief path uses fewer).
                per_run = int(get_config("research_document.crawl_candidates") or 8)
                for s in cands:
                    if ingested >= per_run:
                        break
                    md = await self._crawl(s["url"])
                    if md and len(md) >= 200:
                        r = await self._svc(self._index_id, "ingest_text",
                                            {"profile": profile, "collection": collection,
                                             "text": md, "source": s["url"]}, auth_context)
                        if self._mcp_struct(r).get("job_id"):
                            ingested += 1
                            self._gsources.append({"url": s["url"],
                                                   "title": (s.get("title") or _host(s["url"]))[:120],
                                                   "host": s.get("host") or _host(s["url"])})
                summary["sources_refreshed"] = {"candidates": len(cands), "ingested": ingested}
                summary["source_urls"] = [g["url"] for g in self._gsources]
                if ingested:
                    await asyncio.sleep(6)
            except Exception as exc:
                logger.warning("source refresh failed (continuing on existing pool): %s", exc)
                summary["sources_refreshed"] = {"error": str(exc)[:200]}

        # 2) select the template: per-topic inline template (e.g. NATO doctrine) takes precedence
        # over the assured W28M-1604 country template on Drive.
        template_path = dt.get("template_path") or get_config("research_document.template_path") or _DEFAULT_TEMPLATE
        template = await self._read_template(template_path, auth_context)
        specs = template.get("sections") or []
        if not specs:
            return {**summary, "status": "failed", "failing_step": "read_template",
                    "error": f"no template sections at {template_path}"}
        summary["template"] = {"path": template_path, "version": template.get("version"),
                               "checksum": str(template.get("checksum"))[:12], "sections": len(specs)}

        # 3) full-depth grounded generation + correction (section by section)
        family = template.get("family") or dt.get("family") or "transparent-borders-country"
        finals: List[str] = []
        for spec in specs:
            try:
                finals.append(await self._gen_section(spec, family, target, profile, collection, auth_context))
            except Exception as exc:
                return {**summary, "status": "failed", "failing_step": "generate",
                        "error": str(exc)[:200], "sections_done": len(finals)}
        body = "\n\n".join(finals)
        # title reflects the actual document family (so it is honest — not a mismatched topic label),
        # with a human-readable subtitle. The compact run_ts stays only in the filename.
        # strip a redundant leading 'nato-' from the theme so the title reads
        # "NATO Doctrine Report: Interoperability" not "...: NATO Interoperability".
        strip = dt.get("theme_strip_prefix")
        title_target = re.sub(rf"^{re.escape(strip)}", "", target) if strip else target
        doc_title = f"{_family_title(family)}: {_nice_name(title_target)}"
        human_dt = _human_dt(run_ts)
        subtitle = f"{human_dt} · web-grounded daily report · Cloud-Dog AI demo"
        # real Sources key with clickable links, consistent with the global [S#] used in the body
        if self._gsources:
            sources_md = "## Sources\n\n" + "\n".join(
                f"- **[S{i+1}]** [{g['title']}]({g['url']})" for i, g in enumerate(self._gsources))
        else:
            sources_md = "## Sources\n\n- No fresh web sources were retrieved for this run; the report draws on established public context."
        # provenance byline at the FOOTER (bottom), not under the title
        footer = ("---\n\n*Generated " + human_dt + " by the Cloud-Dog W28M-1606 layered scheduled demo: "
                  "web-grounded research (search + crawl + index) plus the W28M-1604 document template v"
                  f"{template.get('version')} (checksum {str(template.get('checksum'))[:12]}); "
                  "drafted with qwen3:14b and corrected via the Plain-English and Humanise experts.*")
        full_md = f"# {doc_title}\n\n*{subtitle}*\n\n{body}\n\n{sources_md}\n\n{footer}"
        full_html = ("<!doctype html><html><head><meta charset='utf-8'><title>" + doc_title +
                     "</title></head>"
                     "<body style=\"font-family:Georgia,serif;max-width:900px;margin:1.5em auto;"
                     "line-height:1.55;color:#1a1a1a;padding:0 14px\">\n"
                     f"<h1 style=\"font-family:Arial,Helvetica,sans-serif;color:#10243f;margin:0 0 0.2em\">{doc_title}</h1>\n"
                     f"<p style=\"color:#555;margin:0 0 1.2em\"><em>{subtitle}</em></p>\n"
                     + self._md_to_html(body + "\n\n" + sources_md + "\n\n" + footer) +
                     "\n</body></html>")
        words = len(re.findall(r"\w+", body))
        example_words = int(get_config("research_document.example_words") or _DEFAULT_EXAMPLE_WORDS)
        depth_ratio = round(words / max(1, example_words), 4)
        tables = full_md.count("|---") + len(re.findall(r"\n\|", full_md))
        citations = len(re.findall(r"\[S\d+\]", full_md))
        summary["document"] = {"words": words, "sections": len(finals), "depth_ratio": depth_ratio,
                               "example_words": example_words, "tables_markers": tables, "citations": citations}

        # 4) write to Drive (md + html)
        drive_out = (dt.get("drive_out") or f"/CloudDog-Demos/{topic}").rstrip("/") + "/documents"
        summary["drive_out"] = drive_out
        md_path = f"{drive_out}/{run_ts}-{target}-w28m1606.md"
        html_path = f"{drive_out}/{run_ts}-{target}-w28m1606.html"
        sp = get_config("research.storage_profile") or "google_drive"
        w1 = await self._svc(self._file_id, "write_file",
                             {"profile": sp, "path": md_path, "content": full_md, "overwrite": True}, auth_context)
        w2 = await self._svc(self._file_id, "write_file",
                             {"profile": sp, "path": html_path, "content": full_html, "overwrite": True}, auth_context)
        write_ok = not self._mcp_is_error(w1) and not self._mcp_is_error(w2)
        summary["drive"] = {"ok": write_ok, "md": md_path, "html": html_path}

        # 5) deliver (Slack + email) + 6) git audit
        if deliver and write_ok:
            tc = rc or {"email_channel": "email_default", "email_group": "group:Ukraine Digest Admin Group",
                        "slack_channel": "slack_ukraine_news", "subject": dt["label"]}
            # subject MUST match the delivered document (its h1 title) and use a human-readable
            # date — NOT the scheduler's topic label or the compact run_ts (which read as wrong /
            # mismatched in the inbox: e.g. "Ukraine Border Watch ... 20260625T110143Z").
            subject = f"{doc_title} — {human_dt}"
            # idempotency: delivery key is stable per (topic, target, DAY) so a same-day
            # rerun of the same target dedups and does NOT duplicate delivery (TC-1606-05).
            deliv = await self._deliver(tc, subject, full_html,
                                        f"w28m1606-{topic}-{target}-{pick['date']}", auth_context,
                                        slack_endpoint=slack_endpoint)
            summary["delivery"] = deliv
            summary["git_audit"] = await self._git_audit(
                {"drive_out": drive_out}, f"{topic}-{target}", run_ts,
                {"candidates": summary.get("sources_refreshed", {}).get("candidates"),
                 "ingested": summary.get("sources_refreshed", {}).get("ingested"),
                 "kept": len(specs), "retired": 0, "retrieved": citations}, auth_context)
            if not deliv.get("ok"):
                summary["status"] = "partial"
                summary["failing_step"] = "delivery"
        else:
            summary["delivery"] = {"skipped": True, "reason": "deliver=False or drive write failed"}
            if not write_ok:
                summary["status"] = "failed"; summary["failing_step"] = "write_drive"
        summary["doc_head"] = full_md[:200]
        return summary

    async def _record(self, run_id: str, topic: str, res: Dict[str, Any]) -> None:
        res["run_id"] = run_id
        _RUNS[run_id] = res
        # durable status record to Drive (auditable completion)
        try:
            drive_out = (res.get("drive_out") or f"/CloudDog-Demos/{topic}/documents").rstrip("/") + "/_runs"
            await self._svc(self._file_id, "write_file",
                            {"profile": get_config("research.storage_profile") or "google_drive",
                             "path": f"{drive_out}/{run_id}.json",
                             "content": json.dumps(res, default=str)[:60000], "overwrite": True},
                            {"actor": "research-document", "role": "system"})
        except Exception as exc:
            logger.warning("status record write failed: %s", exc)


async def _background_run(run_id: str, topic: str, kw: Dict[str, Any]) -> None:
    """Background full-depth pipeline with its OWN db session (the request session
    is closed once the scheduler call returns; this task lives minutes)."""
    from src.database.connection import get_db
    gen = get_db()
    bdb = next(gen)
    try:
        agent = ResearchDocumentAgent(bdb)
        try:
            res = await agent.run_document(topic, **kw)
        except Exception as exc:
            res = {"status": "failed", "error": str(exc)[:300], "topic": topic}
        await agent._record(run_id, topic, res)
    finally:
        try:
            next(gen, None)  # trigger the session generator's finally (close)
        except StopIteration:
            pass


async def run_research_document(topic: str, *, db: Any = None, target: Optional[str] = None,
                                deliver: bool = True, async_mode: bool = True,
                                slack_endpoint: Optional[str] = None, date_str: Optional[str] = None,
                                refresh_sources: bool = True, actor: str = "research-document") -> Dict[str, Any]:
    """Module entry — the ``run_research_document`` MCP tool / scheduler target.

    async_mode=True (scheduler default): kicks off the full-depth pipeline in the
    background and returns ``{accepted, run_id, status_path}`` immediately so the
    cron run does not hold a multi-minute HTTP request. async_mode=False runs
    synchronously and returns the full result (trial/chat parity)."""
    if db is None:
        from src.database.connection import get_db
        db = next(get_db())
    agent = ResearchDocumentAgent(db)
    run_id = "rd-" + hashlib.sha256(
        f"{topic}|{target}|{date_str or _utc_date()}|{time.strftime('%H%M%S', time.gmtime())}".encode()
    ).hexdigest()[:16]
    kw = dict(target=target, deliver=deliver, slack_endpoint=slack_endpoint,
              date_str=date_str, refresh_sources=refresh_sources, actor=actor)
    if not async_mode:
        res = await agent.run_document(topic, **kw)
        res["run_id"] = run_id
        return res
    task = asyncio.create_task(_background_run(run_id, topic, kw))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)
    # target_pick is a convenience for the accepted response; demos come from Drive DATA
    try:
        demos = await load_demos(agent, {"actor": actor, "role": "system"})
        targets = (demos.get(topic) or {}).get("targets", [topic])
    except Exception:
        targets = [topic]
    pick = deterministic_target(topic, targets, date_str)
    return {"status": "accepted", "run_id": run_id, "topic": topic, "target": target or pick["target"],
            "target_pick": pick, "async": True,
            "status_path": f"(Drive)/CloudDog-Demos/.../documents/_runs/{run_id}.json",
            "note": "full-depth layered generation running in background; result recorded on completion"}


def get_run_status(run_id: str) -> Dict[str, Any]:
    """In-memory status for a background run (also durably recorded to Drive)."""
    return _RUNS.get(run_id, {"status": "unknown_or_running", "run_id": run_id})
