import pytest

from cloud_dog_llm.domain.errors import InvalidRequestError, ProviderUnavailableError

from src.core.knowledge.manager import KnowledgeHistoryManager
from src.servers.api.routes.channels import (
    _build_session_knowledge_prompt,
    _is_retryable_sync_generation_error,
)
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


def test_build_session_knowledge_prompt_includes_normalized_session_entries(monkeypatch):
    def fake_get_knowledge_history(self, user_id, knowledge_type, knowledge_id):
        assert user_id == 7
        assert knowledge_type == "session"
        assert knowledge_id == 11
        return [
            {"content": "  Session code is   atlas-42  "},
            {"content": "Second line\nwith   extra   spacing"},
            {"content": ""},
        ]

    monkeypatch.setattr(
        KnowledgeHistoryManager,
        "get_knowledge_history",
        fake_get_knowledge_history,
    )

    prompt = _build_session_knowledge_prompt(db=object(), user_id=7, session_id=11)

    assert prompt is not None
    assert "Session knowledge is available for this conversation." in prompt
    assert "- Session code is atlas-42" in prompt
    assert "- Second line with extra spacing" in prompt
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


def test_build_session_knowledge_prompt_returns_none_when_no_session_content(monkeypatch):
    monkeypatch.setattr(
        KnowledgeHistoryManager,
        "get_knowledge_history",
        lambda self, user_id, knowledge_type, knowledge_id: [{"content": "   "}],
    )

    assert _build_session_knowledge_prompt(db=object(), user_id=7, session_id=11) is None
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


def test_sync_generation_retryable_errors_match_transient_provider_failures():
    assert _is_retryable_sync_generation_error(ProviderUnavailableError("provider unavailable")) is True
    assert _is_retryable_sync_generation_error(InvalidRequestError("Ollama chat failed with 500")) is True
    assert _is_retryable_sync_generation_error(InvalidRequestError("Ollama chat failed with 503")) is True
    assert _is_retryable_sync_generation_error(InvalidRequestError("Ollama chat failed with 400")) is False
    assert _is_retryable_sync_generation_error(RuntimeError("permanent failure")) is False


_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.llm, pytest.mark.fast]
