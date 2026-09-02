import json
from collections.abc import Callable
from functools import lru_cache

import openai
from pydantic import BaseModel, ValidationError

from analyst.errors import InvalidOutputError, ProviderConfigurationError, ProviderUnavailableError
from analyst.settings import AnalystAISettings
from analyst.telemetry import (
    generation_span,
    operation_span,
    record_error,
    set_generation_response,
)

_NO_RETRY = (openai.AuthenticationError, openai.PermissionDeniedError, openai.BadRequestError)


@lru_cache(maxsize=1)
def _default_gateway_client(settings: AnalystAISettings) -> openai.AsyncOpenAI:
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
    settings: AnalystAISettings,
    client_factory: Callable[[AnalystAISettings], object] | None = None,
) -> T:
    if not settings.gateway_api_key:
        raise ProviderConfigurationError(
            "LLM_GATEWAY_API_KEY is required to call generate_structured"
        )

    client = (client_factory or _default_gateway_client)(settings)
    model = settings.model_route
    with generation_span(model, schema.__name__) as span:
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=_messages(system_prompt, user_prompt),
                response_format=_json_schema_response_format(schema),
                max_tokens=settings.llm_max_output_tokens,
                timeout=settings.llm_timeout_seconds,
            )
        except _NO_RETRY as exc:
            record_error(span, exc, "rejected")
            raise ProviderConfigurationError(f"LLM gateway rejected the request: {exc}") from exc
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
