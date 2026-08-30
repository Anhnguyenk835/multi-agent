from pydantic import BaseModel, ConfigDict, Field


class LLMSignal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    topic: str = Field(min_length=1, max_length=200)
    observation: str = Field(min_length=1, max_length=1000)
    source_tag: str = Field(min_length=1, max_length=64)


class LLMMarketResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    signals: list[LLMSignal] = Field(min_length=1, max_length=6)
    competitors: list[str] = Field(min_length=1, max_length=10)
