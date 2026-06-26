import pytest

from tests.helpers_orchestration import build_api_client, seed_admin, seed_expert


pytestmark = [pytest.mark.system, pytest.mark.pure, pytest.mark.slow, pytest.mark.heavy]
@pytest.mark.ST
@pytest.mark.mcp
@pytest.mark.req("FR-045")


def test_st161_service_subexpert_and_prompt_crud(db_session):
    _, api_key = seed_admin(db_session)
    parent = seed_expert(
        db_session,
        'st_orch_parent',
        'ST Orchestration Parent',
        'System-test parent expert for orchestration CRUD coverage and contract validation.',
    )
    child = seed_expert(
        db_session,
        'st_orch_child',
        'ST Orchestration Child',
        'System-test child expert for orchestration CRUD coverage and contract validation.',
    )
    client = build_api_client(db_session, api_key=api_key)

    service = client.post(
        '/services',
        json={
            'name': 'st-orch-service',
            'service_type': 'rest',
            'endpoint_url': 'https://service.example.test',
            'metadata': {'tools': [{'name': 'fetch-report', 'description': 'Fetch a report'}]},
        },
    )
    assert service.status_code == 200, service.text
    service_id = service.json()['id']

    bound = client.post(f'/experts/{parent.id}/services', json={'service_id': service_id, 'priority': 10})
    assert bound.status_code == 200, bound.text

    listed = client.get(f'/experts/{parent.id}/services')
    assert listed.status_code == 200, listed.text
    assert listed.json()['services'][0]['service']['name'] == 'st-orch-service'

    sub = client.post(f'/experts/{parent.id}/sub-experts', json={'sub_expert_id': child.id, 'max_depth': 2})
    assert sub.status_code == 200, sub.text

    sub_list = client.get(f'/experts/{parent.id}/sub-experts')
    assert sub_list.status_code == 200, sub_list.text
    assert sub_list.json()['sub_experts'][0]['sub_expert']['name'] == child.name

    prompt = client.post('/prompts', json={'name': 'st-template', 'content': 'Services={{ tools }}'})
    assert prompt.status_code == 200, prompt.text
    prompt_id = prompt.json()['id']

    preview = client.post(f'/prompts/{prompt_id}/test', json={'expert_id': parent.id, 'input_text': 'hello'})
    assert preview.status_code == 200, preview.text
    assert 'Services=' in preview.json()['rendered_prompt']
