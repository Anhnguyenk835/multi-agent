import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Protocol, TypedDict

from distributed_agent_contracts import (
    AppendConversationMessageRequest,
    AppMarketResearchInput,
    AppMarketResearchOutput,
    ContractStatus,
    EvidenceFact,
    MarketAnalysisResponse,
    MarketReportDraft,
    PersistMarketReportDraftRequest,
    PublishApprovedMarketReportRequest,
    ReportReviewDecision,
    ResearchPublication,
    SourceSnapshot,
    copy_request_metadata,
)
from distributed_agent_contracts.market_analysis import EvidenceSource, ReportMetadata
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from market_analyst.backend_client import BackendMarketPublisher, MarketPublisher
from market_analyst.errors import GroundingError
from market_analyst.market_analysis import (
    calculate_scorecard,
    normalize_revenue_history,
    validate_source_lineage,
)
from market_analyst.market_model import LiteLLMMarketModel, MarketModel
from market_analyst.market_models import ResearchTask, ResearchTaskResult
from market_analyst.market_review import build_review_context, dimensions_for_sections
from market_analyst.search import ExaSearch
from market_analyst.settings import DemoSettings
from market_analyst.telemetry import operation_span


class MarketSearch(Protocol):
    async def search(
        self,
        query: str,
        call_id: str,
        deadline_at: datetime | None,
    ) -> list[dict[str, object]]: ...


class ExaMarketSearch:
    def __init__(self, settings: DemoSettings) -> None:
        self._settings = settings.exa

    async def search(
        self,
        query: str,
        call_id: str,
        deadline_at: datetime | None,
    ) -> list[dict[str, object]]:
        return await ExaSearch(self._settings, deadline_at=deadline_at).execute(query, call_id)


@dataclass(frozen=True, slots=True)
class MarketResearchDependencies:
    search: MarketSearch
    model: MarketModel
    publisher: MarketPublisher


def _merge_task_results(
    current: list[dict[str, object]], updates: list[dict[str, object]]
) -> list[dict[str, object]]:
    by_dimension: dict[str, list[dict[str, object]]] = {}
    for item in [*current, *updates]:
        dimension = str(item.get("dimension", "unknown"))
        by_dimension.setdefault(dimension, []).append(item)
    return [item for items in by_dimension.values() for item in items[-10:]]


class MarketResearchState(TypedDict, total=False):
    contract_version: str
    request_id: str
    trace_id: str
    attempt: int
    deadline_at: str | None
    run_id: str
    conversation_id: str
    market_name: str
    market_definition: str
    scope: dict[str, object]
    data_period: str
    budgets: dict[str, object]
    require_approval: bool
    publish: bool
    market: dict[str, object]
    tasks: list[dict[str, object]]
    task: dict[str, object]
    task_results: Annotated[list[dict[str, object]], _merge_task_results]
    gap_fill_round: int
    gap_dimensions: list[str]
    sources: list[dict[str, object]]
    facts: list[dict[str, object]]
    report: dict[str, object]
    draft: dict[str, object]
    review_decision: dict[str, object]
    review_event: dict[str, object]
    review_answer: dict[str, object] | None
    revision_count: int
    publication: dict[str, object] | None
    status: str
    warnings: list[str]
    error: dict[str, object] | None


_INPUT_FIELDS = set(AppMarketResearchInput.model_fields)
_DIMENSIONS: tuple[tuple[str, str, tuple[str, str]], ...] = (
    (
        "market_size",
        "Find supported market revenue, downloads, users, product counts, and annual history.",
        ("market size revenue downloads", "annual revenue growth report"),
    ),
    (
        "momentum",
        "Find current growth, demand, adoption, and search momentum signals.",
        ("market growth trend demand", "consumer adoption downloads trend"),
    ),
    (
        "customers",
        "Identify customer segments, jobs, pain points, and willingness to pay.",
        ("users customer segments pain points", "reviews jobs to be done willingness to pay"),
    ),
    (
        "commercial",
        "Find pricing models, annual price ranges, monetization, and retention pressure.",
        ("pricing subscription monetization", "retention churn business model"),
    ),
    (
        "accessibility",
        "Find acquisition channels, distribution barriers, and market accessibility.",
        ("acquisition channels app store SEO", "distribution barriers discovery"),
    ),
    (
        "competitors",
        "Identify direct and indirect competitors, positioning, platforms, pricing, and gaps.",
        ("top apps competitors pricing", "alternatives positioning features"),
    ),
    (
        "risks_opportunities",
        "Find structural market risks and evidence-backed unmet needs.",
        ("market risks churn saturation", "unmet needs complaints opportunities"),
    ),
)


