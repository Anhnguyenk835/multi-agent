import json
from types import SimpleNamespace

from opentelemetry import baggage, propagate
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from orchestrator import telemetry
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


def test_workflow_span_records_business_input_and_output(monkeypatch) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "_tracer", provider.get_tracer("test"))
    request = SimpleNamespace(
        request_id="request-1",
        trace_id="trace-1",
        contract_version="v1",
        attempt=1,
        model_dump=lambda **_: {"query": "market outlook", "attempt": 1},
    )
    response = SimpleNamespace(
        status=SimpleNamespace(value="success"),
        warnings=[],
        error=None,
        model_dump=lambda **_: {"status": "success", "result": "brief"},
    )

    with telemetry.workflow_span(request) as span:
        telemetry.set_workflow_result(span, response)

    attributes = exporter.get_finished_spans()[0].attributes
    expected_input = {"query": "market outlook", "attempt": 1}
    expected_output = {"status": "success", "result": "brief"}
    assert json.loads(attributes["langfuse.trace.input"]) == expected_input
    assert json.loads(attributes["langfuse.observation.input"]) == expected_input
    assert json.loads(attributes["langfuse.trace.output"]) == expected_output
    assert json.loads(attributes["langfuse.observation.output"]) == expected_output
