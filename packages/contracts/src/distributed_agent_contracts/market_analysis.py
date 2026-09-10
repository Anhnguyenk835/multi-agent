from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AnyHttpUrl, Field, model_validator

from distributed_agent_contracts.common import (
    ContractModel,
    RequestMetadata,
    ResponseMetadata,
)

Confidence = Annotated[int, Field(ge=0, le=100)]
QualitativeLevel = Literal["low", "moderate", "high"]
EvidenceClass = Literal["reported", "estimated", "derived", "proxy", "inferred"]
ResearchDimension = Literal[
    "market_size",
    "momentum",
    "customers",
    "commercial",
    "accessibility",
    "competitors",
    "risks_opportunities",
]


class MarketScope(ContractModel):
    geography: list[str] = Field(min_length=1, max_length=10)
    platforms: list[str] = Field(min_length=1, max_length=10)
    customer_type: Literal["B2C", "B2B", "prosumer", "mixed"]
    included: list[str] = Field(default_factory=list, max_length=20)
    excluded: list[str] = Field(default_factory=list, max_length=20)


class MarketIdentity(ContractModel):
    id: str = Field(min_length=1, max_length=120, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
    name: str = Field(min_length=1, max_length=200)
    definition: str = Field(min_length=1, max_length=2_000)
    scope: MarketScope


class ReportMetadata(ContractModel):
    id: str = Field(min_length=1, max_length=120)
    version: int = Field(gt=0)
    status: Literal["partial", "completed"]
    generated_at: str
    data_period: str = Field(min_length=1, max_length=120)
    overall_confidence: Confidence
    freshness: Literal["current", "aging", "stale"]
    warnings: list[str] = Field(default_factory=list, max_length=50)


class MetricRange(ContractModel):
    min: float
    max: float

    @model_validator(mode="after")
    def validate_order(self) -> "MetricRange":
        if self.min > self.max:
            raise ValueError("metric range min must not exceed max")
        return self


class MetricChange(ContractModel):
    value: float
    unit: Literal["percent", "percentage_points", "absolute"]
    period: Literal["MoM", "YoY", "CAGR"]


class MarketMetric(ContractModel):
    id: str = Field(min_length=1, max_length=120)
    label: str = Field(min_length=1, max_length=200)
    value: float | None = None
    range: MetricRange | None = None
    unit: Literal["USD", "percent", "users", "downloads", "products", "index"]
    period: str = Field(min_length=1, max_length=120)
    change: MetricChange | None = None
    evidence_class: EvidenceClass
    confidence: Confidence
    source_ids: list[str] = Field(min_length=1, max_length=20)
    methodology: str | None = Field(default=None, max_length=1_000)

    @model_validator(mode="after")
    def validate_value(self) -> "MarketMetric":
        if self.value is None and self.range is None:
            raise ValueError("market metric requires value or range")
        return self


class RevenueTrendPoint(ContractModel):
    period: str = Field(min_length=1, max_length=40)
    value: float = Field(ge=0)
    unit: Literal["USD"] = "USD"
    evidence_class: EvidenceClass
    confidence: Confidence
    source_ids: list[str] = Field(min_length=1, max_length=20)


class TrendSignal(ContractModel):
    label: str = Field(min_length=1, max_length=200)
    change: float
    unit: Literal["percent", "percentage_points", "absolute"]
    period: Literal["MoM", "YoY", "CAGR"]
    source_ids: list[str] = Field(min_length=1, max_length=20)


class MarketVerdict(ContractModel):
    status: Literal[
        "attractive",
        "selectively_attractive",
        "mature",
        "unattractive",
        "insufficient_evidence",
    ]
    summary: str = Field(min_length=1, max_length=2_000)
    strengths: list[str] = Field(default_factory=list, max_length=10)
    constraints: list[str] = Field(default_factory=list, max_length=10)


class MarketScorecard(ContractModel):
    demand: Confidence
    market_size: Confidence
    momentum: Confidence
    commercial_quality: Confidence
    accessibility: Confidence
    competitive_headroom: Confidence


class MarketSize(ContractModel):
    metrics: list[MarketMetric] = Field(default_factory=list, max_length=20)
    revenue_history: list[RevenueTrendPoint] = Field(default_factory=list, max_length=20)


class MarketMomentum(ContractModel):
    direction: Literal["growing", "stable", "declining", "uncertain"]
    strength: QualitativeLevel
    summary: str = Field(min_length=1, max_length=2_000)
    signals: list[TrendSignal] = Field(default_factory=list, max_length=20)


class CustomerSegment(ContractModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    jobs: list[str] = Field(default_factory=list, max_length=10)
    pain_points: list[str] = Field(default_factory=list, max_length=10)
    willingness_to_pay: QualitativeLevel | Literal["unknown"]
    confidence: Confidence
    source_ids: list[str] = Field(min_length=1, max_length=20)


class PriceRange(ContractModel):
    min: float = Field(ge=0)
    max: float = Field(ge=0)
    unit: Literal["USD"] = "USD"


class CommercialDynamics(ContractModel):
    dominant_model: str = Field(min_length=1, max_length=200)
    typical_annual_price: PriceRange | None = None
    willingness_to_pay: QualitativeLevel | Literal["unknown"]
    retention_pressure: QualitativeLevel | Literal["unknown"]
    summary: str = Field(min_length=1, max_length=2_000)
    source_ids: list[str] = Field(min_length=1, max_length=20)


class MarketAccessibility(ContractModel):
    level: QualitativeLevel | Literal["unknown"]
    channels: list[str] = Field(default_factory=list, max_length=20)
    barriers: list[str] = Field(default_factory=list, max_length=20)
    summary: str = Field(min_length=1, max_length=2_000)
    confidence: Confidence
    source_ids: list[str] = Field(min_length=1, max_length=20)


class MarketRisk(ContractModel):
    id: str = Field(min_length=1, max_length=120)
    category: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=200)
    probability: QualitativeLevel
    impact: QualitativeLevel
    summary: str = Field(min_length=1, max_length=2_000)
    source_ids: list[str] = Field(min_length=1, max_length=20)


class OpportunityGap(ContractModel):
    id: str = Field(min_length=1, max_length=120)
    segment: str = Field(min_length=1, max_length=200)
    unmet_need: str = Field(min_length=1, max_length=1_000)
    competitor_coverage: QualitativeLevel | Literal["unknown"]
    demand_strength: QualitativeLevel | Literal["unknown"]
    commercial_signal: QualitativeLevel | Literal["unknown"]
    confidence: Confidence
    source_ids: list[str] = Field(min_length=1, max_length=20)


class MarketOverview(ContractModel):
    verdict: MarketVerdict
    scorecard: MarketScorecard
    market_size: MarketSize
    momentum: MarketMomentum
    customer_segments: list[CustomerSegment] = Field(default_factory=list, max_length=20)
    commercial_dynamics: CommercialDynamics
    market_accessibility: MarketAccessibility
    risks: list[MarketRisk] = Field(default_factory=list, max_length=20)
    opportunity_gaps: list[OpportunityGap] = Field(default_factory=list, max_length=20)


class CompetitorSummary(ContractModel):
    competition_level: QualitativeLevel | Literal["unknown"]
    market_structure: Literal["concentrated", "fragmented", "mixed", "unknown"]
    tracked_products: int = Field(ge=0)
    top_10_revenue_concentration: float | None = Field(default=None, ge=0, le=100)
    feature_saturation: QualitativeLevel | Literal["unknown"]
    switching_cost: QualitativeLevel | Literal["unknown"]
    source_ids: list[str] = Field(default_factory=list, max_length=20)


class CompetitorPricing(ContractModel):
    model: str = Field(min_length=1, max_length=200)
    annual_price: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=10)


