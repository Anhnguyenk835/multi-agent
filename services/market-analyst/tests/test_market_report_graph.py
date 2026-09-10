from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from distributed_agent_contracts import (
    AppMarketResearchInput,
    AppMarketResearchOutput,
    ContractStatus,
    ConversationMessage,
    ConversationReviewContext,
    MarketReportDraft,
    MarketScope,
    PublishMarketReportResponse,
    ReportReviewEvent,
)
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from market_analyst.market_graph import (
    MarketResearchDependencies,
    build_market_graph_for_settings,
)
from market_analyst.market_models import MarketSynthesis, TaskExtraction
from market_analyst.settings import DemoSettings


class FakeSearch:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def search(self, query, call_id, deadline_at):
        self.calls.append(query)
        now = datetime.now(UTC).isoformat()
        return [
            {
                "tag": f"{call_id}#0",
                "title": f"Source for {call_id}",
                "url": f"https://example.com/{call_id}",
                "publisher": "example.com",
                "published_at": "2026-01-01T00:00:00+00:00",
                "retrieved_at": now,
                "content": f"Grounded market evidence for {query}.",
            }
        ]


class FakeModel:
    async def extract(self, task, sources, deadline_at):
        return TaskExtraction.model_validate(
            {
                "facts": [
                    {
                        "source_id": sources[0]["tag"],
                        "claim_type": "market_signal",
                        "claim": f"Supported evidence for {task.dimension}.",
                        "evidence_class": "reported",
                        "confidence": 80,
                    }
                ]
            }
        )

    async def synthesize(
        self, *, market, data_period, facts, source_ids, deadline_at
    ) -> MarketSynthesis:
        source_id = min(source_ids)
        return MarketSynthesis.model_validate(
            {
                "overview": {
                    "verdict": {
                        "status": "selectively_attractive",
                        "summary": "Demand exists with meaningful competition.",
                        "strengths": ["Demand"],
                        "constraints": ["Competition"],
                    },
                    "scorecard": {
                        "demand": 0,
                        "market_size": 0,
                        "momentum": 0,
                        "commercial_quality": 0,
                        "accessibility": 0,
                        "competitive_headroom": 0,
                    },
                    "market_size": {
                        "metrics": [
                            {
                                "id": "annual_revenue",
                                "label": "Estimated annual revenue",
                                "value": 120000000,
                                "unit": "USD",
                                "period": "2025",
                                "evidence_class": "estimated",
                                "confidence": 70,
                                "source_ids": [source_id],
                            }
                        ],
                        "revenue_history": [
                            {
                                "period": "2024",
                                "value": 100000000,
                                "evidence_class": "estimated",
                                "confidence": 70,
                                "source_ids": [source_id],
                            },
                            {
                                "period": "2025",
                                "value": 120000000,
                                "evidence_class": "estimated",
                                "confidence": 70,
                                "source_ids": [source_id],
                            },
                        ],
                    },
                    "momentum": {
                        "direction": "growing",
                        "strength": "moderate",
                        "summary": "Revenue is growing.",
                        "signals": [
                            {
                                "label": "Revenue",
                                "change": 20,
                                "unit": "percent",
                                "period": "YoY",
                                "source_ids": [source_id],
                            }
                        ],
                    },
                    "customer_segments": [
                        {
                            "id": "professionals",
                            "name": "Professionals",
                            "jobs": ["Track progress"],
                            "pain_points": ["Manual work"],
                            "willingness_to_pay": "moderate",
                            "confidence": 75,
                            "source_ids": [source_id],
                        }
                    ],
                    "commercial_dynamics": {
                        "dominant_model": "Subscription",
                        "willingness_to_pay": "moderate",
                        "retention_pressure": "moderate",
                        "summary": "Subscriptions are common.",
                        "source_ids": [source_id],
                    },
                    "market_accessibility": {
                        "level": "moderate",
                        "channels": ["App stores"],
                        "barriers": ["Competition"],
                        "summary": "The market is reachable.",
                        "confidence": 70,
                        "source_ids": [source_id],
                    },
                    "risks": [
                        {
                            "id": "retention",
                            "category": "Retention",
                            "title": "Churn",
                            "probability": "high",
                            "impact": "high",
                            "summary": "Users may churn.",
                            "source_ids": [source_id],
                        }
                    ],
                    "opportunity_gaps": [
                        {
                            "id": "automation",
                            "segment": "Professionals",
                            "unmet_need": "Less manual work",
                            "competitor_coverage": "low",
                            "demand_strength": "high",
                            "commercial_signal": "moderate",
                            "confidence": 70,
                            "source_ids": [source_id],
                        }
                    ],
                },
                "competitors": {
                    "summary": {
                        "competition_level": "high",
                        "market_structure": "fragmented",
                        "tracked_products": 1,
                        "feature_saturation": "high",
                        "switching_cost": "low",
                        "source_ids": [source_id],
                    },
                    "items": [
                        {
                            "id": "example-app",
                            "name": "Example App",
                            "type": "direct",
                            "positioning": "Simple tracking",
                            "platforms": ["iOS"],
                            "pricing": {"model": "Subscription"},
                            "strengths": ["Simple"],
                            "weaknesses": ["Limited"],
                            "confidence": 70,
                            "source_ids": [source_id],
                        }
                    ],
                },
            }
        )

    async def revise(
        self,
        *,
        report,
        instruction,
        section_ids,
        facts,
        source_ids,
        context,
        deadline_at,
    ):
        synthesis = await self.synthesize(
            market=report.market.model_dump(mode="json"),
            data_period=report.report.data_period,
            facts=facts,
            source_ids=source_ids,
            deadline_at=deadline_at,
        )
        verdict = synthesis.overview.verdict.model_copy(update={"summary": instruction})
        return synthesis.model_copy(
            update={"overview": synthesis.overview.model_copy(update={"verdict": verdict})}
        )

    async def answer_followup(self, *, report, question, facts, context, deadline_at):
        from market_analyst.market_models import ReviewAnswer

        return ReviewAnswer(answer=f"Answer: {question}", source_ids=[facts[0].source_id])


