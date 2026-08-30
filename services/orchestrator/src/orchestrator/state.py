from typing import Any, TypedDict

from distributed_agent_contracts import ContractError, ContractStatus
from pydantic import BaseModel, ConfigDict, Field, model_validator


class AgentBranch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ContractStatus
    attempts: int = Field(ge=1)
    data: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    error: ContractError | None = None

    @model_validator(mode="after")
    def validate_result(self) -> "AgentBranch":
        if self.status is ContractStatus.FAILED and self.error is None:
            raise ValueError("failed branches require an error")
        if self.status is not ContractStatus.FAILED and self.data is None:
            raise ValueError("usable branches require data")
        return self

    @property
    def usable(self) -> bool:
        return self.status is not ContractStatus.FAILED and self.data is not None


class WorkflowState(TypedDict, total=False):
    contract_version: str
    request_id: str
    trace_id: str
    attempt: int
    deadline_at: str | None
    query: str
    research_branch: dict[str, Any]
    market_branch: dict[str, Any]
    analysis_branch: dict[str, Any]
    writer_branch: dict[str, Any]
    workflow_status: str
    warnings: list[str]
    error: dict[str, Any] | None
    final_brief: dict[str, Any] | None
