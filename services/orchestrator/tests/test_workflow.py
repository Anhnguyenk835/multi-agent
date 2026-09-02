import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from distributed_agent_contracts import (
    AnalysisResponse,
    Citation,
    ContractStatus,
    ErrorCode,
    Finding,
    ResearcherOutput,
    Source,
    WorkflowRequest,
    WriterResponse,
    copy_request_metadata,
)
from langgraph.checkpoint.memory import InMemorySaver
from orchestrator.clients import OrchestratorClients
from orchestrator.clients.market import MarketAgentOutput
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


class FakeResearcher:
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
        return ResearcherOutput(
            **copy_request_metadata(request),
            status=ContractStatus.SUCCESS,
            findings=[
                Finding(
                    title="Research sample",
                    claim="Teams require measurable productivity.",
                    source=_source("research"),
                )
            ],
        )


class FlakyResearcher(FakeResearcher):
    async def analyze(self, request):
        self.requests.append(request)
        if request.attempt < 3:
            raise AgentCallError(
                ErrorCode.UPSTREAM_UNAVAILABLE,
                "transient",
                retryable=True,
            )
        return ResearcherOutput(
            **copy_request_metadata(request),
            status=ContractStatus.SUCCESS,
            findings=[
                Finding(
                    title="Research sample",
                    claim="Teams require measurable productivity.",
                    source=_source("research"),
                )
            ],
        )


class FakeMarket:
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
        return MarketAgentOutput(
            status=ContractStatus.SUCCESS,
            market_signals=[
                {
                    "topic": "Governance",
                    "observation": "Enterprises require auditability.",
                    "source": _source("market"),
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
            citations=[_citation("research")],
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
    research_error: AgentCallError | None = None,
    market_error: AgentCallError | None = None,
    analyst_error: AgentCallError | None = None,
    writer_error: AgentCallError | None = None,
    gate: ParallelGate | None = None,
):
    researcher = FakeResearcher(research_error, gate)
    market = FakeMarket(market_error, gate)
    analyst = FakeAnalyst(analyst_error)
    writer = FakeWriter(writer_error)
    clients = OrchestratorClients(researcher, market, analyst, writer)
    policy = AgentPolicy(timeout_seconds=1, max_attempts=1, backoff_seconds=0)
    settings = OrchestratorSettings(
        researcher_policy=policy,
        market_policy=policy,
        analyst_policy=policy,
        writer_policy=policy,
    )
    graph = build_workflow_graph(
        WorkflowNodes(clients, settings),
        InMemorySaver(),
    )
    return WorkflowService(graph), researcher, market, analyst, writer


def _request(request_id=None, query: str = "AI coding assistants") -> WorkflowRequest:
    return WorkflowRequest(
        request_id=request_id or uuid4(),
        trace_id="phase-3-test",
        query=query,
    )


@pytest.mark.anyio
async def test_happy_path_fans_out_concurrently_and_is_idempotent() -> None:
    gate = ParallelGate()
    service, researcher, market, analyst, writer = _service(gate=gate)
    request = _request()

    first = await service.run(request)
    second = await service.run(request)

    assert first.status is ContractStatus.SUCCESS
    assert second == first
    assert gate.count == 2
    assert len(researcher.requests) == len(market.requests) == 1
    assert len(analyst.requests) == len(writer.requests) == 1


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
    assert source["data"]["url"] == "https://example.com/research"


@pytest.mark.anyio
@pytest.mark.parametrize("failed_branch", ["research", "market"])
async def test_one_upstream_failure_produces_degraded_brief(failed_branch: str) -> None:
    service, _, _, analyst, writer = _service(
        research_error=_failure() if failed_branch == "research" else None,
        market_error=_failure() if failed_branch == "market" else None,
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
        research_error=_failure("research failed"),
        market_error=_failure("market failed"),
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
    researcher = FlakyResearcher()
    market = FakeMarket()
    analyst = FakeAnalyst()
    writer = FakeWriter()
    clients = OrchestratorClients(researcher, market, analyst, writer)
    retry_policy = AgentPolicy(timeout_seconds=1, max_attempts=3, backoff_seconds=0)
    settings = OrchestratorSettings(
        researcher_policy=retry_policy,
        market_policy=AgentPolicy(1, 1, 0),
        analyst_policy=AgentPolicy(1, 1, 0),
        writer_policy=AgentPolicy(1, 1, 0),
    )
    service = WorkflowService(
        build_workflow_graph(WorkflowNodes(clients, settings), InMemorySaver())
    )

    response = await service.run(_request())

    assert response.status is ContractStatus.SUCCESS
    assert [request.attempt for request in researcher.requests] == [1, 2, 3]
