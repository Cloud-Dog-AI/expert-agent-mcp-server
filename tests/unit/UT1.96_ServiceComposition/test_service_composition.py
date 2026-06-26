import asyncio
import json

import httpx
import pytest

from src.core.service.composition import ServiceCompositionManager
from src.database.models import ExternalService, ExpertConfig, ServiceBinding, ServiceInvocationLog
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_service_discovery_and_invocation(db_session):
    expert = ExpertConfig(
        name='ut_service_expert',
        title='UT Service Expert',
        description='Detailed expert used for service composition unit coverage.',
        llm_provider='openai',
        llm_model='gpt-4.1-mini',
        enabled=True,
    )
    service = ExternalService(
        name='ut_mcp_service',
        type='mcp',
        endpoint_url='https://service.example.test/mcp',
        auth_config_json=json.dumps({'type': 'api_key', 'value': 'svc-key'}),
    )
    db_session.add(expert)
    db_session.add(service)
    db_session.commit()
    db_session.refresh(expert)
    db_session.refresh(service)
    binding = ServiceBinding(expert_config_id=expert.id, service_id=service.id, enabled=True)
    db_session.add(binding)
    db_session.commit()

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode())
        if payload['method'] == 'tools/list':
            return httpx.Response(200, json={'result': {'tools': [{'name': 'search', 'description': 'Search remote corpus'}]}})
        if payload['method'] == 'tools/call':
            return httpx.Response(200, json={'result': {'output': 'remote ok', 'tokens_used': 11}})
        raise AssertionError(payload)

    manager = ServiceCompositionManager(db_session, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    manager.health_check = _healthy  # type: ignore[method-assign]

    tools = asyncio.run(manager.discover_tools(service.id))
    assert tools[0]['name'] == 'search'

    available = asyncio.run(manager.get_available_tools(expert.id))
    assert available[0]['tools'][0]['name'] == 'search'

    result = asyncio.run(
        manager.invoke_tool(service.id, 'search', {'query': 'europe'}, {'user_id': 1}, session_id=None)
    )
    assert result['status'] == 'ok'
    assert result['result']['output'] == 'remote ok'
    assert db_session.query(ServiceInvocationLog).count() == 1


async def _healthy(service_id: int):
    return {'service_id': service_id, 'health_status': 'healthy', 'detail': 'ok'}
