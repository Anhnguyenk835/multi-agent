from datetime import UTC, datetime, timedelta
from uuid import uuid4

import grpc
import pytest
from competitor_analyst.models import CompetitorAnalysis, CompetitorProfile, EvidenceSource
from competitor_analyst.runner import CompetitorAnalysisResult
from competitor_analyst.server import create_server
from competitor_analyst.settings import DemoSettings, FailureMode
from distributed_agent_contracts.competitor.v1 import competitor_pb2, competitor_pb2_grpc


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def valid_request() -> competitor_pb2.CompetitorAnalysisRequest:
    return competitor_pb2.CompetitorAnalysisRequest(
        metadata=competitor_pb2.RequestMetadata(
            contract_version="v1",
            request_id=str(uuid4()),
            trace_id="trace-phase-2",
            attempt=1,
        ),
        query="habit tracking apps",
    )


@pytest.mark.anyio
async def test_transient_failure_maps_to_grpc_unavailable() -> None:
    server, port = await create_server(
        "127.0.0.1:0", DemoSettings(failure_mode=FailureMode.TRANSIENT_ERROR)
    )
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            with pytest.raises(grpc.aio.AioRpcError) as error:
                await competitor_pb2_grpc.CompetitorAnalystStub(channel).AnalyzeCompetitors(
                    valid_request()
                )
    finally:
        await server.stop(grace=None)

    assert error.value.code() is grpc.StatusCode.UNAVAILABLE


@pytest.mark.anyio
async def test_expired_deadline_stops_before_agent_run() -> None:
    request = valid_request()
    request.metadata.deadline_unix_ms = int(
        (datetime.now(UTC) - timedelta(seconds=1)).timestamp() * 1000
    )
    server, port = await create_server("127.0.0.1:0", DemoSettings())
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            response = await competitor_pb2_grpc.CompetitorAnalystStub(channel).AnalyzeCompetitors(
                request
            )
    finally:
        await server.stop(grace=None)

    assert response.error.code == competitor_pb2.ERROR_CODE_DEADLINE_EXCEEDED


class _FakeRunner:
    async def analyze(self, query, request_id, *, deadline_at=None):
        source = EvidenceSource(
            id="src_1",
            title="Example",
            url="https://example.com/product",
            publisher="example.com",
            published_at=None,
            retrieved_at=datetime(2026, 1, 2, tzinfo=UTC),
            content="Example is positioned for independent builders.",
        )
        profile = CompetitorProfile(
            id="competitor_1",
            name="Example",
            type="direct",
            positioning={"text": "Built for independent builders", "source_ids": ["src_1"]},
            target_segments=[],
            jobs_to_be_done=[],
            platforms=[{"text": "Web", "source_ids": ["src_1"]}],
            pricing={"model": "freemium", "source_ids": ["src_1"]},
            features=[],
            traction_signals=[],
            review_themes=[],
            distribution_channels=[],
            retention_mechanics=[],
            strengths=[],
            weaknesses=[],
            confidence=62,
            source_ids=["src_1"],
        )
        analysis = CompetitorAnalysis(
            competition_level="moderate",
            market_structure="fragmented",
            tracked_products=1,
            feature_saturation="moderate",
            switching_cost="low",
            competitors=[profile],
            gaps=[],
            coverage=100,
            source_ids=["src_1"],
        )
        return CompetitorAnalysisResult(
            competitive_signals=[
                {
                    "topic": "Example: Positioning",
                    "observation": "Built for independent builders",
                    "source": {
                        "title": source.title,
                        "url": source.url,
                        "publisher": source.publisher,
                        "published_at_unix_ms": 0,
                        "retrieved_at_unix_ms": int(source.retrieved_at.timestamp() * 1000),
                        "content": source.content,
                    },
                }
            ],
            competitors=["Example"],
            analysis=analysis,
            evidence=[source],
            warnings=[],
        )


@pytest.mark.anyio
async def test_response_contains_legacy_and_structured_analysis() -> None:
    server, port = await create_server("127.0.0.1:0", DemoSettings(), runner=_FakeRunner())
    await server.start()
    try:
        async with grpc.aio.insecure_channel(f"127.0.0.1:{port}") as channel:
            response = await competitor_pb2_grpc.CompetitorAnalystStub(channel).AnalyzeCompetitors(
                valid_request()
            )
    finally:
        await server.stop(grace=None)

    assert response.status == competitor_pb2.RESPONSE_STATUS_SUCCESS
    assert response.competitors == ["Example"]
    assert response.competitive_signals[0].source.url == "https://example.com/product"
    assert response.analysis.competitors[0].positioning.source_ids == ["src_1"]
    assert response.evidence[0].id == "src_1"
