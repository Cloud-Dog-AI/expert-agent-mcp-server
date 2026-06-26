# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Dynamic research cycle — web-grounded, self-pruning knowledge loop.

Precursor to W28M-1606 (ReAct/Codeflow/RM). ONE topic-scoped daily cycle the
scheduler invokes as the MCP tool ``run_research_cycle``:

    1. web research  : search-mcp-server ``search`` (live web) -> candidate sources
    2. add to repo   : ``crawl`` NEW sources -> ``ingest_text`` into the topic's
                       index collection (source_uri = canonical url)
    3. rank + prune  : score every source (search relevance x recency); when the
                       pool exceeds ``research.max_sources`` retire the lowest-
                       ranked/oldest -> drop its register row AND ``delete_by_filter``
                       its indexed content
    4. grounded gen  : retrieve top-K from the (now fresh) collection and generate a
                       daily brief grounded in CURRENT web facts (cited)
    5. deliver       : write the brief to Drive, persist the register, git audit,
                       and notify the topic's recipients

Additive: composes ``ServiceCompositionManager.invoke_tool`` (registered Vault
creds), ``TransactionalExecutor.execute`` (generation), and a direct httpx call to
the UNAUTHENTICATED search-mcp-server ``/mcp`` (url from config). It does NOT modify
``chat_tool``/``execute_tool``/``invoke_service_tool`` or the executor graph.
"""

from __future__ import annotations

import json
import time
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import httpx

from src.config.loader import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)

# --- registered downstream services (resolved BY NAME at run time; ids are the
#     preprod defaults but a fresh local container assigns different ids) --------
INDEX_SVC = 9       # indexretriever0
FILE_SVC = 10       # filemcpserver0
NOTIFY_SVC = 11     # notificationagent0
GIT_SVC = 12        # gitmcpserver0
GENERATOR_EXPERT = 30  # DEMO-Document-Generator (qwen3:14b)

_DELIVERED_STATES = {"sent", "delivered", "accepted"}
_DEFAULT_SEARCH_URL = "https://searchmcp0.cloud-dog.net/mcp"
_AUDIT_WORKSPACE = "demo-agentic-audit-c1d2704ef2e1"

# Per-topic configuration for the four daily demo jobs. Recipients follow the
# operator-confirmed policy: TB demos -> client (Colin) + internal; NATO/Ukraine
# -> internal only. Slack destinations carry the channel NAME; the webhook
# endpoint is resolved at delivery time (send_notification soft-fails on name only).
TOPICS: Dict[str, Dict[str, Any]] = {
    "ukraine": {
        "label": "Ukraine Border Watch",
        "queries": ["Ukraine border situation latest news", "Ukraine refugee crossing update"],
        "collection": "demo-research-ukraine",
        "profile": "default",
        "register": "research-loop/ukraine/source-register.jsonl",
        "drive_out": "/CloudDog-Demos/researcher-ukraine-war/research-loop",
        "slack_channel": "slack_ukraine_news",
        "email_channel": "email_default",
        "email_group": "group:Ukraine Digest Admin Group",
        "subject": "Ukraine Border Watch — Web-Grounded Daily Brief",
    },
    "transparent-borders": {
        "label": "Transparent Borders Research",
        "queries": ["transparent borders migration policy latest", "border crossing controls news"],
        "collection": "demo-research-transparent-borders",
        "profile": "default",
        "register": "research-loop/transparent-borders/source-register.jsonl",
        "drive_out": "/CloudDog-Demos/transparent-borders/research-loop",
        "slack_channel": "slack_transparentborders",
        "email_channel": "email_transparent_borders_research",
        "email_group": "group:Transparent Borders Research Admin Group",
        "subject": "Transparent Borders — Web-Grounded Daily Brief",
    },
    "nato-doctrine": {
        "label": "NATO Doctrine Watch",
        "queries": ["NATO allied joint doctrine update", "NATO military doctrine news"],
        "collection": "demo-research-nato-doctrine",
        "profile": "default",
        "register": "research-loop/nato-doctrine/source-register.jsonl",
        "drive_out": "/CloudDog-Demos/nato-doctrine/research-loop",
        "slack_channel": "slack_cloud_dog_ai_notification",
        "email_channel": "email_nato_doctrine_admin",
        "email_group": "group:NATO Doctrine Admin Group",
        "subject": "NATO Doctrine — Web-Grounded Daily Brief",
    },
    "transparent-borders-report": {
        "label": "Transparent Borders Country Report",
        "queries": ["country border management policy latest", "migration border statistics report"],
        "collection": "demo-research-transparent-borders-report",
        "profile": "default",
        "register": "research-loop/transparent-borders-report/source-register.jsonl",
        "drive_out": "/CloudDog-Demos/transparent-borders-report-generation/research-loop",
        "slack_channel": "slack_transparentborders",
        "email_channel": "email_transparent_borders_report_generation",
        "email_group": "group:Transparent Borders Report Generation Admin Group",
        "subject": "Transparent Borders — Web-Grounded Country Brief",
    },
}


def _canonical_url(u: str) -> str:
    try:
        p = urllib.parse.urlsplit((u or "").strip())
        q = [(k, v) for k, v in urllib.parse.parse_qsl(p.query)
             if not k.lower().startswith(("utm_", "fbclid", "gclid"))]
        path = p.path.rstrip("/") or "/"
        return urllib.parse.urlunsplit((p.scheme.lower(), p.netloc.lower(), path,
                                        urllib.parse.urlencode(q), ""))
    except Exception:
        return (u or "").strip()


def _host(u: str) -> str:
    try:
        return urllib.parse.urlsplit(u).netloc.lower()
    except Exception:
        return ""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H%M%SZ", time.gmtime())


class ResearchCycleAgent:
    """Web-grounded, self-pruning daily research loop (in-process)."""

    INDEX_NAME = "indexretriever0"
    FILE_NAME = "filemcpserver0"
    NOTIFY_NAME = "notificationagent0"
    GIT_NAME = "gitmcpserver0"
    GENERATOR_NAME = "Document Generator"

    def __init__(self, db: Any) -> None:
        self.db = db
        self._index_id = INDEX_SVC
        self._file_id = FILE_SVC
        self._notify_id = NOTIFY_SVC
        self._git_id = GIT_SVC
        self._gen_id = GENERATOR_EXPERT

    # ---------------------------------------------------------- id resolution
    def _service_id(self, name: str, default_id: int) -> int:
        try:
            from src.core.service.manager import ServiceManager
            svc = ServiceManager(self.db).get_service(name=name)
            if svc:
                return int(svc.id)
        except Exception as exc:
            logger.warning("service resolve by name '%s' failed: %s", name, exc)
        return default_id

    def _expert_id(self, title: str, default_id: int) -> int:
        try:
            from src.core.expert.manager import ExpertManager
            for e in ExpertManager(self.db).list_experts():
                if (getattr(e, "title", None) or "").strip().lower() == title.strip().lower():
                    return int(e.id)
        except Exception as exc:
            logger.warning("expert resolve by name '%s' failed: %s", title, exc)
        return default_id

    def _resolve_ids(self) -> None:
        self._index_id = self._service_id(self.INDEX_NAME, INDEX_SVC)
        self._file_id = self._service_id(self.FILE_NAME, FILE_SVC)
        self._notify_id = self._service_id(self.NOTIFY_NAME, NOTIFY_SVC)
        self._git_id = self._service_id(self.GIT_NAME, GIT_SVC)
        self._gen_id = self._expert_id(self.GENERATOR_NAME, GENERATOR_EXPERT)

    # ------------------------------------------------------- mcp envelope helpers
    @staticmethod
    def _unwrap(result: Dict[str, Any]) -> Dict[str, Any]:
        if isinstance(result, dict) and isinstance(result.get("result"), dict) \
                and ("content" in result["result"] or "structuredContent" in result["result"]
                     or "isError" in result["result"]):
            return result["result"]
        return result or {}

    @classmethod
    def _mcp_text(cls, result: Dict[str, Any]) -> str:
        inner = cls._unwrap(result)
        content = inner.get("content") or []
        if content and isinstance(content[0], dict):
            return content[0].get("text", "") or ""
        return ""

    @classmethod
    def _mcp_struct(cls, result: Dict[str, Any]) -> Dict[str, Any]:
        inner = cls._unwrap(result)
        struct = inner.get("structuredContent")
        if struct:
            return struct
        txt = cls._mcp_text(result)
        try:
            return json.loads(txt) if txt else {}
        except Exception:
            return {}

    @classmethod
    def _mcp_is_error(cls, envelope: Dict[str, Any]) -> bool:
        if isinstance(envelope, dict) and envelope.get("status") in ("failed", "error", "skipped"):
            return True
        return bool(cls._unwrap(envelope).get("isError"))

    async def _svc(self, service_id: int, tool: str, args: Dict[str, Any],
                   auth_context: Dict[str, Any]) -> Dict[str, Any]:
        from src.core.service.composition import ServiceCompositionManager
        mgr = ServiceCompositionManager(self.db)
        return await mgr.invoke_tool(service_id=service_id, tool_name=tool,
                                     arguments=args, auth_context=auth_context)

    async def _execute(self, expert_id: int, input_text: str, auth_context: Dict[str, Any],
                       max_tokens: int = 1500, temperature: float = 0.2) -> str:
        from src.core.execution.transactional import TransactionalExecutor
        executor = TransactionalExecutor(self.db)
        result = await executor.execute(
            expert_id=expert_id, input_text=input_text,
            parameters={"max_tokens": max_tokens, "temperature": temperature},
            auth_context=auth_context)
        out = result.get("output_text", "") if isinstance(result, dict) else ""
        try:
            return json.loads(out).get("output_text", out)
        except Exception:
            return out

    # ----------------------------------------------------------------- searx
    async def _searx(self, tool: str, args: Dict[str, Any], timeout: float = 180.0) -> Dict[str, Any]:
        """Call the UNAUTHENTICATED search-mcp-server /mcp (url from config)."""
        url = get_config("research.search_url") or _DEFAULT_SEARCH_URL
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": tool, "arguments": args}}
        from src.core.http import get_shared_async_client
        client = get_shared_async_client(timeout=timeout)
        resp = await client.post(url, json=body, timeout=timeout,
                                 headers={"Accept": "application/json, text/event-stream",
                                          "Content-Type": "application/json"})
        txt = resp.text
        for line in txt.splitlines():
            line = line.strip()
            if line.startswith("data:"):
                line = line[5:].strip()
            if line.startswith("{"):
                try:
                    o = json.loads(line)
                    if "result" in o or "error" in o:
                        res = o.get("result", {})
                        return res.get("structuredContent") or res or o
                except Exception:
                    pass
        try:
            o = json.loads(txt)
            return o.get("result", {}).get("structuredContent") or o.get("result", {}) or o
        except Exception:
            return {}

    # --------------------------------------------------------- stage 1: research
    async def _research(self, tc: Dict[str, Any]) -> List[Dict[str, Any]]:
        seen, cands = set(), []
        smax = int(get_config("research.search_max_results") or 6)
        for q in tc["queries"]:
            r = await self._searx("search", {"query": q, "language": "en", "max_results": smax})
            for it in (r.get("results") or []):
                cu = _canonical_url(it.get("url") or "")
                if not cu or cu in seen:
                    continue
                seen.add(cu)
                cands.append({"url": cu, "title": (it.get("title") or "")[:200], "host": _host(cu),
                              "engine": it.get("engine"), "search_score": float(it.get("score") or 0.0),
                              "published": it.get("publishedDate"), "query": q})
        return cands

    async def _crawl(self, url: str) -> str:
        r = await self._searx("crawl", {"urls": url, "output_format": "markdown", "stealth": True})
        docs = r.get("documents") or []
        if docs and docs[0].get("status") == "success":
            return docs[0].get("markdown") or ""
        return ""

    # ------------------------------------------------- register read / merge / write
    async def _read_register(self, path: str, auth_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        res = await self._svc(self._file_id, "read_file", {"profile": "default", "path": path}, auth_context)
        struct = self._mcp_struct(res)
        txt = struct.get("value") if isinstance(struct, dict) and isinstance(struct.get("value"), str) \
            else self._mcp_text(res)
        rows = []
        for ln in (txt or "").splitlines():
            ln = ln.strip()
            if not ln:
                continue
            try:
                rows.append(json.loads(ln))
            except Exception:
                pass
        return rows

    async def _write_register(self, path: str, rows: List[Dict[str, Any]],
                              auth_context: Dict[str, Any]) -> None:
        payload = "\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in rows)
        payload = payload + ("\n" if rows else "")
        await self._svc(self._file_id, "write_file",
                        {"profile": "default", "path": path, "content": payload, "overwrite": True},
                        auth_context)

    @staticmethod
    def _merge(existing: List[Dict[str, Any]], cands: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        by_url = {r["url"]: r for r in existing if r.get("url")}
        new = []
        for c in cands:
            if c["url"] in by_url:
                by_url[c["url"]].update({"search_score": c.get("search_score"), "last_seen_at": _now()})
                continue
            c = dict(c); c["first_seen_at"] = _now(); c["last_seen_at"] = c["first_seen_at"]
            by_url[c["url"]] = c; new.append(c)
        return list(by_url.values()), new

    # ---------------------------------------------------------- stage 3: rank + prune
    @staticmethod
    def _recency(first_seen: Optional[str]) -> float:
        if not first_seen:
            return 0.5
        try:
            t = time.mktime(time.strptime(first_seen[:15], "%Y-%m-%dT%H%M%S"))
            half = float(get_config("research.recency_halflife_days") or 30.0)
            age_days = max(0.0, (time.time() - t) / 86400.0)
            return 0.5 ** (age_days / half)
        except Exception:
            return 0.5

    def _score(self, s: Dict[str, Any]) -> float:
        rel = min(1.0, float(s.get("search_score") or 0.0) / 5.0)
        rec = self._recency(s.get("first_seen_at"))
        ing = 0.15 if s.get("ingested") else 0.0
        return round(0.6 * rel + 0.25 * rec + ing, 6)

    async def _rank_and_prune(self, profile: str, collection: str, sources: List[Dict[str, Any]],
                              auth_context: Dict[str, Any], do_delete: bool) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        max_sources = int(get_config("research.max_sources") or 50)
        for s in sources:
            s["score"] = self._score(s)
        ranked = sorted(sources, key=lambda s: (s["score"], s.get("first_seen_at") or ""), reverse=True)
        keep, retire = ranked[:max_sources], ranked[max_sources:]
        for s in retire:
            if do_delete:
                try:
                    await self._svc(self._index_id, "delete_by_filter",
                                    {"profile": profile, "collection": collection,
                                     "filters": {"source_uri": s["url"]}}, auth_context)
                except Exception as exc:
                    logger.warning("prune delete failed for %s: %s", s.get("url"), exc)
            s["retired_at"] = _now()
        for i, s in enumerate(keep):
            s["rank"] = i + 1
        return keep, retire

    # ------------------------------------------------------- stage 4: grounded gen
    async def _grounded_generate(self, profile: str, collection: str, label: str,
                                 auth_context: Dict[str, Any]) -> Dict[str, Any]:
        sr = await self._svc(self._index_id, "search",
                             {"profile": profile, "collection": collection,
                              "query": f"{label} latest developments", "top_k": 6}, auth_context)
        hits = self._mcp_struct(sr).get("results") or []
        facts = "\n\n".join(f"[S{i+1}] {h.get('source_uri')}\n{(h.get('text') or '')[:1200]}"
                            for i, h in enumerate(hits))
        prompt = (
            f"You are the {label} researcher. Using ONLY the SOURCE FACTS below (freshly "
            f"retrieved from the web today), write a concise daily brief in clean semantic HTML "
            f"with an <h1> title and 2-3 <h2> sections. Cite sources inline as [S1],[S2]. "
            f"Do not invent facts.\n\nSOURCE FACTS:\n{facts}\n")
        doc = await self._execute(self._gen_id, prompt, auth_context, max_tokens=1500, temperature=0.2)
        return {"retrieved": len(hits), "facts_chars": len(facts), "document": doc}

    # --------------------------------------------------------------- delivery
    async def _slack_endpoint(self, channel_name: str, auth_context: Dict[str, Any]) -> str:
        try:
            ch = await self._svc(self._notify_id, "list_channels", {}, auth_context)
            items = self._mcp_struct(ch).get("channels") or self._mcp_struct(ch).get("items") or []
            for c in items:
                if c.get("name") == channel_name:
                    return str((c.get("config") or {}).get("endpoint") or "")
        except Exception as exc:
            logger.warning("slack endpoint resolve failed: %s", exc)
        return ""

    async def _deliver(self, tc: Dict[str, Any], subject: str, html: str, idem: str,
                       auth_context: Dict[str, Any], slack_endpoint: Optional[str] = None) -> Dict[str, Any]:
        dests = [{"channel": tc["email_channel"], "address": tc["email_group"],
                  "preferences": {"content_style": "html", "format_mode": "passthrough"}}]
        # Operator-requested direct feed recipients (e.g. ukraine + nato-doctrine): delivered
        # alongside the group as direct email destinations (no platform accounts created).
        for addr in (tc.get("extra_recipients") or []):
            dests.append({"channel": tc["email_channel"], "address": addr,
                          "preferences": {"content_style": "html", "format_mode": "passthrough"}})
        # Slack needs the webhook ENDPOINT address (a channel name soft-fails). The
        # MCP list_channels surface is permission-scoped/empty for this caller, so the
        # endpoint is supplied by the scheduler (resolved at schedule-creation time via
        # the admin channels API), with a runtime resolve as a best-effort fallback.
        endpoint = slack_endpoint or await self._slack_endpoint(tc["slack_channel"], auth_context)
        if endpoint:
            dests.insert(0, {"channel": tc["slack_channel"], "address": endpoint,
                             "preferences": {"content_style": "html"}})
        send = await self._svc(self._notify_id, "send_notification", {
            "destinations": dests, "subject": subject,
            "content": [{"type": "html", "body": html}], "idempotency_key": idem}, auth_context)
        struct = self._mcp_struct(send)
        mid = struct.get("message_id")
        if not mid:
            return {"ok": False, "message_id": None, "states": [], "raw": str(send)[:300]}
        states: List[Dict[str, Any]] = []
        for _ in range(18):
            time.sleep(5)
            dl = await self._svc(self._notify_id, "list_deliveries", {"message_id": mid}, auth_context)
            items = self._mcp_struct(dl).get("items") or self._mcp_struct(dl).get("deliveries") or []
            states = [{"channel": it.get("channel_name") or it.get("channel"),
                       "to": it.get("destination"), "state": it.get("state") or it.get("status")}
                      for it in items]
            if states and all((s["state"] in _DELIVERED_STATES or "fail" in str(s["state"]).lower())
                              for s in states):
                break
        any_ok = any(s["state"] in _DELIVERED_STATES for s in states)
        return {"ok": bool(any_ok), "message_id": mid, "states": states,
                "destinations": [d["channel"] for d in dests]}

    async def _git_audit(self, tc: Dict[str, Any], topic: str, run_ts: str, summary: Dict[str, Any],
                         auth_context: Dict[str, Any]) -> Dict[str, Any]:
        path = f"docs/audit/research-loop/{topic}/{run_ts}.md"
        body = (f"# Research-loop audit — {topic} — {run_ts}\n\n"
                f"candidates={summary.get('candidates')} new={summary.get('new_sources')} "
                f"ingested={summary.get('ingested')} kept={summary.get('kept')} "
                f"retired={summary.get('retired')} retrieved={summary.get('retrieved')}\n")
        try:
            await self._svc(self._git_id, "file_write",
                            {"workspace_id": _AUDIT_WORKSPACE, "path": path, "content": body}, auth_context)
            await self._svc(self._git_id, "git_add",
                            {"workspace_id": _AUDIT_WORKSPACE, "paths": [path]}, auth_context)
            await self._svc(self._git_id, "git_commit",
                            {"workspace_id": _AUDIT_WORKSPACE,
                             "message": f"research-loop {topic} {run_ts}",
                             "author_name": "research-loop", "author_email": "research-loop@cloud-dog.net",
                             "committer_name": "research-loop", "committer_email": "research-loop@cloud-dog.net"},
                            auth_context)
            return {"ok": True, "path": path}
        except Exception as exc:
            logger.warning("git audit failed: %s", exc)
            return {"ok": False, "error": str(exc)[:200]}

    # ------------------------------------------------------------------- run
    async def run(self, topic: str, *, deliver: bool = True, dry_run: bool = False,
                  actor: str = "research-loop", slack_endpoint: Optional[str] = None) -> Dict[str, Any]:
        if topic not in TOPICS:
            return {"action_taken": False, "status": "failed",
                    "error": f"unknown topic '{topic}'; known: {list(TOPICS)}"}
        self._resolve_ids()
        tc = TOPICS[topic]
        run_ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        profile = tc["profile"]
        collection = tc["collection"] + ("-test" if dry_run else "")
        register = ("research-loop-test/" if dry_run else "") + tc["register"]
        auth_context = {"actor": actor, "role": "system",
                        "correlation_id": f"research-loop-{topic}-{run_ts}"}
        summary: Dict[str, Any] = {"action_taken": True, "status": "ok", "topic": topic,
                                   "run_ts": run_ts, "dry_run": dry_run, "collection": collection}

        # ensure collection exists
        await self._svc(self._index_id, "admin_collection_create",
                        {"profile": profile, "collection": collection}, auth_context)

        # 1. research
        cands = await self._research(tc)
        summary["candidates"] = len(cands)

        # register merge
        existing = await self._read_register(register, auth_context)
        combined, new_rows = self._merge(existing, cands)
        summary["existing_sources"] = len(existing)
        summary["new_sources"] = len(new_rows)

        # 2. crawl + ingest the NEW ones (bounded per run)
        per_run = int(get_config("research.crawl_new_per_run") or 4)
        ingested = 0
        for s in new_rows[:per_run]:
            md = await self._crawl(s["url"])
            if md and len(md) >= 200:
                res = await self._svc(self._index_id, "ingest_text",
                                      {"profile": profile, "collection": collection,
                                       "text": md, "source": s["url"]}, auth_context)
                if self._mcp_struct(res).get("job_id"):
                    s["ingested"] = True
                    s["crawl_chars"] = len(md)
                    ingested += 1
        summary["ingested"] = ingested
        if ingested:
            time.sleep(6)  # let async embedding settle

        # 3. rank + prune at threshold
        keep, retire = await self._rank_and_prune(profile, collection, combined, auth_context, do_delete=True)
        summary["kept"] = len(keep)
        summary["retired"] = len(retire)
        summary["retired_hosts"] = [s.get("host") for s in retire][:10]
        summary["top_sources"] = [{"rank": s.get("rank"), "score": s.get("score"), "host": s.get("host")}
                                  for s in keep[:5]]
        await self._write_register(register, keep, auth_context)
        summary["register"] = register

        # 4. grounded generation
        gen = await self._grounded_generate(profile, collection, tc["label"], auth_context)
        summary["retrieved"] = gen["retrieved"]
        summary["doc_chars"] = len(gen["document"])
        html = gen["document"]
        if not html.strip():
            summary["status"] = "partial"
            summary["failing_step"] = "generation"
            return summary

        # 5. deliver (Drive write + notify + git audit)  — skipped in dry_run
        if deliver and not dry_run:
            drive_path = f"{tc['drive_out'].rstrip('/')}/{run_ts}-{topic}-brief.html"
            wr = await self._svc(self._file_id, "write_file",
                                 {"profile": get_config("research.storage_profile") or "google_drive",
                                  "path": drive_path, "content": html, "overwrite": True}, auth_context)
            summary["drive_written"] = (not self._mcp_is_error(wr))
            summary["drive_path"] = drive_path
            deliv = await self._deliver(tc, tc["subject"] + f" — {run_ts}",
                                        f"<p>Cloud-Dog AI · web-grounded · {run_ts}</p>\n" + html,
                                        f"research-loop-{topic}-{run_ts}", auth_context,
                                        slack_endpoint=slack_endpoint)
            summary["delivery"] = deliv
            summary["git_audit"] = await self._git_audit(tc, topic, run_ts, summary, auth_context)
            if not deliv.get("ok"):
                summary["status"] = "partial"
                summary["failing_step"] = "delivery"
        else:
            summary["delivery"] = {"skipped": True, "reason": "dry_run" if dry_run else "deliver=False"}
        summary["doc_head"] = html[:240]
        return summary


async def run_research_cycle(topic: str, *, db: Any = None, deliver: bool = True,
                             dry_run: bool = False, actor: str = "research-loop",
                             slack_endpoint: Optional[str] = None) -> Dict[str, Any]:
    """Module entry — invoked by the ``run_research_cycle`` MCP tool / scheduler."""
    if db is None:
        from src.database.connection import get_db
        db = next(get_db())
    agent = ResearchCycleAgent(db)
    return await agent.run(topic, deliver=deliver, dry_run=dry_run, actor=actor,
                           slack_endpoint=slack_endpoint)
