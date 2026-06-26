# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""W28M-1605 — Agentic document-process action interface.

Turns ONE natural-language instruction (e.g. *"Run the Document Researcher
process for France, and send to all recipients, return here confirmation of
delivery."*) into a capability invocation:

    intent-parse (qwen3) -> IDAM gate -> invoke the W28M-1604 document-generation
    capability via the proven execute path -> in-chat confirmation.

Additive: this module is the ONLY new execution surface. It does NOT modify
``chat_tool``, ``execute_tool``, ``invoke_service_tool`` or the
``TransactionalExecutor`` graph — it composes them. Generation runs in-process
through ``TransactionalExecutor.execute`` (the proven action path the scheduler
uses); cross-service Drive read/write + notification delivery run in-process
through ``ServiceCompositionManager.invoke_tool`` (downstream creds resolved from
registered Vault service credentials, not caller auth).

IDAM is enforced at the capability boundary via LIVE group membership
(W28M-1604 finding: ``execute_tool`` does not enforce expert access_control):
  * ``chat.docprocess.invoke``       == member of group ``DEMO-DocGen-Operators``
  * ``chat.docprocess.allrecipients``== member of group ``DEMO-DocGen-AllRecipients``
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.config.loader import get_config
from src.utils.logger import get_logger

logger = get_logger(__name__)

# --- capability wiring (live entities reused from W28M-1604) -------------------
GENERATOR_EXPERT = 30       # DEMO-Document-Generator (qwen3:14b)
PLAIN_ENGLISH_EXPERT = 26   # DEMO-Plain-English-Rewrite
HUMANISE_EXPERT = 27        # DEMO-Humanise-Text
FILE_SVC = 10               # filemcpserver0
NOTIFY_SVC = 11             # notificationagent0
OPERATORS_GROUP = "DEMO-DocGen-Operators"          # gid 22 -> chat.docprocess.invoke
ALLRECIPIENTS_GROUP = "DEMO-DocGen-AllRecipients"  # chat.docprocess.allrecipients

# Confirmed, assured template on Drive (built + assured by W28M-1604 Capability A/A2).
DRIVE_OUT = "/CloudDog-Demos/transparent-borders-report-generation/output"
TEMPLATE_DRIVE_PATH = f"{DRIVE_OUT}/templates/transparent-borders-country-template-v1.json"

# Bounded section count for a chat-driven document (kept tractable for an
# interactive session — a chat request is synchronous). W28M-1604 owns the full
# >=0.9-depth proof; the chat interface produces a real, multi-section,
# corrected, delivered document. Tunable via config ``docgen.chat_max_sections``.
DEFAULT_MAX_SECTIONS = 4

_DELIVERED_STATES = {"sent", "delivered", "accepted"}
_PROCESS_SYNONYMS = {
    "document-researcher": ("document researcher", "documentresearcher", "researcher", "research", "document research"),
    "country-report": ("country report", "country-report", "report"),
    "template-build": ("template build", "template-build", "build template", "template"),
}
_RECIPIENT_SYNONYMS = {
    "all": ("all recipients", "all", "everyone", "external"),
    "admin": ("admin only", "admin-only", "admin", "internal", "internal only"),
}


@dataclass
class IntentResult:
    """Parsed agentic intent (FR-1605-02)."""

    process: Optional[str] = None
    target: Optional[str] = None
    recipients: Optional[str] = None        # "all" | "admin" | "group:<Name>"
    return_mode: str = "in-chat"
    ambiguous: bool = False
    clarifying_question: Optional[str] = None
    raw: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "process": self.process,
            "target": self.target,
            "recipients": self.recipients,
            "return_mode": self.return_mode,
            "ambiguous": self.ambiguous,
            "clarifying_question": self.clarifying_question,
        }


def _strip_think(text: str) -> str:
    """Remove qwen3 ``<think>...</think>`` chain-of-thought blocks."""
    return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()


def _canonical(value: Optional[str], synonyms: Dict[str, tuple]) -> Optional[str]:
    if not value:
        return None
    low = str(value).strip().lower()
    for canon, alts in synonyms.items():
        if low == canon or low in alts:
            return canon
    for canon, alts in synonyms.items():
        if any(a in low for a in alts) or canon in low:
            return canon
    return None


