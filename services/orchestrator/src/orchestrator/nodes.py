import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from functools import wraps
from inspect import iscoroutinefunction
from time import perf_counter

from distributed_agent_contracts import (
    AnalysisRequest,
    AnalysisResponse,
    ContractError,
    ContractStatus,
    ErrorCode,
    MarketAnalystInput,
    MarketAnalystOutput,
    WriterRequest,
    WriterResponse,
)

from orchestrator.clients import OrchestratorClients
from orchestrator.clients.competitor_analyst import (
    CompetitorAnalystOutput,
    CompetitorAnalystRequest,
)
from orchestrator.config import AgentPolicy, OrchestratorSettings
from orchestrator.errors import AgentCallError
from orchestrator.retry import invoke_with_retry
from orchestrator.state import AgentBranch, WorkflowState
from orchestrator.streaming import emit_event, safe_source_url, sanitize_query
from orchestrator.telemetry import (
    operation_span,
    set_observation_input,
    set_observation_output,
)

logger = logging.getLogger("uvicorn.error")

_UPSTREAM_DEADLINE_GRACE_SECONDS = 5.0


def _traced_node(name: str):
    def decorate(function):
        def attributes(state):
            return {
                "app.workflow_node": name,
                "app.request_id": str(state["request_id"]),
                "app.business_trace_id": state["trace_id"],
            }

        if iscoroutinefunction(function):

            @wraps(function)
            async def async_wrapper(self, state):
                with operation_span(
                    f"orchestrator.node {name}",
                    attributes=attributes(state),
                ):
                    return await function(self, state)

            return async_wrapper

        @wraps(function)
        def sync_wrapper(self, state):
            with operation_span(
                f"orchestrator.node {name}",
                attributes=attributes(state),
            ):
                return function(self, state)

        return sync_wrapper

    return decorate


