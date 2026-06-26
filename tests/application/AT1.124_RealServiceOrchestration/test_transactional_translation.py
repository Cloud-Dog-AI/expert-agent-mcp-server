import uuid

import pytest

from tests.helpers_orchestration import build_api_client, seed_admin
from tests.helpers_real_orchestration import require_llm, write_evidence


pytestmark = [pytest.mark.application, pytest.mark.llm, pytest.mark.slow, pytest.mark.heavy, pytest.mark.timeout(300)]
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_transactional_translation_persistence_modes(db_session):
    test_name = "test_transactional_translation_persistence_modes"
    require_llm()

    api_key = f"orch-translate-{uuid.uuid4().hex}"
    _, api_key = seed_admin(db_session, api_key=api_key)
    client = build_api_client(db_session, api_key=api_key)

    suffix = uuid.uuid4().hex[:8]
    expert_id = None
    persisted_session_id = None

    try:
        expert = client.post(
            "/experts",
            json={
                "name": f"translation_expert_{suffix}",
                "title": "Translation Expert",
                "description": "Translates user input to the requested language and returns only the translated text.",
                "prompt_template": (
                    "Return exactly one French sentence translation and nothing else."
                ),
            },
        )
        assert expert.status_code == 200, expert.text
        expert_id = expert.json()["id"]

        before = client.get("/sessions")
        assert before.status_code == 200, before.text
        before_total = before.json()["total"]

        transient = client.post(
            f"/experts/{expert_id}/execute",
            json={
                "input_text": "Respond only with the French translation of this sentence: The weather is beautiful today",
                "parameters": {"persist_session": False, "max_tokens": 120, "temperature": 0.0},
            },
        )
        assert transient.status_code == 200, transient.text
        transient_body = transient.json()
        write_evidence(test_name, "transient_execute", transient_body)

        transient_text = transient_body["output_text"].lower()
        assert transient_body["session_id"] is None
        assert transient_body["token_usage"] is not None
        assert transient_body["execution_time_ms"] > 0
        assert any(
            phrase in transient_text
            for phrase in [
                "le temps est beau aujourd",
                "il fait beau aujourd",
                "le temps est magnifique aujourd",
            ]
        )

        after_transient = client.get("/sessions")
        assert after_transient.status_code == 200, after_transient.text
        assert after_transient.json()["total"] == before_total

        persisted = client.post(
            f"/experts/{expert_id}/execute",
            json={
                "input_text": "Respond only with the French translation of this sentence: The weather is beautiful today",
                "parameters": {"persist_session": True, "max_tokens": 120, "temperature": 0.0},
            },
        )
        assert persisted.status_code == 200, persisted.text
        persisted_body = persisted.json()
        write_evidence(test_name, "persisted_execute", persisted_body)

        persisted_session_id = persisted_body["session_id"]
        assert persisted_session_id is not None
        assert persisted_body["token_usage"] is not None
        assert persisted_body["execution_time_ms"] > 0

        after_persisted = client.get("/sessions")
        assert after_persisted.status_code == 200, after_persisted.text
        assert after_persisted.json()["total"] == before_total + 1
    finally:
        if persisted_session_id is not None:
            client.delete(f"/sessions/{persisted_session_id}")
        if expert_id is not None:
            client.delete(f"/experts/{expert_id}")
        client.close()
