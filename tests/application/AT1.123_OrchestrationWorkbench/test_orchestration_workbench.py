import pytest

from tests.helpers_orchestration import build_api_client, seed_admin, seed_expert


pytestmark = [pytest.mark.application, pytest.mark.pure, pytest.mark.slow, pytest.mark.heavy]


async def _fake_invoke(self, service_id, tool_name, arguments=None, auth_context=None, session_id=None):
    return {
        'service_id': service_id,
        'tool_name': tool_name,
        'status': 'ok',
        'result': {'answer': 'saved remote result'},
    }


async def _fake_initialize(self, **kwargs):
    return None


async def _fake_generate(self, messages, temperature, max_tokens, **kwargs):
    return {'content': 'Application orchestration response', 'tokens_used': 31, 'model': 'stub'}
@pytest.mark.AT
@pytest.mark.mcp
@pytest.mark.req("FR-044")


def test_at123_orchestration_workbench_flow(monkeypatch, db_session):
    _, api_key = seed_admin(db_session)
    expert = seed_expert(
        db_session,
        'at_orch_parent',
        'AT Orchestration Parent',
        'Application-test expert covering prompt, services, and transactional orchestration.',
    )
    client = build_api_client(db_session, api_key=api_key)
    try:
        service = client.post(
            '/services',
            json={
                'name': 'at-orch-service',
                'service_type': 'rest',
                'endpoint_url': 'https://service.example.test',
                'metadata': {'tools': [{'name': 'draft-brief'}]},
            },
        )
        assert service.status_code == 200, service.text
        service_id = service.json()['id']

        prompt = client.post(
            '/prompts',
            json={
                'name': 'at-orch-template',
                'content': 'You can use {{ tools }} and {{ services }} to answer the request.',
            },
        )
        assert prompt.status_code == 200, prompt.text
        preview = client.post(
            f"/prompts/{prompt.json()['id']}/test",
            json={'expert_id': expert.id, 'input_text': 'Draft a briefing'},
        )
        assert preview.status_code == 200, preview.text

        assert (
            client.post(
                f'/experts/{expert.id}/services',
                json={'service_id': service_id, 'priority': 1},
            ).status_code
            == 200
        )

        monkeypatch.setattr('src.core.service.composition.ServiceCompositionManager.invoke_tool', _fake_invoke)
        monkeypatch.setattr('src.core.llm.manager.LLMManager.initialize', _fake_initialize)
        monkeypatch.setattr('src.core.llm.manager.LLMManager.generate', _fake_generate)

        execute = client.post(
            f'/experts/{expert.id}/execute',
            json={
                'input_text': 'Draft the final briefing',
                'parameters': {'service_tool_calls': [{'service_id': service_id, 'tool_name': 'draft-brief'}]},
                'context': {'documents': ['file-mcp://briefing-source.md']},
            },
        )
        assert execute.status_code == 200, execute.text
        body = execute.json()
        assert body['output_text'] == 'Application orchestration response'
        assert body['services_invoked'][0]['service_id'] == service_id
        assert body['execution_time_ms'] >= 0
    finally:
        client.close()
