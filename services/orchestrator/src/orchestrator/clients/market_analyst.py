from collections.abc import Callable

from distributed_agent_contracts import (
    ContractStatus,
    ErrorCode,
    MarketAnalystInput,
    MarketAnalystOutput,
)
from langgraph.pregel.remote import RemoteException, RemoteGraph
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


class MarketAnalystClient:
    def __init__(self, url: str) -> None:
        self._graph = RemoteGraph("market_analyst", url=url)

    async def analyze(self, request: MarketAnalystInput) -> MarketAnalystOutput:
        headers = inject_context()
        try:
            payload = await self._graph.ainvoke(
                request.model_dump(mode="json"),
                config={"configurable": {"otel_headers": headers}},
                headers=headers,
            )
            response = MarketAnalystOutput.model_validate(payload)
        except (ValidationError, APIResponseValidationError) as error:
            raise AgentCallError(
                ErrorCode.UPSTREAM_INVALID_RESPONSE,
                "Market Analyst returned an invalid response",
                retryable=False,
            ) from error
        except Exception as error:
            raise _map_market_analyst_error(error, streaming=False) from error

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
        request: MarketAnalystInput,
        on_event: Callable[[str, dict[str, object]], None],
    ) -> MarketAnalystOutput:
        final: MarketAnalystOutput | None = None
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
                        final = MarketAnalystOutput.model_validate(chunk["data"])
                    except ValidationError:
                        continue
        except Exception as error:
            raise _map_market_analyst_error(error, streaming=True) from error

        if final is None:
            raise AgentCallError(
                ErrorCode.UPSTREAM_INVALID_RESPONSE,
                "Market Analyst stream returned no final response",
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


def _map_market_analyst_error(error: Exception, *, streaming: bool) -> AgentCallError:
    suffix = " stream" if streaming else ""
    if isinstance(error, RemoteException):
        return _map_remote_graph_error(error)
    if isinstance(error, APITimeoutError):
        return AgentCallError(
            ErrorCode.DEADLINE_EXCEEDED,
            f"Market Analyst{suffix} deadline exceeded",
            retryable=True,
        )
    if isinstance(error, AuthenticationError):
        return AgentCallError(
            ErrorCode.UNAUTHORIZED,
            f"Market Analyst{suffix} rejected authentication",
            retryable=False,
        )
    if isinstance(error, PermissionDeniedError):
        return AgentCallError(
            ErrorCode.FORBIDDEN,
            f"Market Analyst{suffix} denied the request",
            retryable=False,
        )
    if isinstance(error, RateLimitError):
        return AgentCallError(
            ErrorCode.RATE_LIMITED,
            f"Market Analyst{suffix} rate limited the request",
            retryable=True,
        )
    if isinstance(error, APIConnectionError):
        return AgentCallError(
            ErrorCode.UPSTREAM_UNAVAILABLE,
            f"Market Analyst{suffix} transport is unavailable",
            retryable=True,
        )
    if isinstance(error, APIStatusError):
        return AgentCallError(
            ErrorCode.UPSTREAM_UNAVAILABLE,
            f"Market Analyst{suffix} returned HTTP {error.status_code}",
            retryable=error.status_code >= 500,
        )
    return AgentCallError(
        ErrorCode.INTERNAL_ERROR,
        f"Unexpected Market Analyst{suffix} client failure",
        retryable=False,
    )


def _map_remote_graph_error(error: RemoteException) -> AgentCallError:
    payload = error.args[0] if error.args else None
    if not isinstance(payload, dict):
        return AgentCallError(
            ErrorCode.INTERNAL_ERROR,
            "Market Analyst remote graph failed without a structured error",
            retryable=False,
        )

    error_type = str(payload.get("error", ""))
    remote_message = str(payload.get("message", ""))
    if error_type == "InvalidOutputError":
        return AgentCallError(
            ErrorCode.UPSTREAM_INVALID_RESPONSE,
            f"Market Analyst model returned invalid structured output: {remote_message}",
            retryable=False,
        )
    if error_type == "ToolCallLimitReachedError":
        return AgentCallError(
            ErrorCode.UPSTREAM_INVALID_RESPONSE,
            f"Market Analyst search limit reached before final output: {remote_message}",
            retryable=False,
        )
    if error_type == "GroundingError":
        return AgentCallError(
            ErrorCode.UPSTREAM_INVALID_RESPONSE,
            f"Market Analyst returned ungrounded output: {remote_message}",
            retryable=False,
        )
    if error_type == "TimeoutError":
        return AgentCallError(
            ErrorCode.DEADLINE_EXCEEDED,
            "Market Analyst remote graph deadline exceeded",
            retryable=True,
        )
    if error_type == "ProviderConfigurationError":
        return AgentCallError(
            ErrorCode.INTERNAL_ERROR,
            "Market Analyst provider configuration is invalid",
            retryable=False,
        )
    return AgentCallError(
        ErrorCode.INTERNAL_ERROR,
        f"Market Analyst remote graph failed ({error_type or 'unknown error'}): {remote_message}",
        retryable=False,
    )


def _validate_correlation(request: MarketAnalystInput, response: MarketAnalystOutput) -> None:
    if response.request_id != request.request_id or response.trace_id != request.trace_id:
        raise AgentCallError(
            ErrorCode.UPSTREAM_INVALID_RESPONSE,
            "Market Analyst returned mismatched correlation metadata",
            retryable=False,
        )
