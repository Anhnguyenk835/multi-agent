from datetime import UTC, datetime

import grpc
from distributed_agent_contracts import (
    ContractStatus,
    ErrorCode,
    MarketSignal,
    RequestMetadata,
    Source,
)
from distributed_agent_contracts.market.v1 import market_pb2, market_pb2_grpc
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from orchestrator.errors import AgentCallError
from orchestrator.langsmith_tracing import current_headers


class MarketAgentRequest(RequestMetadata):
    query: str = Field(min_length=1, max_length=2_000)


class MarketAgentOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ContractStatus
    market_signals: list[MarketSignal]
    competitors: list[str]
    warnings: list[str]


class MarketClient:
    def __init__(self, channel: grpc.aio.Channel) -> None:
        self._stub = market_pb2_grpc.MarketAgentStub(channel)

    async def analyze(self, request: MarketAgentRequest) -> MarketAgentOutput:
        proto_request = market_pb2.MarketRequest(
            metadata=market_pb2.RequestMetadata(
                contract_version=request.contract_version,
                request_id=str(request.request_id),
                trace_id=request.trace_id,
                attempt=request.attempt,
                deadline_unix_ms=_datetime_to_unix_ms(request.deadline_at),
            ),
            query=request.query,
        )
        try:
            response = await self._stub.AnalyzeMarket(
                proto_request, metadata=tuple(current_headers().items())
            )
        except grpc.aio.AioRpcError as error:
            raise _grpc_error(error) from error

        if (
            response.metadata.request_id != str(request.request_id)
            or response.metadata.trace_id != request.trace_id
        ):
            raise AgentCallError(
                ErrorCode.UPSTREAM_INVALID_RESPONSE,
                "Market Agent returned mismatched correlation metadata",
                retryable=False,
            )

        if response.status == market_pb2.RESPONSE_STATUS_FAILED:
            code = _proto_error_code(response.error.code)
            raise AgentCallError(
                code,
                response.error.message or "Market Agent failed",
                retryable=response.error.retryable,
            )
        if response.status not in {
            market_pb2.RESPONSE_STATUS_SUCCESS,
            market_pb2.RESPONSE_STATUS_DEGRADED,
        }:
            raise AgentCallError(
                ErrorCode.UPSTREAM_INVALID_RESPONSE,
                "Market Agent returned an invalid status",
                retryable=False,
            )

        try:
            return MarketAgentOutput(
                status=(
                    ContractStatus.SUCCESS
                    if response.status == market_pb2.RESPONSE_STATUS_SUCCESS
                    else ContractStatus.DEGRADED
                ),
                market_signals=[_market_signal(signal) for signal in response.market_signals],
                competitors=list(response.competitors),
                warnings=list(response.warnings),
            )
        except ValidationError as error:
            raise AgentCallError(
                ErrorCode.UPSTREAM_INVALID_RESPONSE,
                "Market Agent returned an invalid response",
                retryable=False,
            ) from error


def _market_signal(signal: market_pb2.MarketSignal) -> MarketSignal:
    return MarketSignal(
        topic=signal.topic,
        observation=signal.observation,
        source=Source(
            title=signal.source.title,
            url=signal.source.url,
            publisher=signal.source.publisher,
            published_at=_unix_ms_to_datetime(signal.source.published_at_unix_ms),
            retrieved_at=_unix_ms_to_datetime(signal.source.retrieved_at_unix_ms),
            content=signal.source.content or None,
        ),
    )


def _grpc_error(error: grpc.aio.AioRpcError) -> AgentCallError:
    if error.code() is grpc.StatusCode.DEADLINE_EXCEEDED:
        return AgentCallError(
            ErrorCode.DEADLINE_EXCEEDED,
            "Market Agent deadline exceeded",
            retryable=True,
        )
    if error.code() is grpc.StatusCode.RESOURCE_EXHAUSTED:
        return AgentCallError(
            ErrorCode.RATE_LIMITED,
            "Market Agent rate limited the request",
            retryable=True,
        )
    if error.code() is grpc.StatusCode.UNAUTHENTICATED:
        return AgentCallError(
            ErrorCode.UNAUTHORIZED,
            "Market Agent rejected authentication",
            retryable=False,
        )
    if error.code() is grpc.StatusCode.PERMISSION_DENIED:
        return AgentCallError(
            ErrorCode.FORBIDDEN,
            "Market Agent denied the request",
            retryable=False,
        )
    if error.code() is grpc.StatusCode.INVALID_ARGUMENT:
        return AgentCallError(
            ErrorCode.VALIDATION_ERROR,
            "Market Agent rejected the request contract",
            retryable=False,
        )
    retryable = error.code() in {grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.ABORTED}
    return AgentCallError(
        ErrorCode.UPSTREAM_UNAVAILABLE,
        f"Market Agent gRPC call failed: {error.code().name}",
        retryable=retryable,
    )


def _proto_error_code(value: int) -> ErrorCode:
    name = market_pb2.ErrorCode.Name(value).removeprefix("ERROR_CODE_")
    try:
        return ErrorCode(name)
    except ValueError:
        return ErrorCode.INTERNAL_ERROR


def _datetime_to_unix_ms(value: datetime | None) -> int:
    return 0 if value is None else int(value.timestamp() * 1_000)


def _unix_ms_to_datetime(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1_000, tz=UTC)
