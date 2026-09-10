from typing import Protocol

from distributed_agent_contracts import (
    AnalysisRequest,
    AnalysisResponse,
    MarketAnalystInput,
    MarketAnalystOutput,
    WriterRequest,
    WriterResponse,
)

from orchestrator.clients.competitor_analyst import (
    CompetitorAnalystOutput,
    CompetitorAnalystRequest,
)


class MarketAnalystClientProtocol(Protocol):
    async def analyze(self, request: MarketAnalystInput) -> MarketAnalystOutput: ...


class CompetitorAnalystClientProtocol(Protocol):
    async def analyze(self, request: CompetitorAnalystRequest) -> CompetitorAnalystOutput: ...


class AnalystClientProtocol(Protocol):
    async def analyze(self, request: AnalysisRequest) -> AnalysisResponse: ...


class WriterClientProtocol(Protocol):
    async def write(self, request: WriterRequest) -> WriterResponse: ...
