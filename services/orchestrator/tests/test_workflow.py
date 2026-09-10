import asyncio
import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from distributed_agent_contracts import (
    AnalysisResponse,
    Citation,
    ContractStatus,
    ErrorCode,
    Finding,
    MarketAnalystOutput,
    Source,
    WorkflowRequest,
    WriterResponse,
    copy_request_metadata,
)
from langgraph.checkpoint.memory import InMemorySaver
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from orchestrator import telemetry
from orchestrator.clients import OrchestratorClients
from orchestrator.clients.competitor_analyst import CompetitorAnalystOutput
from orchestrator.config import AgentPolicy, OrchestratorSettings
from orchestrator.errors import AgentCallError, WorkflowConflictError
from orchestrator.graph import build_workflow_graph
from orchestrator.nodes import WorkflowNodes
from orchestrator.workflow import WorkflowService

SAMPLE_TIME = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


class ParallelGate:
    def __init__(self) -> None:
        self.count = 0
        self.ready = asyncio.Event()

    async def enter(self) -> None:
        self.count += 1
        if self.count == 2:
            self.ready.set()
        await asyncio.wait_for(self.ready.wait(), timeout=0.5)


class FakeMarketAnalyst:
    def __init__(self, error: AgentCallError | None = None, gate: ParallelGate | None = None):
        self.error = error
        self.gate = gate
        self.requests = []

    async def analyze(self, request):
        self.requests.append(request)
        if self.gate:
            await self.gate.enter()
        if self.error:
            raise self.error
        return MarketAnalystOutput(
            **copy_request_metadata(request),
            status=ContractStatus.SUCCESS,
            findings=[
                Finding(
                    title="Research sample",
                    claim="Teams require measurable productivity.",
                    source=_source("market_analysis"),
                )
            ],
        )


class FlakyMarketAnalyst(FakeMarketAnalyst):
    async def analyze(self, request):
        self.requests.append(request)
        if request.attempt < 3:
            raise AgentCallError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "transient",
                retryable=True,
            )
        return MarketAnalystOutput(
            **copy_request_metadata(request),
            status=ContractStatus.SUCCESS,
            findings=[
                Finding(
                    title="Research sample",
                    claim="Teams require measurable productivity.",
                    source=_source("market_analysis"),
                )
            ],
        )


class FakeCompetitorAnalyst:
    def __init__(self, error: AgentCallError | None = None, gate: ParallelGate | None = None):
        self.error = error
        self.gate = gate
        self.requests = []

    async def analyze(self, request):
        self.requests.append(request)
        if self.gate:
            await self.gate.enter()
        if self.error:
            raise self.error
        return CompetitorAnalystOutput(
            status=ContractStatus.SUCCESS,
            competitive_signals=[
                {
                    "topic": "Governance",
                    "observation": "Enterprises require auditability.",
                    "source": _source("competitor_analyst"),
                }
            ],
            competitors=["Example Competitor"],
            warnings=[],
        )