class Competitor(ContractModel):
    id: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=200)
    type: Literal["direct", "indirect", "substitute", "emerging"]
    positioning: str = Field(min_length=1, max_length=1_000)
    platforms: list[str] = Field(default_factory=list, max_length=10)
    pricing: CompetitorPricing
    strengths: list[str] = Field(default_factory=list, max_length=10)
    weaknesses: list[str] = Field(default_factory=list, max_length=10)
    confidence: Confidence
    source_ids: list[str] = Field(min_length=1, max_length=20)


class CompetitorAnalysis(ContractModel):
    summary: CompetitorSummary
    items: list[Competitor] = Field(default_factory=list, max_length=50)


class EvidenceSource(ContractModel):
    id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=500)
    publisher: str = Field(min_length=1, max_length=200)
    url: AnyHttpUrl
    published_at: str | None = None
    retrieved_at: str
    evidence_class: EvidenceClass


class MarketAnalysisResponse(ContractModel):
    schema_version: Literal["market-analysis.v1"] = "market-analysis.v1"
    market: MarketIdentity
    report: ReportMetadata
    overview: MarketOverview
    competitors: CompetitorAnalysis
    evidence: list[EvidenceSource] = Field(min_length=1, max_length=100)


class MarketResearchBudgets(ContractModel):
    max_search_queries: int = Field(default=14, ge=7, le=70)
    max_sources: int = Field(default=40, ge=7, le=100)
    max_gap_fill_rounds: int = Field(default=1, ge=0, le=2)


class AppMarketResearchInput(RequestMetadata):
    run_id: UUID
    conversation_id: UUID | None = None
    market_name: str = Field(min_length=1, max_length=200)
    market_definition: str = Field(min_length=1, max_length=2_000)
    scope: MarketScope
    data_period: str = Field(min_length=1, max_length=120)
    budgets: MarketResearchBudgets = Field(default_factory=MarketResearchBudgets)
    require_approval: bool = False
    publish: bool = True


