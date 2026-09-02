from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from opentelemetry import baggage, context, propagate, trace
from opentelemetry.trace import Span

_tracer = trace.get_tracer(__name__)


@contextmanager
def extracted_request_context(
    request: Any,
    carrier: Mapping[str, str] | None,
) -> Iterator[None]:
    current = propagate.extract(dict(carrier or {}))
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

