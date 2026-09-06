from collections.abc import AsyncIterator

from distributed_agent_contracts import (
    ContractError,
    ContractStatus,
    WorkflowRequest,
    WorkflowResponse,
    WriterResponse,
    copy_request_metadata,
)

from orchestrator.errors import WorkflowConflictError
from orchestrator.state import WorkflowState
from orchestrator.telemetry import set_workflow_result, workflow_span


class WorkflowService:
    def __init__(self, graph) -> None:
        self._graph = graph

    async def run(self, request: WorkflowRequest) -> WorkflowResponse:
        with workflow_span(request) as span:
            config = _thread_config(request)
            snapshot = await self._graph.aget_state(config)
            existing = dict(snapshot.values) if snapshot.values else None

            if existing:
                if existing.get("query") != request.query:
                    raise WorkflowConflictError(
                        "request_id is already associated with a different query"
                    )
                if not snapshot.next and existing.get("workflow_status"):
                    response = _workflow_response(existing)
                    set_workflow_result(span, response)
                    return response
                result = await self._graph.ainvoke(None, config)
            else:
                result = await self._graph.ainvoke(request.model_dump(mode="json"), config)

            response = _workflow_response(result)
            set_workflow_result(span, response)
            return response

    async def stream(self, request: WorkflowRequest) -> AsyncIterator[dict[str, object]]:
        """Run the existing graph while forwarding its safe custom events."""
        with workflow_span(request) as span:
            config = _thread_config(request)
            snapshot = await self._graph.aget_state(config)
            existing = dict(snapshot.values) if snapshot.values else None

            if existing and existing.get("query") != request.query:
                raise WorkflowConflictError(
                    "request_id is already associated with a different query"
                )

            yield _event("workflow.started", request)
            if existing and not snapshot.next and existing.get("workflow_status"):
                response = _workflow_response(existing)
                set_workflow_result(span, response)
                yield _terminal_event(response)
                return

            graph_input = None if existing else request.model_dump(mode="json")
            async for mode, event in self._graph.astream(
                graph_input,
                config,
                stream_mode=["custom", "updates"],
            ):
                if mode == "custom":
                    yield event

            final_snapshot = await self._graph.aget_state(config)
            response = _workflow_response(dict(final_snapshot.values))
            set_workflow_result(span, response)
            yield _terminal_event(response)


def _thread_config(request: WorkflowRequest) -> dict[str, object]:
    return {"configurable": {"thread_id": str(request.request_id)}}


def _workflow_response(state: WorkflowState) -> WorkflowResponse:
    request = WorkflowRequest.model_validate(
        {name: state.get(name) for name in WorkflowRequest.model_fields}
    )
    status = ContractStatus(state["workflow_status"])
    final_brief = (
        WriterResponse.model_validate(state["final_brief"])
        if state.get("final_brief") is not None
        else None
    )
    error = ContractError.model_validate(state["error"]) if state.get("error") else None
    return WorkflowResponse(
        **copy_request_metadata(request),
        status=status,
        warnings=state.get("warnings", []),
        error=error,
        final_brief=final_brief,
    )


def _event(event_type: str, request: WorkflowRequest) -> dict[str, object]:
    return {
        "version": "v1",
        "type": event_type,
        "request_id": str(request.request_id),
        "trace_id": request.trace_id,
        "data": {},
    }


def _terminal_event(response: WorkflowResponse) -> dict[str, object]:
    return {
        "version": "v1",
        "type": "workflow.completed"
        if response.status is not ContractStatus.FAILED
        else "workflow.failed",
        "request_id": str(response.request_id),
        "trace_id": response.trace_id,
        "data": {"response": response.model_dump(mode="json")},
    }
