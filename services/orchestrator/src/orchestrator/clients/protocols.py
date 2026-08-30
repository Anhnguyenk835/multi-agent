from typing import Protocol

from distributed_agent_contracts import (
    AnalysisRequest,
    AnalysisResponse,
    ResearcherInput,
    ResearcherOutput,
    WriterRequest,
    WriterResponse,
)

from orchestrator.clients.market import MarketAgentOutput, MarketAgentRequest


class ResearcherClientProtocol(Protocol):
    async def analyze(self, request: ResearcherInput) -> ResearcherOutput: ...


class MarketClientProtocol(Protocol):
    async def analyze(self, request: MarketAgentRequest) -> MarketAgentOutput: ...


class AnalystClientProtocol(Protocol):
    async def analyze(self, request: AnalysisRequest) -> AnalysisResponse: ...


class WriterClientProtocol(Protocol):
    async def write(self, request: WriterRequest) -> WriterResponse: ...
