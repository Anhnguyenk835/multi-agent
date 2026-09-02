from types import SimpleNamespace

from opentelemetry import baggage, propagate
from orchestrator.telemetry import inject_context, request_context


def test_request_context_propagates_only_correlation_metadata() -> None:
    request = SimpleNamespace(
        request_id="request-1",
        trace_id="trace-1",
        contract_version="v1",
        query="must not be propagated",
    )

    with request_context(request):
        carrier = inject_context()

    extracted = propagate.extract(carrier)
    assert baggage.get_baggage("app.request_id", context=extracted) == "request-1"
    assert baggage.get_baggage("app.business_trace_id", context=extracted) == "trace-1"
    assert baggage.get_baggage("query", context=extracted) is None
