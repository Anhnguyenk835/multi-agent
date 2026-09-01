import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from functools import lru_cache
from time import monotonic

import openai
from pydantic import BaseModel, ValidationError

from writer.errors import InvalidOutputError, ProviderConfigurationError, ProviderUnavailableError
from writer.settings import WriterAISettings

logger = logging.getLogger("writer.llm_client")

_NO_RETRY = (openai.AuthenticationError, openai.PermissionDeniedError, openai.BadRequestError)


@dataclass(frozen=True, slots=True)
class StructuredStreamChunk[T: BaseModel]:
    kind: str
    text: str = ""
    result: T | None = None


@lru_cache(maxsize=1)
def _default_openai_client(settings: WriterAISettings) -> openai.AsyncOpenAI:
    return openai.AsyncOpenAI(api_key=settings.openai_api_key)


def _log_telemetry(model: str, latency_seconds: float, outcome: str, error_type: str | None) -> None:
    logger.info(
        "writer_llm_call",
        extra={
            "provider": "openai",
            "model": model,
            "latency_ms": round(latency_seconds * 1000, 1),
            "outcome": outcome,
            "error_type": error_type,
        },
    )


def _messages(system_prompt: str, user_prompt: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _json_schema_response_format(schema: type[BaseModel]) -> dict[str, object]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema.__name__,
            "schema": schema.model_json_schema(),
            "strict": True,
        },
    }


def _parse[T: BaseModel](schema: type[T], content: str, model: str) -> T:
    try:
        data = json.loads(content)
        return schema.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as exc:
        raise InvalidOutputError(
            f"openai/{model} returned output that failed schema validation: {exc}"
        ) from exc


async def generate_structured[T: BaseModel](
    *,
    schema: type[T],
    system_prompt: str,
    user_prompt: str,
    settings: WriterAISettings,
    client_factory: Callable[[WriterAISettings], object] | None = None,
) -> T:
    if not settings.openai_api_key:
        raise ProviderConfigurationError("OPENAI_API_KEY is required to call generate_structured")

    client = (client_factory or _default_openai_client)(settings)
    model = settings.openai_model
    started = monotonic()
    try:
        response = await client.chat.completions.create(
            model=model,
            messages=_messages(system_prompt, user_prompt),
            response_format=_json_schema_response_format(schema),
            timeout=settings.llm_timeout_seconds,
        )
    except _NO_RETRY as exc:
        _log_telemetry(model, monotonic() - started, "rejected", type(exc).__name__)
        raise ProviderConfigurationError(f"openai rejected the request: {exc}") from exc
    except Exception as exc:
        _log_telemetry(model, monotonic() - started, "unavailable", type(exc).__name__)
        raise ProviderUnavailableError(f"openai is unavailable: {exc}") from exc

    content = response.choices[0].message.content
    if not content:
        _log_telemetry(model, monotonic() - started, "unavailable", "EmptyCompletion")
        raise ProviderUnavailableError("openai returned an empty completion")

    _log_telemetry(model, monotonic() - started, "success", None)
    return _parse(schema, content, model)


async def generate_structured_stream[T: BaseModel](
    *,
    schema: type[T],
    system_prompt: str,
    user_prompt: str,
    settings: WriterAISettings,
    client_factory: Callable[[WriterAISettings], object] | None = None,
):
    """Yield provider JSON fragments, then a schema-validated structured result.

    The caller is responsible for converting raw JSON fragments into a safe
    display format. Raw model output must never cross the Writer boundary.
    """
    if not settings.openai_api_key:
        raise ProviderConfigurationError("OPENAI_API_KEY is required to call generate_structured")

    client = (client_factory or _default_openai_client)(settings)
    model = settings.openai_model
    started = monotonic()
    parts: list[str] = []
    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=_messages(system_prompt, user_prompt),
            response_format=_json_schema_response_format(schema),
            stream=True,
            timeout=settings.llm_timeout_seconds,
        )
        async for chunk in stream:
            content = chunk.choices[0].delta.content if chunk.choices else None
            if content:
                parts.append(content)
                yield StructuredStreamChunk[T](kind="raw_delta", text=content)
    except _NO_RETRY as exc:
        _log_telemetry(model, monotonic() - started, "rejected", type(exc).__name__)
        raise ProviderConfigurationError(f"openai rejected the request: {exc}") from exc
    except Exception as exc:
        _log_telemetry(model, monotonic() - started, "unavailable", type(exc).__name__)
        raise ProviderUnavailableError(f"openai is unavailable: {exc}") from exc

    content = "".join(parts)
    if not content:
        _log_telemetry(model, monotonic() - started, "unavailable", "EmptyCompletion")
        raise ProviderUnavailableError("openai returned an empty completion")

    _log_telemetry(model, monotonic() - started, "success", None)
    yield StructuredStreamChunk[T](kind="completed", result=_parse(schema, content, model))
