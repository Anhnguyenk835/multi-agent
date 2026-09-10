from typing import TypedDict

from pydantic import Field

from distributed_agent_contracts.common import Finding, RequestMetadata, ResponseMetadata


class MarketAnalystInput(RequestMetadata):
    """JSON-serializable input accepted by the Market Analyst RemoteGraph."""

    query: str = Field(min_length=1, max_length=2_000)


class MarketAnalystOutput(ResponseMetadata):
    """JSON-serializable output returned by the Market Analyst RemoteGraph."""

    findings: list[Finding] = Field(default_factory=list, max_length=20)


class MarketAnalystRemoteState(TypedDict, total=False):
    """State fields transferred across the RemoteGraph service boundary."""

    contract_version: str
    request_id: str
    trace_id: str
    attempt: int
    deadline_at: str | None
    query: str
    status: str
    findings: list[dict[str, object]]
    warnings: list[str]
    error: dict[str, object] | None
