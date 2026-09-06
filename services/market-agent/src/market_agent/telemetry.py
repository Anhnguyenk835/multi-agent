from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Any

from opentelemetry import baggage, context, trace
from opentelemetry.trace import Span

_tracer = trace.get_tracer(__name__)


@contextmanager
def request_span(request: Any) -> Iterator[Span]:
    metadata = request.metadata
    current = context.get_current()
    for key, value in {
        "app.request_id": metadata.request_id,
        "app.business_trace_id": metadata.trace_id,
        "app.contract_version": metadata.contract_version,
    }.items():
        current = baggage.set_baggage(key, str(value), context=current)
    token = context.attach(current)
    try:
        with operation_span(
            "market-agent.analyze",
            observation_type="agent",
            attributes={"app.agent": "market", "app.attempt": metadata.attempt},
        ) as span:
            yield span
    finally:
        context.detach(token)


@contextmanager
def operation_span(
    name: str,
    *,
    observation_type: str = "span",
    attributes: Mapping[str, Any] | None = None,
) -> Iterator[Span]:
    request_id = baggage.get_baggage("app.request_id")
    business_trace_id = baggage.get_baggage("app.business_trace_id")
    contract_version = baggage.get_baggage("app.contract_version")
    span_attributes = {
        "langfuse.observation.type": observation_type,
        **{key: value for key, value in (attributes or {}).items() if value is not None},
    }
    if request_id is not None:
        span_attributes["app.request_id"] = str(request_id)
        span_attributes["langfuse.trace.metadata.request_id"] = str(request_id)
    if business_trace_id is not None:
        span_attributes["app.business_trace_id"] = str(business_trace_id)
        span_attributes["langfuse.trace.metadata.business_trace_id"] = str(business_trace_id)
    if contract_version is not None:
        span_attributes["app.contract_version"] = str(contract_version)
    with _tracer.start_as_current_span(name, attributes=span_attributes) as span:
        yield span
