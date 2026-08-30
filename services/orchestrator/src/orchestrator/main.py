import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from distributed_agent_contracts import (
    ContractError,
    ContractStatus,
    ErrorCode,
    WorkflowRequest,
    WorkflowResponse,
    copy_request_metadata,
)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from orchestrator.checkpointer import open_postgres_checkpointer
from orchestrator.clients import OrchestratorClients
from orchestrator.config import OrchestratorSettings
from orchestrator.errors import WorkflowConflictError
from orchestrator.graph import build_workflow_graph
from orchestrator.nodes import WorkflowNodes
from orchestrator.streaming import encode_sse
from orchestrator.workflow import WorkflowService

logger = logging.getLogger("uvicorn.error")


def create_app(
    settings: OrchestratorSettings | None = None,
    workflow_service: WorkflowService | None = None,
) -> FastAPI:
    runtime_settings = settings or OrchestratorSettings.from_environment()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if workflow_service is not None:
            app.state.workflow_service = workflow_service
            app.state.ready = True
            yield
            return

        async with open_postgres_checkpointer(
            runtime_settings.checkpoint_database_url
        ) as checkpointer:
            clients = OrchestratorClients.create(runtime_settings)
            try:
                graph = build_workflow_graph(
                    WorkflowNodes(clients, runtime_settings),
                    checkpointer,
                )
                app.state.workflow_service = WorkflowService(graph)
                app.state.ready = True
                yield
            finally:
                app.state.ready = False
                await clients.aclose()

    app = FastAPI(
        title="Distributed Agents Orchestrator",
        version="1.0.0",
        lifespan=lifespan,
    )
    allowed_origins = [
        origin.strip()
        for origin in os.getenv(
            "ORCHESTRATOR_ALLOWED_ORIGINS", "http://localhost:5173"
        ).split(",")
        if origin.strip()
    ]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["POST", "GET"],
        allow_headers=["Content-Type", "Accept"],
    )
    app.state.ready = False

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"service": "orchestrator", "status": "ok"}

    @app.get("/ready")
    async def ready():
        if not app.state.ready:
            return JSONResponse(status_code=503, content={"status": "not_ready"})
        return {"service": "orchestrator", "status": "ready"}

    @app.post("/workflows", response_model=WorkflowResponse)
    async def run_workflow(request: WorkflowRequest):
        try:
            response = await app.state.workflow_service.run(request)
        except WorkflowConflictError as error:
            conflict = WorkflowResponse(
                **copy_request_metadata(request),
                status=ContractStatus.FAILED,
                error=ContractError(
                    code=ErrorCode.VALIDATION_ERROR,
                    message=str(error),
                    retryable=False,
                ),
            )
            return JSONResponse(status_code=409, content=conflict.model_dump(mode="json"))

        if response.status is ContractStatus.FAILED:
            status_code = (
                504
                if response.error and response.error.code is ErrorCode.DEADLINE_EXCEEDED
                else 502
            )
            return JSONResponse(
                status_code=status_code,
                content=response.model_dump(mode="json"),
            )
        return response

    @app.post("/workflows/stream")
    async def stream_workflow(request: WorkflowRequest):
        async def events():
            try:
                async for event in app.state.workflow_service.stream(request):
                    yield encode_sse(event)
            except WorkflowConflictError as error:
                yield encode_sse(_error_event(request, ErrorCode.VALIDATION_ERROR, str(error)))
            except Exception:
                logger.exception(
                    "workflow_stream_failed request_id=%s trace_id=%s",
                    request.request_id,
                    request.trace_id,
                )
                yield encode_sse(
                    _error_event(
                        request, ErrorCode.INTERNAL_ERROR, "Workflow stream interrupted"
                    )
                )

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return app


app = create_app()


def _error_event(request: WorkflowRequest, code: ErrorCode, message: str) -> dict[str, object]:
    return {
        "version": "v1",
        "type": "workflow.failed",
        "request_id": str(request.request_id),
        "trace_id": request.trace_id,
        "data": {"error": {"code": code, "message": message, "retryable": False}},
    }
