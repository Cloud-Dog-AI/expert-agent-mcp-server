import pytest

from src.core.prompt.manager import PromptManager
from src.database.models import ExpertConfig, ExternalService, ServiceBinding, SubExpertBinding
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_prompt_templates_support_assignment_and_variable_expansion(db_session):
    manager = PromptManager(db_session)
    parent = ExpertConfig(
        name='prompt_parent',
        title='Prompt Parent',
        description='Prompt parent expert with detailed scope for template testing.',
        llm_provider='openai',
        llm_model='gpt-4.1-mini',
        enabled=True,
    )
    child = ExpertConfig(
        name='prompt_child',
        title='Prompt Child',
        description='Prompt child expert with detailed scope for template testing.',
        llm_provider='openai',
        llm_model='gpt-4.1-mini',
        enabled=True,
    )
    service = ExternalService(
        name='prompt_service',
        type='rest',
        endpoint_url='https://svc.example.test',
        metadata_json='{"tools": [{"name": "fetch"}]}',
    )
    db_session.add(parent)
    db_session.add(child)
    db_session.add(service)
    db_session.commit()
    db_session.refresh(parent)
    db_session.refresh(child)
    db_session.refresh(service)
    db_session.add(ServiceBinding(expert_config_id=parent.id, service_id=service.id, enabled=True))
    db_session.add(SubExpertBinding(parent_expert_id=parent.id, child_expert_id=child.id, enabled=True))
    db_session.commit()

    template = manager.create_prompt_template(
        name='composed-prompt',
        content='Services={{ tools }} SubExperts={{ sub_experts }} User={{ user.username }}',
        variables_schema={'type': 'object'},
    )
    manager.assign_prompt_template(parent.id, template.id)
    rendered = manager.render_expert_prompt(parent.id, user={'username': 'alice'})

    assert 'fetch' in rendered
    assert 'prompt_child' in rendered
    assert 'alice' in rendered