def build_market_graph_for_settings(
    settings: DemoSettings,
    dependencies: MarketResearchDependencies | None = None,
    checkpointer: BaseCheckpointSaver | None = None,
):
    deps = dependencies or MarketResearchDependencies(
        search=ExaMarketSearch(settings),
        model=LiteLLMMarketModel(settings.ai),
        publisher=BackendMarketPublisher(settings.market),
    )

    async def normalize_request(state: MarketResearchState) -> dict[str, object]:
        request = _extract_request(state)
        market = {
            "id": _slugify(request.market_name),
            "name": request.market_name,
            "definition": request.market_definition,
            "scope": request.scope.model_dump(mode="json"),
        }
        return {
            "market": market,
            "conversation_id": str(request.conversation_id or request.run_id),
            "task_results": [],
            "warnings": [],
            "revision_count": 0,
            "review_answer": None,
        }

    async def plan_research(state: MarketResearchState) -> dict[str, object]:
        request = _extract_request(state)
        query_count = request.budgets.max_search_queries
        reserved_gap_queries = min(
            query_count - len(_DIMENSIONS),
            request.budgets.max_gap_fill_rounds * len(_DIMENSIONS),
        )
        initial_queries = query_count - reserved_gap_queries
        base_queries = initial_queries // len(_DIMENSIONS)
        extra_queries = initial_queries % len(_DIMENSIONS)
        base_sources = request.budgets.max_sources // len(_DIMENSIONS)
        extra_sources = request.budgets.max_sources % len(_DIMENSIONS)
        tasks: list[ResearchTask] = []
        for index, (dimension, question, suffixes) in enumerate(_DIMENSIONS):
            count = min(len(suffixes), base_queries + (1 if index < extra_queries else 0))
            queries = [f"{request.market_name} {suffix}" for suffix in suffixes[: max(1, count)]]
            tasks.append(
                ResearchTask(
                    id=f"{request.run_id}:{dimension}",
                    dimension=dimension,
                    question=question,
                    queries=queries,
                    source_limit=base_sources + (1 if index < extra_sources else 0),
                )
            )
        return {
            "tasks": [task.model_dump(mode="json") for task in tasks],
            "gap_fill_round": 0,
            "gap_dimensions": [],
        }

    async def approve_plan(state: MarketResearchState) -> dict[str, object]:
        request = _extract_request(state)
        if not request.require_approval:
            return {}
        decision = interrupt(
            {
                "type": "market_research.plan_approval",
                "run_id": str(request.run_id),
                "market": state["market"],
                "tasks": state["tasks"],
                "budgets": request.budgets.model_dump(mode="json"),
            }
        )
        approved = decision is True or (
            isinstance(decision, dict) and decision.get("approved") is True
        )
        if not approved:
            raise ValueError("market research plan was not approved")
        return {}

    def dispatch_tasks(state: MarketResearchState) -> list[Send]:
        return [
            Send(
                "research_task",
                {
                    "task": task,
                    "deadline_at": state.get("deadline_at"),
                },
            )
            for task in state["tasks"]
        ]

    async def research_task(state: MarketResearchState) -> dict[str, object]:
        task = ResearchTask.model_validate(state["task"])
        deadline_at = _parse_datetime(state.get("deadline_at"))
        with operation_span(
            f"market_research.task {task.dimension}",
            observation_type="agent",
            attributes={
                "app.agent": "market_report_analyst",
                "app.research.task_id": task.id,
                "app.research.dimension": task.dimension,
                "app.research.query_count": len(task.queries),
            },
        ) as span:
            raw_sources: list[dict[str, object]] = []
            warnings: list[str] = []
            for index, query in enumerate(task.queries, start=1):
                try:
                    with operation_span(
                        "market_research.search",
                        attributes={
                            "app.research.dimension": task.dimension,
                            "app.research.query_index": index,
                        },
                    ):
                        raw_sources.extend(
                            await deps.search.search(
                                query,
                                f"{task.dimension}-{index}",
                                deadline_at,
                            )
                        )
                except Exception as error:  # noqa: BLE001 - one failed query must not cancel siblings
                    warnings.append(f"Search failed for {query!r}: {type(error).__name__}")

            deduplicated = _deduplicate_sources(raw_sources)[: task.source_limit]
            if not deduplicated:
                result = ResearchTaskResult(
                    task_id=task.id,
                    dimension=task.dimension,
                    status="failed",
                    query_count=len(task.queries),
                    warnings=warnings or ["No usable sources found"],
                )
            else:
                snapshots = [_to_snapshot(source, settings) for source in deduplicated]
                extraction = await deps.model.extract(task, deduplicated, deadline_at)
                known_ids = {source.public_id for source in snapshots}
                facts = [
                    EvidenceFact(
                        **fact.model_dump(mode="json"),
                        dimension=task.dimension,
                    )
                    for fact in extraction.facts
                    if fact.source_id in known_ids
                ]
                dropped = len(extraction.facts) - len(facts)
                if dropped:
                    warnings.append(f"Dropped {dropped} facts with unknown source IDs")
                warnings.extend(extraction.warnings)
                result = ResearchTaskResult(
                    task_id=task.id,
                    dimension=task.dimension,
                    status="completed" if facts else "partial",
                    query_count=len(task.queries),
                    sources=snapshots,
                    facts=facts,
                    warnings=warnings,
                )
            span.set_attribute("app.research.source_count", len(result.sources))
            span.set_attribute("app.research.fact_count", len(result.facts))
            span.set_attribute("app.research.status", result.status)
            return {"task_results": [result.model_dump(mode="json")]}

    async def join_evidence(state: MarketResearchState) -> dict[str, object]:
        request = _extract_request(state)
        results = [ResearchTaskResult.model_validate(item) for item in state["task_results"]]
        source_map: dict[str, SourceSnapshot] = {}
        aliases: dict[str, str] = {}
        for result in reversed(results):
            for source in result.sources:
                canonical_key = str(source.url).rstrip("/").lower()
                if canonical_key not in source_map:
                    public_id = f"src_{len(source_map) + 1:02d}"
                    source_map[canonical_key] = source.model_copy(update={"public_id": public_id})
                aliases[source.public_id] = source_map[canonical_key].public_id

        facts: list[EvidenceFact] = []
        allowed_source_ids = {
            source.public_id for source in list(source_map.values())[: request.budgets.max_sources]
        }
        fact_keys: set[str] = set()
        for result in reversed(results):
            for fact in result.facts:
                normalized_id = aliases.get(fact.source_id)
                if normalized_id not in allowed_source_ids:
                    continue
                normalized = fact.model_copy(update={"source_id": normalized_id})
                fact_key = hashlib.sha256(normalized.model_dump_json().encode()).hexdigest()
                if fact_key not in fact_keys and len(facts) < 500:
                    facts.append(normalized)
                    fact_keys.add(fact_key)

        if not facts:
            raise GroundingError("market research produced no grounded evidence facts")
        referenced_source_ids = {fact.source_id for fact in facts}
        used_sources = [
            source
            for source in list(source_map.values())[: request.budgets.max_sources]
            if source.public_id in referenced_source_ids
        ]
        warnings = [warning for result in results for warning in result.warnings]
        return {
            "sources": [source.model_dump(mode="json") for source in used_sources],
            "facts": [fact.model_dump(mode="json") for fact in facts],
            "warnings": warnings,
        }

    async def assess_coverage(state: MarketResearchState) -> dict[str, object]:
        request = _extract_request(state)
        latest = _latest_results(state["task_results"])
        missing = [
            dimension for dimension, result in latest.items() if result.status != "completed"
        ]
        used_queries = sum(
            ResearchTaskResult.model_validate(item).query_count for item in state["task_results"]
        )
        available_queries = max(0, request.budgets.max_search_queries - used_queries)
        can_retry = (
            missing
            and state.get("gap_fill_round", 0) < request.budgets.max_gap_fill_rounds
            and available_queries > 0
        )
        return {
            "gap_dimensions": missing[:available_queries] if can_retry else [],
            "gap_fill_round": state.get("gap_fill_round", 0) + (1 if can_retry else 0),
        }

    def route_after_coverage(state: MarketResearchState):
        if not state.get("gap_dimensions"):
            return "synthesize_report"
        tasks_by_dimension = {
            task["dimension"]: ResearchTask.model_validate(task) for task in state["tasks"]
        }
        round_number = state["gap_fill_round"]
        return [
            Send(
                "research_task",
                {
                    "task": tasks_by_dimension[dimension]
                    .model_copy(
                        update={
                            "id": f"{tasks_by_dimension[dimension].id}:gap-{round_number}",
                            "queries": [
                                " ".join(
                                    (
                                        state["market_name"],
                                        dimension.replace("_", " "),
                                        "verified data alternative sources",
                                    )
                                )
                            ],
                        }
                    )
                    .model_dump(mode="json"),
                    "deadline_at": state.get("deadline_at"),
                },
            )
            for dimension in state["gap_dimensions"]
        ]

    async def synthesize_report(state: MarketResearchState) -> dict[str, object]:
        request = _extract_request(state)
        facts = [EvidenceFact.model_validate(item) for item in state["facts"]]
        sources = [SourceSnapshot.model_validate(item) for item in state["sources"]]
        synthesis = await deps.model.synthesize(
            market=state["market"],
            data_period=request.data_period,
            facts=facts,
            source_ids={source.public_id for source in sources},
            deadline_at=request.deadline_at,
        )
        failed_dimensions = {
            dimension
            for dimension, result in _latest_results(state["task_results"]).items()
            if result.status != "completed"
        }
        report_status = "partial" if failed_dimensions else "completed"
        evidence = [
            EvidenceSource(
                id=source.public_id,
                title=source.title,
                publisher=source.publisher,
                url=source.url,
                published_at=source.published_at,
                retrieved_at=source.retrieved_at,
                evidence_class=_source_evidence_class(source.public_id, facts),
            )
            for source in sources
        ]
        confidence = round(sum(fact.confidence for fact in facts) / len(facts))
        report = MarketAnalysisResponse(
            market=state["market"],
            report=ReportMetadata(
                id=str(request.run_id),
                version=1,
                status=report_status,
                generated_at=datetime.now(UTC).isoformat(),
                data_period=request.data_period,
                overall_confidence=confidence,
                freshness="current",
                warnings=state.get("warnings", []),
            ),
            overview=synthesis.overview,
            competitors=synthesis.competitors,
            evidence=evidence,
        )
        report = _normalize_and_validate_report(report)
        return {"report": report.model_dump(mode="json"), "review_answer": None}

    def route_after_synthesis(state: MarketResearchState) -> str:
        return "persist_draft" if _extract_request(state).publish else "finalize"

    async def persist_draft(state: MarketResearchState) -> dict[str, object]:
        request = _extract_request(state)
        report = MarketAnalysisResponse.model_validate(state["report"])
        previous = MarketReportDraft.model_validate(state["draft"]) if state.get("draft") else None
        revision_count = state.get("revision_count", 0)
        draft_request = PersistMarketReportDraftRequest(
            run_id=request.run_id,
            conversation_id=state["conversation_id"],
            idempotency_key=f"market-draft:{request.run_id}:{revision_count}",
            report=report,
            sources=[SourceSnapshot.model_validate(item) for item in state["sources"]],
            facts=[EvidenceFact.model_validate(item) for item in state["facts"]],
            based_on_draft_id=previous.draft_id if previous else None,
        )
        with operation_span(
            "market_report.persist_draft",
            attributes={
                "app.market.id": report.market.id,
                "app.review.revision_count": revision_count,
            },
        ):
            draft = await deps.publisher.persist_draft(draft_request)
        if previous is not None:
            decision = ReportReviewDecision.model_validate(state["review_decision"])
            await deps.publisher.append_message(
                AppendConversationMessageRequest(
                    conversation_id=state["conversation_id"],
                    role="assistant",
                    kind="revision_summary",
                    content=(
                        f"Created draft v{draft.version} after {decision.action}: "
                        f"{decision.message}"
                    ),
                    idempotency_key=f"draft-summary:{draft.draft_id}",
                )
            )
        return {"draft": draft.model_dump(mode="json"), "review_decision": {}}

    async def review_report(state: MarketResearchState) -> dict[str, object]:
        draft = MarketReportDraft.model_validate(state["draft"])
        decision = ReportReviewDecision.model_validate(
            interrupt(
                {
                    "type": "market_report_review.v1",
                    "conversation_id": str(draft.conversation_id),
                    "run_id": str(draft.run_id),
                    "draft_id": str(draft.draft_id),
                    "draft_version": draft.version,
                    "draft_hash": draft.report_hash,
                    "report": draft.report.model_dump(mode="json"),
                    "answer": state.get("review_answer"),
                    "allowed_actions": [
                        "ask_followup",
                        "request_revision",
                        "request_more_research",
                        "approve_publish",
                        "cancel",
                    ],
                }
            )
        )
        if decision.draft_id != draft.draft_id:
            raise ValueError("review decision targets a different draft")
        if decision.expected_draft_hash != draft.report_hash:
            raise ValueError("review decision targets a stale draft hash")
        event = await deps.publisher.record_review(state["conversation_id"], decision)
        return {
            "review_decision": decision.model_dump(mode="json"),
            "review_event": event.model_dump(mode="json"),
            "review_answer": None,
        }

    def route_after_review(state: MarketResearchState) -> str:
        action = ReportReviewDecision.model_validate(state["review_decision"]).action
        return {
            "ask_followup": "answer_followup",
            "request_revision": "revise_report",
            "request_more_research": "prepare_delta_research",
            "approve_publish": "publish_report",
            "cancel": "finalize",
        }[action]

    async def answer_followup(state: MarketResearchState) -> dict[str, object]:
        decision = ReportReviewDecision.model_validate(state["review_decision"])
        if not decision.message:
            raise ValueError("ask_followup requires a question")
        report = MarketAnalysisResponse.model_validate(state["report"])
        facts = [EvidenceFact.model_validate(item) for item in state["facts"]]
        conversation = await deps.publisher.get_review_context(state["conversation_id"])
        context = build_review_context(
            report=report,
            facts=facts,
            conversation=conversation,
            section_ids=decision.section_ids,
        )
        answer = await deps.model.answer_followup(
            report=report,
            question=decision.message,
            facts=facts,
            context=context,
            deadline_at=decision.action_deadline_at,
        )
        await deps.publisher.append_message(
            AppendConversationMessageRequest(
                conversation_id=state["conversation_id"],
                role="assistant",
                kind="assistant_answer",
                content=answer.answer,
                idempotency_key=f"review-answer:{decision.idempotency_key}",
            )
        )
        return {"review_answer": answer.model_dump(mode="json")}

    async def revise_report(state: MarketResearchState) -> dict[str, object]:
        decision = ReportReviewDecision.model_validate(state["review_decision"])
        if not decision.message:
            raise ValueError("request_revision requires revision instructions")
        report = MarketAnalysisResponse.model_validate(state["report"])
        facts = [EvidenceFact.model_validate(item) for item in state["facts"]]
        sources = [SourceSnapshot.model_validate(item) for item in state["sources"]]
        conversation = await deps.publisher.get_review_context(state["conversation_id"])
        context = build_review_context(
            report=report,
            facts=facts,
            conversation=conversation,
            section_ids=decision.section_ids,
        )
        synthesis = await deps.model.revise(
            report=report,
            instruction=decision.message,
            section_ids=decision.section_ids,
            facts=facts,
            source_ids={source.public_id for source in sources},
            context=context,
            deadline_at=decision.action_deadline_at,
        )
        revised = report.model_copy(
            update={
                "report": report.report.model_copy(
                    update={"generated_at": datetime.now(UTC).isoformat()}
                ),
                "overview": synthesis.overview,
                "competitors": synthesis.competitors,
            }
        )
        revised = _normalize_and_validate_report(revised)
        return {
            "report": revised.model_dump(mode="json"),
            "revision_count": state.get("revision_count", 0) + 1,
        }

    async def prepare_delta_research(state: MarketResearchState) -> dict[str, object]:
        decision = ReportReviewDecision.model_validate(state["review_decision"])
        if not decision.message:
            raise ValueError("request_more_research requires research instructions")
        dimensions = dimensions_for_sections(decision.section_ids)
        if not dimensions:
            dimensions = {dimension for dimension, _, _ in _DIMENSIONS}
        definitions = {dimension: question for dimension, question, _ in _DIMENSIONS}
        source_limit = max(
            1, min(10, _extract_request(state).budgets.max_sources // len(dimensions))
        )
        tasks = [
            ResearchTask(
                id=f"{state['run_id']}:{dimension}:revision-{state.get('revision_count', 0) + 1}",
                dimension=dimension,
                question=f"{definitions[dimension]} User request: {decision.message}",
                queries=[
                    f"{state['market_name']} {decision.message} {dimension.replace('_', ' ')}"
                ],
                source_limit=source_limit,
            )
            for dimension in sorted(dimensions)
        ]
        return {
            "tasks": [task.model_dump(mode="json") for task in tasks],
            "gap_dimensions": [],
            "gap_fill_round": 0,
            "revision_count": state.get("revision_count", 0) + 1,
            "deadline_at": (
                decision.action_deadline_at.isoformat() if decision.action_deadline_at else None
            ),
        }

    async def publish_report(state: MarketResearchState) -> dict[str, object]:
        request = _extract_request(state)
        report = MarketAnalysisResponse.model_validate(state["report"])
        draft = MarketReportDraft.model_validate(state["draft"])
        publish_request = PublishApprovedMarketReportRequest(
            draft_id=draft.draft_id,
            expected_draft_hash=draft.report_hash,
            idempotency_key=f"market-report:{request.run_id}:{draft.draft_id}",
        )
        with operation_span(
            "market_report.publish",
            attributes={"app.market.id": report.market.id},
        ):
            publication = await deps.publisher.publish_approved(publish_request)
        return {"publication": publication.model_dump(mode="json")}

    async def finalize(state: MarketResearchState) -> dict[str, object]:
        request = _extract_request(state)
        report = MarketAnalysisResponse.model_validate(state["report"])
        publication = state.get("publication")
        response = AppMarketResearchOutput(
            **copy_request_metadata(request),
            run_id=request.run_id,
            status=(
                ContractStatus.DEGRADED
                if report.report.status == "partial"
                else ContractStatus.SUCCESS
            ),
            warnings=report.report.warnings,
            report=report,
            publication=(ResearchPublication.model_validate(publication) if publication else None),
        )
        return response.model_dump(mode="json")

    builder = StateGraph(
        MarketResearchState,
        input_schema=AppMarketResearchInput,
        output_schema=AppMarketResearchOutput,
    )
    builder.add_node("normalize_request", normalize_request)
    builder.add_node("plan_research", plan_research)
    builder.add_node("approve_plan", approve_plan)
    builder.add_node("research_task", research_task)
    builder.add_node("join_evidence", join_evidence)
    builder.add_node("assess_coverage", assess_coverage)
    builder.add_node("synthesize_report", synthesize_report)
    builder.add_node("persist_draft", persist_draft)
    builder.add_node("review_report", review_report)
    builder.add_node("answer_followup", answer_followup)
    builder.add_node("revise_report", revise_report)
    builder.add_node("prepare_delta_research", prepare_delta_research)
    builder.add_node("publish_report", publish_report)
    builder.add_node("finalize", finalize)
    builder.add_edge(START, "normalize_request")
    builder.add_edge("normalize_request", "plan_research")
    builder.add_edge("plan_research", "approve_plan")
    builder.add_conditional_edges("approve_plan", dispatch_tasks, ["research_task"])
    builder.add_edge("research_task", "join_evidence")
    builder.add_edge("join_evidence", "assess_coverage")
    builder.add_conditional_edges(
        "assess_coverage",
        route_after_coverage,
        ["research_task", "synthesize_report"],
    )
    builder.add_conditional_edges(
        "synthesize_report",
        route_after_synthesis,
        ["persist_draft", "finalize"],
    )
    builder.add_edge("persist_draft", "review_report")
    builder.add_conditional_edges(
        "review_report",
        route_after_review,
        [
            "answer_followup",
            "revise_report",
            "prepare_delta_research",
            "publish_report",
            "finalize",
        ],
    )
    builder.add_edge("answer_followup", "review_report")
    builder.add_edge("revise_report", "persist_draft")
    builder.add_conditional_edges("prepare_delta_research", dispatch_tasks, ["research_task"])
    builder.add_edge("publish_report", "finalize")
    builder.add_edge("finalize", END)
    return builder.compile(checkpointer=checkpointer)


def build_market_graph(config: RunnableConfig):
    del config
    return build_market_graph_for_settings(DemoSettings.from_environment())


def _normalize_and_validate_report(
    report: MarketAnalysisResponse,
) -> MarketAnalysisResponse:
    market_size = normalize_revenue_history(report.overview.market_size)
    report = report.model_copy(
        update={"overview": report.overview.model_copy(update={"market_size": market_size})}
    )
    report = report.model_copy(
        update={
            "overview": report.overview.model_copy(
                update={"scorecard": calculate_scorecard(report)}
            )
        }
    )
    validate_source_lineage(report)
    return report


def _extract_request(state: MarketResearchState) -> AppMarketResearchInput:
    return AppMarketResearchInput.model_validate(
        {key: value for key, value in state.items() if key in _INPUT_FIELDS}
    )


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug[:120] or "app-market"


def _deduplicate_sources(sources: list[dict[str, object]]) -> list[dict[str, object]]:
    unique: dict[str, dict[str, object]] = {}
    for source in sources:
        url = str(source.get("url", "")).rstrip("/").lower()
        content = str(source.get("content", "")).strip()
        if url and content and url not in unique:
            unique[url] = source
    return list(unique.values())


def _to_snapshot(source: dict[str, object], settings: DemoSettings) -> SourceSnapshot:
    content = str(source["content"])
    return SourceSnapshot(
        public_id=str(source["tag"]),
        title=str(source["title"]),
        publisher=str(source["publisher"]),
        url=str(source["url"]),
        published_at=(str(source["published_at"]) if source.get("published_at") else None),
        retrieved_at=str(source["retrieved_at"]),
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        content_excerpt=content[: settings.market.source_excerpt_characters],
    )


def _source_evidence_class(source_id: str, facts: list[EvidenceFact]):
    for fact in facts:
        if fact.source_id == source_id:
            return fact.evidence_class
    return "inferred"


def _latest_results(items: list[dict[str, object]]) -> dict[str, ResearchTaskResult]:
    latest: dict[str, ResearchTaskResult] = {}
    for item in items:
        result = ResearchTaskResult.model_validate(item)
        latest[result.dimension] = result
    return latest


def _parse_datetime(value: object) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))
