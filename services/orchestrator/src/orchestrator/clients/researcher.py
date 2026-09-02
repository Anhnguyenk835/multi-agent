from collections.abc import Callable

from distributed_agent_contracts import (
    ContractStatus,
    ErrorCode,
    ResearcherInput,
    ResearcherOutput,
)
from langgraph.pregel.remote import RemoteGraph
from langgraph_sdk.errors import (
    APIConnectionError,
    APIResponseValidationError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import ValidationError

from orchestrator.errors import AgentCallError
from orchestrator.telemetry import inject_context


class ResearcherClient:
    def __init__(self, url: str) -> None:
        self._graph = RemoteGraph("researcher", url=url)

    async def analyze(self, request: ResearcherInput) -> ResearcherOutput:
        headers = inject_context()
        try:
            payload = await self._graph.ainvoke(
                request.model_dump(mode="json"),
                config={"configurable": {"otel_headers": headers}},
                headers=headers,
            )
            response = ResearcherOutput.model_validate(payload)
        except (ValidationError, APIResponseValidationError) as error:
            raise AgentCallError(
                ErrorCode.UPSTREAM_INVALID_RESPONSE,
                "Researcher returned an invalid response",
                retryable=False,
            ) from error
        except Exception as error:
            raise _map_researcher_error(error, streaming=False) from error

        _validate_correlation(request, response)
        if response.status is ContractStatus.FAILED:
            assert response.error is not None
            raise AgentCallError(
                response.error.code,
                response.error.message,
                retryable=response.error.retryable,
            )
        return response

    async def analyze_stream(
        self,
        request: ResearcherInput,
        on_event: Callable[[str, dict[str, object]], None],
    ) -> ResearcherOutput:
        final: ResearcherOutput | None = None
        headers = inject_context()
        try:
            async for chunk in self._graph.astream(
                request.model_dump(mode="json"),
                config={"configurable": {"otel_headers": headers}},
                headers=headers,
                stream_mode=["custom", "values"],
                version="v2",
            ):
                if chunk["type"] == "custom":
                    payload = chunk["data"]
                    if isinstance(payload, dict) and payload.get("type") in {
                        "research.search.started",
                        "research.search.completed",
                    }:
                        data = payload.get("data", {})
                        on_event(str(payload["type"]), data if isinstance(data, dict) else {})
                elif chunk["type"] == "values":
                    try:
                        final = ResearcherOutput.model_validate(chunk["data"])
                    except ValidationError:
                        continue
        except Exception as error:
            raise _map_researcher_error(error, streaming=True) from error

        if final is None:
            raise AgentCallError(
                ErrorCode.UPSTREAM_INVALID_RESPONSE,
                "Researcher stream returned no final response",
                retryable=False,
            )
        _validate_correlation(request, final)
        if final.status is ContractStatus.FAILED:
            assert final.error is not None
            raise AgentCallError(
                final.error.code,
                final.error.message,
                retryable=final.error.retryable,
            )
        return final


def _map_researcher_error(error: Exception, *, streaming: bool) -> AgentCallError:
    suffix = " stream" if streaming else ""
    if isinstance(error, APITimeoutError):
        return AgentCallError(
            ErrorCode.DEADLINE_EXCEEDED, f"Researcher{suffix} deadline exceeded", retryable=True
        )
    if isinstance(error, AuthenticationError):
        return AgentCallError(
            ErrorCode.UNAUTHORIZED,
            f"Researcher{suffix} rejected authentication",
            retryable=False,
        )
    if isinstance(error, PermissionDeniedError):
        return AgentCallError(
            ErrorCode.FORBIDDEN, f"Researcher{suffix} denied the request", retryable=False
        )
    if isinstance(error, RateLimitError):
        return AgentCallError(
            ErrorCode.RATE_LIMITED,
            f"Researcher{suffix} rate limited the request",
            retryable=True,
        )
    if isinstance(error, APIConnectionError):
        return AgentCallError(
            ErrorCode.UPSTREAM_UNAVAILABLE,
            f"Researcher{suffix} transport is unavailable",
            retryable=True,
        )
    if isinstance(error, APIStatusError):
        return AgentCallError(
            ErrorCode.UPSTREAM_UNAVAILABLE,
            f"Researcher{suffix} returned HTTP {error.status_code}",
            retryable=error.status_code >= 500,
        )
    return AgentCallError(
        ErrorCode.INTERNAL_ERROR, f"Unexpected Researcher{suffix} client failure", retryable=False
    )


def _validate_correlation(request: ResearcherInput, response: ResearcherOutput) -> None:
    if response.request_id != request.request_id or response.trace_id != request.trace_id:
        raise AgentCallError(
            ErrorCode.UPSTREAM_INVALID_RESPONSE,
            "Researcher returned mismatched correlation metadata",
            retryable=False,
        )