class FakePublisher:
    def __init__(self) -> None:
        self.requests = []
        self.drafts = []
        self.decisions = []
        self.messages = []

    async def publish(self, request):
        self.requests.append(request)
        return PublishMarketReportResponse(
            market_id=request.report.market.id,
            report_id="report-1",
            report_version=2,
        )

    async def persist_draft(self, request):
        self.drafts.append(request)
        version = len(self.drafts)
        return MarketReportDraft(
            draft_id=uuid4(),
            run_id=request.run_id,
            conversation_id=request.conversation_id,
            version=version,
            status="in_review",
            report_hash=f"{version:064x}",
            report=request.report,
        )

    async def record_review(self, conversation_id, decision):
        self.decisions.append(decision)
        return ReportReviewEvent(
            event_id=uuid4(),
            conversation_id=conversation_id,
            draft_id=decision.draft_id,
            review_generation=len(self.drafts),
            action=decision.action,
            status=("approved" if decision.action == "approve_publish" else "in_review"),
        )

    async def append_message(self, request):
        self.messages.append(request)
        return ConversationMessage(
            message_id=uuid4(),
            conversation_id=request.conversation_id,
            sequence=len(self.messages),
            role=request.role,
            kind=request.kind,
            content=request.content,
        )

    async def get_review_context(self, conversation_id):
        return ConversationReviewContext(
            conversation_id=conversation_id,
            summary={},
            recent_messages=[],
        )

    async def publish_approved(self, request):
        self.requests.append(request)
        return PublishMarketReportResponse(
            market_id="habit-tracking-apps",
            report_id="report-1",
            report_version=2,
        )


class GapFillModel(FakeModel):
    def __init__(self) -> None:
        self.market_size_attempts = 0

    async def extract(self, task, sources, deadline_at):
        if task.dimension == "market_size":
            self.market_size_attempts += 1
            if self.market_size_attempts == 1:
                return TaskExtraction(facts=[], warnings=["Initial evidence was insufficient"])
        return await super().extract(task, sources, deadline_at)


