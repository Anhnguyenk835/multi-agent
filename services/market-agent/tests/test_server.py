from uuid import uuid4

import grpc
import pytest
from distributed_agent_contracts.market.v1 import market_pb2, market_pb2_grpc
from google.adk.events import Event
from google.genai import types
from market_agent.server import create_server
from market_agent.settings import AIMode, DemoSettings, FailureMode, MarketAISettings


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def valid_request() -> market_pb2.MarketRequest:
    return market_pb2.MarketRequest(
        metadata=market_pb2.RequestMetadata(
            contract_version="v1",
            request_id=str(uuid4()),
            trace_id="trace-phase-2",
            attempt=1,
        ),
        query="AI coding assistants",
    )


@pytest.mark.anyio
async def test_analyze_market_over_grpc() -> None:
    server, port = await create_server("127.0.0.1:0", DemoSettings())
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            response = await market_pb2_grpc.MarketAgentStub(channel).AnalyzeMarket(valid_request())
    finally:
        await server.stop(grace=None)

    assert response.status == market_pb2.RESPONSE_STATUS_SUCCESS
    assert response.metadata.trace_id == "trace-phase-2"
    assert len(response.market_signals) == 2
    assert response.competitors


@pytest.mark.anyio
async def test_transient_failure_maps_to_grpc_unavailable() -> None:
    settings = DemoSettings(failure_mode=FailureMode.TRANSIENT_ERROR)
    server, port = await create_server("127.0.0.1:0", settings)
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            with pytest.raises(grpc.aio.AioRpcError) as error:
                await market_pb2_grpc.MarketAgentStub(channel).AnalyzeMarket(valid_request())
    finally:
        await server.stop(grace=None)

    assert error.value.code() is grpc.StatusCode.UNAVAILABLE


def _live_settings() -> DemoSettings:
    from market_agent.settings import MarketExaSettings

    return DemoSettings(
        ai=MarketAISettings(ai_mode=AIMode.LIVE, openai_api_key="test-key"),
        exa=MarketExaSettings(exa_api_key="test-exa-key"),
    )


class _FakeRunner:
    """Fakes `google.adk.runners.Runner` at the boundary `runner.py` uses it,
    yielding a scripted tool-call -> tool-response -> final-answer event
    sequence built from real ADK event/content types."""

    def __init__(self, *, agent, **kwargs) -> None:
        self._agent = agent

    async def run_async(self, *, user_id, session_id, new_message):
        yield Event(
            author=self._agent.name,
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            id="fc-1", name="search", args={"query": "AI coding assistants"}
                        )
                    )
                ],
            ),
        )
        yield Event(
            author=self._agent.name,
            content=types.Content(
                role="user",
                parts=[
                    types.Part(
                        function_response=types.FunctionResponse(
                            id="fc-1",
                            name="search",
                            response={
                                "results": [
                                    {
                                        "tag": "fc-1#0",
                                        "title": "Live market source",
                                        "url": "https://example.com/market",
                                        "publisher": "example.com",
                                        "published_at": None,
                                        "retrieved_at": "2026-01-02T00:00:00+00:00",
                                        "content": "Buyers prioritize workflow integration.",
                                    }
                                ]
                            },
                        )
                    )
                ],
            ),
        )
        yield Event(
            author=self._agent.name,
            content=types.Content(
                role="model",
                parts=[
                    types.Part(
                        function_call=types.FunctionCall(
                            id="fc-2",
                            name="submit_market_analysis",
                            args={
                                "response": {
                                    "signals": [
                                        {
                                            "topic": "Integration",
                                            "observation": "Buyers want integration.",
                                            "source_tag": "fc-1#0",
                                        }
                                    ],
                                    "competitors": ["Example Competitor"],
                                }
                            },
                        )
                    )
                ],
            ),
        )


@pytest.mark.anyio
async def test_analyze_market_live_mode_grounds_signals_in_tool_results(monkeypatch) -> None:
    import market_agent.runner as runner_module

    monkeypatch.setattr(runner_module, "Runner", _FakeRunner)

    server, port = await create_server("127.0.0.1:0", _live_settings())
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            response = await market_pb2_grpc.MarketAgentStub(channel).AnalyzeMarket(valid_request())
    finally:
        await server.stop(grace=None)

    assert response.status == market_pb2.RESPONSE_STATUS_SUCCESS
    assert len(response.market_signals) == 1
    assert response.market_signals[0].source.url == "https://example.com/market"
    assert response.competitors == ["Example Competitor"]
