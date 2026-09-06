import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from opentelemetry import baggage, context, propagate, trace
from opentelemetry.trace import Span, Status, StatusCode

_tracer = trace.get_tracer(__name__)
_BAGGAGE_KEYS = (
    "app.request_id",
    "app.business_trace_id",
    "app.contract_version",
)


@contextmanager
def request_context(request: Any) -> Iterator[None]:
    values = {
        "app.request_id": getattr(request, "request_id", None),
        "app.business_trace_id": getattr(request, "trace_id", None),
        "app.contract_version": getattr(request, "contract_version", None),
    }
    current = context.get_current()
    for key, value in values.items():
        if value is not None:
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
def workflow_span(request: Any) -> Iterator[Span]:
    trace_input = _json_attribute(request)
    with (
        request_context(request),
        operation_span(
            "orchestrator.workflow",
            observation_type="agent",
            attributes={
                "app.attempt": request.attempt,
                "langfuse.trace.name": "distributed-agent-workflow",
                "langfuse.trace.input": trace_input,
                "langfuse.observation.input": trace_input,
                "langfuse.session.id": str(request.request_id),
            },
        ) as span,
    ):
        yield span


def set_workflow_result(span: Span, response: Any) -> None:
    trace_output = _json_attribute(response)
    span.set_attribute("langfuse.trace.output", trace_output)
    span.set_attribute("langfuse.observation.output", trace_output)
    span.set_attribute("app.workflow_status", response.status.value)
    span.set_attribute("app.warning_count", len(response.warnings))
    if response.error is not None:
        span.set_attribute("app.error_code", response.error.code.value)
        span.set_status(Status(StatusCode.ERROR, "workflow failed"))


def set_observation_input(span: Span, value: Any) -> None:
    span.set_attribute("langfuse.observation.input", _json_attribute(value))


def set_observation_output(span: Span, value: Any) -> None:
    span.set_attribute("langfuse.observation.output", _json_attribute(value))


def inject_context() -> dict[str, str]:
    carrier: dict[str, str] = {}
    propagate.inject(carrier)
    return carrier


def _correlation_attributes() -> dict[str, str]:
    attributes: dict[str, str] = {}
    for key in _BAGGAGE_KEYS:
        if (value := baggage.get_baggage(key)) is not None:
            attributes[key] = str(value)
    if request_id := attributes.get("app.request_id"):
        attributes["langfuse.trace.metadata.request_id"] = request_id
        attributes["langfuse.session.id"] = request_id
    if trace_id := attributes.get("app.business_trace_id"):
        attributes["langfuse.trace.metadata.business_trace_id"] = trace_id
    return attributes


def _json_attribute(value: Any) -> str:
    if callable(model_dump := getattr(value, "model_dump", None)):
        value = model_dump(mode="json")
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), default=str)
