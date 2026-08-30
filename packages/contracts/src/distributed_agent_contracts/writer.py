from pydantic import Field, model_validator

from distributed_agent_contracts.common import (
    Citation,
    ContractStatus,
    LongText,
    RequestMetadata,
    ResponseMetadata,
)


class WriterRequest(RequestMetadata):
    query: str = Field(min_length=1, max_length=2_000)
    # Analyst's write-up, not raw research — Writer never sees page content.
    analysis: LongText
    citations: list[Citation] = Field(default_factory=list, max_length=30)
    warnings: list[str] = Field(default_factory=list, max_length=20)


class ExecutiveBrief(ResponseMetadata):
    content: LongText | None = None
    citations: list[Citation] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_success_content(self) -> "ExecutiveBrief":
        if self.status is ContractStatus.SUCCESS and self.content is None:
            raise ValueError("successful briefs require content")
        return self


WriterResponse = ExecutiveBrief
