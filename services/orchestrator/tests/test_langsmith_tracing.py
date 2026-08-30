from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from distributed_agent_contracts import ResearcherInput
from distributed_agent_contracts.market.v1 import market_pb2
from orchestrator.clients import http as http_client_module
from orchestrator.clients import market as market_client_module
from orchestrator.clients import researcher as researcher_client_module
from orchestrator.clients.market import MarketAgentRequest, MarketClient
from orchestrator.clients.researcher import ResearcherClient
from orchestrator.langsmith_tracing import redact, tracing_enabled


def _metadata() -> dict[str, object]:
    return {
        "contract_version": "v1",
        "request_id": uuid4(),
        "trace_id": "trace-langsmith",
        "attempt": 1,
    }


def test_redaction_removes_credentials_without_hiding_trace_payloads() -> None:
    payload = {
        "request_id": "request-1",
        "prompt": "secret user input",
        "authorization": "Bearer private-token",
        "nested": {
            "api_key": "sk-private",
            "status": "success",
            "usage_metadata": {
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
            },
        },
    }

    assert redact(payload) == {
        "request_id": "request-1",
        "prompt": "secret user input",
        "authorization": "[REDACTED]",
        "nested": {
            "api_key": "[REDACTED]",
            "status": "success",
            "usage_metadata": {
                "input_tokens": 10,
                "output_tokens": 20,
                "total_tokens": 30,
            },
        },
    }


def test_tracing_is_inactive_until_an_api_key_is_configured(monkeypatch) -> None:
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.delenv("LANGSMITH_API_KEY", raising=False)

    assert tracing_enabled() is False


@pytest.mark.anyio
async def test_remotegraph_client_forwards_langsmith_headers(monkeypatch) -> None:
    headers = {"langsmith-trace": "trace-header", "baggage": "langsmith-project=demo"}
    monkeypatch.setattr(researcher_client_module, "current_headers", lambda: headers)
    request = ResearcherInput(**_metadata(), query="AI coding assistants")
    captured: dict[str, object] = {}

    class FakeGraph:
        async def ainvoke(self, payload, **kwargs):
            captured.update(kwargs)
            return {
                **request.model_dump(mode="json", exclude={"query"}),
                "status": "success",
                "findings": [],
                "warnings": [],
                "error": None,
            }

    client = ResearcherClient("http://example.invalid")
    client._graph = FakeGraph()

    await client.analyze(request)

    assert captured["headers"] == headers
    assert captured["config"] == {"configurable": headers}


def test_remotegraph_enables_langsmith_distributed_tracing() -> None:
    client = ResearcherClient("http://example.invalid")

    assert client._graph.distributed_tracing is True


@pytest.mark.anyio
async def test_http_and_grpc_clients_forward_langsmith_headers(monkeypatch) -> None:
    headers = {"langsmith-trace": "trace-header", "baggage": "langsmith-project=demo"}
    monkeypatch.setattr(http_client_module, "current_headers", lambda: headers)
    monkeypatch.setattr(market_client_module, "current_headers", lambda: headers)
    captured_http: dict[str, object] = {}
    captured_grpc: dict[str, object] = {}

    class FakeHttpClient:
        async def post(self, url, **kwargs):
            captured_http.update(kwargs)
            return SimpleNamespace()

    await http_client_module._post(FakeHttpClient(), "http://example.invalid", {"ok": True})

    request = MarketAgentRequest(**_metadata(), query="AI coding assistants")
    now_ms = int(datetime.now(UTC).timestamp() * 1_000)

    class FakeStub:
        async def AnalyzeMarket(self, proto_request, **kwargs):
            captured_grpc.update(kwargs)
            return market_pb2.MarketResponse(
                metadata=proto_request.metadata,
                status=market_pb2.RESPONSE_STATUS_SUCCESS,
                market_signals=[
                    market_pb2.MarketSignal(
                        topic="Integration",
                        observation="Buyers value integration.",
                        source=market_pb2.Source(
                            title="Source",
                            url="https://example.com/source",
                            publisher="Example",
                            retrieved_at_unix_ms=now_ms,
                        ),
                    )
                ],
            )

    client = object.__new__(MarketClient)
    client._stub = FakeStub()

    await client.analyze(request)

    assert captured_http["headers"] == headers
    assert captured_grpc["metadata"] == tuple(headers.items())