class ResearchPublication(ContractModel):
    market_id: str
    report_id: str
    report_version: int = Field(gt=0)


class AppMarketResearchOutput(ResponseMetadata):
    run_id: UUID
    report: MarketAnalysisResponse | None = None
    publication: ResearchPublication | None = None


class EvidenceFact(ContractModel):
    source_id: str = Field(min_length=1, max_length=120)
    dimension: ResearchDimension
    claim_type: str = Field(min_length=1, max_length=120)
    claim: str = Field(min_length=1, max_length=2_000)
    evidence_class: EvidenceClass
    confidence: Confidence
    numeric_value: float | None = None
    unit: str | None = Field(default=None, max_length=40)
    period: str | None = Field(default=None, max_length=120)


class SourceSnapshot(ContractModel):
    public_id: str = Field(min_length=1, max_length=120)
    title: str = Field(min_length=1, max_length=500)
    publisher: str = Field(min_length=1, max_length=200)
    url: AnyHttpUrl
    published_at: str | None = None
    retrieved_at: str
    content_hash: str = Field(min_length=64, max_length=64)
    content_excerpt: str = Field(min_length=1, max_length=8_000)


class PublishMarketReportRequest(ContractModel):
    run_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=200)
    report: MarketAnalysisResponse
    sources: list[SourceSnapshot] = Field(min_length=1, max_length=100)
    facts: list[EvidenceFact] = Field(min_length=1, max_length=500)


class PublishMarketReportResponse(ContractModel):
    market_id: str
    report_id: str
    report_version: int = Field(gt=0)


ReportReviewAction = Literal[
    "ask_followup",
    "request_revision",
    "request_more_research",
    "approve_publish",
    "cancel",
]
MarketReportDraftStatus = Literal[
    "in_review",
    "approved",
    "published",
    "superseded",
    "cancelled",
]


class PersistMarketReportDraftRequest(ContractModel):
    run_id: UUID
    conversation_id: UUID
    idempotency_key: str = Field(min_length=1, max_length=200)
    report: MarketAnalysisResponse
    sources: list[SourceSnapshot] = Field(min_length=1, max_length=100)
    facts: list[EvidenceFact] = Field(min_length=1, max_length=500)
    based_on_draft_id: UUID | None = None


class MarketReportDraft(ContractModel):
    draft_id: UUID
    run_id: UUID
    conversation_id: UUID
    version: int = Field(gt=0)
    status: MarketReportDraftStatus
    report_hash: str = Field(min_length=64, max_length=64)
    report: MarketAnalysisResponse


class ReportReviewActionInput(ContractModel):
    action: ReportReviewAction
    draft_id: UUID
    expected_draft_hash: str = Field(min_length=64, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=200)
    message: str | None = Field(default=None, max_length=10_000)
    section_ids: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_action_payload(self) -> "ReportReviewActionInput":
        message_actions = {"ask_followup", "request_revision", "request_more_research"}
        if self.action in message_actions and not (self.message and self.message.strip()):
            raise ValueError(f"{self.action} requires a non-empty message")
        return self


class ReportReviewDecision(ReportReviewActionInput):
    actor_id: str = Field(min_length=1, max_length=200)
    action_deadline_at: datetime | None = None


class ReportReviewEvent(ContractModel):
    event_id: UUID
    conversation_id: UUID
    draft_id: UUID
    review_generation: int = Field(ge=1)
    action: ReportReviewAction
    status: MarketReportDraftStatus


class ConversationMessage(ContractModel):
    message_id: UUID
    conversation_id: UUID
    sequence: int = Field(ge=1)
    role: Literal["user", "assistant", "system"]
    kind: Literal[
        "user_question",
        "assistant_answer",
        "revision_request",
        "revision_summary",
        "approval",
        "system_event",
    ]
    content: str = Field(min_length=1, max_length=20_000)


class AppendConversationMessageRequest(ContractModel):
    conversation_id: UUID
    role: Literal["user", "assistant", "system"]
    kind: Literal[
        "user_question",
        "assistant_answer",
        "revision_request",
        "revision_summary",
        "approval",
        "system_event",
    ]
    content: str = Field(min_length=1, max_length=20_000)
    idempotency_key: str = Field(min_length=1, max_length=200)


class ConversationReviewContext(ContractModel):
    conversation_id: UUID
    summary: dict[str, object]
    recent_messages: list[ConversationMessage]


class PublishApprovedMarketReportRequest(ContractModel):
    draft_id: UUID
    expected_draft_hash: str = Field(min_length=64, max_length=64)
    idempotency_key: str = Field(min_length=1, max_length=200)
