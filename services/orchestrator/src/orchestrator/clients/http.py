import json
from collections.abc import Callable

import httpx
from distributed_agent_contracts import (
    AnalysisRequest,
    AnalysisResponse,
    ContractStatus,
    ErrorCode,
    WriterRequest,
    WriterResponse,
)
from pydantic import ValidationError

from orchestrator.errors import AgentCallError
from orchestrator.langsmith_tracing import current_headers


class AnalystClient:
    def __init__(self, client: httpx.AsyncClient, base_url: str) -> None:
        self._client = client
        self._url = f"{base_url.rstrip('/')}/analyze"

    async def analyze(self, request: AnalysisRequest) -> AnalysisResponse:
        response = await _post(self._client, self._url, request.model_dump(mode="json"))
        try:
            result = AnalysisResponse.model_validate(response.json())
        except (ValidationError, ValueError) as error:
            if response.status_code >= 400:
                raise _http_status_error("Analyst", response.status_code) from error
            raise _invalid_response("Analyst") from error
        _validate_response("Analyst", request, result, response.status_code)
        return result


class WriterClient:
    def __init__(self, client: httpx.AsyncClient, base_url: str) -> None:
        self._client = client
        self._url = f"{base_url.rstrip('/')}/write"
        self._stream_url = f"{base_url.rstrip('/')}/write/stream"

    async def write(self, request: WriterRequest) -> WriterResponse:
        response = await _post(self._client, self._url, request.model_dump(mode="json"))
        try:
            result = WriterResponse.model_validate(response.json())
        except (ValidationError, ValueError) as error:
            if response.status_code >= 400:
                raise _http_status_error("Writer", response.status_code) from error
            raise _invalid_response("Writer") from error
        _validate_response("Writer", request, result, response.status_code)
        return result

    async def write_stream(
        self,
        request: WriterRequest,
        on_event: Callable[[str, dict[str, object]], None],
    ) -> WriterResponse:
        """Consume the Writer's private SSE stream and retain the v1 response checks."""
        try:
            async with self._client.stream(
                "POST",
                self._stream_url,
                json=request.model_dump(mode="json"),
                headers={**current_headers(), "Accept": "text/event-stream"},
            ) as response:
                if response.status_code >= 400:
                    raise _http_status_error("Writer", response.status_code)
                completed: WriterResponse | None = None
                event_type = ""
                async for line in response.aiter_lines():
                    if line.startswith("event: "):
                        event_type = line.removeprefix("event: ")
                    elif line.startswith("data: "):
                        payload = json.loads(line.removeprefix("data: "))
                        if event_type in {"writer.delta", "writer.reset"}:
                            on_event(event_type, payload)
                        elif event_type == "writer.completed":
                            completed = WriterResponse.model_validate(payload["response"])
                        elif event_type == "writer.failed":
                            error = payload.get("error", {})
                            raise AgentCallError(
                                ErrorCode(error.get("code", ErrorCode.UPSTREAM_UNAVAILABLE)),
                                str(error.get("message", "Writer stream failed")),
                                retryable=True,
                            )
                if completed is None:
                    raise _invalid_response("Writer")
        except httpx.TimeoutException as error:
            raise AgentCallError(
                ErrorCode.DEADLINE_EXCEEDED,
                "Writer stream deadline exceeded",
                retryable=True,
            ) from error
        except httpx.TransportError as error:
            raise AgentCallError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "Writer stream transport is unavailable",
                retryable=True,
            ) from error

        _validate_response("Writer", request, completed, 200)
        return completed


async def _post(client: httpx.AsyncClient, url: str, payload: dict[str, object]) -> httpx.Response:
    try:
        return await client.post(url, json=payload, headers=current_headers())
    except httpx.TimeoutException as error:
        raise AgentCallError(
            ErrorCode.DEADLINE_EXCEEDED,
            "HTTP agent deadline exceeded",
            retryable=True,
        ) from error
    except httpx.TransportError as error:
        raise AgentCallError(
            ErrorCode.UPSTREAM_UNAVAILABLE,
            "HTTP agent transport is unavailable",
            retryable=True,
        ) from error


def _validate_response(name, request, response, status_code: int) -> None:
    if response.request_id != request.request_id or response.trace_id != request.trace_id:
        raise _invalid_response(name)
    if response.status is ContractStatus.FAILED:
        assert response.error is not None
        raise AgentCallError(
            response.error.code,
            response.error.message,
            retryable=response.error.retryable,
        )
    if status_code >= 400:
        raise _http_status_error(name, status_code)


def _http_status_error(name: str, status_code: int) -> AgentCallError:
    if status_code == 401:
        code = ErrorCode.UNAUTHORIZED
    elif status_code == 403:
        code = ErrorCode.FORBIDDEN
    elif status_code == 429:
        code = ErrorCode.RATE_LIMITED
    elif status_code == 504:
        code = ErrorCode.DEADLINE_EXCEEDED
    elif status_code >= 500:
        code = ErrorCode.UPSTREAM_UNAVAILABLE
    else:
        code = ErrorCode.VALIDATION_ERROR
    return AgentCallError(
        code,
        f"{name} returned HTTP {status_code}",
        retryable=status_code in {429, 502, 503, 504},
    )


def _invalid_response(name: str) -> AgentCallError:
    return AgentCallError(
        ErrorCode.UPSTREAM_INVALID_RESPONSE,
        f"{name} returned an invalid response",
        retryable=False,
    )
