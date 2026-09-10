import json
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from langchain.agents.middleware import wrap_model_call
from langchain_core.messages import AIMessage, message_to_dict, messages_to_dict
from opentelemetry import baggage, context, propagate, trace
from opentelemetry.trace import Span, Status, StatusCode

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


@dataclass(slots=True)
class _AgentTurn:
    span: Span
    model_output: dict[str, Any]
    pending_tool_calls: set[str]
    tool_outputs: dict[str, Any] = field(default_factory=dict)


class ReactAgentTelemetry:
    """Trace each ReAct turn without carrying attached context across async tasks."""

    def __init__(self, model: str, *, tool_names: set[str] | None = None) -> None:
        self._model = model
        self._tool_names = tool_names or set()
        self._turn = 0
        self._turns_by_tool_call: dict[str, _AgentTurn] = {}
        self._active_turns: dict[int, _AgentTurn] = {}

    def middleware(self):
        @wrap_model_call
        async def trace_model_turn(request, handler):
            return await self._run_model_turn(request, handler)

        return trace_model_turn

    async def _run_model_turn(self, request: Any, handler: Any) -> Any:
        self._turn += 1
        turn_number = self._turn
        model_input = {
            "model": self._model,
            "messages": messages_to_dict(
                ([request.system_message] if request.system_message is not None else [])
                + list(request.messages)
            ),
        }
        turn_span = _tracer.start_span(
            f"agent.turn {turn_number}",
            attributes={
                **_correlation_attributes(),
                "app.agent": "market_analyst",
                "app.agent.turn": turn_number,
                "langfuse.observation.type": "agent",
                "langfuse.observation.input": _json_attribute(model_input),
            },
        )
        try:
            with (
                trace.use_span(turn_span, end_on_exit=False),
                operation_span(
                    "call_llm",
                    observation_type="generation",
                    attributes={
                        "app.agent": "market_analyst",
                        "app.llm.turn": turn_number,
                        "gen_ai.request.model": self._model,
                        "langfuse.observation.model.name": self._model,
                        "langfuse.observation.input": _json_attribute(model_input),
                    },
                ) as model_span,
            ):
                response = await handler(request)
                model_output = {
                    "messages": [message_to_dict(message) for message in response.result],
                    "structured_response": response.structured_response,
                }
                model_span.set_attribute(
                    "langfuse.observation.output", _json_attribute(model_output)
                )
        except BaseException as error:
            turn_span.record_exception(error)
            turn_span.set_status(Status(StatusCode.ERROR, str(error)))
            turn_span.set_attribute(
                "langfuse.observation.output",
                _json_attribute({"error": {"type": type(error).__name__, "message": str(error)}}),
            )
            turn_span.end()
            raise

        pending = {
            str(tool_call["id"])
            for message in response.result
            if isinstance(message, AIMessage)
            for tool_call in message.tool_calls
            if tool_call.get("id") and tool_call.get("name") in self._tool_names
        }
        if not pending:
            turn_span.set_attribute("langfuse.observation.output", _json_attribute(model_output))
            turn_span.end()
            return response

        turn = _AgentTurn(turn_span, model_output, pending)
        self._active_turns[turn_number] = turn
        for tool_call_id in pending:
            self._turns_by_tool_call[tool_call_id] = turn
        return response

    @contextmanager
    def tool_context(self, tool_call_id: str) -> Iterator[None]:
        turn = self._turns_by_tool_call.get(tool_call_id)
        if turn is None:
            yield
            return
        try:
            with trace.use_span(turn.span, end_on_exit=False):
                yield
        except BaseException as error:
            self.fail_tool(tool_call_id, error)
            raise

    def complete_tool(self, tool_call_id: str, output: Any) -> None:
        turn = self._turns_by_tool_call.pop(tool_call_id, None)
        if turn is None:
            return
        turn.tool_outputs[tool_call_id] = output
        turn.pending_tool_calls.discard(tool_call_id)
        if not turn.pending_tool_calls:
            self._finish_turn(turn)

    def fail_tool(self, tool_call_id: str, error: BaseException) -> None:
        turn = self._turns_by_tool_call.get(tool_call_id)
        if turn is not None:
            turn.span.record_exception(error)
            turn.span.set_status(Status(StatusCode.ERROR, str(error)))
        self.complete_tool(
            tool_call_id,
            {"error": {"type": type(error).__name__, "message": str(error)}},
        )

    def close(self) -> None:
        for turn in list(self._active_turns.values()):
            turn.span.set_attribute("app.agent.turn.incomplete", True)
            turn.span.set_status(Status(StatusCode.ERROR, "agent turn ended before its tools"))
            self._finish_turn(turn)

    def _finish_turn(self, turn: _AgentTurn) -> None:
        turn.span.set_attribute(
            "langfuse.observation.output",
            _json_attribute({"model": turn.model_output, "tools": turn.tool_outputs}),
        )
        turn.span.end()
        self._active_turns = {
            number: active for number, active in self._active_turns.items() if active is not turn
        }
        self._turns_by_tool_call = {
            call_id: active
            for call_id, active in self._turns_by_tool_call.items()
            if active is not turn
        }


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


def _json_attribute(value: Any) -> str:
    return json.dumps(value, ensure_ascii=True, separators=(",", ":"), default=str)
