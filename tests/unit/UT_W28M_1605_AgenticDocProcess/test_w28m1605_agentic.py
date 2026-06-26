# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""W28M-1605 — unit tests for the agentic document-process action interface.

Deterministic + offline: the LLM intent parse is forced to fall back to the
keyword normaliser (so no live model is needed in CI), and IDAM authorisation is
exercised against a seeded in-process DB. Covers the intent grammar (FR-1605-02),
the IDAM capability-boundary gate + downgrade (FR-1605-05), and the failure-safe
confirmation renderer (FR-1605-04/06).
"""

import pytest

from src.core.agentic import document_process as dp

# W28M-1605 agentic chat-action interface (additive feature). Tier=UT, surface=a2a
# (the module backs the A2A run_document_process skill); bound to the FR rows it
# exercises so PS-REQ-TEST-TRACE marker enforcement is satisfied.
pytestmark = [
    pytest.mark.UT,
    pytest.mark.a2a,
    pytest.mark.req("FR-1605-01", "FR-1605-02", "FR-1605-04", "FR-1605-05", "FR-1605-06"),
]


# --------------------------------------------------------------------- helpers
def test_canonical_process_synonyms():
    assert dp._canonical("Document Researcher", dp._PROCESS_SYNONYMS) == "document-researcher"
    assert dp._canonical("country report", dp._PROCESS_SYNONYMS) == "country-report"
    assert dp._canonical("build template", dp._PROCESS_SYNONYMS) == "template-build"
    assert dp._canonical("unrelated", dp._PROCESS_SYNONYMS) is None


def test_canonical_recipients_synonyms():
    assert dp._canonical("all recipients", dp._RECIPIENT_SYNONYMS) == "all"
    assert dp._canonical("admin only", dp._RECIPIENT_SYNONYMS) == "admin"


def test_strip_think_blocks():
    assert dp._strip_think("<think>reasoning</think>final") == "final"


# --------------------------------------------------------------- intent parsing
@pytest.mark.asyncio
async def test_parse_intent_france_fallback(monkeypatch, db_session):
    """France headline sentence resolves to {document-researcher, france, all, in-chat}
    even when the LLM is unavailable (deterministic fallback)."""
    async def _boom(*a, **k):
        raise RuntimeError("LLM offline")

    monkeypatch.setattr("src.core.llm.manager.LLMManager.initialize", _boom)
    agent = dp.DocumentProcessAgent(db_session)
    intent = await agent.parse_intent(
        "Run the Document Researcher process for France, and send to all recipients, "
        "return here confirmation of delivery.")
    assert intent.process == "document-researcher"
    assert intent.target == "france"
    assert intent.recipients == "all"
    assert intent.return_mode == "in-chat"
    assert intent.ambiguous is False


@pytest.mark.asyncio
async def test_parse_intent_ambiguous_clarifies(monkeypatch, db_session):
    async def _boom(*a, **k):
        raise RuntimeError("LLM offline")

    monkeypatch.setattr("src.core.llm.manager.LLMManager.initialize", _boom)
    agent = dp.DocumentProcessAgent(db_session)
    intent = await agent.parse_intent("run the report")
    assert intent.ambiguous is True
    assert intent.clarifying_question
    # no target was sniffed -> no action should be taken
    assert intent.target is None


# ------------------------------------------------------------------------ IDAM
def _seed_idam(db):
    from src.core.auth.user_manager import UserManager
    from src.core.auth.group_manager import GroupManager
    um, gm = UserManager(db), GroupManager(db)
    g_ops = gm.create_group(name=dp.OPERATORS_GROUP, description="invoke")
    g_all = gm.create_group(name=dp.ALLRECIPIENTS_GROUP, description="allrecipients")
    op = um.create_user(username="op", email="op@x.net", role="user")
    restr = um.create_user(username="restr", email="r@x.net", role="user")
    um.create_user(username="outsider", email="o@x.net", role="user")
    gm.add_member(int(g_ops.id), int(op.id))
    gm.add_member(int(g_all.id), int(op.id))
    gm.add_member(int(g_ops.id), int(restr.id))
    return gm


def test_authorise_operator_all(db_session):
    _seed_idam(db_session)
    a = dp.DocumentProcessAgent(db_session).authorise("op", "all")
    assert a["allowed"] is True
    assert a["effective_recipients"] == "all"
    assert a["downgraded"] is False


def test_authorise_restricted_downgrades(db_session):
    _seed_idam(db_session)
    a = dp.DocumentProcessAgent(db_session).authorise("restr", "all")
    assert a["allowed"] is True
    assert a["effective_recipients"] == "admin"
    assert a["downgraded"] is True
    assert a["reason"] == "DOWNGRADED_NO_ALLRECIPIENTS"


def test_authorise_outsider_refused(db_session):
    _seed_idam(db_session)
    a = dp.DocumentProcessAgent(db_session).authorise("outsider", "admin")
    assert a["allowed"] is False
    assert a["reason"] == "NOT_AUTHORISED_TO_INVOKE"


def test_authorise_unknown_actor_refused(db_session):
    _seed_idam(db_session)
    a = dp.DocumentProcessAgent(db_session).authorise("ghost", "admin")
    assert a["allowed"] is False
    assert a["reason"] == "UNKNOWN_OR_DISABLED_ACTOR"


# ------------------------------------------------------- confirmation renderer
def test_render_confirmation_clarify():
    out = dp.render_confirmation({"status": "clarify", "clarifying_question": "Which process?"})
    assert "Which process?" in out


def test_render_confirmation_refused():
    out = dp.render_confirmation({"status": "refused", "actor": "x", "reason": "NOT_AUTHORISED_TO_INVOKE"})
    assert "refused" in out.lower()
    assert "chat.docprocess.invoke" in out


def test_render_confirmation_failure_never_claims_delivered():
    out = dp.render_confirmation({"status": "failed", "failing_step": "email", "error": "svc down"})
    assert "did not complete" in out.lower()
    assert "no delivery was claimed" in out.lower()


def test_render_confirmation_completed_has_msgid_and_states():
    out = dp.render_confirmation({
        "status": "completed", "intent": {"return_mode": "in-chat"},
        "process": "document-researcher", "target": "france",
        "recipients_requested": "all", "recipients_resolved": "all", "downgraded": False,
        "sections": 6, "words": 2400, "template_version": 1,
        "drive_md": "/d/x.md", "drive_html": "/d/x.html",
        "notification_message_id": 5331,
        "delivery_states": [{"channel": "slack_transparentborders", "state": "sent"},
                            {"channel": "email", "state": "delivered"}],
    })
    assert "5331" in out
    assert "slack_transparentborders: sent" in out
    assert "/d/x.md" in out
