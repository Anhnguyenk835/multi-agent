from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

Confidence = Annotated[int, Field(ge=0, le=100)]
QualitativeLevel = Literal["low", "moderate", "high"]
EvidenceClass = Literal["reported", "estimated", "derived", "proxy", "inferred"]


class ApiModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MarketScope(ApiModel):
    geography: list[str]
    platforms: list[str]
    customer_type: Literal["B2C", "B2B", "prosumer", "mixed"]
    included: list[str]
    excluded: list[str]


class MarketIdentity(ApiModel):
    id: str
    name: str
    definition: str
    scope: MarketScope


class ReportMetadata(ApiModel):
    id: str
    version: int = Field(gt=0)
    status: Literal["partial", "completed"]
    generated_at: str
    data_period: str
    overall_confidence: Confidence
    freshness: Literal["current", "aging", "stale"]
    warnings: list[str]


class MetricRange(ApiModel):
    min: float
    max: float


class MetricChange(ApiModel):
    value: float
    unit: Literal["percent", "percentage_points", "absolute"]
    period: Literal["MoM", "YoY", "CAGR"]


class MarketMetric(ApiModel):
    id: str
    label: str
    value: float | None = None
    range: MetricRange | None = None
    unit: Literal["USD", "percent", "users", "downloads", "products", "index"]
    period: str
    change: MetricChange | None = None
    evidence_class: EvidenceClass
    confidence: Confidence
    source_ids: list[str]
    methodology: str | None = None


class RevenueTrendPoint(ApiModel):
    period: str
    value: float
    unit: Literal["USD"]
    evidence_class: EvidenceClass
    confidence: Confidence
    source_ids: list[str]


class TrendSignal(ApiModel):
    label: str
    change: float
    unit: Literal["percent", "percentage_points", "absolute"]
    period: Literal["MoM", "YoY", "CAGR"]
    source_ids: list[str]


class MarketVerdict(ApiModel):
    status: Literal[
        "attractive",
        "selectively_attractive",
        "mature",
        "unattractive",
        "insufficient_evidence",
    ]
    summary: str
    strengths: list[str]
    constraints: list[str]


class MarketScorecard(ApiModel):
    demand: Confidence
    market_size: Confidence
    momentum: Confidence
    commercial_quality: Confidence
    accessibility: Confidence
    competitive_headroom: Confidence


class MarketSize(ApiModel):
    metrics: list[MarketMetric]
    revenue_history: list[RevenueTrendPoint]


class MarketMomentum(ApiModel):
    direction: Literal["growing", "stable", "declining", "uncertain"]
    strength: QualitativeLevel
    summary: str
    signals: list[TrendSignal]


class CustomerSegment(ApiModel):
    id: str
    name: str
    jobs: list[str]
    pain_points: list[str]
    willingness_to_pay: QualitativeLevel | Literal["unknown"]
    confidence: Confidence
    source_ids: list[str]


class PriceRange(ApiModel):
    min: float
    max: float
    unit: Literal["USD"]


class CommercialDynamics(ApiModel):
    dominant_model: str
    typical_annual_price: PriceRange | None = None
    willingness_to_pay: QualitativeLevel | Literal["unknown"]
    retention_pressure: QualitativeLevel | Literal["unknown"]
    summary: str
    source_ids: list[str]


class MarketAccessibility(ApiModel):
    level: QualitativeLevel | Literal["unknown"]
    channels: list[str]
    barriers: list[str]
    summary: str
    confidence: Confidence
    source_ids: list[str]


class MarketRisk(ApiModel):
    id: str
    category: str
    title: str
    probability: QualitativeLevel
    impact: QualitativeLevel
    summary: str
    source_ids: list[str]


class OpportunityGap(ApiModel):
    id: str
    segment: str
    unmet_need: str
    competitor_coverage: QualitativeLevel | Literal["unknown"]
    demand_strength: QualitativeLevel | Literal["unknown"]
    commercial_signal: QualitativeLevel | Literal["unknown"]
    confidence: Confidence
    source_ids: list[str]


class MarketOverview(ApiModel):
    verdict: MarketVerdict
    scorecard: MarketScorecard
    market_size: MarketSize
    momentum: MarketMomentum
    customer_segments: list[CustomerSegment]
    commercial_dynamics: CommercialDynamics
    market_accessibility: MarketAccessibility
    risks: list[MarketRisk]
    opportunity_gaps: list[OpportunityGap]


class CompetitorSummary(ApiModel):
    competition_level: QualitativeLevel | Literal["unknown"]
    market_structure: Literal["concentrated", "fragmented", "mixed", "unknown"]
    tracked_products: int = Field(ge=0)
    top_10_revenue_concentration: float | None = None
    feature_saturation: QualitativeLevel | Literal["unknown"]
    switching_cost: QualitativeLevel | Literal["unknown"]
    source_ids: list[str]


class CompetitorPricing(ApiModel):
    model: str
    annual_price: float | None = None
    currency: str | None = None


class Competitor(ApiModel):
    id: str
    name: str
    type: Literal["direct", "indirect", "substitute", "emerging"]
    positioning: str
    platforms: list[str]
    pricing: CompetitorPricing
    strengths: list[str]
    weaknesses: list[str]
    confidence: Confidence
    source_ids: list[str]


class CompetitorAnalysis(ApiModel):
    summary: CompetitorSummary
    items: list[Competitor]


class EvidenceSource(ApiModel):
    id: str
    title: str
    publisher: str
    url: HttpUrl
    published_at: str | None = None
    retrieved_at: str
    evidence_class: EvidenceClass


class MarketAnalysisResponse(ApiModel):
    schema_version: Literal["market-analysis.v1"]
    market: MarketIdentity
    report: ReportMetadata
    overview: MarketOverview
    competitors: CompetitorAnalysis
    evidence: list[EvidenceSource]


class MarketSummary(ApiModel):
    id: str
    name: str
    definition: str
    momentum_score: Confidence
