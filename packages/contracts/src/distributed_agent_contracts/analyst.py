from pydantic import Field, model_validator

from distributed_agent_contracts.common import (
    Citation,
    CompetitiveSignal,
    ContractStatus,
    Finding,
    LongText,
    RequestMetadata,
    ResponseMetadata,
)


class AnalysisRequest(RequestMetadata):
    query: str = Field(min_length=1, max_length=2_000)
    research_findings: list[Finding] = Field(default_factory=list, max_length=20)
    competitive_signals: list[CompetitiveSignal] = Field(default_factory=list, max_length=20)
    competitors: list[str] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def validate_available_research(self) -> "AnalysisRequest":
        if not self.research_findings and not self.competitive_signals:
            raise ValueError("analysis requires research findings or market signals")
        return self


class AnalysisResponse(ResponseMetadata):
    content: LongText | None = None
    citations: list[Citation] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_success_content(self) -> "AnalysisResponse":
        if self.status is ContractStatus.SUCCESS and self.content is None:
            raise ValueError("successful analyses require content")
        return self
