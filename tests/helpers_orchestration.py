import uuid
from typing import Iterator

from cloud_dog_idam.api_keys.hashing import hash_api_key
from fastapi.testclient import TestClient

from src.core.auth.user_manager import UserManager
from src.database.connection import get_db
from src.database.models import APIKey, ExpertConfig
from src.servers.api.server import APIServer


def seed_admin(db_session, api_key: str = 'orchestration-test-key'):
    manager = UserManager(db_session)
    unique = uuid.uuid4().hex[:8]
    user = manager.create_user(
        username=f'orchestrator_{unique}',
        email=f'orchestrator_{unique}@example.com',
        password='Password123!',
        display_name='Orchestrator Admin',
        role='admin',
        enabled=True,
    )
    key = APIKey(
        key_hash=hash_api_key(api_key),
        user_id=user.id,
        name='orchestration_test_key',
        read_channels=True,
        write_channels=True,
        read_logs=True,
        write_logs=True,
        read_histories=True,
        write_histories=True,
        revoked=False,
    )
    db_session.add(key)
    db_session.commit()
    db_session.refresh(user)
    return user, api_key


def seed_expert(db_session, name: str, title: str, description: str):
    expert = ExpertConfig(
        name=name,
        title=title,
        description=description,
        llm_provider='openai',
        llm_model='gpt-4.1-mini',
        enabled=True,
        prompt_template='You are {{ expert.title }}. Services: {{ services }}. Sub experts: {{ sub_experts }}.',
    )
    db_session.add(expert)
    db_session.commit()
    db_session.refresh(expert)
    return expert


def build_api_client(db_session, api_key: str = 'orchestration-test-key') -> Iterator[TestClient]:
    server = APIServer()

    def override_get_db():
        yield db_session

    server.app.dependency_overrides[get_db] = override_get_db
    client = TestClient(server.app)
    client.headers.update({'X-API-Key': api_key})
    return client
