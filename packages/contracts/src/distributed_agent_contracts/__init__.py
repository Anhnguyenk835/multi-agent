"""Versioned contracts shared across independently deployable services."""

from distributed_agent_contracts.analyst import AnalysisRequest, AnalysisResponse
from distributed_agent_contracts.common import (
    Citation,
    ContractError,
    ContractStatus,
    ErrorCode,
    Finding,
    MarketSignal,
    RequestMetadata,
    Source,
    copy_request_metadata,
    render_citation_links,
)
from distributed_agent_contracts.orchestrator import WorkflowRequest, WorkflowResponse
from distributed_agent_contracts.researcher import (
    ResearcherInput,
    ResearcherOutput,
    ResearcherRemoteState,
)
from distributed_agent_contracts.writer import ExecutiveBrief, WriterRequest, WriterResponse

__all__ = [
    "AnalysisRequest",
    "AnalysisResponse",
    "Citation",
    "ContractError",
    "ContractStatus",
    "ErrorCode",
    "ExecutiveBrief",
    "Finding",
    "MarketSignal",
    "RequestMetadata",
    "ResearcherInput",
    "ResearcherOutput",
    "ResearcherRemoteState",
    "Source",
    "WorkflowRequest",
    "WorkflowResponse",
    "WriterRequest",
    "WriterResponse",
    "copy_request_metadata",
    "render_citation_links",
]
