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
Integration Test: IT2.1 - Vector Store Integration

License: Apache 2.0
Ownership: Cloud Dog
Description: Tests for vector store integration with session management

Related Requirements: FR1.3
Related Tasks: T014
Related Architecture: CC4.1.1
Related Tests: IT2.1

Recent Changes:
- Initial implementation
"""

import asyncio
import pytest
from src.core.vector.manager import VectorStoreManager
from src.core.session.manager import SessionManager
from src.database.models import ExpertConfig
from src.config.loader import get_config, load_config
from src.core.auth.password import validate_password_policy
import uuid
# Removed unused import


async def _init_qdrant_with_retry(provider, config: dict, attempts: int = 5) -> bool:
    """Retry Qdrant provider initialization to reduce transient backend flakes."""
    for attempt in range(attempts):
        if await provider.initialize(config):
            return True
        if attempt < (attempts - 1):
            await asyncio.sleep(0.5)
    return False


@pytest.fixture
def test_user(db_session):
    """Create a test user."""
    import uuid
    from src.core.auth.user_manager import UserManager

    manager = UserManager(db_session)
    username = get_config("test.user.username")
    email = get_config("test.user.email")
    password = get_config("test.user.password")
    if not username or not email or not password:
        pytest.fail("Missing test.user.username/test.user.email/test.user.password in config")
    try:
        validate_password_policy(str(password))
    except Exception:
        password = "TestPassword123!"
    unique = uuid.uuid4().hex[:8]
    if "@" not in email:
        pytest.fail("test.user.email must include a domain (e.g. user@example.com)")
    domain = email.split("@", 1)[1]
    return manager.create_user(
        username=f"{username}_it2_1_{unique}", email=f"it2_1_{unique}@{domain}", password=password
    )


@pytest.fixture
def test_expert(db_session, test_config):
    """Create a test expert configuration."""
    import uuid

    llm_provider = get_config("llm.provider")
    llm_model = get_config("llm.model")
    if not llm_provider or not llm_model:
        pytest.fail("Missing llm.provider/llm.model in config")
    expert = ExpertConfig(
        name=f"test_expert_it2_1_vectorstoreintegration_{str(uuid.uuid4())[:8]}",
        title="Test Expert",
        description="Test expert configuration",
        llm_provider=llm_provider,
        llm_model=llm_model,
        enabled=True,
    )
    db_session.add(expert)
    db_session.commit()
    db_session.refresh(expert)
    return expert
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_vector_store_with_session(test_user, test_expert, db_session):
    """Test vector store integration with session management."""
    load_config.cache_clear()

    session_manager = SessionManager(db_session)
    vector_manager = VectorStoreManager()

    # Create session
    session, _ = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id
    )

    # Get Qdrant provider
    qdrant_config = get_config("vector_stores_config.qdrant._DEFAULT_")
    if not isinstance(qdrant_config, dict):
        pytest.fail("Missing vector_stores_config.qdrant._DEFAULT_ config")
    provider = vector_manager._get_provider("qdrant")
    base_collection = qdrant_config.get("collection_name")
    if not base_collection:
        pytest.fail("Missing Qdrant collection_name in vector_stores_config.qdrant._DEFAULT_")
    collection = f"{base_collection}_{uuid.uuid4().hex[:8]}"

    config = {
        "host": qdrant_config.get("host"),
        "port": qdrant_config.get("port"),
        "api_key": qdrant_config.get("api_key"),
        "collection_name": collection,
    }
    if not config["host"] or config["port"] is None:
        pytest.fail("Missing Qdrant host/port in vector_stores_config.qdrant._DEFAULT_")
    if config["api_key"] is None:
        pytest.fail(
            "Missing Qdrant api_key in vector_stores_config.qdrant._DEFAULT_ (use empty string if not required)"
        )

    initialized = await _init_qdrant_with_retry(provider, config)
    if not initialized:
        pytest.fail(
            "Qdrant provider failed to initialise (service should be available with current --env)"
        )

    unique = uuid.uuid4().hex[:8]
    documents = [
        f"Session context document 1 {unique}",
        f"Session context document 2 {unique}",
    ]

    try:
        ids = await provider.add_documents(
            collection=collection,
            documents=documents,
            metadatas=[{"session_id": session.id} for _ in documents],
        )
    except Exception as e:
        pytest.fail(f"Qdrant add_documents failed: {e}")

    assert len(ids) == 2

    # Search in session context
    try:
        results = await provider.search(collection=collection, query=unique, n_results=2)
    except Exception as e:
        pytest.fail(f"Qdrant search failed: {e}")

    assert len(results) > 0
@pytest.mark.IT
@pytest.mark.mcp
@pytest.mark.req("FR-022")


@pytest.mark.asyncio
async def test_vector_retrieval_for_conversation(test_user, test_expert, db_session):
    """Test vector retrieval to enhance conversation context."""
    load_config.cache_clear()

    session_manager = SessionManager(db_session)
    vector_manager = VectorStoreManager()

    # Create session
    session, _ = session_manager.create_session(
        user_id=test_user.id, expert_config_id=test_expert.id
    )

    # Initialize vector store
    qdrant_config = get_config("vector_stores_config.qdrant._DEFAULT_")
    if not isinstance(qdrant_config, dict):
        pytest.fail("Missing vector_stores_config.qdrant._DEFAULT_ config")
    provider = vector_manager._get_provider("qdrant")
    base_collection = qdrant_config.get("collection_name")
    if not base_collection:
        pytest.fail("Missing Qdrant collection_name in vector_stores_config.qdrant._DEFAULT_")
    collection = f"{base_collection}_{uuid.uuid4().hex[:8]}"

    config = {
        "host": qdrant_config.get("host"),
        "port": qdrant_config.get("port"),
        "api_key": qdrant_config.get("api_key"),
        "collection_name": collection,
    }
    if not config["host"] or config["port"] is None:
        pytest.fail("Missing Qdrant host/port in vector_stores_config.qdrant._DEFAULT_")
    if config["api_key"] is None:
        pytest.fail(
            "Missing Qdrant api_key in vector_stores_config.qdrant._DEFAULT_ (use empty string if not required)"
        )

    try:
        initialized = await _init_qdrant_with_retry(provider, config)
        if not initialized or not provider._initialized:
            pytest.fail(
                "Qdrant provider failed to initialise (service should be available with current --env)"
            )
    except Exception as e:
        pytest.fail(f"Qdrant initialisation raised: {e}")

    unique = uuid.uuid4().hex[:8]
    documents = [
        f"The expert agent system provides intelligent responses. {unique}",
        f"Vector stores enable semantic search over knowledge bases. {unique}",
        f"Sessions maintain conversation context and history. {unique}",
    ]

    try:
        await provider.add_documents(collection=collection, documents=documents)
    except Exception as e:
        pytest.fail(f"Qdrant add_documents failed: {e}")

    # User asks question
    session_manager.add_message(session.id, "user", "How does the expert agent work?")

    # Retrieve relevant context
    try:
        results = await provider.search(collection=collection, query=unique, n_results=2)
    except Exception as e:
        pytest.fail(f"Qdrant search failed: {e}")

    assert len(results) > 0

    # Context can be used to enhance LLM prompt
    context_docs = [r.get("document", "") for r in results]
    assert len(context_docs) > 0

# W28A-202 marker augmentation
_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.integration, pytest.mark.vdb, pytest.mark.db, pytest.mark.smtp, pytest.mark.heavy]
