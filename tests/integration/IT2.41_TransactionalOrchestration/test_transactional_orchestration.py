import pytest

from tests.helpers_orchestration import build_api_client, seed_admin, seed_expert


pytestmark = [pytest.mark.integration, pytest.mark.pure, pytest.mark.slow, pytest.mark.heavy]


async def _fake_invoke(self, service_id, tool_name, arguments=None, auth_context=None, session_id=None):
    return {
        'service_id': service_id,
        'tool_name': tool_name,
        'status': 'ok',
        'result': {'answer': 'service-result', 'echo': arguments or {}},
    }


async def _fake_initialize(self, **kwargs):
    return None


async def _fake_generate(self, messages, temperature, max_tokens, **kwargs):
    return {'content': 'Integrated orchestration response', 'tokens_used': 23, 'model': 'stub'}
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-047")


def test_it241_transactional_execute_includes_service_and_delegation(monkeypatch, db_session):
    user, api_key = seed_admin(db_session)
    parent = seed_expert(
        db_session,
        'it_orch_parent',
        'IT Orchestration Parent',
        'Integration-test parent expert for transactional orchestration flow validation.',
    )
    child = seed_expert(
        db_session,
        'it_orch_child',
        'IT Orchestration Child',
        'Integration-test child expert for transactional orchestration flow validation.',
    )
    client = build_api_client(db_session, api_key=api_key)

    service = client.post(
        '/services',
        json={
            'name': 'it-orch-service',
            'service_type': 'rest',
            'endpoint_url': 'https://service.example.test',
            'metadata': {'tools': [{'name': 'lookup'}]},
        },
    )
    assert service.status_code == 200, service.text
    service_id = service.json()['id']
    assert client.post(f'/experts/{parent.id}/services', json={'service_id': service_id}).status_code == 200
    assert client.post(f'/experts/{parent.id}/sub-experts', json={'sub_expert_id': child.id}).status_code == 200

    monkeypatch.setattr('src.core.service.composition.ServiceCompositionManager.invoke_tool', _fake_invoke)
    monkeypatch.setattr('src.core.llm.manager.LLMManager.initialize', _fake_initialize)
    monkeypatch.setattr('src.core.llm.manager.LLMManager.generate', _fake_generate)

    response = client.post(
        f'/experts/{parent.id}/execute',
        json={
            'input_text': 'Run the composed workflow',
            'parameters': {
                'persist_session': True,
                'service_tool_calls': [{'service_id': service_id, 'tool_name': 'lookup', 'arguments': {'topic': 'europe'}}],
                'delegations': [{'sub_expert_id': child.id, 'task': 'Summarise the lookup'}],
            },
            'context': {'messages': [{'role': 'user', 'content': 'Prior context'}]},
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['output_text'] == 'Integrated orchestration response'
    assert body['services_invoked'][0]['tool_name'] == 'lookup'
    assert body['delegations'][0]['sub_expert_id'] == child.id
    assert body['session_id'] is not None
