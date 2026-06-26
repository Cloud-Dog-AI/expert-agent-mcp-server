# Copyright 2026 Cloud-Dog, Viewdeck Engineering Limited
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
UT1.134 — demo expert tool dispatch + access_control unification + per-expert llm_model.

License: Apache 2.0
Ownership: Cloud-Dog, Viewdeck Engineering Limited
Description:
    Proves W28C-1704 EA4/EA7/EA11 (W28M-FIX-1615):
      * EA4: TransactionalExecutor reads the expert's bound ``tools`` and
        auto-invokes grounding tools (search/retrieve/query/read), surfacing the
        results as ``services_invoked``; action tools are listed available.
      * EA7: ``normalise_access_control`` unifies the legacy ``{roles:[...]}`` and
        ``{demo:true,collection,surface}`` shapes into ``{type,...}`` and
        ``is_authorized`` dispatches on type.
      * EA11: the executor passes the per-expert ``llm_model`` to the LLM service
        rather than a container default.

Related Tasks: W28M-FIX-1615 / W28C-1704 EA4/EA7/EA11
"""

import asyncio
import json

import pytest

from src.core.auth.user_manager import UserManager
from src.core.execution.transactional import TransactionalExecutor
from src.core.expert.access_control import is_authorized, normalise_access_control
from src.database.models import ExpertConfig, ExternalService


class RecordingLLMManager:
    def __init__(self):
        self.init_model = None

    async def initialize(self, **kwargs):
        self.init_model = kwargs.get("model")

    async def generate(self, messages, temperature, max_tokens, **kwargs):
        return {"content": "ok", "tokens_used": 5, "model": self.init_model}


# ---------------------------------------------------------------- EA7 schema ----
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_normalise_legacy_rbac_shape():
    out = normalise_access_control({"roles": ["admin", "viewer"]})
    assert out["type"] == "rbac"
    assert out["roles"] == ["admin", "viewer"]
    assert out["demo_surface"] is None
    assert out["allowed_groups"] == []
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_normalise_legacy_demo_shape():
    out = normalise_access_control(
        {"demo": True, "collection": "demo_researcher_ukraine_war_qdrant", "surface": "DEMO-024"}
    )
    assert out["type"] == "demo"
    assert out["demo_collection"] == "demo_researcher_ukraine_war_qdrant"
    assert out["demo_surface"] == "DEMO-024"
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_normalise_is_idempotent():
    once = normalise_access_control({"roles": ["admin"]})
    twice = normalise_access_control(once)
    assert once == twice
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_is_authorized_dispatches_on_type():
    # demo: open within surface
    assert is_authorized({"demo": True, "surface": "DEMO-024"}, user_role="viewer") is True
    # rbac no group gate: open
    assert is_authorized({"roles": ["admin", "viewer"]}, user_role="viewer") is True
    # rbac with group gate: denied for non-member, allowed for member, admin override
    gated = {"type": "rbac", "allowed_groups": [7]}
    assert is_authorized(gated, user_role="viewer", user_group_ids=[1, 2]) is False
    assert is_authorized(gated, user_role="viewer", user_group_ids=[7]) is True
    assert is_authorized(gated, user_role="admin", user_group_ids=[1]) is True


# ---------------------------------------------------------------- EA4 dispatch --
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_executor_dispatches_expert_bound_grounding_tools(db_session, monkeypatch):
    user = UserManager(db_session).create_user(
        username="ea4_user",
        email="ea4_user@example.com",
        password="Password123!",
        role="admin",
    )
    expert = ExpertConfig(
        name="ea4_research_expert",
        title="EA4 Research Expert",
        description="Expert with bound grounding tools for dispatch testing.",
        llm_provider="ollama",
        llm_model="granite4:tiny-h",
        enabled=True,
        prompt_template="You are {{ expert.title }}.",
        tools_json=json.dumps(
            [
                {
                    "service": "indexretriever0",
                    "tool": "search",
                    "default_collection": "demo_researcher_ukraine_war_qdrant",
                },
                {"service": "filemcpserver0", "tool": "write_file", "default_profile": "tbrg"},
            ]
        ),
        access_control_json=json.dumps({"type": "rbac", "roles": ["admin", "viewer"]}),
    )
    service = ExternalService(
        name="indexretriever0",
        type="mcp",
        endpoint_url="https://indexretriever0.cloud-dog.net/mcp",
    )
    db_session.add(expert)
    db_session.add(service)
    db_session.commit()

    captured = {}

    async def fake_invoke(self, service_id, tool_name, arguments=None, auth_context=None, session_id=None):
        captured["service_id"] = service_id
        captured["tool_name"] = tool_name
        captured["arguments"] = arguments
        return {
            "service_id": service_id,
            "service_name": "indexretriever0",
            "tool_name": tool_name,
            "status": "ok",
            "result": {"hits": 3},
        }

    monkeypatch.setattr(
        "src.core.service.composition.ServiceCompositionManager.invoke_tool", fake_invoke
    )

    executor = TransactionalExecutor(db_session, llm_manager=RecordingLLMManager())
    result = asyncio.run(
        executor.execute(
            expert.id,
            "What is the latest on the conflict?",
            auth_context={"user_id": user.id, "username": user.username, "role": "admin"},
        )
    )

    names = [s.get("tool_name") for s in result["services_invoked"]]
    # The grounding tool was invoked...
    assert "search" in names
    assert captured["tool_name"] == "search"
    assert captured["arguments"]["query"] == "What is the latest on the conflict?"
    assert captured["arguments"]["collection"] == "demo_researcher_ukraine_war_qdrant"
    # ...and the write_file action tool is surfaced as available, not auto-fired.
    actions = [s for s in result["services_invoked"] if s.get("tool_name") == "write_file"]
    assert actions and actions[0]["status"] == "available"


# ---------------------------------------------------------------- EA11 model ----
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_executor_honours_per_expert_llm_model(db_session):
    UserManager(db_session).create_user(
        username="ea11_user",
        email="ea11_user@example.com",
        password="Password123!",
        role="admin",
    )
    expert = ExpertConfig(
        name="ea11_expert",
        title="EA11 Expert",
        description="Expert that must be executed with its own per-expert llm_model.",
        llm_provider="ollama",
        llm_model="granite4:tiny-h",
        enabled=True,
        prompt_template="You are {{ expert.title }}.",
    )
    db_session.add(expert)
    db_session.commit()

    recorder = RecordingLLMManager()
    executor = TransactionalExecutor(db_session, llm_manager=recorder)
    result = asyncio.run(executor.execute(expert.id, "hello"))

    # The per-expert model was passed to the LLM service, not a container default.
    assert recorder.init_model == "granite4:tiny-h"
    assert result["llm_model"] == "granite4:tiny-h"