class WorkflowNodes:
    def __init__(
        self,
        clients: OrchestratorClients,
        settings: OrchestratorSettings,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._clients = clients
        self._settings = settings
        self._sleep = sleep

    @_traced_node("call_market_analyst")
    async def call_market_analyst(self, state: WorkflowState) -> dict[str, object]:
        _emit(state, "agent.started", "market_analyst")
        _emit(
            state,
            "agent.activity",
            "market_analyst",
            {"message": "Searching public sources"},
        )
        analyze_stream = getattr(self._clients.market_analyst, "analyze_stream", None)
        if analyze_stream is None:
            _emit(
                state,
                "research.search.started",
                "market_analyst",
                {"query_preview": sanitize_query(state["query"])},
            )

        def request_factory(attempt: int) -> MarketAnalystInput:
            return MarketAnalystInput(
                **_request_fields(
                    state,
                    attempt,
                    deadline_at=_child_deadline_at(
                        state,
                        self._settings.market_analyst_policy.timeout_seconds,
                    ),
                ),
                query=state["query"],
            )

        async def operation(request: MarketAnalystInput) -> MarketAnalystOutput:
            if analyze_stream is not None:
                return await analyze_stream(
                    request,
                    lambda event_type, data: _emit(
                        state,
                        event_type,
                        "market_analyst",
                        _safe_research_event_data(data),
                    ),
                )
            return await self._clients.market_analyst.analyze(request)

        branch = await self._invoke_branch(
            "market_analyst",
            state,
            self._settings.market_analyst_policy,
            request_factory,
            operation,
        )
        if branch.usable:
            response = MarketAnalystOutput.model_validate(branch.data)
            seen_urls: set[str] = set()
            for finding in response.findings:
                url = safe_source_url(str(finding.source.url))
                if url is None or url in seen_urls:
                    continue
                seen_urls.add(url)
                _emit(
                    state,
                    "research.source_found",
                    "market_analyst",
                    {
                        "title": sanitize_query(finding.source.title),
                        "publisher": sanitize_query(finding.source.publisher),
                        "url": url,
                    },
                )
            _emit(
                state,
                "agent.activity",
                "market_analyst",
                {"message": f"Selected {len(seen_urls)} grounded sources"},
            )
        return {"market_analysis_branch": branch.model_dump(mode="json")}

    @_traced_node("call_competitor_analyst")
    async def call_competitor_analyst(self, state: WorkflowState) -> dict[str, object]:
        _emit(state, "agent.started", "competitor_analyst")
        _emit(
            state,
            "agent.activity",
            "competitor_analyst",
            {"message": "Analyzing competitors"},
        )

        def request_factory(attempt: int) -> CompetitorAnalystRequest:
            return CompetitorAnalystRequest(
                **_request_fields(
                    state,
                    attempt,
                    deadline_at=_child_deadline_at(
                        state,
                        self._settings.competitor_analyst_policy.timeout_seconds,
                    ),
                ),
                query=state["query"],
            )

        async def operation(request: CompetitorAnalystRequest) -> CompetitorAnalystOutput:
            return await self._clients.competitor_analyst.analyze(request)

        branch = await self._invoke_branch(
            "competitor_analyst",
            state,
            self._settings.competitor_analyst_policy,
            request_factory,
            operation,
        )
        return {"competitor_analysis_branch": branch.model_dump(mode="json")}

    @_traced_node("join_market_intelligence")
    def join_market_intelligence(self, state: WorkflowState) -> dict[str, object]:
        market_analysis = AgentBranch.model_validate(state["market_analysis_branch"])
        competitor_analysis = AgentBranch.model_validate(state["competitor_analysis_branch"])
        warnings = [*market_analysis.warnings, *competitor_analysis.warnings]

        for name, branch in (
            ("Market Analyst", market_analysis),
            ("Competitor Analyst", competitor_analysis),
        ):
            if not branch.usable:
                warnings.append(f"{name} unavailable after {branch.attempts} attempt(s).")

        if not market_analysis.usable and not competitor_analysis.usable:
            branch_errors = [
                branch.error for branch in (market_analysis, competitor_analysis) if branch.error
            ]
            if branch_errors and all(
                error.code is ErrorCode.DEADLINE_EXCEEDED for error in branch_errors
            ):
                error = ContractError(
                    code=ErrorCode.DEADLINE_EXCEEDED,
                    message="Workflow deadline exceeded for both upstream branches",
                    retryable=False,
                )
            else:
                error = ContractError(
                    code=ErrorCode.WORKFLOW_ABORTED,
                    message="Market Analyst and Competitor Analyst both failed",
                    retryable=False,
                )
            return {
                "workflow_status": ContractStatus.FAILED,
                "warnings": warnings,
                "error": error.model_dump(mode="json"),
            }

        status = (
            ContractStatus.SUCCESS
            if market_analysis.status is ContractStatus.SUCCESS
            and competitor_analysis.status is ContractStatus.SUCCESS
            else ContractStatus.DEGRADED
        )
        return {"workflow_status": status, "warnings": warnings, "error": None}

    @_traced_node("call_analyst")
    async def call_analyst(self, state: WorkflowState) -> dict[str, object]:
        _emit(state, "agent.started", "analyst")
        _emit(
            state,
            "agent.activity",
            "analyst",
            {"message": "Synthesizing research and market evidence"},
        )
        market_analysis = AgentBranch.model_validate(state["market_analysis_branch"])
        competitor_analysis = AgentBranch.model_validate(state["competitor_analysis_branch"])
        market_analysis_output = (
            MarketAnalystOutput.model_validate(market_analysis.data)
            if market_analysis.usable
            else None
        )
        competitor_analysis_output = (
            CompetitorAnalystOutput.model_validate(competitor_analysis.data)
            if competitor_analysis.usable
            else None
        )

        def request_factory(attempt: int) -> AnalysisRequest:
            return AnalysisRequest(
                **_request_fields(
                    state,
                    attempt,
                    deadline_at=_child_deadline_at(
                        state,
                        self._settings.analyst_policy.timeout_seconds,
                    ),
                ),
                query=state["query"],
                research_findings=(
                    market_analysis_output.findings if market_analysis_output else []
                ),
                competitive_signals=(
                    competitor_analysis_output.competitive_signals
                    if competitor_analysis_output
                    else []
                ),
                competitors=(
                    competitor_analysis_output.competitors if competitor_analysis_output else []
                ),
            )

        async def operation(request: AnalysisRequest) -> AnalysisResponse:
            return await self._clients.analyst.analyze(request)

        branch = await self._invoke_branch(
            "analyst",
            state,
            self._settings.analyst_policy,
            request_factory,
            operation,
        )
        updates: dict[str, object] = {"analysis_branch": branch.model_dump(mode="json")}
        updates.update(_branch_status_updates(branch))
        if branch.usable:
            updates["warnings"] = _deduplicate([*state.get("warnings", []), *branch.warnings])
        return updates

    @_traced_node("call_writer")
    async def call_writer(self, state: WorkflowState) -> dict[str, object]:
        _emit(state, "agent.started", "writer")
        _emit(
            state,
            "agent.activity",
            "writer",
            {"message": "Drafting executive brief"},
        )
        analysis_branch = AgentBranch.model_validate(state["analysis_branch"])
        analysis = AnalysisResponse.model_validate(analysis_branch.data)

        def request_factory(attempt: int) -> WriterRequest:
            return WriterRequest(
                **_request_fields(
                    state,
                    attempt,
                    deadline_at=_child_deadline_at(
                        state,
                        self._settings.writer_policy.timeout_seconds,
                    ),
                ),
                query=state["query"],
                analysis=analysis.content,
                citations=analysis.citations,
                warnings=state.get("warnings", []),
            )

        async def operation(request: WriterRequest) -> WriterResponse:
            write_stream = getattr(self._clients.writer, "write_stream", None)
            if write_stream is not None:
                return await write_stream(
                    request,
                    lambda event_type, data: _emit(state, event_type, "writer", data),
                )
            return await self._clients.writer.write(request)

        branch = await self._invoke_branch(
            "writer",
            state,
            self._settings.writer_policy,
            request_factory,
            operation,
        )
        updates: dict[str, object] = {"writer_branch": branch.model_dump(mode="json")}
        updates.update(_branch_status_updates(branch))
        return updates

    @_traced_node("finalize_success")
    def finalize_success(self, state: WorkflowState) -> dict[str, object]:
        writer = AgentBranch.model_validate(state["writer_branch"])
        brief = WriterResponse.model_validate(writer.data)
        return {
            "final_brief": brief.model_dump(mode="json"),
            "warnings": _deduplicate([*state.get("warnings", []), *writer.warnings]),
            "error": None,
        }

    @_traced_node("finalize_failure")
    def finalize_failure(self, state: WorkflowState) -> dict[str, object]:
        return {"final_brief": None, "workflow_status": ContractStatus.FAILED}

    async def _invoke_branch(
        self,
        agent: str,
        state: WorkflowState,
        policy: AgentPolicy,
        request_factory,
        operation,
    ) -> AgentBranch:
        started_at = perf_counter()
        deadline_at = _deadline_from_state(state)

        async def traced_operation(attempt: int):
            request = request_factory(attempt)
            with operation_span(
                f"agent.call {agent}",
                observation_type="agent",
                attributes={
                    "app.agent": agent,
                    "app.attempt": attempt,
                    "app.request_id": str(state["request_id"]),
                    "app.business_trace_id": state["trace_id"],
                },
            ) as span:
                set_observation_input(span, request)
                try:
                    response = await operation(request)
                except AgentCallError as error:
                    set_observation_output(
                        span,
                        {
                            "status": ContractStatus.FAILED,
                            "error": error.to_contract_error(),
                        },
                    )
                    raise
                set_observation_output(span, response)
                return response

        try:
            result = await invoke_with_retry(
                traced_operation,
                policy,
                deadline_at,
                sleep=self._sleep,
                on_retry=lambda error, attempt: _emit(
                    state,
                    "agent.retrying",
                    agent,
                    {"attempt": attempt, "error_code": error.code},
                ),
            )
            response = result.value
            branch = AgentBranch(
                status=response.status,
                attempts=result.attempts,
                data=response.model_dump(mode="json"),
                warnings=list(response.warnings),
            )
        except AgentCallError as error:
            branch = AgentBranch(
                status=ContractStatus.FAILED,
                attempts=error.attempts,
                error=error.to_contract_error(),
            )

        _log_transition(agent, state, branch, started_at)
        _emit(
            state,
            "agent.completed" if branch.usable else "agent.failed",
            agent,
            {
                "attempts": branch.attempts,
                "status": branch.status,
                **({"error_code": branch.error.code} if branch.error else {}),
            },
        )
        return branch


def route_after_market_intelligence(state: WorkflowState) -> str:
    return "failure" if state["workflow_status"] == ContractStatus.FAILED else "analyst"


def route_after_analyst(state: WorkflowState) -> str:
    branch = AgentBranch.model_validate(state["analysis_branch"])
    return "writer" if branch.usable else "failure"


def route_after_writer(state: WorkflowState) -> str:
    branch = AgentBranch.model_validate(state["writer_branch"])
    return "success" if branch.usable else "failure"


def _branch_status_updates(branch: AgentBranch) -> dict[str, object]:
    if not branch.usable:
        return {
            "workflow_status": ContractStatus.FAILED,
            "error": branch.error.model_dump(mode="json") if branch.error else None,
        }
    if branch.status is ContractStatus.DEGRADED:
        return {"workflow_status": ContractStatus.DEGRADED}
    return {}


def _request_fields(
    state: WorkflowState,
    attempt: int,
    *,
    deadline_at: datetime | None = None,
) -> dict[str, object]:
    return {
        "contract_version": state["contract_version"],
        "request_id": state["request_id"],
        "trace_id": state["trace_id"],
        "attempt": attempt,
        "deadline_at": deadline_at or state.get("deadline_at"),
    }


def _deadline_from_state(state: WorkflowState) -> datetime | None:
    value = state.get("deadline_at")
    return datetime.fromisoformat(value) if value else None


def _child_deadline_at(state: WorkflowState, parent_timeout_seconds: float) -> datetime:
    now = datetime.now(UTC)
    parent_deadline = now + timedelta(seconds=parent_timeout_seconds)
    workflow_deadline = _deadline_from_state(state)
    if workflow_deadline is not None:
        if workflow_deadline.tzinfo is None:
            workflow_deadline = workflow_deadline.replace(tzinfo=UTC)
        parent_deadline = min(parent_deadline, workflow_deadline)

    grace = min(_UPSTREAM_DEADLINE_GRACE_SECONDS, parent_timeout_seconds * 0.1)
    return max(now, parent_deadline - timedelta(seconds=grace))


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def _log_transition(
    agent: str,
    state: WorkflowState,
    branch: AgentBranch,
    started_at: float,
) -> None:
    logger.info(
        json.dumps(
            {
                "event": "agent_call_completed",
                "request_id": state["request_id"],
                "trace_id": state["trace_id"],
                "agent": agent,
                "attempt": branch.attempts,
                "latency_ms": round((perf_counter() - started_at) * 1_000, 2),
                "status": branch.status,
                "error_code": branch.error.code if branch.error else None,
            },
            default=str,
        )
    )


def _emit(
    state: WorkflowState,
    event_type: str,
    agent: str,
    data: dict[str, object] | None = None,
) -> None:
    emit_event(
        event_type,
        request_id=state["request_id"],
        trace_id=state["trace_id"],
        agent=agent,
        data=data,
    )


def _safe_research_event_data(data: dict[str, object]) -> dict[str, object]:
    query_preview = data.get("query_preview")
    if isinstance(query_preview, str):
        return {"query_preview": sanitize_query(query_preview)}
    result_count = data.get("result_count")
    return {"result_count": result_count} if isinstance(result_count, int) else {}
