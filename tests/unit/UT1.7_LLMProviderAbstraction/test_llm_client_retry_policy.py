import pytest

from cloud_dog_llm.domain.errors import (
    InvalidRequestError,
    ProviderUnavailableError,
    TimeoutError as PlatformTimeoutError,
)

from src.common.llm_client import LLMClient
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


def test_should_retry_chat_error_respects_timeout_flag():
    client = LLMClient.__new__(LLMClient)

    assert client._should_retry_chat_error(PlatformTimeoutError("read timeout"), True) is True
    assert client._should_retry_chat_error(PlatformTimeoutError("read timeout"), False) is False
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


def test_should_retry_chat_error_retries_transient_provider_failures():
    client = LLMClient.__new__(LLMClient)

    assert client._should_retry_chat_error(ProviderUnavailableError("provider unavailable"), True) is True
    assert (
        client._should_retry_chat_error(InvalidRequestError("Ollama chat failed with 500"), True)
        is True
    )
    assert (
        client._should_retry_chat_error(InvalidRequestError("Ollama chat failed with 503"), True)
        is True
    )
@pytest.mark.UT
@pytest.mark.mcp
@pytest.mark.req("FR-043")


def test_should_retry_chat_error_skips_non_retryable_invalid_requests():
    client = LLMClient.__new__(LLMClient)

    assert (
        client._should_retry_chat_error(InvalidRequestError("Ollama chat failed with 400"), True)
        is False
    )
    assert client._should_retry_chat_error(RuntimeError("permanent failure"), True) is False


_w28a_202_existing_pytestmark = globals().get("pytestmark", [])
if not isinstance(_w28a_202_existing_pytestmark, list):
    _w28a_202_existing_pytestmark = [_w28a_202_existing_pytestmark]
pytestmark = _w28a_202_existing_pytestmark + [pytest.mark.unit, pytest.mark.llm, pytest.mark.fast]
