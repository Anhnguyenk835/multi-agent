from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from opentelemetry import baggage, context, trace
from opentelemetry.trace import Span, Status, StatusCode

_tracer = trace.get_tracer(__name__)


@contextmanager
def request_context(request: Any) -> Iterator[None]:
    current = context.get_current()
    for key, value in {
        "app.request_id": request.request_id,
        "app.business_trace_id": request.trace_id,
        "app.contract_version": request.contract_version,
    }.items():
        current = baggage.set_baggage(key, str(value), context=current)
    token = context.attach(current)
    try:
        yield
    finally:
        context.detach(token)


@contextmanager
def operation_span(
    name: str,
    *,
    observation_type: str = "span",
    attributes: Mapping[str, Any] | None = None,
) -> Iterator[Span]:
    span_attributes = _correlation_attributes()
    span_attributes.update(
        {key: value for key, value in (attributes or {}).items() if value is not None}
    )
    span_attributes["langfuse.observation.type"] = observation_type
    with _tracer.start_as_current_span(name, attributes=span_attributes) as span:
        yield span


@contextmanager
def generation_span(route: str, schema_name: str) -> Iterator[Span]:
    with operation_span(
        f"gen_ai.chat {route}",
        observation_type="generation",
        attributes={
            "app.agent": "analyst",
            "app.output_schema": schema_name,
            "gen_ai.operation.name": "chat",
            "gen_ai.provider.name": "litellm",
            "gen_ai.request.model": route,
            "langfuse.observation.model.name": route,
        },
    ) as span:
        yield span


def set_generation_response(span: Span, response: Any) -> None:
    if model := getattr(response, "model", None):
        span.set_attribute("gen_ai.response.model", model)
    if (usage := getattr(response, "usage", None)) is not None:
        if (value := getattr(usage, "prompt_tokens", None)) is not None:
            span.set_attribute("gen_ai.usage.input_tokens", value)
        if (value := getattr(usage, "completion_tokens", None)) is not None:
            span.set_attribute("gen_ai.usage.output_tokens", value)


def record_error(span: Span, error: BaseException, outcome: str) -> None:
    span.record_exception(error)
    span.set_attribute("app.outcome", outcome)
    span.set_attribute("error.type", type(error).__name__)
    span.set_status(Status(StatusCode.ERROR, str(error)))


def _correlation_attributes() -> dict[str, str]:
    request_id = baggage.get_baggage("app.request_id")
    business_trace_id = baggage.get_baggage("app.business_trace_id")
    contract_version = baggage.get_baggage("app.contract_version")
    return {
        key: str(value)
        for key, value in {
            "app.request_id": request_id,
            "app.business_trace_id": business_trace_id,
            "app.contract_version": contract_version,
            "langfuse.trace.metadata.request_id": request_id,
            "langfuse.trace.metadata.business_trace_id": business_trace_id,
        }.items()
        if value is not None
    }