@pytest.mark.anyio
async def test_market_graph_builds_grounded_dashboard_report_and_publishes() -> None:
    search = FakeSearch()
    publisher = FakePublisher()
    dependencies = MarketResearchDependencies(
        search=search,
        model=FakeModel(),
        publisher=publisher,
    )
    run_id = uuid4()
    conversation_id = uuid4()
    request = AppMarketResearchInput(
        request_id=uuid4(),
        trace_id="market-trace",
        run_id=run_id,
        conversation_id=conversation_id,
        deadline_at=datetime.now(UTC) + timedelta(minutes=5),
        market_name="Habit Tracking Apps",
        market_definition="Consumer apps for building recurring habits.",
        scope=MarketScope(
            geography=["Global"],
            platforms=["iOS", "Android", "Web"],
            customer_type="B2C",
        ),
        data_period="2024 - 2026",
    )

    graph = build_market_graph_for_settings(DemoSettings(), dependencies, InMemorySaver())
    config = {"configurable": {"thread_id": str(conversation_id)}}
    interrupted = await graph.ainvoke(request.model_dump(mode="json"), config)
    review = interrupted["__interrupt__"][0].value
    result = await graph.ainvoke(
        Command(
            resume={
                "action": "approve_publish",
                "draft_id": review["draft_id"],
                "expected_draft_hash": review["draft_hash"],
                "idempotency_key": "approve-1",
                "actor_id": "user-1",
            }
        ),
        config,
    )
    response = AppMarketResearchOutput.model_validate(result)

    assert response.status is ContractStatus.SUCCESS
    assert response.report is not None
    assert response.report.market.id == "habit-tracking-apps"
    assert len(response.report.evidence) == 7
    assert len(search.calls) == 7
    assert response.report.overview.scorecard.demand > 0
    assert response.report.overview.market_size.metrics[0].change is not None
    assert response.report.overview.market_size.metrics[0].change.value == 20
    assert response.publication is not None
    assert response.publication.report_version == 2
    assert len(publisher.requests) == 1
    assert len(publisher.drafts[0].facts) == 7


@pytest.mark.anyio
async def test_market_graph_gap_fill_is_bounded_and_recovers_missing_dimension() -> None:
    search = FakeSearch()
    model = GapFillModel()
    publisher = FakePublisher()
    request = AppMarketResearchInput(
        request_id=uuid4(),
        trace_id="gap-fill-trace",
        run_id=uuid4(),
        market_name="Personal Finance Apps",
        market_definition="Consumer applications for managing personal finances.",
        scope=MarketScope(
            geography=["Global"],
            platforms=["iOS", "Android"],
            customer_type="B2C",
        ),
        data_period="2024 - 2026",
        publish=False,
    )

    result = await build_market_graph_for_settings(
        DemoSettings(),
        MarketResearchDependencies(search=search, model=model, publisher=publisher),
    ).ainvoke(request.model_dump(mode="json"))
    response = AppMarketResearchOutput.model_validate(result)

    assert response.status is ContractStatus.SUCCESS
    assert model.market_size_attempts == 2
    assert len(search.calls) == 8
    assert publisher.requests == []


