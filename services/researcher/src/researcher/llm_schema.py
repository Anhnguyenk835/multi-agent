from pydantic import BaseModel, ConfigDict, Field


class LLMFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=200)
    claim: str = Field(min_length=1, max_length=1000)
    source_tag: str = Field(min_length=1, max_length=64)


class LLMFindingsResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    findings: list[LLMFinding] = Field(min_length=1, max_length=6)
