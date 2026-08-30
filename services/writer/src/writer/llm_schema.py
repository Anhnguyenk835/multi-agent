from pydantic import BaseModel, ConfigDict, Field


class LLMBrief(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # Cites with bare [N] markers — no URL field, so nothing to invent.
    content: str = Field(min_length=1)
