from types import SimpleNamespace

import httpx
import openai
import pytest
from analyst.errors import InvalidOutputError, ProviderConfigurationError, ProviderUnavailableError
from analyst.llm_client import generate_structured
from analyst.settings import AIMode, AnalystAISettings
from pydantic import BaseModel, ConfigDict, Field


class _Answer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(min_length=1)


def _live_settings(**overrides: object) -> AnalystAISettings:
    defaults: dict[str, object] = {
        "ai_mode": AIMode.LIVE,
        "openai_api_key": "openai-test-key",
        "llm_timeout_seconds": 1.0,
    }
    defaults.update(overrides)
    return AnalystAISettings(**defaults)


class _FakeClient:
    def __init__(self, *, response: object = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls: list[dict[str, object]] = []

        async def create(**kwargs: object) -> object:
            self.calls.append(kwargs)
            if self._error is not None:
                raise self._error
            return self._response

        self.chat = SimpleNamespace(completions=SimpleNamespace(create=create))


def _chat_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def _request() -> httpx.Request:
    return httpx.Request("POST", "https://example.invalid/v1/chat/completions")


def _response(status_code: int) -> httpx.Response:
    return httpx.Response(status_code=status_code, request=_request())


@pytest.mark.anyio
async def test_openai_success_returns_validated_schema() -> None:
    client = _FakeClient(response=_chat_response('{"value": "ok"}'))

    result = await generate_structured(
        schema=_Answer,
        system_prompt="system",
        user_prompt="user",
        settings=_live_settings(),
        client_factory=lambda settings: client,
    )

    assert result == _Answer(value="ok")
    assert len(client.calls) == 1


@pytest.mark.anyio
async def test_openai_timeout_raises_provider_unavailable_error() -> None:
    client = _FakeClient(error=openai.APITimeoutError(request=_request()))

    with pytest.raises(ProviderUnavailableError):
        await generate_structured(
            schema=_Answer,
            system_prompt="system",
            user_prompt="user",
            settings=_live_settings(),
            client_factory=lambda settings: client,
        )


@pytest.mark.anyio
async def test_openai_authentication_error_raises_provider_configuration_error() -> None:
    client = _FakeClient(
        error=openai.AuthenticationError("bad key", response=_response(401), body=None)
    )

    with pytest.raises(ProviderConfigurationError):
        await generate_structured(
            schema=_Answer,
            system_prompt="system",
            user_prompt="user",
            settings=_live_settings(),
            client_factory=lambda settings: client,
        )


@pytest.mark.anyio
async def test_openai_bad_request_raises_provider_configuration_error() -> None:
    client = _FakeClient(
        error=openai.BadRequestError("invalid schema", response=_response(400), body=None)
    )

    with pytest.raises(ProviderConfigurationError):
        await generate_structured(
            schema=_Answer,
            system_prompt="system",
            user_prompt="user",
            settings=_live_settings(),
            client_factory=lambda settings: client,
        )


@pytest.mark.anyio
async def test_invalid_json_from_openai_raises_invalid_output_error() -> None:
    client = _FakeClient(response=_chat_response("not-json"))

    with pytest.raises(InvalidOutputError):
        await generate_structured(
            schema=_Answer,
            system_prompt="system",
            user_prompt="user",
            settings=_live_settings(),
            client_factory=lambda settings: client,
        )


@pytest.mark.anyio
async def test_schema_violation_from_openai_raises_invalid_output_error() -> None:
    client = _FakeClient(response=_chat_response('{"unexpected": "field"}'))

    with pytest.raises(InvalidOutputError):
        await generate_structured(
            schema=_Answer,
            system_prompt="system",
            user_prompt="user",
            settings=_live_settings(),
            client_factory=lambda settings: client,
        )


@pytest.mark.anyio
async def test_empty_completion_raises_provider_unavailable_error() -> None:
    client = _FakeClient(response=_chat_response(""))

    with pytest.raises(ProviderUnavailableError):
        await generate_structured(
            schema=_Answer,
            system_prompt="system",
            user_prompt="user",
            settings=_live_settings(),
            client_factory=lambda settings: client,
        )


@pytest.mark.anyio
async def test_missing_openai_api_key_raises_before_any_client_call() -> None:
    with pytest.raises(ProviderConfigurationError):
        await generate_structured(
            schema=_Answer,
            system_prompt="system",
            user_prompt="user",
            settings=_live_settings(openai_api_key=None),
        )
