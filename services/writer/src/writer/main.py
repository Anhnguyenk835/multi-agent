import json

from distributed_agent_contracts import (
    ContractError,
    ContractStatus,
    ErrorCode,
    WriterRequest,
    WriterResponse,
    copy_request_metadata,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from writer.brief import (
    stream_brief_fixture,
    stream_brief_live,
    write_brief_fixture,
    write_brief_live,
)
from writer.errors import InvalidOutputError, ProviderConfigurationError, ProviderUnavailableError
from writer.langsmith_tracing import trace_operation
from writer.settings import AIMode, DemoSettings, FailureMode


def create_app(settings: DemoSettings | None = None) -> FastAPI:
    runtime_settings = settings or DemoSettings.from_environment()
    app = FastAPI(title="Distributed Agents Writer", version="1.0.0")

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"service": "writer", "status": "ok"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        return {"service": "writer", "status": "ready"}

    @app.post("/write", response_model=WriterResponse)
    async def write(request: WriterRequest, http_request: Request):
        with trace_operation(
            "writer.write",
            metadata={
                "service": "writer",
                "request_id": str(request.request_id),
                "business_trace_id": request.trace_id,
                "attempt": request.attempt,
                "citations": len(request.citations),
            },
            parent_headers=http_request.headers,
            inputs={"request": request.model_dump(mode="json")},
        ) as run:
            try:
                await runtime_settings.apply_delay()
                if runtime_settings.failure_mode is FailureMode.TRANSIENT_ERROR:
                    failure = WriterResponse(
                        **copy_request_metadata(request),
                        status=ContractStatus.FAILED,
                        error=ContractError(
                            code=ErrorCode.UPSTREAM_UNAVAILABLE,
                            message="injected transient Writer failure",
                            retryable=True,
                        ),
                    )
                    return _respond(run, failure.model_dump(mode="json"), 503)
                if runtime_settings.failure_mode is FailureMode.INVALID_RESPONSE:
                    return _respond(run, {"status": "invalid"}, 200)

                if runtime_settings.ai.ai_mode is AIMode.FIXTURE:
                    response = write_brief_fixture(request)
                else:
                    response = await write_brief_live(request, runtime_settings.ai)
                if run is not None:
                    run.end(outputs={"response": response.model_dump(mode="json")})
                return response
            except ProviderConfigurationError:
                failure = _failure_response(
                    request,
                    ErrorCode.INTERNAL_ERROR,
                    "Writer provider configuration is invalid",
                    retryable=False,
                )
                return _respond(run, failure.model_dump(mode="json"), 500)
            except ProviderUnavailableError:
                failure = _failure_response(
                    request,
                    ErrorCode.UPSTREAM_UNAVAILABLE,
                    "Writer LLM provider is unavailable",
                    retryable=True,
                )
                return _respond(run, failure.model_dump(mode="json"), 503)
            except InvalidOutputError:
                failure = _failure_response(
                    request,
                    ErrorCode.UPSTREAM_INVALID_RESPONSE,
                    "Writer LLM returned invalid structured output",
                    retryable=False,
                )
                return _respond(run, failure.model_dump(mode="json"), 502)

    @app.post("/write/stream")
    async def stream_write(request: WriterRequest, http_request: Request):
        async def events():
            with trace_operation(
                "writer.write_stream",
                metadata={"service": "writer", "request_id": str(request.request_id)},
                parent_headers=http_request.headers,
                inputs={"request": request.model_dump(mode="json")},
            ) as run:
                try:
                    await runtime_settings.apply_delay()
                    if runtime_settings.failure_mode is FailureMode.TRANSIENT_ERROR:
                        output = {
                            "event": "writer.failed",
                            "error": {
                                "code": "UPSTREAM_UNAVAILABLE",
                                "message": "Writer unavailable",
                            },
                        }
                        if run is not None:
                            run.end(outputs=output)
                        yield _sse("writer.failed", {"error": output["error"]})
                        return
                    stream = (
                        stream_brief_fixture(request)
                        if runtime_settings.ai.ai_mode is AIMode.FIXTURE
                        else stream_brief_live(request, runtime_settings.ai)
                    )
                    final_response: dict[str, object] | None = None
                    event_count = 0
                    async for event in stream:
                        event_count += 1
                        if event["type"] == "writer.completed":
                            response = event.get("data", {}).get("response")
                            if isinstance(response, dict):
                                final_response = response
                        yield _sse(event["type"], event["data"])
                    if run is not None:
                        run.end(outputs={"event_count": event_count, "response": final_response})
                except (
                    ProviderConfigurationError,
                    ProviderUnavailableError,
                    InvalidOutputError,
                ) as error:
                    output = _stream_failure_output(error)
                    if run is not None:
                        run.end(outputs=output)
                    yield _sse("writer.failed", {"error": output["error"]})

        return StreamingResponse(events(), media_type="text/event-stream")

    return app


app = create_app()


def _sse(event_type: str, data: dict[str, object]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, default=str, separators=(',', ':'))}\n\n"


def _respond(run: object, payload: dict[str, object], status_code: int) -> JSONResponse:
    if run is not None:
        run.end(outputs={"response": payload})
    return JSONResponse(status_code=status_code, content=payload)


def _failure_response(
    request: WriterRequest,
    code: ErrorCode,
    message: str,
    *,
    retryable: bool,
) -> WriterResponse:
    return WriterResponse(
        **copy_request_metadata(request),
        status=ContractStatus.FAILED,
        error=ContractError(code=code, message=message, retryable=retryable),
    )


def _stream_failure_output(error: Exception) -> dict[str, object]:
    if isinstance(error, ProviderConfigurationError):
        code = ErrorCode.INTERNAL_ERROR
        message = "Writer provider configuration is invalid"
        retryable = False
    elif isinstance(error, InvalidOutputError):
        code = ErrorCode.UPSTREAM_INVALID_RESPONSE
        message = "Writer LLM returned invalid structured output"
        retryable = False
    else:
        code = ErrorCode.UPSTREAM_UNAVAILABLE
        message = "Writer LLM provider is unavailable"
        retryable = True
    return {
        "event": "writer.failed",
        "error": {"code": code, "message": message, "retryable": retryable},
    }
