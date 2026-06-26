import asyncio

import pytest

from src.core.auth.user_manager import UserManager
from src.core.execution.transactional import TransactionalExecutor
from src.database.models import ExpertConfig, ExternalService, ServiceBinding


class StubLLMManager:
    async def initialize(self, **kwargs):
        return None

    async def generate(self, messages, temperature, max_tokens):
        return {'content': f"stubbed::{messages[-1]['content']}", 'tokens_used': 17}
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_transactional_executor_returns_structured_response(db_session, monkeypatch):
    user = UserManager(db_session).create_user(
        username='txn_user',
        email='txn_user@example.com',
        password='Password123!',
        role='admin',
    )
    expert = ExpertConfig(
        name='txn_expert',
        title='Transactional Expert',
        description='Transactional expert with enough descriptive detail for execution testing.',
        llm_provider='openai',
        llm_model='gpt-4.1-mini',
        enabled=True,
        prompt_template='You are {{ expert.title }} and can use {{ tools }}.',
    )
    service = ExternalService(
        name='txn_rest_service',
        type='rest',
        endpoint_url='https://rest.example.test/tool',
        metadata_json='{"tools": [{"name": "lookup"}]}',
    )
    db_session.add(expert)
    db_session.add(service)
    db_session.commit()
    db_session.refresh(expert)
    db_session.refresh(service)
    db_session.add(ServiceBinding(expert_config_id=expert.id, service_id=service.id, enabled=True))
    db_session.commit()

    async def fake_invoke(self, service_id, tool_name, arguments=None, auth_context=None, session_id=None):
        return {'service_id': service_id, 'tool_name': tool_name, 'status': 'ok', 'result': {'answer': 'lookup ok'}}

    monkeypatch.setattr('src.core.service.composition.ServiceCompositionManager.invoke_tool', fake_invoke)

    executor = TransactionalExecutor(db_session, llm_manager=StubLLMManager())
    result = asyncio.run(
        executor.execute(
            expert.id,
            'Translate this text',
            parameters={'service_tool_calls': [{'service_id': service.id, 'tool_name': 'lookup'}]},
            context={'messages': [{'role': 'user', 'content': 'prior context'}]},
            auth_context={'user_id': user.id, 'username': user.username, 'role': user.role},
        )
    )

    assert result['output_text'] == 'stubbed::Translate this text'
    assert result['services_invoked'][0]['tool_name'] == 'lookup'
    assert result['execution_time_ms'] >= 0


@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")
@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_transactional_interpolates_prior_service_results(db_session, monkeypatch):
    user = UserManager(db_session).create_user(
        username='txn_chain_user',
        email='txn_chain_user@example.com',
        password='Password123!',
        role='admin',
    )
    expert = ExpertConfig(
        name='txn_chain_expert',
        title='Transactional Chain Expert',
        description='Transactional expert for chained service result interpolation.',
        llm_provider='openai',
        llm_model='gpt-4.1-mini',
        enabled=True,
        prompt_template='Use chained tool output.',
    )
    service = ExternalService(
        name='txn_chain_service',
        type='mcp',
        endpoint_url='https://chain.example.test/mcp',
        metadata_json='{"tools": [{"name": "generate"}, {"name": "export"}, {"name": "write"}]}',
    )
    db_session.add(expert)
    db_session.add(service)
    db_session.commit()
    db_session.refresh(expert)
    db_session.refresh(service)
    db_session.add(ServiceBinding(expert_config_id=expert.id, service_id=service.id, enabled=True))
    db_session.commit()

    seen_arguments = []

    async def fake_invoke(self, service_id, tool_name, arguments=None, auth_context=None, session_id=None):
        seen_arguments.append((tool_name, arguments))
        if tool_name == 'generate':
            return {'tool_name': tool_name, 'result': {'template_id': 'tmpl_123', 'payload': {'a': 1}}}
        if tool_name == 'export':
            return {
                'tool_name': tool_name,
                'result': {
                    'template_id': arguments['template_id'],
                    'content': '# Generated template',
                    'payload': arguments['payload'],
                },
            }
        return {'tool_name': tool_name, 'status': 'ok', 'arguments': arguments}

    monkeypatch.setattr('src.core.service.composition.ServiceCompositionManager.invoke_tool', fake_invoke)

    executor = TransactionalExecutor(db_session, llm_manager=StubLLMManager())
    result = asyncio.run(
        executor.execute(
            expert.id,
            'Generate a template',
            parameters={
                'service_tool_calls': [
                    {
                        'service_id': service.id,
                        'tool_name': 'generate',
                        'arguments': {'name': 'demo'},
                    },
                    {
                        'service_id': service.id,
                        'tool_name': 'export',
                        'arguments': {
                            'template_id': '${service_results[0].result.template_id}',
                            'payload': '${service_results[0].result.payload}',
                        },
                    },
                ],
                'post_service_tool_calls': [
                    {
                        'service_id': service.id,
                        'tool_name': 'write',
                        'arguments': {
                            'path': '/out/template.md',
                            'content': '${service_results[1].result.content}',
                            'summary': 'saved ${service_results[1].result.template_id}',
                        },
                    }
                ],
            },
            auth_context={'user_id': user.id, 'username': user.username, 'role': user.role},
        )
    )

    assert seen_arguments[1][1]['template_id'] == 'tmpl_123'
    assert seen_arguments[1][1]['payload'] == {'a': 1}
    assert seen_arguments[2][1]['content'] == '# Generated template'
    assert seen_arguments[2][1]['summary'] == 'saved tmpl_123'
    assert result['post_service_results'][0]['status'] == 'ok'
