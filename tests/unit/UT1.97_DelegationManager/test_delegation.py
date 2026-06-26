import pytest

from src.core.auth.user_manager import UserManager
from src.core.expert.delegation import DelegationManager
from src.database.models import ExpertConfig, SubExpertBinding
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_delegate_creates_child_session_and_tree(db_session):
    user = UserManager(db_session).create_user(
        username='delegate_user',
        email='delegate_user@example.com',
        password='Password123!',
    )
    parent = ExpertConfig(
        name='delegate_parent',
        title='Delegate Parent',
        description='Parent expert with enough detail for validation coverage.',
        llm_provider='openai',
        llm_model='gpt-4.1-mini',
        enabled=True,
    )
    child = ExpertConfig(
        name='delegate_child',
        title='Delegate Child',
        description='Child expert with enough detail for validation coverage.',
        llm_provider='openai',
        llm_model='gpt-4.1-mini',
        enabled=True,
    )
    db_session.add(parent)
    db_session.add(child)
    db_session.commit()
    db_session.refresh(parent)
    db_session.refresh(child)

    db_session.add(SubExpertBinding(parent_expert_id=parent.id, child_expert_id=child.id, max_depth=3))
    db_session.commit()

    manager = DelegationManager(db_session)
    root, _ = manager.session_manager.create_session(user.id, parent.id, check_limits=False)
    result = manager.delegate(root.id, child.id, 'Summarise the file list', {'messages': []})

    assert result['parent_session_id'] == root.id
    tree = manager.get_delegation_tree(root.id)
    assert tree['children'][0]['expert_config_id'] == child.id
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


@pytest.mark.unit
@pytest.mark.pure
@pytest.mark.fast
def test_delegate_blocks_self_referencing_loops(db_session):
    user = UserManager(db_session).create_user(
        username='loop_user',
        email='loop_user@example.com',
        password='Password123!',
    )
    expert = ExpertConfig(
        name='loop_expert',
        title='Loop Expert',
        description='Loop expert with enough descriptive entropy for unit validation.',
        llm_provider='openai',
        llm_model='gpt-4.1-mini',
        enabled=True,
    )
    db_session.add(expert)
    db_session.commit()
    db_session.refresh(expert)
    db_session.add(SubExpertBinding(parent_expert_id=expert.id, child_expert_id=expert.id, max_depth=3))
    db_session.commit()

    manager = DelegationManager(db_session)
    root, _ = manager.session_manager.create_session(user.id, expert.id, check_limits=False)
    with pytest.raises(ValueError, match='loop'):
        manager.delegate(root.id, expert.id, 'recursive task', {})