@pytest.mark.anyio
async def test_market_graph_review_loop_answers_revises_then_publishes() -> None:
    conversation_id = uuid4()
    publisher = FakePublisher()
    graph = build_market_graph_for_settings(
        DemoSettings(),
        MarketResearchDependencies(search=FakeSearch(), model=FakeModel(), publisher=publisher),
        InMemorySaver(),
    )
    config = {"configurable": {"thread_id": str(conversation_id)}}
    request = AppMarketResearchInput(
        request_id=uuid4(),
        trace_id="review-loop",
        run_id=uuid4(),
        conversation_id=conversation_id,
        market_name="Habit Tracking Apps",
        market_definition="Consumer apps for building recurring habits.",
        scope=MarketScope(
            geography=["Global"],
            platforms=["iOS", "Android"],
            customer_type="B2C",
        ),
        data_period="2024 - 2026",
    )

    initial = await graph.ainvoke(request.model_dump(mode="json"), config)
    first_review = initial["__interrupt__"][0].value
    followup = await graph.ainvoke(
        Command(
            resume={
                "action": "ask_followup",
                "draft_id": first_review["draft_id"],
                "expected_draft_hash": first_review["draft_hash"],
                "idempotency_key": "question-1",
                "actor_id": "user-1",
                "message": "Why is this market only selectively attractive?",
            }
        ),
        config,
    )
    same_draft_review = followup["__interrupt__"][0].value
    assert same_draft_review["draft_id"] == first_review["draft_id"]
    assert same_draft_review["answer"]["answer"].startswith("Answer:")

    revised = await graph.ainvoke(
        Command(
            resume={
                "action": "request_revision",
                "draft_id": same_draft_review["draft_id"],
                "expected_draft_hash": same_draft_review["draft_hash"],
                "idempotency_key": "revision-1",
                "actor_id": "user-1",
                "message": "Use a more conservative verdict.",
                "section_ids": ["verdict"],
            }
        ),
        config,
    )
    second_review = revised["__interrupt__"][0].value
    assert second_review["draft_id"] != first_review["draft_id"]
    assert second_review["draft_version"] == 2
    assert second_review["report"]["overview"]["verdict"]["summary"] == (
        "Use a more conservative verdict."
    )

    result = await graph.ainvoke(
        Command(
            resume={
                "action": "approve_publish",
                "draft_id": second_review["draft_id"],
                "expected_draft_hash": second_review["draft_hash"],
                "idempotency_key": "approval-2",
                "actor_id": "user-1",
            }
        ),
        config,
    )

    response = AppMarketResearchOutput.model_validate(result)
    assert response.publication is not None
    assert len(publisher.drafts) == 2
    assert [decision.action for decision in publisher.decisions] == [
        "ask_followup",
        "request_revision",
        "approve_publish",
    ]
    assert [message.kind for message in publisher.messages] == [
        "assistant_answer",
        "revision_summary",
    ]


@pytest.mark.anyio
async def test_market_graph_delta_research_creates_new_draft_then_cancels() -> None:
    conversation_id = uuid4()
    search = FakeSearch()
    publisher = FakePublisher()
    graph = build_market_graph_for_settings(
        DemoSettings(),
        MarketResearchDependencies(search=search, model=FakeModel(), publisher=publisher),
        InMemorySaver(),
    )
    config = {"configurable": {"thread_id": str(conversation_id)}}
    request = AppMarketResearchInput(
        request_id=uuid4(),
        trace_id="delta-research",
        run_id=uuid4(),
        conversation_id=conversation_id,
        market_name="Habit Tracking Apps",
        market_definition="Consumer apps for building recurring habits.",
        scope=MarketScope(
            geography=["Global"],
            platforms=["iOS", "Android"],
            customer_type="B2C",
        ),
        data_period="2024 - 2026",
    )

    initial = await graph.ainvoke(request.model_dump(mode="json"), config)
    first_review = initial["__interrupt__"][0].value
    researched = await graph.ainvoke(
        Command(
            resume={
                "action": "request_more_research",
                "draft_id": first_review["draft_id"],
                "expected_draft_hash": first_review["draft_hash"],
                "idempotency_key": "research-more-1",
                "actor_id": "user-1",
                "message": "Find newer revenue evidence.",
                "section_ids": ["market_size"],
            }
        ),
        config,
    )
    second_review = researched["__interrupt__"][0].value

    assert second_review["draft_version"] == 2
    assert second_review["draft_id"] != first_review["draft_id"]
    assert len(search.calls) == 8

    result = await graph.ainvoke(
        Command(
            resume={
                "action": "cancel",
                "draft_id": second_review["draft_id"],
                "expected_draft_hash": second_review["draft_hash"],
                "idempotency_key": "cancel-2",
                "actor_id": "user-1",
            }
        ),
        config,
    )

    response = AppMarketResearchOutput.model_validate(result)
    assert response.publication is None
    assert [decision.action for decision in publisher.decisions] == [
        "request_more_research",
        "cancel",
    ]
