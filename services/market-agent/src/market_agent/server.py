import asyncio

import grpc
from distributed_agent_contracts.market.v1 import market_pb2, market_pb2_grpc
from grpc_health.v1 import health, health_pb2, health_pb2_grpc

from market_agent.errors import (
    InvalidOutputError,
    ProviderConfigurationError,
    ProviderUnavailableError,
)
from market_agent.langsmith_tracing import trace_operation
from market_agent.runner import MarketAgentRunner
from market_agent.settings import DemoSettings, FailureMode


class MarketAgentService(market_pb2_grpc.MarketAgentServicer):
    def __init__(
        self,
        runner: MarketAgentRunner | None = None,
        settings: DemoSettings | None = None,
    ) -> None:
        self._settings = settings or DemoSettings.from_environment()
        self._runner = runner or MarketAgentRunner(settings=self._settings)

    async def AnalyzeMarket(self, request, context):
        metadata = request.metadata
        parent_headers = dict(context.invocation_metadata())
        with trace_operation(
            "market-agent.analyze",
            metadata={
                "service": "market-agent",
                "request_id": metadata.request_id,
                "business_trace_id": metadata.trace_id,
                "attempt": metadata.attempt,
                "query_length": len(request.query),
            },
            parent_headers=parent_headers,
            inputs={"request": {"metadata": _metadata_dict(metadata), "query": request.query}},
        ) as run:
            if (
                metadata.contract_version != "v1"
                or not metadata.request_id
                or not metadata.trace_id
                or metadata.attempt < 1
                or not request.query.strip()
            ):
                await context.abort(grpc.StatusCode.INVALID_ARGUMENT, "invalid market request")

            await self._settings.apply_delay()
            if self._settings.failure_mode is FailureMode.TRANSIENT_ERROR:
                await context.abort(grpc.StatusCode.UNAVAILABLE, "injected transient failure")
            if self._settings.failure_mode is FailureMode.INVALID_RESPONSE:
                return market_pb2.MarketResponse(
                    metadata=metadata,
                    status=market_pb2.RESPONSE_STATUS_UNSPECIFIED,
                )

            try:
                result = await self._runner.analyze(request.query, metadata.request_id)
            except ProviderConfigurationError:
                response = _failure_response(
                    metadata,
                    market_pb2.ERROR_CODE_INTERNAL_ERROR,
                    "Market Agent provider configuration is invalid",
                    retryable=False,
                )
                return _end_run(run, response)
            except ProviderUnavailableError:
                response = _failure_response(
                    metadata,
                    market_pb2.ERROR_CODE_UPSTREAM_UNAVAILABLE,
                    "Market Agent LLM provider is unavailable",
                    retryable=True,
                )
                return _end_run(run, response)
            except InvalidOutputError:
                response = _failure_response(
                    metadata,
                    market_pb2.ERROR_CODE_UPSTREAM_INVALID_RESPONSE,
                    "Market Agent returned invalid structured output",
                    retryable=False,
                )
                return _end_run(run, response)
            signals = [
                market_pb2.MarketSignal(
                    topic=signal["topic"],
                    observation=signal["observation"],
                    source=market_pb2.Source(**signal["source"]),
                )
                for signal in result.market_signals
            ]
            response = market_pb2.MarketResponse(
                metadata=metadata,
                status=market_pb2.RESPONSE_STATUS_SUCCESS,
                market_signals=signals,
                competitors=result.competitors,
            )
            return _end_run(run, response)


async def create_server(
    address: str = "[::]:50051",
    settings: DemoSettings | None = None,
) -> tuple[grpc.aio.Server, int]:
    server = grpc.aio.server()
    market_pb2_grpc.add_MarketAgentServicer_to_server(
        MarketAgentService(settings=settings),
        server,
    )

    health_service = health.aio.HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_service, server)
    await health_service.set("", health_pb2.HealthCheckResponse.SERVING)
    await health_service.set(
        market_pb2.DESCRIPTOR.services_by_name["MarketAgent"].full_name,
        health_pb2.HealthCheckResponse.SERVING,
    )

    port = server.add_insecure_port(address)
    return server, port


async def serve() -> None:
    server, _ = await create_server()
    await server.start()
    await server.wait_for_termination()


def _metadata_dict(metadata) -> dict[str, object]:
    return {
        "contract_version": metadata.contract_version,
        "request_id": metadata.request_id,
        "trace_id": metadata.trace_id,
        "attempt": metadata.attempt,
        "deadline_unix_ms": metadata.deadline_unix_ms,
    }


def _end_run(run, response):
    if run is not None:
        run.end(outputs={"response": _response_output(response)})
    return response


def _response_output(response) -> dict[str, object]:
    return {
        "metadata": _metadata_dict(response.metadata),
        "status": market_pb2.ResponseStatus.Name(response.status),
        "market_signals": [
            {
                "topic": signal.topic,
                "observation": signal.observation,
                "source": {
                    "title": signal.source.title,
                    "url": signal.source.url,
                    "publisher": signal.source.publisher,
                    "published_at_unix_ms": signal.source.published_at_unix_ms,
                    "retrieved_at_unix_ms": signal.source.retrieved_at_unix_ms,
                    "content": signal.source.content,
                },
            }
            for signal in response.market_signals
        ],
        "competitors": list(response.competitors),
        "warnings": list(response.warnings),
        "error": (
            {
                "code": market_pb2.ErrorCode.Name(response.error.code),
                "message": response.error.message,
                "retryable": response.error.retryable,
            }
            if response.HasField("error")
            else None
        ),
    }


def _failure_response(metadata, code: int, message: str, *, retryable: bool):
    return market_pb2.MarketResponse(
        metadata=metadata,
        status=market_pb2.RESPONSE_STATUS_FAILED,
        error=market_pb2.ContractError(code=code, message=message, retryable=retryable),
    )


if __name__ == "__main__":
    asyncio.run(serve())