class DocumentProcessAgent:
    """Agentic interface that drives the W28M-1604 document capability from text."""

    # Default entity names (preprod ids GENERATOR_EXPERT/26/27, FILE_SVC/NOTIFY_SVC)
    # are resolved by NAME at run time so the module is portable across a fresh
    # local container (different auto-increment ids) and preprod.
    GENERATOR_NAME = "Document Generator"
    PLAIN_ENGLISH_NAME = "Plain English Rewrite"
    HUMANISE_NAME = "Humanise Text"
    FILE_SVC_NAME = "filemcpserver0"
    NOTIFY_SVC_NAME = "notificationagent0"

    def __init__(self, db: Any) -> None:
        self.db = db
        self._gen_id = GENERATOR_EXPERT
        self._pe_id = PLAIN_ENGLISH_EXPERT
        self._hu_id = HUMANISE_EXPERT
        self._file_id = FILE_SVC
        self._notify_id = NOTIFY_SVC

    def _expert_id(self, title: str, default_id: int) -> int:
        try:
            from src.core.expert.manager import ExpertManager
            for e in ExpertManager(self.db).list_experts():
                if (getattr(e, "title", None) or "").strip().lower() == title.strip().lower():
                    return int(e.id)
        except Exception as exc:
            logger.warning("expert resolve by name '%s' failed: %s", title, exc)
        return default_id

    def _service_id(self, name: str, default_id: int) -> int:
        try:
            from src.core.service.manager import ServiceManager
            svc = ServiceManager(self.db).get_service(name=name)
            if svc:
                return int(svc.id)
        except Exception as exc:
            logger.warning("service resolve by name '%s' failed: %s", name, exc)
        return default_id

    def _resolve_ids(self) -> None:
        self._gen_id = self._expert_id(self.GENERATOR_NAME, GENERATOR_EXPERT)
        self._pe_id = self._expert_id(self.PLAIN_ENGLISH_NAME, PLAIN_ENGLISH_EXPERT)
        self._hu_id = self._expert_id(self.HUMANISE_NAME, HUMANISE_EXPERT)
        self._file_id = self._service_id(self.FILE_SVC_NAME, FILE_SVC)
        self._notify_id = self._service_id(self.NOTIFY_SVC_NAME, NOTIFY_SVC)

    # ------------------------------------------------------------------ intent
    async def parse_intent(self, text: str) -> IntentResult:
        """Extract ``{process, target, recipients, return_mode}`` from free text
        via qwen3, with a deterministic normaliser/safety-net (FR-1605-02).

        On a missing process or target the result is marked ambiguous with a
        clarifying question and NO action is taken.
        """
        from src.core.llm.manager import LLMManager

        provider = get_config("llm.provider") or "ollama"
        model = get_config("llm.model") or "qwen3:14b"
        sys_prompt = (
            "You extract a structured document-generation instruction. "
            "Return ONLY a compact JSON object with keys: process, target, recipients, "
            "return_mode, ambiguous, clarifying_question.\n"
            "process is one of: document-researcher, country-report, template-build (or null).\n"
            "target is the country or topic (or null).\n"
            "recipients is one of: all, admin, or group:<Name> (or null).\n"
            "return_mode is 'in-chat' when the user asks for confirmation here.\n"
            "Set ambiguous=true and give a clarifying_question when process or target is missing or unclear. "
            "Do not invent a target. JSON only."
        )
        parsed: Dict[str, Any] = {}
        try:
            llm = LLMManager()
            await llm.initialize(provider=provider, model=model)
            resp = await llm.generate(
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": text},
                ],
                temperature=0.0,
                max_tokens=300,
            )
            body = _strip_think(resp.get("content", ""))
            m = re.search(r"\{.*\}", body, re.DOTALL)
            if m:
                parsed = json.loads(m.group(0))
        except Exception as exc:  # qwen3 unreachable / malformed -> deterministic fallback
            logger.warning("intent parse via LLM failed, using deterministic fallback: %s", exc)
            parsed = {}

        low = (text or "").lower()
        process = _canonical(parsed.get("process"), _PROCESS_SYNONYMS) or _canonical(low, _PROCESS_SYNONYMS)
        recipients = self._canonical_recipients(parsed.get("recipients"), low)
        target = parsed.get("target")
        if not target:
            # deterministic target sniff: 'for <Country>' / 'about <Country>'
            tm = re.search(r"\b(?:for|about|on)\s+([A-Z][a-zA-Z]+)", text or "")
            target = tm.group(1) if tm else None
        if isinstance(target, str):
            target = target.strip().strip(".,").lower() or None
        asked_in_chat = any(tok in low for tok in ("here", "in chat", "confirmation"))
        model_mode = parsed.get("return_mode")
        return_mode = "in-chat" if (asked_in_chat or model_mode in (None, "in-chat")) else str(model_mode)

        ambiguous = bool(parsed.get("ambiguous")) or not process or not target
        clarifying = parsed.get("clarifying_question")
        if ambiguous and not clarifying:
            missing = []
            if not process:
                missing.append("which process (document-researcher, country-report, or template-build)")
            if not target:
                missing.append("which target (country or topic)")
            clarifying = "Which document process would you like, and for which target? Please specify " + \
                         " and ".join(missing) + "."
        return IntentResult(
            process=process, target=target, recipients=recipients,
            return_mode=return_mode or "in-chat", ambiguous=ambiguous,
            clarifying_question=clarifying if ambiguous else None, raw=parsed,
        )

    @staticmethod
    def _canonical_recipients(value: Optional[str], low_text: str) -> Optional[str]:
        if isinstance(value, str) and value.lower().startswith("group:"):
            return value
        gm = re.search(r"group:([\w \-]+)", low_text)
        if gm:
            return "group:" + gm.group(1).strip()
        canon = _canonical(value, _RECIPIENT_SYNONYMS) or _canonical(low_text, _RECIPIENT_SYNONYMS)
        return canon

    # ------------------------------------------------------------------ IDAM
    def _group_member(self, username: str, group_name: str) -> bool:
        from src.core.auth.group_manager import GroupManager

        try:
            gm = GroupManager(self.db)
            group = gm.get_group(name=group_name)
            if not group:
                return False
            members = gm.get_group_members(int(group.id))
            return any((getattr(u, "username", None) == username) for u in members)
        except Exception as exc:
            logger.warning("group membership check failed for %s/%s: %s", username, group_name, exc)
            return False

    def _resolve_user(self, username: str) -> Any:
        from src.core.auth.user_manager import UserManager

        try:
            return UserManager(self.db).get_user(username=username)
        except Exception:
            return None

    def authorise(self, actor: str, recipients: Optional[str]) -> Dict[str, Any]:
        """Capability-boundary IDAM gate (FR-1605-05).

        Returns ``{allowed, effective_recipients, downgraded, reason, roles}``.
        ``chat.docprocess.invoke`` == member of DEMO-DocGen-Operators;
        ``chat.docprocess.allrecipients`` == member of DEMO-DocGen-AllRecipients.
        A caller with invoke but not allrecipients who asks for ``all`` is
        downgraded to ``admin`` (internal-only); a non-operator is refused.
        """
        user = self._resolve_user(actor)
        if user is None or not getattr(user, "enabled", True):
            return {"allowed": False, "reason": "UNKNOWN_OR_DISABLED_ACTOR", "actor": actor,
                    "roles": [], "effective_recipients": None, "downgraded": False}
        can_invoke = self._group_member(actor, OPERATORS_GROUP)
        can_all = self._group_member(actor, ALLRECIPIENTS_GROUP)
        roles = ([f"chat.docprocess.invoke({OPERATORS_GROUP})"] if can_invoke else []) + \
                ([f"chat.docprocess.allrecipients({ALLRECIPIENTS_GROUP})"] if can_all else [])
        if not can_invoke:
            return {"allowed": False, "reason": "NOT_AUTHORISED_TO_INVOKE", "actor": actor,
                    "roles": roles, "effective_recipients": None, "downgraded": False}
        requested = recipients or "admin"
        downgraded = False
        effective = requested
        reason = "OK"
        if requested == "all" and not can_all:
            effective = "admin"
            downgraded = True
            reason = "DOWNGRADED_NO_ALLRECIPIENTS"
        return {"allowed": True, "reason": reason, "actor": actor, "roles": roles,
                "effective_recipients": effective, "downgraded": downgraded,
                "can_invoke": can_invoke, "can_all": can_all, "user_id": int(getattr(user, "id", 0) or 0)}

    # ---------------------------------------------------------- service helpers
    @staticmethod
    def _unwrap(result: Dict[str, Any]) -> Dict[str, Any]:
        """``ServiceCompositionManager.invoke_tool`` returns an envelope
        ``{service_id, ..., status, result: <mcp result>}``. Unwrap to the MCP
        result so content/structuredContent/isError are reachable."""
        if isinstance(result, dict) and isinstance(result.get("result"), dict) \
                and ("content" in result["result"] or "structuredContent" in result["result"]
                     or "isError" in result["result"]):
            return result["result"]
        return result or {}

    @classmethod
    def _mcp_text(cls, result: Dict[str, Any]) -> str:
        inner = cls._unwrap(result)
        content = (inner.get("content") or [])
        if content and isinstance(content[0], dict):
            return content[0].get("text", "") or ""
        return ""

    @classmethod
    def _mcp_struct(cls, result: Dict[str, Any]) -> Dict[str, Any]:
        return (cls._unwrap(result).get("structuredContent")) or {}

    @classmethod
    def _mcp_is_error(cls, envelope: Dict[str, Any]) -> bool:
        if isinstance(envelope, dict) and envelope.get("status") in ("failed", "error", "skipped"):
            return True
        return bool(cls._unwrap(envelope).get("isError"))

    def _profile(self) -> str:
        return get_config("docgen.storage_profile") or "google_drive"

    async def _svc(self, service_id: int, tool: str, args: Dict[str, Any], auth_context: Dict[str, Any]) -> Dict[str, Any]:
        from src.core.service.composition import ServiceCompositionManager

        mgr = ServiceCompositionManager(self.db)
        return await mgr.invoke_tool(service_id=service_id, tool_name=tool, arguments=args, auth_context=auth_context)

    async def _execute(self, expert_id: int, input_text: str, auth_context: Dict[str, Any],
                       max_tokens: int = 1200, temperature: float = 0.3) -> str:
        """Run an expert through the proven execute path (in-process)."""
        from src.core.execution.transactional import TransactionalExecutor

        executor = TransactionalExecutor(self.db)
        result = await executor.execute(
            expert_id=expert_id, input_text=input_text,
            parameters={"max_tokens": max_tokens, "temperature": temperature},
            auth_context=auth_context,
        )
        out = result.get("output_text", "") if isinstance(result, dict) else ""
        try:
            return json.loads(out).get("output_text", out)
        except Exception:
            return out

    # ------------------------------------------------------------- correction
    @staticmethod
    def _split_sections(md: str) -> List[tuple]:
        out, title, body = [], None, []
        for ln in md.splitlines():
            m = re.match(r"^#{1,3}\s+(.*)$", ln)
            if m:
                if title is not None:
                    out.append((title, "\n".join(body).strip()))
                title, body = m.group(1).strip(), []
            elif title is not None:
                body.append(ln)
        if title is not None:
            out.append((title, "\n".join(body).strip()))
        return [(t, b) for t, b in out if t]

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
        """Prose-only style/vocabulary correction via experts 26->27, preserving
        headings/tables/lists verbatim and every numeric token (FR-1605-03)."""
        out, buf = [], []

        async def flush():
            text = "\n".join(buf)
            buf.clear()
            if not text.strip():
                out.append(text)
                return
            prot, nums = self._protect_nums(text)
            pe = await self._execute(
                self._pe_id,
                "Rewrite the following report prose for clarity and plain English. Keep every "
                "⟦n⟧ token EXACTLY as written and do not drop any. Return only the rewritten prose.\n\n" + prot,
                auth_context, max_tokens=900)
            hu = await self._execute(
                self._hu_id,
                "Humanise the following prose for a natural, consistent professional style. Keep every "
                "⟦n⟧ token EXACTLY. Return only the prose.\n\n" + pe,
                auth_context, max_tokens=900)
            if hu and all(("⟦%d⟧" % i) in hu for i in range(len(nums))):
                out.append(self._restore_nums(hu, nums))
            else:
                out.append(text)  # number-fidelity guard: revert on drop

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
        h, ul = [], False
        for ln in md.splitlines():
            s = ln.rstrip()
            m = re.match(r"^(#{1,4})\s+(.*)$", s)
            if m:
                if ul:
                    h.append("</ul>"); ul = False
                lvl = min(len(m.group(1)) + 1, 4)
                h.append(f"<h{lvl}>{m.group(2).strip()}</h{lvl}>"); continue
            if re.match(r"^[-*]\s+", s):
                if not ul:
                    h.append("<ul>"); ul = True
                h.append("<li>" + re.sub(r"^[-*]\s+", "", s) + "</li>"); continue
            if "|" in s and s.strip().startswith("|"):
                h.append("<p style='font-family:monospace'>" + s.strip() + "</p>"); continue
            if ul:
                h.append("</ul>"); ul = False
            if s.strip():
                h.append("<p>" + s.strip() + "</p>")
        if ul:
            h.append("</ul>")
        return "\n".join(h)

    # ----------------------------------------------------------------- delivery
    async def _slack_endpoint(self, channel_name: str, auth_context: Dict[str, Any]) -> str:
        """Resolve a Slack channel's webhook endpoint address. send_notification
        soft-fails when a Slack destination carries only the channel NAME, so the
        endpoint address must be looked up and supplied explicitly (1604 pattern)."""
        try:
            ch = await self._svc(self._notify_id, "list_channels", {}, auth_context)
            items = self._mcp_struct(ch).get("channels") or self._mcp_struct(ch).get("items")
            if not items:
                txt = self._mcp_text(ch)
                j = json.loads(txt) if txt else {}
                items = j.get("channels") or j.get("items") or []
            for c in items or []:
                if c.get("name") == channel_name:
                    return str((c.get("config") or {}).get("endpoint") or "")
        except Exception as exc:
            logger.warning("slack endpoint resolve failed: %s", exc)
        return ""

    async def _destinations(self, recipients: str, auth_context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Resolve recipients -> notification destinations (NF-1604-04 policy).

        all   -> email to the TB admin group (incl. external client) + Slack when the
                 webhook endpoint resolves (Slack needs the endpoint address).
        admin -> internal email group only (no external client, no public Slack).
        group:<Name> -> that email group.
        """
        email_pref = {"content_style": "html", "format_mode": "passthrough"}
        if recipients == "all":
            dests = [{"channel": "email_transparent_borders_report_generation",
                      "address": "group:Transparent Borders Report Generation Admin Group",
                      "preferences": email_pref}]
            endpoint = await self._slack_endpoint("slack_transparentborders", auth_context)
            if endpoint:
                dests.insert(0, {"channel": "slack_transparentborders", "address": endpoint,
                                 "preferences": {"content_style": "html"}})
            return dests
        if recipients and recipients.startswith("group:"):
            return [{"channel": "email_transparent_borders_report_generation",
                     "address": recipients, "preferences": email_pref}]
        # admin / internal-only
        internal_group = get_config("docgen.admin_internal_group") or \
            "group:Transparent Borders Report Generation Internal Admin Group"
        return [{"channel": "email_transparent_borders_report_generation",
                 "address": internal_group, "preferences": email_pref}]

    async def _deliver(self, subject: str, html: str, recipients: str, idem: str,
                       auth_context: Dict[str, Any]) -> Dict[str, Any]:
        dests = await self._destinations(recipients, auth_context)
        send = await self._svc(self._notify_id, "send_notification", {
            "destinations": dests, "subject": subject,
            "content": [{"type": "html", "body": html}], "idempotency_key": idem,
        }, auth_context)
        if isinstance(send, dict) and send.get("status") == "skipped":
            return {"ok": False, "step": "email", "error": "notification service unhealthy",
                    "message_id": None, "states": []}
        struct = self._mcp_struct(send)
        if not struct:
            txt = self._mcp_text(send)
            try:
                struct = json.loads(txt) if txt else {}
            except Exception:
                struct = {}
        mid = struct.get("message_id")
        if not mid:
            return {"ok": False, "step": "email", "error": "no message_id returned (send failed)",
                    "message_id": None, "states": [], "raw": str(send)[:400]}
        states: List[Dict[str, Any]] = []
        for _ in range(18):
            time.sleep(5)
            dl = await self._svc(self._notify_id, "list_deliveries", {"message_id": mid}, auth_context)
            d = self._mcp_struct(dl)
            if not d:
                t = self._mcp_text(dl)
                try:
                    d = json.loads(t) if t else {}
                except Exception:
                    d = {}
            items = d.get("items") or d.get("deliveries") or []
            states = [{"channel": it.get("channel") or it.get("channel_name"),
                       "state": it.get("state") or it.get("status")} for it in items]
            if states and all((s["state"] in _DELIVERED_STATES or "fail" in str(s["state"]).lower())
                              for s in states):
                break
        any_fail = any("fail" in str(s["state"]).lower() for s in states)
        any_ok = any(s["state"] in _DELIVERED_STATES for s in states)
        return {"ok": bool(any_ok and not (any_fail and not any_ok)), "step": "email",
                "message_id": mid, "states": states, "deduped": struct.get("deduped"),
                "destinations": [d.get("channel") for d in dests]}

    # ------------------------------------------------------------------- run
    async def run(self, text: str, actor: str, *, deliver: bool = True,
                  max_sections: int = DEFAULT_MAX_SECTIONS,
                  storage_profile: Optional[str] = None, template_path: Optional[str] = None,
                  output_dir: Optional[str] = None) -> Dict[str, Any]:
        """End-to-end agentic action (FR-1605-03/04/06). Returns a structured
        confirmation; never reports a false 'delivered'. Storage settings default
        to config (canonical google_drive) but may be overridden per call."""
        run_ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        self._resolve_ids()
        intent = await self.parse_intent(text)
        if intent.ambiguous:
            return {"action_taken": False, "status": "clarify", "intent": intent.to_dict(),
                    "clarifying_question": intent.clarifying_question}

        authz = self.authorise(actor, intent.recipients)
        if not authz["allowed"]:
            return {"action_taken": False, "status": "refused", "intent": intent.to_dict(),
                    "actor": actor, "reason": authz["reason"], "roles": authz["roles"]}

        recipients = authz["effective_recipients"]
        auth_context = {"user_id": authz.get("user_id"), "actor": actor, "role": "user",
                        "correlation_id": f"w28m1605-{actor}-{run_ts}"}
        steps: Dict[str, Any] = {}

        # 1) read the confirmed, assured template (file-mcp; storage profile configurable —
        # per-call override > config > built-in default)
        profile = storage_profile or self._profile()
        template_path = template_path or get_config("docgen.template_path") or TEMPLATE_DRIVE_PATH
        output_dir = (output_dir or get_config("docgen.output_dir") or DRIVE_OUT).rstrip("/")
        tpl_raw = await self._svc(self._file_id, "read_file",
                                  {"profile": profile, "path": template_path}, auth_context)
        if self._mcp_is_error(tpl_raw):
            detail = self._mcp_text(tpl_raw) or (tpl_raw.get("detail") if isinstance(tpl_raw, dict) else "")
            return {"action_taken": False, "status": "failed", "failing_step": "read_template",
                    "error": f"storage backend '{profile}' unavailable: {detail}"[:300],
                    "intent": intent.to_dict()}
        try:
            template = json.loads(self._mcp_text(tpl_raw))
        except Exception as exc:
            return {"action_taken": False, "status": "failed", "failing_step": "read_template",
                    "error": f"could not parse template: {exc}", "intent": intent.to_dict()}
        specs = template.get("sections") or []
        if max_sections:
            specs = specs[:max_sections]
        steps["read_template"] = {"ok": True, "version": template.get("version"),
                                  "checksum": str(template.get("checksum"))[:12], "sections": len(specs)}

        # 2) section-by-section generation (execute path) + correction (26->27)
        target = intent.target
        family = template.get("family") or "transparent-borders-country"
        finals: List[str] = []
        gen_error = None
        for i, spec in enumerate(specs, 1):
            title = spec.get("title", f"Section {i}")
            gp = (f"Write the '{title}' section of a {family} document for {str(target).title()}.\n"
                  f"Purpose: {spec.get('purpose','')}\n"
                  f"Required elements: {', '.join(spec.get('required_elements') or [])}\n"
                  f"Style: {spec.get('style','analytical UK English')}; "
                  f"Vocabulary: {spec.get('vocabulary','policy')}.\n"
                  f"Target length about {spec.get('target_words',400)} words.\n"
                  f"Write detailed Markdown beginning '## {title}'. Use a Markdown table or bullet list "
                  f"where the required elements call for it. Add analysis. Return only this section's Markdown.")
            try:
                draft = await self._execute(self._gen_id, gp, auth_context, max_tokens=1300, temperature=0.3)
                if not draft.strip():
                    raise RuntimeError("generator returned empty section")
                corrected = await self._correct_section(draft, auth_context)
                if not re.search(r"^##\s", corrected, re.M):
                    corrected = f"## {title}\n\n{corrected}"
                finals.append(corrected.strip())
            except Exception as exc:
                gen_error = f"section '{title}': {exc}"
                logger.warning("generation failed: %s", gen_error)
                break
        if gen_error or not finals:
            return {"action_taken": False, "status": "failed", "failing_step": "generate",
                    "error": gen_error or "no sections generated", "intent": intent.to_dict(),
                    "steps": steps}
        steps["generate"] = {"ok": True, "sections": len(finals)}

        # 3) assemble + write to Drive (md + html)
        byline = (f"*Generated {time.strftime('%Y-%m-%d')} by Cloud-Dog W28M-1605 agentic chat action "
                  f"(template v{template.get('version')} {str(template.get('checksum'))[:12]}); "
                  f"drafted on qwen3:14b; corrected via plain-english + humanise experts.*")
        body = "\n\n".join(finals)
        full_md = f"# {family.title()} Document: {str(target).title()}\n\n{byline}\n\n{body}"
        full_html = (f"<h1>{family.title()} Document: {str(target).title()}</h1>\n"
                     f"<p><em>{byline.strip('*')}</em></p>\n" + self._md_to_html(body))
        words = len(re.findall(r"\w+", full_md))
        md_path = f"{output_dir}/{run_ts}-{target}-w28m1605-agentic-chat.md"
        html_path = f"{output_dir}/{run_ts}-{target}-w28m1605-agentic-chat.html"
        w1 = await self._svc(self._file_id, "write_file",
                             {"profile": profile, "path": md_path, "content": full_md, "overwrite": True},
                             auth_context)
        w2 = await self._svc(self._file_id, "write_file",
                             {"profile": profile, "path": html_path, "content": full_html, "overwrite": True},
                             auth_context)
        write_ok = not self._mcp_is_error(w1) and not self._mcp_is_error(w2)
        steps["write_drive"] = {"ok": bool(write_ok), "md": md_path, "html": html_path, "words": words}
        if not write_ok:
            return {"action_taken": True, "status": "failed", "failing_step": "write_drive",
                    "error": "Drive write failed", "intent": intent.to_dict(), "steps": steps,
                    "drive_md": md_path}

        # 4) deliver (notification) — never report a false delivered
        delivery = {"skipped": True}
        if deliver:
            subject = f"W28M-1605 — {family.title()} Document: {str(target).title()} ({run_ts})"
            idem = f"w28m1605-{target}-{recipients}-{template.get('version')}-{run_ts}"
            delivery = await self._deliver(subject, full_html, recipients, idem, auth_context)
            steps["deliver"] = delivery

        overall_ok = bool(write_ok) and (delivery.get("skipped") or delivery.get("ok"))
        return {
            "action_taken": True,
            "status": "completed" if overall_ok else "partial_failure",
            "intent": intent.to_dict(),
            "actor": actor,
            "process": intent.process,
            "target": target,
            "recipients_requested": intent.recipients,
            "recipients_resolved": recipients,
            "downgraded": authz.get("downgraded", False),
            "drive_md": md_path,
            "drive_html": html_path,
            "words": words,
            "sections": len(finals),
            "template_version": template.get("version"),
            "notification_message_id": delivery.get("message_id"),
            "delivery_states": delivery.get("states", []),
            "failing_step": None if overall_ok else (delivery.get("step") if not delivery.get("ok") else None),
            "steps": steps,
            "run_ts": run_ts,
        }


def render_confirmation(result: Dict[str, Any]) -> str:
    """Render the structured result as an in-chat confirmation string (FR-1605-04)."""
    status = result.get("status")
    if status == "clarify":
        return "I need a bit more detail before I can run that.\n\n" + (
            result.get("clarifying_question") or "Which process and target would you like?")
    if status == "refused":
        return (f"Request refused. Actor '{result.get('actor')}' is not authorised to run the "
                f"document process (reason: {result.get('reason')}). Required role: "
                f"chat.docprocess.invoke (member of DEMO-DocGen-Operators).")
    if status == "failed":
        return (f"The document process did not complete. Failing step: "
                f"{result.get('failing_step')} — {result.get('error')}. No delivery was claimed.")

    intent = result.get("intent", {})
    lines = [
        f"Document process complete ({result.get('status')}).",
        f"- Process: {result.get('process')}",
        f"- Target: {result.get('target')}",
        f"- Recipients requested: {result.get('recipients_requested')}",
        f"- Recipients resolved: {result.get('recipients_resolved')}"
        + ("  (downgraded — actor lacks chat.docprocess.allrecipients)" if result.get("downgraded") else ""),
        f"- Document: {result.get('sections')} sections, {result.get('words')} words "
        f"(template v{result.get('template_version')})",
        f"- Drive (markdown): {result.get('drive_md')}",
        f"- Drive (html): {result.get('drive_html')}",
    ]
    mid = result.get("notification_message_id")
    states = result.get("delivery_states") or []
    if mid:
        lines.append(f"- Notification message id: {mid}")
        if states:
            lines.append("- Per-recipient delivery states:")
            for s in states:
                lines.append(f"    - {s.get('channel')}: {s.get('state')}")
        else:
            lines.append("- Delivery: submitted (no per-recipient state yet)")
    elif intent.get("return_mode") and result.get("steps", {}).get("deliver"):
        lines.append("- Delivery: NOT confirmed (email step did not return a message id).")
    return "\n".join(lines)


async def run_document_process(text: str, *, db: Any = None, actor: Optional[str] = None,
                               deliver: bool = True, max_sections: Optional[int] = None) -> str:
    """A2A skill entry point (FR-1605-01): free text -> in-chat confirmation string.

    The actor identity may be supplied explicitly (in-process callers) or carried
    in the instruction text as a leading ``[actor:<username>]`` tag (the chat
    client injects the authenticated user); it is then validated against LIVE
    IDAM. With no actor, the configured default chat actor is used and still
    validated against IDAM (an unknown/under-privileged actor is refused).
    """
    owns_db = False
    if db is None:
        from src.database.connection import get_db
        db = next(get_db())
        owns_db = True
    if max_sections is None:
        try:
            max_sections = int(get_config("docgen.chat_max_sections") or DEFAULT_MAX_SECTIONS)
        except (TypeError, ValueError):
            max_sections = DEFAULT_MAX_SECTIONS
    try:
        # Leading bracket directives are optional automation/test hooks parsed off
        # the front of the instruction: [actor:<user>] [storage:<profile>]
        # [template:<path>] [output:<dir>]. They override the defaults; plain
        # natural-language instructions use the configured defaults (google_drive).
        overrides: Dict[str, str] = {}
        while True:
            m = re.match(r"^\s*\[(actor|storage|template|output):([^\]]+)\]\s*", text or "")
            if not m:
                break
            overrides[m.group(1)] = m.group(2).strip()
            text = text[m.end():]
        if actor is None:
            actor = overrides.get("actor") or get_config("docgen.default_chat_actor") or "demo-docgen-user"
        agent = DocumentProcessAgent(db)
        result = await agent.run(text, actor, deliver=deliver, max_sections=max_sections,
                                 storage_profile=overrides.get("storage"),
                                 template_path=overrides.get("template"),
                                 output_dir=overrides.get("output"))
        return render_confirmation(result)
    finally:
        if owns_db:
            try:
                db.close()
            except Exception:
                pass
