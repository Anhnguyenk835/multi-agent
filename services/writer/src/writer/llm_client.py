import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from time import monotonic

import openai
from distributed_agent_contracts import model_timeout_budget
from pydantic import BaseModel, ValidationError

from writer.errors import InvalidOutputError, ProviderConfigurationError, ProviderUnavailableError
from writer.settings import WriterAISettings
from writer.telemetry import (
    generation_span,
    operation_span,
    record_error,
    set_generation_response,
)

_NO_RETRY = (openai.AuthenticationError, openai.PermissionDeniedError, openai.BadRequestError)


@dataclass(frozen=True, slots=True)
class StructuredStreamChunk[T: BaseModel]:
    kind: str
    text: str = ""
    result: T | None = None


@lru_cache(maxsize=1)
def _default_gateway_client(settings: WriterAISettings) -> openai.AsyncOpenAI:
    return openai.AsyncOpenAI(
        api_key=settings.gateway_api_key,
        base_url=settings.gateway_base_url,
        max_retries=0,
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
    with operation_span(
        "output.schema_validate",
        observation_type="guardrail",
        attributes={"app.output_schema": schema.__name__},
    ):
        try:
            data = json.loads(content)
            return schema.model_validate(data)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise InvalidOutputError(
                f"gateway route {model!r} returned output that failed schema validation: {exc}"
            ) from exc


async def generate_structured[T: BaseModel](
    *,
    schema: type[T],
    system_prompt: str,
    user_prompt: str,
    settings: WriterAISettings,
    deadline_at: datetime | None = None,
    client_factory: Callable[[WriterAISettings], object] | None = None,
) -> T:
    if not settings.gateway_api_key:
        raise ProviderConfigurationError(
            "LLM_GATEWAY_API_KEY is required to call generate_structured"
        )

    client = (client_factory or _default_gateway_client)(settings)
    model = settings.model_route
    budget = _model_budget(settings, deadline_at)
    with generation_span(model, schema.__name__) as span:
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=_messages(system_prompt, user_prompt),
                response_format=_json_schema_response_format(schema),
                max_tokens=settings.llm_max_output_tokens,
                timeout=budget.client_seconds,
                extra_body=(
                    {"request_timeout": budget.provider_attempt_seconds}
                    if deadline_at is not None
                    else None
                ),
            )
        except _NO_RETRY as exc:
            record_error(span, exc, "rejected")
            raise ProviderConfigurationError(f"LLM gateway rejected the request: {exc}") from exc
        except openai.APITimeoutError as exc:
            record_error(span, exc, "deadline_exceeded")
            if deadline_at is not None:
                raise TimeoutError("writer deadline reached during model call") from exc
            raise ProviderUnavailableError(f"LLM gateway is unavailable: {exc}") from exc
        except Exception as exc:
            record_error(span, exc, "unavailable")
            raise ProviderUnavailableError(f"LLM gateway is unavailable: {exc}") from exc

        content = response.choices[0].message.content
        if not content:
            error = ProviderUnavailableError("LLM gateway returned an empty completion")
            record_error(span, error, "unavailable")
            raise error

        set_generation_response(span, response)
        span.set_attribute("app.outcome", "success")
    return _parse(schema, content, model)


async def generate_structured_stream[T: BaseModel](
    *,
    schema: type[T],
    system_prompt: str,
    user_prompt: str,
    settings: WriterAISettings,
    deadline_at: datetime | None = None,
    client_factory: Callable[[WriterAISettings], object] | None = None,
):
    """Yield provider JSON fragments, then a schema-validated structured result.

    The caller is responsible for converting raw JSON fragments into a safe
    display format. Raw model output must never cross the Writer boundary.
    """
    if not settings.gateway_api_key:
        raise ProviderConfigurationError(
            "LLM_GATEWAY_API_KEY is required to call generate_structured"
        )

    client = (client_factory or _default_gateway_client)(settings)
    model = settings.model_route
    budget = _model_budget(settings, deadline_at)
    started = monotonic()
    parts: list[str] = []
    with generation_span(
        model,
        schema_name=schema.__name__,
        stream=True,
    ) as span:
        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=_messages(system_prompt, user_prompt),
                response_format=_json_schema_response_format(schema),
                stream=True,
                max_tokens=settings.llm_max_output_tokens,
                timeout=budget.client_seconds,
                extra_body=(
                    {"request_timeout": budget.provider_attempt_seconds}
                    if deadline_at is not None
                    else None
                ),
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content if chunk.choices else None
                if content:
                    if not parts:
                        span.set_attribute(
                            "gen_ai.response.time_to_first_chunk",
                            monotonic() - started,
                        )
                    parts.append(content)
                    yield StructuredStreamChunk[T](kind="raw_delta", text=content)
        except _NO_RETRY as exc:
            record_error(span, exc, "rejected")
            raise ProviderConfigurationError(f"LLM gateway rejected the request: {exc}") from exc
        except openai.APITimeoutError as exc:
            record_error(span, exc, "deadline_exceeded")
            if deadline_at is not None:
                raise TimeoutError("writer deadline reached during model stream") from exc
            raise ProviderUnavailableError(f"LLM gateway is unavailable: {exc}") from exc
        except Exception as exc:
            record_error(span, exc, "unavailable")
            raise ProviderUnavailableError(f"LLM gateway is unavailable: {exc}") from exc

        content = "".join(parts)
        if not content:
            error = ProviderUnavailableError("LLM gateway returned an empty completion")
            record_error(span, error, "unavailable")
            raise error

        span.set_attribute("app.stream.chunk_count", len(parts))
        span.set_attribute("app.outcome", "success")
    yield StructuredStreamChunk[T](kind="completed", result=_parse(schema, content, model))


def _model_budget(settings: WriterAISettings, deadline_at: datetime | None):
    budget = model_timeout_budget(
        deadline_at,
        configured_seconds=settings.llm_timeout_seconds,
        provider_attempts=settings.gateway_max_provider_attempts,
    )
    if budget.provider_attempt_seconds <= 0 or budget.client_seconds <= 0:
        raise TimeoutError("writer deadline reached before model call")
    return budget
