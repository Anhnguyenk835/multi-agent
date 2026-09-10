from datetime import UTC, datetime

import grpc
from distributed_agent_contracts import (
    CompetitiveSignal,
    ContractStatus,
    ErrorCode,
    RequestMetadata,
    Source,
    remaining_seconds,
)
from distributed_agent_contracts.competitor.v1 import competitor_pb2, competitor_pb2_grpc
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from orchestrator.errors import AgentCallError


class CompetitorAnalystRequest(RequestMetadata):
    query: str = Field(min_length=1, max_length=2_000)


class CompetitorAnalystOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ContractStatus
    competitive_signals: list[CompetitiveSignal]
    competitors: list[str]
    warnings: list[str]


class CompetitorAnalystClient:
    def __init__(self, channel: grpc.aio.Channel) -> None:
        self._stub = competitor_pb2_grpc.CompetitorAnalystStub(channel)

    async def analyze(self, request: CompetitorAnalystRequest) -> CompetitorAnalystOutput:
        proto_request = competitor_pb2.CompetitorAnalysisRequest(
            metadata=competitor_pb2.RequestMetadata(
                contract_version=request.contract_version,
                request_id=str(request.request_id),
                trace_id=request.trace_id,
                attempt=request.attempt,
                deadline_unix_ms=_datetime_to_unix_ms(request.deadline_at),
            ),
            query=request.query,
        )
        timeout = remaining_seconds(request.deadline_at)
        if timeout is not None and timeout <= 0:
            raise AgentCallError(
                ErrorCode.DEADLINE_EXCEEDED,
                "Competitor Analyst deadline exceeded before the gRPC call",
                retryable=True,
            )
        try:
            response = await self._stub.AnalyzeCompetitors(proto_request, timeout=timeout)
        except grpc.aio.AioRpcError as error:
            raise _grpc_error(error) from error

        if (
            response.metadata.request_id != str(request.request_id)
            or response.metadata.trace_id != request.trace_id
        ):
            raise AgentCallError(
                ErrorCode.UPSTREAM_INVALID_RESPONSE,
                "Competitor Analyst returned mismatched correlation metadata",
                retryable=False,
            )

        if response.status == competitor_pb2.RESPONSE_STATUS_FAILED:
            code = _proto_error_code(response.error.code)
            raise AgentCallError(
                code,
                response.error.message or "Competitor Analyst failed",
                retryable=response.error.retryable,
            )
        if response.status not in {
            competitor_pb2.RESPONSE_STATUS_SUCCESS,
            competitor_pb2.RESPONSE_STATUS_DEGRADED,
        }:
            raise AgentCallError(
                ErrorCode.UPSTREAM_INVALID_RESPONSE,
                "Competitor Analyst returned an invalid status",
                retryable=False,
            )

        try:
            return CompetitorAnalystOutput(
                status=(
                    ContractStatus.SUCCESS
                    if response.status == competitor_pb2.RESPONSE_STATUS_SUCCESS
                    else ContractStatus.DEGRADED
                ),
                competitive_signals=[
                    _competitive_signal(signal) for signal in response.competitive_signals
                ],
                competitors=list(response.competitors),
                warnings=list(response.warnings),
            )
        except ValidationError as error:
            raise AgentCallError(
                ErrorCode.UPSTREAM_INVALID_RESPONSE,
                "Competitor Analyst returned an invalid response",
                retryable=False,
            ) from error


def _competitive_signal(signal: competitor_pb2.CompetitiveSignal) -> CompetitiveSignal:
    return CompetitiveSignal(
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
            "Competitor Analyst deadline exceeded",
            retryable=True,
        )
    if error.code() is grpc.StatusCode.RESOURCE_EXHAUSTED:
        return AgentCallError(
            ErrorCode.RATE_LIMITED,
            "Competitor Analyst rate limited the request",
            retryable=True,
        )
    if error.code() is grpc.StatusCode.UNAUTHENTICATED:
        return AgentCallError(
            ErrorCode.UNAUTHORIZED,
            "Competitor Analyst rejected authentication",
            retryable=False,
        )
    if error.code() is grpc.StatusCode.PERMISSION_DENIED:
        return AgentCallError(
            ErrorCode.FORBIDDEN,
            "Competitor Analyst denied the request",
            retryable=False,
        )
    if error.code() is grpc.StatusCode.INVALID_ARGUMENT:
        return AgentCallError(
            ErrorCode.VALIDATION_ERROR,
            "Competitor Analyst rejected the request contract",
            retryable=False,
        )
    retryable = error.code() in {grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.ABORTED}
    return AgentCallError(
        ErrorCode.UPSTREAM_UNAVAILABLE,
        f"Competitor Analyst gRPC call failed: {error.code().name}",
        retryable=retryable,
    )


def _proto_error_code(value: int) -> ErrorCode:
    name = competitor_pb2.ErrorCode.Name(value).removeprefix("ERROR_CODE_")
    try:
        return ErrorCode(name)
    except ValueError:
        return ErrorCode.INTERNAL_ERROR


def _datetime_to_unix_ms(value: datetime | None) -> int:
    return 0 if value is None else int(value.timestamp() * 1_000)


def _unix_ms_to_datetime(value: int) -> datetime:
    return datetime.fromtimestamp(value / 1_000, tz=UTC)
