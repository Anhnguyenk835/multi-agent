import os
from uuid import uuid4

import grpc
import httpx
import pytest
from distributed_agent_contracts import (
    AnalysisRequest,
    AnalysisResponse,
    ResearcherInput,
    ResearcherOutput,
    WriterRequest,
    WriterResponse,
)
from distributed_agent_contracts.market.v1 import market_pb2, market_pb2_grpc
from langgraph.pregel.remote import RemoteGraph

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.getenv("RUN_INTEGRATION_TESTS") != "1",
        reason="set RUN_INTEGRATION_TESTS=1 with Docker Compose running",
    ),
]


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def metadata() -> dict[str, object]:
    return {
        "contract_version": "v1",
        "request_id": uuid4(),
        "trace_id": "phase-2-compose-smoke",
        "attempt": 1,
    }


@pytest.mark.anyio
async def test_all_phase_2_services_over_real_transports() -> None:
    request_metadata = metadata()
    researcher_request = ResearcherInput(
        **request_metadata,
        query="AI coding assistants",
    )
    researcher_state = await RemoteGraph(
        "researcher",
        url="http://localhost:8001",
    ).ainvoke(researcher_request.model_dump(mode="json"))
    researcher_response = ResearcherOutput.model_validate(researcher_state)

    market_request = market_pb2.MarketRequest(
        metadata=market_pb2.RequestMetadata(
            contract_version="v1",
            request_id=str(request_metadata["request_id"]),
            trace_id=str(request_metadata["trace_id"]),
            attempt=1,
        ),
        query=researcher_request.query,
    )
    async with grpc.aio.insecure_channel("localhost:50051") as channel:
        market_response = await market_pb2_grpc.MarketAgentStub(channel).AnalyzeMarket(
            market_request
        )

    analysis_request = AnalysisRequest(
        **request_metadata,
        query=researcher_request.query,
        research_findings=[finding.model_dump(mode="json") for finding in researcher_response.findings],
        market_signals=[
            {
                "topic": signal.topic,
                "observation": signal.observation,
                "source": {
                    "title": signal.source.title,
                    "url": signal.source.url,
                    "publisher": signal.source.publisher,
                    "published_at": None,
                    "retrieved_at": "2026-01-01T00:00:00Z",
                },
            }
            for signal in market_response.market_signals
        ],
        competitors=list(market_response.competitors),
    )
    async with httpx.AsyncClient() as client:
        analysis_http_response = await client.post(
            "http://localhost:8002/analyze",
            json=analysis_request.model_dump(mode="json"),
        )
        analysis_http_response.raise_for_status()
        analysis_response = AnalysisResponse.model_validate(analysis_http_response.json())

        writer_request = WriterRequest(
            **request_metadata,
            query=researcher_request.query,
            analysis=analysis_response.content,
            citations=analysis_response.citations,
            warnings=analysis_response.warnings,
        )
        writer_http_response = await client.post(
            "http://localhost:8003/write",
            json=writer_request.model_dump(mode="json"),
        )
        writer_http_response.raise_for_status()
        writer_response = WriterResponse.model_validate(writer_http_response.json())

    assert researcher_response.status.value == "success"
    assert market_response.status == market_pb2.RESPONSE_STATUS_SUCCESS
    assert analysis_response.status.value == "success"
    assert writer_response.status.value == "success"
    assert writer_response.trace_id == request_metadata["trace_id"]
