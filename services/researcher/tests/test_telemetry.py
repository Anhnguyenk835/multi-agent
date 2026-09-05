import json
from types import SimpleNamespace

import pytest
from langchain.agents.middleware import ModelResponse
from langchain_core.messages import AIMessage, HumanMessage, ToolCall
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from researcher import telemetry


@pytest.mark.anyio
async def test_react_turn_parents_model_and_tool_spans(monkeypatch) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "_tracer", provider.get_tracer("test"))
    observer = telemetry.ReactAgentTelemetry("research-fast", tool_names={"search"})
    request = SimpleNamespace(
        system_message=None,
        messages=[HumanMessage(content="market outlook")],
    )

    async def call_model(_request):
        with telemetry.operation_span("POST /v1/chat/completions"):
            pass
        return ModelResponse(
            result=[
                AIMessage(
                    content="",
                    tool_calls=[ToolCall(name="search", args={"query": "market"}, id="call-1")],
                )
            ]
        )

    with telemetry.operation_span("researcher.run_react_agent"):
        await observer._run_model_turn(request, call_model)
        with observer.tool_context("call-1"), telemetry.operation_span("search"):
            pass
        observer.complete_tool("call-1", {"result_count": 8})

    spans = {span.name: span for span in exporter.get_finished_spans()}
    agent_turn = spans["agent.turn 1"]
    logical_call = spans["call_llm"]
    provider_call = spans["POST /v1/chat/completions"]
    tool_call = spans["search"]
    input_value = json.loads(logical_call.attributes["langfuse.observation.input"])
    turn_output = json.loads(agent_turn.attributes["langfuse.observation.output"])

    assert input_value["model"] == "research-fast"
    assert input_value["messages"][0]["data"]["content"] == "market outlook"
    assert turn_output["tools"]["call-1"] == {"result_count": 8}
    assert logical_call.parent.span_id == agent_turn.context.span_id
    assert provider_call.parent.span_id == logical_call.context.span_id
    assert tool_call.parent.span_id == agent_turn.context.span_id
    assert logical_call.end_time <= tool_call.start_time
    assert "gen_ai.usage.input_tokens" not in logical_call.attributes
