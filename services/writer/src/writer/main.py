import asyncio
import json

from distributed_agent_contracts import (
    ContractError,
    ContractStatus,
    ErrorCode,
    WriterRequest,
    WriterResponse,
    copy_request_metadata,
    remaining_seconds,
)
from fastapi import FastAPI
from fastapi.responses import JSONResponse, StreamingResponse

from writer.brief import (
    stream_brief_live,
    write_brief_live,
)
from writer.errors import InvalidOutputError, ProviderConfigurationError, ProviderUnavailableError
from writer.settings import DemoSettings, FailureMode
from writer.telemetry import (
    operation_span,
    request_context,
)


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
    async def write(request: WriterRequest):
        try:
            with (
                request_context(request),
                operation_span(
                    "writer.write",
                    observation_type="agent",
                    attributes={"app.agent": "writer", "app.attempt": request.attempt},
                ),
            ):
                remaining = remaining_seconds(request.deadline_at)
                if remaining is None:
                    return await _write(request, runtime_settings)
                if remaining <= 0:
                    raise TimeoutError
                async with asyncio.timeout(remaining):
                    return await _write(request, runtime_settings)
        except TimeoutError:
            failure = _failure_response(
                request,
                ErrorCode.DEADLINE_EXCEEDED,
                "Writer deadline exceeded",
                retryable=True,
            )
            return _respond(failure.model_dump(mode="json"), 504)
        except ProviderConfigurationError:
            failure = _failure_response(
                request,
                ErrorCode.INTERNAL_ERROR,
                "Writer provider configuration is invalid",
                retryable=False,
            )
            return _respond(failure.model_dump(mode="json"), 500)
        except ProviderUnavailableError:
            failure = _failure_response(
                request,
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Writer LLM provider is unavailable",
                retryable=True,
            )
            return _respond(failure.model_dump(mode="json"), 503)
        except InvalidOutputError:
            failure = _failure_response(
                request,
                ErrorCode.UPSTREAM_INVALID_RESPONSE,
                "Writer LLM returned invalid structured output",
                retryable=False,
            )
            return _respond(failure.model_dump(mode="json"), 502)

    @app.post("/write/stream")
    async def stream_write(request: WriterRequest):
        async def events():
            try:
                with (
                    request_context(request),
                    operation_span(
                        "writer.write_stream",
                        observation_type="agent",
                        attributes={"app.agent": "writer", "app.attempt": request.attempt},
                    ),
                ):
                    remaining = remaining_seconds(request.deadline_at)
                    if remaining is None:
                        async for event in _stream(request, runtime_settings):
                            yield event
                    else:
                        if remaining <= 0:
                            raise TimeoutError
                        async with asyncio.timeout(remaining):
                            async for event in _stream(request, runtime_settings):
                                yield event
            except (
                TimeoutError,
                ProviderConfigurationError,
                ProviderUnavailableError,
                InvalidOutputError,
            ) as error:
                output = _stream_failure_output(error)
                yield _sse("writer.failed", {"error": output["error"]})

        return StreamingResponse(events(), media_type="text/event-stream")

    return app


async def _write(request: WriterRequest, settings: DemoSettings):
    await settings.apply_delay()
    if settings.failure_mode is FailureMode.TRANSIENT_ERROR:
        failure = WriterResponse(
            **copy_request_metadata(request),
            status=ContractStatus.FAILED,
            error=ContractError(
                code=ErrorCode.UPSTREAM_UNAVAILABLE,
                message="injected transient Writer failure",
                retryable=True,
            ),
        )
        return _respond(failure.model_dump(mode="json"), 503)
    if settings.failure_mode is FailureMode.INVALID_RESPONSE:
        return _respond({"status": "invalid"}, 200)
    return await write_brief_live(request, settings.ai)


async def _stream(request: WriterRequest, settings: DemoSettings):
    await settings.apply_delay()
    if settings.failure_mode is FailureMode.TRANSIENT_ERROR:
        yield _sse(
            "writer.failed",
            {"error": {"code": "UPSTREAM_UNAVAILABLE", "message": "Writer unavailable"}},
        )
        return
    async for event in stream_brief_live(request, settings.ai):
        yield _sse(event["type"], event["data"])


app = create_app()


def _sse(event_type: str, data: dict[str, object]) -> str:
    return f"event: {event_type}\ndata: {json.dumps(data, default=str, separators=(',', ':'))}\n\n"


def _respond(payload: dict[str, object], status_code: int) -> JSONResponse:
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
    if isinstance(error, TimeoutError):
        code = ErrorCode.DEADLINE_EXCEEDED
        message = "Writer deadline exceeded"
        retryable = True
    elif isinstance(error, ProviderConfigurationError):
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
