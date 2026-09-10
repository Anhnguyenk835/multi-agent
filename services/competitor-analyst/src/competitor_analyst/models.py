from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CompetitorType = Literal["direct", "indirect", "substitute", "emerging"]
QualitativeLevel = Literal["low", "moderate", "high", "unknown"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceClaimInput(StrictModel):
    text: str = Field(min_length=1, max_length=1_000)
    source_tags: list[str] = Field(min_length=1, max_length=5)


class DiscoveryCandidateInput(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    type: CompetitorType
    rationale: str = Field(min_length=1, max_length=500)
    source_tag: str = Field(min_length=1, max_length=4_096)


class CompetitorDiscoveryInput(StrictModel):
    candidates: list[DiscoveryCandidateInput] = Field(min_length=1, max_length=20)


class CompetitorPricingInput(StrictModel):
    model: str = Field(min_length=1, max_length=200)
    annual_price: float | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=10)
    source_tags: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def validate_evidence(self) -> "CompetitorPricingInput":
        if (
            self.model.casefold() != "unknown" or self.annual_price is not None
        ) and not self.source_tags:
            raise ValueError("known pricing requires at least one source tag")
        return self


class CompetitorProfileInput(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    type: CompetitorType
    positioning: EvidenceClaimInput
    target_segments: list[EvidenceClaimInput] = Field(default_factory=list, max_length=8)
    jobs_to_be_done: list[EvidenceClaimInput] = Field(default_factory=list, max_length=8)
    platforms: list[EvidenceClaimInput] = Field(default_factory=list, max_length=10)
    pricing: CompetitorPricingInput
    features: list[EvidenceClaimInput] = Field(default_factory=list, max_length=15)
    traction_signals: list[EvidenceClaimInput] = Field(default_factory=list, max_length=10)
    review_themes: list[EvidenceClaimInput] = Field(default_factory=list, max_length=10)
    distribution_channels: list[EvidenceClaimInput] = Field(default_factory=list, max_length=10)
    retention_mechanics: list[EvidenceClaimInput] = Field(default_factory=list, max_length=10)
    strengths: list[EvidenceClaimInput] = Field(default_factory=list, max_length=10)
    weaknesses: list[EvidenceClaimInput] = Field(default_factory=list, max_length=10)


class CompetitiveGapInput(StrictModel):
    segment: str = Field(min_length=1, max_length=200)
    unmet_need: str = Field(min_length=1, max_length=1_000)
    competitor_coverage: QualitativeLevel
    demand_strength: QualitativeLevel
    commercial_signal: QualitativeLevel
    source_ids: list[str] = Field(min_length=1, max_length=20)


class CompetitorSynthesisInput(StrictModel):
    competition_level: QualitativeLevel
    market_structure: Literal["concentrated", "fragmented", "mixed", "unknown"]
    feature_saturation: QualitativeLevel
    switching_cost: QualitativeLevel
    gaps: list[CompetitiveGapInput] = Field(default_factory=list, max_length=15)


class EvidenceClaim(StrictModel):
    text: str
    source_ids: list[str]


class CompetitorPricing(StrictModel):
    model: str
    annual_price: float | None = None
    currency: str | None = None
    source_ids: list[str] = Field(default_factory=list)


class CompetitorProfile(StrictModel):
    id: str
    name: str
    type: CompetitorType
    positioning: EvidenceClaim
    target_segments: list[EvidenceClaim]
    jobs_to_be_done: list[EvidenceClaim]
    platforms: list[EvidenceClaim]
    pricing: CompetitorPricing
    features: list[EvidenceClaim]
    traction_signals: list[EvidenceClaim]
    review_themes: list[EvidenceClaim]
    distribution_channels: list[EvidenceClaim]
    retention_mechanics: list[EvidenceClaim]
    strengths: list[EvidenceClaim]
    weaknesses: list[EvidenceClaim]
    confidence: int = Field(ge=0, le=100)
    source_ids: list[str]


class CompetitiveGap(StrictModel):
    id: str
    segment: str
    unmet_need: str
    competitor_coverage: QualitativeLevel
    demand_strength: QualitativeLevel
    commercial_signal: QualitativeLevel
    confidence: int = Field(ge=0, le=100)
    source_ids: list[str]


class EvidenceSource(StrictModel):
    id: str
    title: str
    url: str
    publisher: str
    published_at: datetime | None
    retrieved_at: datetime
    content: str


class CompetitorAnalysis(StrictModel):
    competition_level: QualitativeLevel
    market_structure: Literal["concentrated", "fragmented", "mixed", "unknown"]
    tracked_products: int = Field(ge=0)
    feature_saturation: QualitativeLevel
    switching_cost: QualitativeLevel
    competitors: list[CompetitorProfile]
    gaps: list[CompetitiveGap]
    coverage: int = Field(ge=0, le=100)
    source_ids: list[str]

    @model_validator(mode="after")
    def validate_tracked_products(self) -> "CompetitorAnalysis":
        if self.tracked_products != len(self.competitors):
            raise ValueError("tracked_products must match the number of competitor profiles")
        return self