class FakeAnalyst:
    def __init__(self, error: AgentCallError | None = None):
        self.error = error
        self.requests = []

    async def analyze(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return AnalysisResponse(
            **copy_request_metadata(request),
            status=ContractStatus.SUCCESS,
            content="## Insights\n\n- Measure outcomes. [1]",
            citations=[_citation("market_analysis")],
        )


class FakeWriter:
    def __init__(self, error: AgentCallError | None = None):
        self.error = error
        self.requests = []

    async def write(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return WriterResponse(
            **copy_request_metadata(request),
            status=ContractStatus.SUCCESS,
            content="# Executive brief\n\nValidated deterministic summary. [1]",
            citations=request.citations,
        )


def _source(suffix: str) -> Source:
    return Source(
        title=f"{suffix} sample",
        url=f"https://example.com/{suffix}",
        publisher="Demo",
        retrieved_at=SAMPLE_TIME,
    )


def _citation(suffix: str) -> Citation:
    return Citation(title=f"{suffix} sample", url=f"https://example.com/{suffix}", publisher="Demo")


def _failure(message: str = "injected failure") -> AgentCallError:
    return AgentCallError(
        ErrorCode.UPSTREAM_UNAVAILABLE,
        message,
        retryable=False,
    )


def _service(
    *,
    market_analysis_error: AgentCallError | None = None,
    competitor_analysis_error: AgentCallError | None = None,
    analyst_error: AgentCallError | None = None,
    writer_error: AgentCallError | None = None,
    gate: ParallelGate | None = None,
):
    market_analyst = FakeMarketAnalyst(market_analysis_error, gate)
    competitor_analyst = FakeCompetitorAnalyst(competitor_analysis_error, gate)
    analyst = FakeAnalyst(analyst_error)
    writer = FakeWriter(writer_error)
    clients = OrchestratorClients(market_analyst, competitor_analyst, analyst, writer)
    policy = AgentPolicy(timeout_seconds=1, max_attempts=1, backoff_seconds=0)
    settings = OrchestratorSettings(
        market_analyst_policy=policy,
        competitor_analyst_policy=policy,
        analyst_policy=policy,
        writer_policy=policy,
    )
    graph = build_workflow_graph(
        WorkflowNodes(clients, settings),
        InMemorySaver(),
    )
    return WorkflowService(graph), market_analyst, competitor_analyst, analyst, writer


def _request(request_id=None, query: str = "AI coding assistants") -> WorkflowRequest:
    return WorkflowRequest(
        request_id=request_id or uuid4(),
        trace_id="phase-3-test",
        query=query,
    )


@pytest.mark.anyio
async def test_happy_path_fans_out_concurrently_and_is_idempotent() -> None:
    gate = ParallelGate()
    service, market_analyst, competitor_analyst, analyst, writer = _service(gate=gate)
    request = _request()

    first = await service.run(request)
    second = await service.run(request)

    assert first.status is ContractStatus.SUCCESS
    assert second == first
    assert gate.count == 2
    assert len(market_analyst.requests) == len(competitor_analyst.requests) == 1
    assert len(analyst.requests) == len(writer.requests) == 1
    child_requests = [
        market_analyst.requests[0],
        competitor_analyst.requests[0],
        analyst.requests[0],
        writer.requests[0],
    ]
    assert all(request.deadline_at is not None for request in child_requests)
    assert all(
        0 < (request.deadline_at - datetime.now(UTC)).total_seconds() <= 1
        for request in child_requests
    )


@pytest.mark.anyio
async def test_agent_call_span_records_contract_input_and_output(monkeypatch) -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    monkeypatch.setattr(telemetry, "_tracer", provider.get_tracer("test"))
    service, *_ = _service()

    await service.run(_request(query="AI agent market in 2026"))

    competitor_span = next(
        span
        for span in exporter.get_finished_spans()
        if span.name == "agent.call competitor_analyst"
    )
    input_value = json.loads(competitor_span.attributes["langfuse.observation.input"])
    output_value = json.loads(competitor_span.attributes["langfuse.observation.output"])
    assert input_value["query"] == "AI agent market in 2026"
    assert input_value["attempt"] == 1
    assert output_value["status"] == "success"
    assert output_value["competitive_signals"]
    assert "langfuse.trace.input" not in competitor_span.attributes


@pytest.mark.anyio
async def test_stream_emits_safe_agent_progress_sources_and_terminal_response() -> None:
    service, *_ = _service()
    request = _request(query="Find sk-this-must-not-reach-the-ui sources")

    events = [event async for event in service.stream(request)]
    event_types = [event["type"] for event in events]

    assert event_types[0] == "workflow.started"
    assert "agent.started" in event_types
    assert "research.search.started" in event_types
    assert "research.source_found" in event_types
    assert event_types[-1] == "workflow.completed"
    search = next(event for event in events if event["type"] == "research.search.started")
    assert "sk-this" not in search["data"]["query_preview"]
    source = next(event for event in events if event["type"] == "research.source_found")
    assert source["data"]["url"] == "https://example.com/market_analysis"


@pytest.mark.anyio
@pytest.mark.parametrize("failed_branch", ["market_analysis", "competitor_analyst"])
async def test_one_upstream_failure_produces_degraded_brief(failed_branch: str) -> None:
    service, _, _, analyst, writer = _service(
        market_analysis_error=_failure() if failed_branch == "market_analysis" else None,
        competitor_analysis_error=(_failure() if failed_branch == "competitor_analyst" else None),
    )

    response = await service.run(_request())

    assert response.status is ContractStatus.DEGRADED
    assert response.final_brief is not None
    assert response.warnings
    assert len(response.warnings) == len(set(response.warnings))
    assert len(analyst.requests) == len(writer.requests) == 1


@pytest.mark.anyio
async def test_both_upstreams_failed_stops_before_analyst() -> None:
    service, _, _, analyst, writer = _service(
        market_analysis_error=_failure("market analysis failed"),
        competitor_analysis_error=_failure("competitor analysis failed"),
    )

    response = await service.run(_request())

    assert response.status is ContractStatus.FAILED
    assert response.error and response.error.code is ErrorCode.WORKFLOW_ABORTED
    assert analyst.requests == []
    assert writer.requests == []


@pytest.mark.anyio
@pytest.mark.parametrize("terminal_agent", ["analyst", "writer"])
async def test_downstream_failure_is_terminal(terminal_agent: str) -> None:
    service, _, _, analyst, writer = _service(
        analyst_error=_failure() if terminal_agent == "analyst" else None,
        writer_error=_failure() if terminal_agent == "writer" else None,
    )

    response = await service.run(_request())

    assert response.status is ContractStatus.FAILED
    assert response.error and response.error.code is ErrorCode.UPSTREAM_UNAVAILABLE
    assert len(analyst.requests) == 1
    assert len(writer.requests) == (0 if terminal_agent == "analyst" else 1)


@pytest.mark.anyio
async def test_request_id_cannot_be_reused_for_different_query() -> None:
    service, *_ = _service()
    request_id = uuid4()
    await service.run(_request(request_id, "first query"))

    with pytest.raises(WorkflowConflictError):
        await service.run(_request(request_id, "different query"))


@pytest.mark.anyio
async def test_retry_attempt_is_propagated_to_agent_contract() -> None:
    market_analyst = FlakyMarketAnalyst()
    competitor_analyst = FakeCompetitorAnalyst()
    analyst = FakeAnalyst()
    writer = FakeWriter()
    clients = OrchestratorClients(market_analyst, competitor_analyst, analyst, writer)
    retry_policy = AgentPolicy(timeout_seconds=1, max_attempts=3, backoff_seconds=0)
    settings = OrchestratorSettings(
        market_analyst_policy=retry_policy,
        competitor_analyst_policy=AgentPolicy(1, 1, 0),
        analyst_policy=AgentPolicy(1, 1, 0),
        writer_policy=AgentPolicy(1, 1, 0),
    )
    service = WorkflowService(
        build_workflow_graph(WorkflowNodes(clients, settings), InMemorySaver())
    )

    response = await service.run(_request())

    assert response.status is ContractStatus.SUCCESS
    assert [request.attempt for request in market_analyst.requests] == [1, 2, 3]
    assert all(request.deadline_at is not None for request in market_analyst.requests)
    assert all(
        0 < (request.deadline_at - datetime.now(UTC)).total_seconds() <= 1
        for request in market_analyst.requests
    )
