from typing import Literal

from distributed_agent_contracts import EvidenceFact, SourceSnapshot
from distributed_agent_contracts.market_analysis import (
    CompetitorAnalysis,
    MarketOverview,
    ResearchDimension,
)
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ResearchTask(StrictModel):
    id: str
    dimension: ResearchDimension
    question: str
    queries: list[str] = Field(min_length=1, max_length=4)
    source_limit: int = Field(ge=1, le=30)


class ExtractedFact(StrictModel):
    source_id: str = Field(min_length=1, max_length=4096)
    claim_type: str = Field(min_length=1, max_length=120)
    claim: str = Field(min_length=1, max_length=2_000)
    evidence_class: Literal["reported", "estimated", "proxy", "inferred"]
    confidence: int = Field(ge=0, le=100)
    numeric_value: float | None = None
    unit: str | None = Field(default=None, max_length=40)
    period: str | None = Field(default=None, max_length=120)


class TaskExtraction(StrictModel):
    facts: list[ExtractedFact] = Field(default_factory=list, max_length=40)
    warnings: list[str] = Field(default_factory=list, max_length=10)


class ResearchTaskResult(StrictModel):
    task_id: str
    dimension: ResearchDimension
    status: Literal["completed", "partial", "failed"]
    query_count: int = Field(ge=0)
    sources: list[SourceSnapshot] = Field(default_factory=list, max_length=30)
    facts: list[EvidenceFact] = Field(default_factory=list, max_length=100)
    warnings: list[str] = Field(default_factory=list, max_length=20)


class MarketSynthesis(StrictModel):
    overview: MarketOverview
    competitors: CompetitorAnalysis


class ReviewAnswer(StrictModel):
    answer: str = Field(min_length=1, max_length=10_000)
    source_ids: list[str] = Field(default_factory=list, max_length=20)
