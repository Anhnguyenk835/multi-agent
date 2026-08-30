from uuid import uuid4

from distributed_agent_contracts import (
    ContractError,
    ContractStatus,
    ErrorCode,
    WorkflowResponse,
    copy_request_metadata,
)
from fastapi.testclient import TestClient
from orchestrator.main import create_app


class StubWorkflowService:
    def __init__(self, status: ContractStatus) -> None:
        self.status = status

    async def run(self, request):
        if self.status is ContractStatus.FAILED:
            return WorkflowResponse(
                **copy_request_metadata(request),
                status=self.status,
                error=ContractError(
                    code=ErrorCode.UPSTREAM_UNAVAILABLE,
                    message="terminal failure",
                    retryable=False,
                ),
            )
        return WorkflowResponse(
            **copy_request_metadata(request),
            status=self.status,
            warnings=["degraded"] if self.status is ContractStatus.DEGRADED else [],
            final_brief={
                **copy_request_metadata(request),
                "status": "success",
                "content": "# Executive brief\n\nSummary",
            },
        )

    async def stream(self, request):
        yield {
            "version": "v1",
            "type": "workflow.started",
            "request_id": str(request.request_id),
            "trace_id": request.trace_id,
            "data": {},
        }
        response = await self.run(request)
        yield {
            "version": "v1",
            "type": "workflow.completed",
            "request_id": str(request.request_id),
            "trace_id": request.trace_id,
            "data": {"response": response.model_dump(mode="json")},
        }


def payload() -> dict[str, object]:
    return {
        "request_id": str(uuid4()),
        "trace_id": "phase-3-api",
        "query": "AI coding assistants",
    }


def test_workflow_endpoint_returns_degraded_response() -> None:
    app = create_app(workflow_service=StubWorkflowService(ContractStatus.DEGRADED))
    with TestClient(app) as client:
        response = client.post("/workflows", json=payload())

    assert response.status_code == 200
    assert response.json()["status"] == "degraded"


def test_workflow_endpoint_maps_terminal_failure_to_bad_gateway() -> None:
    app = create_app(workflow_service=StubWorkflowService(ContractStatus.FAILED))
    with TestClient(app) as client:
        response = client.post("/workflows", json=payload())

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "UPSTREAM_UNAVAILABLE"


def test_workflow_stream_endpoint_returns_sse_terminal_response() -> None:
    app = create_app(workflow_service=StubWorkflowService(ContractStatus.SUCCESS))
    with TestClient(app) as client:
        response = client.post("/workflows/stream", json=payload())

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: workflow.started" in response.text
    assert "event: workflow.completed" in response.text
