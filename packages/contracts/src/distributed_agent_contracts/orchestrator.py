from pydantic import Field, model_validator

from distributed_agent_contracts.common import ContractStatus, RequestMetadata, ResponseMetadata
from distributed_agent_contracts.writer import ExecutiveBrief


class WorkflowRequest(RequestMetadata):
    query: str = Field(min_length=1, max_length=2_000)


class WorkflowResponse(ResponseMetadata):
    final_brief: ExecutiveBrief | None = None

    @model_validator(mode="after")
    def validate_final_brief(self) -> "WorkflowResponse":
        if self.status in {ContractStatus.SUCCESS, ContractStatus.DEGRADED}:
            if self.final_brief is None:
                raise ValueError("successful and degraded workflows require a final brief")
        elif self.final_brief is not None:
            raise ValueError("failed workflows cannot include a final brief")
        return self
